/* Reusable "Send report" control for a report version.

   Opens a modal where the author adds N recipient email addresses (as chips),
   an optional subject + message, then sends. The backend
   (POST /api/reports/{id}/send) renders the PDF once and emails it to every
   recipient, returning a per-recipient delivery result so we can report partial
   success. Like DownloadPdfButton, an optional `beforeSend` hook runs first so
   unsaved editor edits are persisted before the PDF is rendered server-side. */
import { useState } from "react";
import { Send, LoaderCircle, X, Plus, Mail } from "lucide-react";
import { api } from "../api";
import { BTN_PRIMARY, BTN_GHOST, INPUT_CLS } from "../ui";
import { useToast } from "../toast.jsx";

// Same loose check the backend uses — catch obvious typos before sending.
function isEmail(s) {
  const v = (s || "").trim();
  if (!v || (v.match(/@/g) || []).length !== 1) return false;
  const [local, domain] = v.split("@");
  return !!local && domain.includes(".") && !domain.startsWith(".") && !domain.endsWith(".");
}

export default function SendReportButton({
  versionId,
  periodKey,
  label = false, // true → text button (editor headers); false → icon-only (list rows)
  className = "",
  beforeSend, // optional async hook (e.g. save the draft) run before the send
  onSent, // optional callback(result) after a successful send
}) {
  const [open, setOpen] = useState(false);
  const [emails, setEmails] = useState([]); // confirmed recipient chips
  const [draft, setDraft] = useState(""); // the text currently being typed
  const [subject, setSubject] = useState("");
  const [message, setMessage] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState(null);
  const toast = useToast();

  const reset = () => {
    setEmails([]);
    setDraft("");
    setSubject("");
    setMessage("");
    setError(null);
  };

  const close = () => {
    if (sending) return;
    setOpen(false);
    reset();
  };

  // Commit the typed text (or a pasted, comma/space/newline-separated list) into
  // chips. Silently drops blanks and exact duplicates; flags malformed ones.
  const commitDraft = (text = draft) => {
    const parts = text.split(/[\s,;]+/).map((s) => s.trim()).filter(Boolean);
    if (parts.length === 0) return;
    const bad = [];
    setEmails((prev) => {
      const next = [...prev];
      const seen = new Set(prev.map((e) => e.toLowerCase()));
      for (const p of parts) {
        const key = p.toLowerCase();
        if (seen.has(key)) continue;
        if (!isEmail(p)) { bad.push(p); continue; }
        seen.add(key);
        next.push(p);
      }
      return next;
    });
    setDraft("");
    setError(bad.length ? `Not a valid email: ${bad.join(", ")}` : null);
  };

  const removeEmail = (target) =>
    setEmails((prev) => prev.filter((e) => e !== target));

  const onKeyDown = (e) => {
    if (["Enter", ",", " ", "Tab"].includes(e.key)) {
      if (draft.trim()) {
        e.preventDefault();
        commitDraft();
      }
    } else if (e.key === "Backspace" && !draft && emails.length) {
      removeEmail(emails[emails.length - 1]);
    }
  };

  const send = async () => {
    // Fold any half-typed address in the box into the list before sending.
    const pending = draft.trim();
    let recipients = emails;
    if (pending) {
      if (!isEmail(pending)) { setError(`Not a valid email: ${pending}`); return; }
      recipients = emails.includes(pending) ? emails : [...emails, pending];
      setEmails(recipients);
      setDraft("");
    }
    if (recipients.length === 0) { setError("Add at least one email address."); return; }

    setSending(true);
    setError(null);
    try {
      if (beforeSend) await beforeSend();
      const res = await api(`/reports/${versionId}/send`, {
        method: "POST",
        body: { recipients, subject: subject.trim() || undefined, message: message.trim() || undefined },
      });
      const failed = res.failed || 0;
      const ok = res.sent || 0;
      if (failed > 0) {
        toast.error(`Sent to ${ok}, failed for ${failed}.`, { title: "Partly sent" });
      } else {
        toast.success(
          `Report sent to ${ok} recipient${ok === 1 ? "" : "s"}.`,
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
          <div className="bg-white rounded-xl shadow-xl w-full max-w-md p-5">
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

            {/* Recipients: chip list + a free-typing input */}
            <label className="block text-xs font-medium text-stone-600 mt-4 mb-1">
              Recipients
            </label>
            <div className="flex flex-wrap gap-1.5 rounded-lg border border-stone-300 bg-white px-2 py-2 focus-within:border-orange-400">
              {emails.map((e) => (
                <span key={e} className="inline-flex items-center gap-1 rounded-md bg-stone-100 text-stone-700 text-xs px-2 py-1">
                  {e}
                  <button
                    onClick={() => removeEmail(e)}
                    className="text-stone-400 hover:text-red-600"
                    aria-label={`Remove ${e}`}
                  >
                    <X size={12} />
                  </button>
                </span>
              ))}
              <input
                type="email"
                value={draft}
                onChange={(ev) => setDraft(ev.target.value)}
                onKeyDown={onKeyDown}
                onBlur={() => draft.trim() && commitDraft()}
                onPaste={(ev) => {
                  const text = ev.clipboardData.getData("text");
                  if (/[\s,;]/.test(text)) { ev.preventDefault(); commitDraft(text); }
                }}
                placeholder={emails.length ? "Add another…" : "name@example.com"}
                className="flex-1 min-w-[10rem] outline-none text-sm py-0.5"
              />
            </div>
            <p className="text-[11px] text-stone-400 mt-1">
              Press Enter, comma, or space to add each address. Add as many as you like.
            </p>

            {/* Optional subject + message */}
            <label className="block text-xs font-medium text-stone-600 mt-3 mb-1">
              Subject <span className="text-stone-400 font-normal">(optional)</span>
            </label>
            <input
              type="text"
              value={subject}
              onChange={(e) => setSubject(e.target.value)}
              placeholder="A default subject is used if left blank"
              className={INPUT_CLS}
            />

            <label className="block text-xs font-medium text-stone-600 mt-3 mb-1">
              Message <span className="text-stone-400 font-normal">(optional)</span>
            </label>
            <textarea
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
