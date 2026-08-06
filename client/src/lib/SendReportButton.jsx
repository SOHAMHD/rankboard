import { useState } from "react";
import { Send, LoaderCircle, X, Plus, Mail, Users } from "lucide-react";
import { api } from "../api";
import { BTN_PRIMARY, BTN_GHOST, INPUT_CLS } from "../ui";
import { useToast } from "../toast.jsx";

function isEmail(s) {
  const v = (s || "").trim();
  if (!v || (v.match(/@/g) || []).length !== 1) return false;
  const [local, domain] = v.split("@");
  return !!local && domain.includes(".") && !domain.startsWith(".") && !domain.endsWith(".");
}

/**
 * The address chip input, shared by Recipients and Cc.
 *
 * Extracted rather than copied: the paste-splitting, backspace-to-remove and
 * commit-on-blur behaviour is fiddly enough that two copies would drift.
 * `taken` holds the addresses already used by the other field, so the same
 * person can't be put on both lines — the server drops that duplicate anyway,
 * and it's clearer to say so here.
 */
function AddressInput({ id, values, onChange, draft, onDraftChange, taken = [], placeholder, onError }) {
  const commitDraft = (text = draft) => {
    const parts = text.split(/[\s,;]+/).map((s) => s.trim()).filter(Boolean);
    if (parts.length === 0) return;
    const bad = [];
    const dupes = [];
    const next = [...values];
    const seen = new Set([...values, ...taken].map((e) => e.toLowerCase()));
    for (const p of parts) {
      const key = p.toLowerCase();
      if (seen.has(key)) {
        if (taken.some((t) => t.toLowerCase() === key)) dupes.push(p);
        continue;
      }
      if (!isEmail(p)) { bad.push(p); continue; }
      seen.add(key);
      next.push(p);
    }
    onChange(next);
    onDraftChange("");
    if (bad.length) onError(`Not a valid email: ${bad.join(", ")}`);
    else if (dupes.length) onError(`${dupes.join(", ")} is already on the other line.`);
    else onError(null);
  };

  const remove = (target) => onChange(values.filter((e) => e !== target));

  const onKeyDown = (e) => {
    if (["Enter", ",", " ", "Tab"].includes(e.key)) {
      if (draft.trim()) {
        e.preventDefault();
        commitDraft();
      }
    } else if (e.key === "Backspace" && !draft && values.length) {
      remove(values[values.length - 1]);
    }
  };

  return (
    <div className="flex flex-wrap gap-1.5 rounded-lg border border-stone-300 bg-white px-2 py-2 focus-within:border-orange-400">
      {values.map((e) => (
        <span key={e} className="inline-flex items-center gap-1 rounded-md bg-stone-100 text-stone-700 text-xs px-2 py-1">
          {e}
          <button
            onClick={() => remove(e)}
            className="text-stone-400 hover:text-red-600"
            aria-label={`Remove ${e}`}
          >
            <X size={12} />
          </button>
        </span>
      ))}
      <input
        id={id}
        type="email"
        value={draft}
        onChange={(ev) => onDraftChange(ev.target.value)}
        onKeyDown={onKeyDown}
        onBlur={() => draft.trim() && commitDraft()}
        onPaste={(ev) => {
          const text = ev.clipboardData.getData("text");
          if (/[\s,;]/.test(text)) { ev.preventDefault(); commitDraft(text); }
        }}
        placeholder={values.length ? "Add another…" : placeholder}
        className="flex-1 min-w-[10rem] outline-none text-sm py-0.5"
      />
    </div>
  );
}

export default function SendReportButton({
  versionId,
  periodKey,
  label = false,
  className = "",
  beforeSend,
  onSent,
}) {
  const [open, setOpen] = useState(false);
  const [emails, setEmails] = useState([]);
  const [draft, setDraft] = useState("");
  const [cc, setCc] = useState([]);
  const [ccDraft, setCcDraft] = useState("");
  const [showCc, setShowCc] = useState(false);
  const [subject, setSubject] = useState("");
  const [message, setMessage] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState(null);
  const toast = useToast();

  const reset = () => {
    setEmails([]);
    setDraft("");
    setCc([]);
    setCcDraft("");
    setShowCc(false);
    setSubject("");
    setMessage("");
    setError(null);
  };

  const close = () => {
    if (sending) return;
    setOpen(false);
    reset();
  };

  // A typed-but-not-yet-committed address should still send, so fold the draft in
  // before validating. Same treatment for both lines.
  const foldDraft = (values, pending, other) => {
    const clean = (pending || "").trim();
    if (!clean) return { values, error: null };
    if (!isEmail(clean)) return { values, error: `Not a valid email: ${clean}` };
    const seen = new Set([...values, ...other].map((e) => e.toLowerCase()));
    if (seen.has(clean.toLowerCase())) return { values, error: null };
    return { values: [...values, clean], error: null };
  };

  const send = async () => {
    const to = foldDraft(emails, draft, cc);
    if (to.error) { setError(to.error); return; }
    const copies = foldDraft(cc, ccDraft, to.values);
    if (copies.error) { setError(copies.error); return; }

    setEmails(to.values);
    setDraft("");
    setCc(copies.values);
    setCcDraft("");

    if (to.values.length === 0) { setError("Add at least one email address."); return; }

    setSending(true);
    setError(null);
    try {
      if (beforeSend) await beforeSend();
      const res = await api(`/reports/${versionId}/send`, {
        method: "POST",
        body: {
          recipients: to.values,
          cc: copies.values.length ? copies.values : undefined,
          subject: subject.trim() || undefined,
          message: message.trim() || undefined,
        },
      });
      const failed = res.failed || 0;
      const ok = res.sent || 0;
      const ccCount = (res.cc || []).length;
      if (failed > 0) {
        toast.error(`Sent to ${ok}, failed for ${failed}.`, { title: "Partly sent" });
      } else {
        toast.success(
          `Report sent to ${ok - ccCount} recipient${ok - ccCount === 1 ? "" : "s"}` +
            (ccCount ? `, copied to ${ccCount}.` : "."),
          { title: "Report sent" }
        );
      }
      onSent?.(res);
      setOpen(false);
      reset();
    } catch (e) {
      const msg = e.message || "Couldn't send the report — try again.";
      setError(msg);
      toast.error(msg, { title: "Send failed" });
    } finally {
      setSending(false);
    }
  };

  const totalAddresses = emails.length + cc.length;

  const trigger = label ? (
    <button onClick={() => setOpen(true)} className={`${BTN_GHOST} px-3 py-1.5 ${className}`}>
      <Send size={14} /> Send report
    </button>
  ) : (
    <button
      onClick={() => setOpen(true)}
      aria-label={`Email ${periodKey || `report ${versionId}`}`}
      title="Send report by email"
      className={`inline-flex items-center justify-center rounded-lg p-1.5 text-stone-400 hover:text-orange-600 hover:bg-orange-50 transition-colors ${className}`}
    >
      <Send size={15} />
    </button>
  );

  return (
    <>
      {trigger}

      {open && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
          role="dialog"
          aria-modal="true"
        >
          <div className="bg-white rounded-xl shadow-xl w-full max-w-md p-5 max-h-[90vh] overflow-y-auto">
            <div className="flex items-start gap-3">
              <span className="shrink-0 rounded-full bg-orange-100 text-orange-600 p-2">
                <Mail size={18} />
              </span>
              <div className="min-w-0 flex-1">
                <h3 className="text-base font-bold text-stone-900 font-display">
                  Send report by email
                </h3>
                <p className="text-sm text-stone-500 mt-0.5">
                  {periodKey ? `${periodKey} report` : "This report"} will be attached as a PDF.
                </p>
              </div>
              <button onClick={close} disabled={sending} className="text-stone-400 hover:text-stone-700 disabled:opacity-40">
                <X size={18} />
              </button>
            </div>

            <div className="flex items-baseline justify-between mt-4 mb-1">
              <label htmlFor="send-report-to" className="block text-xs font-medium text-stone-600">
                Recipients
              </label>
              {!showCc && (
                <button
                  onClick={() => setShowCc(true)}
                  className="text-xs font-medium text-orange-600 hover:underline inline-flex items-center gap-1"
                >
                  <Plus size={12} /> Add Cc
                </button>
              )}
            </div>
            <AddressInput
              id="send-report-to"
              values={emails}
              onChange={setEmails}
              draft={draft}
              onDraftChange={setDraft}
              taken={cc}
              placeholder="name@example.com"
              onError={setError}
            />
            <p className="text-[11px] text-stone-400 mt-1">
              Press Enter, comma, or space to add each address. Add as many as you like.
            </p>

            {showCc && (
              <>
                <div className="flex items-baseline justify-between mt-3 mb-1">
                  <label htmlFor="send-report-cc" className="block text-xs font-medium text-stone-600">
                    Cc
                  </label>
                  <button
                    onClick={() => { setShowCc(false); setCc([]); setCcDraft(""); }}
                    className="text-xs text-stone-400 hover:text-stone-600"
                  >
                    Remove Cc
                  </button>
                </div>
                <AddressInput
                  id="send-report-cc"
                  values={cc}
                  onChange={setCc}
                  draft={ccDraft}
                  onDraftChange={setCcDraft}
                  taken={emails}
                  placeholder="colleague@example.com"
                  onError={setError}
                />
              </>
            )}

            {totalAddresses > 1 && (
              // Worth stating plainly: the report goes out as one message, so
              // everybody named on it can see everybody else. Easy to forget when
              // several clients are in the list.
              <p className="text-[11px] text-stone-500 bg-stone-50 border border-stone-200 rounded-lg px-2.5 py-2 mt-2 flex gap-1.5">
                <Users size={13} className="shrink-0 mt-0.5 text-stone-400" />
                <span>
                  This goes out as one email, so all {totalAddresses} addresses are visible to
                  each other. Send separately if a client shouldn&apos;t see the others.
                </span>
              </p>
            )}

            <label htmlFor="send-report-subject" className="block text-xs font-medium text-stone-600 mt-3 mb-1">
              Subject <span className="text-stone-400 font-normal">(optional)</span>
            </label>
            <input
              id="send-report-subject"
              type="text"
              value={subject}
              onChange={(e) => setSubject(e.target.value)}
              placeholder="A default subject is used if left blank"
              className={INPUT_CLS}
            />

            <label htmlFor="send-report-message" className="block text-xs font-medium text-stone-600 mt-3 mb-1">
              Message <span className="text-stone-400 font-normal">(optional)</span>
            </label>
            <textarea
              id="send-report-message"
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              rows={3}
              placeholder="Add a short note to include in the email body…"
              className={`${INPUT_CLS} resize-none`}
            />

            {error && (
              <p className="text-sm text-red-600 bg-red-50 border border-red-100 rounded-lg px-3 py-2 mt-3">
                {error}
              </p>
            )}

            <div className="flex justify-end gap-2 mt-5">
              <button onClick={close} disabled={sending} className={`${BTN_GHOST} px-3 py-1.5`}>
                Cancel
              </button>
              <button
                onClick={send}
                disabled={sending || (emails.length === 0 && !draft.trim())}
                className={`${BTN_PRIMARY} px-4 py-1.5`}
              >
                {sending ? (
                  <>
                    <LoaderCircle size={14} className="animate-spin" /> Sending…
                  </>
                ) : (
                  <>
                    <Send size={14} /> Send
                    {emails.length > 0 ? ` to ${emails.length}` : ""}
                    {cc.length > 0 ? ` +${cc.length} cc` : ""}
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
