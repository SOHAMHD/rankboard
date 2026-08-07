import { useEffect, useState } from "react";
import { Send, LoaderCircle, X, Plus, Mail, Users, Save, Bookmark } from "lucide-react";
import { api } from "../api";
import { BTN_PRIMARY, BTN_GHOST, INPUT_CLS } from "../ui";
import { useToast } from "../toast.jsx";
import AddressInput, { foldDraft } from "./AddressInput";

export default function SendReportButton({
  versionId,
  periodKey,
  projectId,
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
  const [loadingSaved, setLoadingSaved] = useState(false);
  const [savingDefault, setSavingDefault] = useState(false);
  const [savedAt, setSavedAt] = useState(null);
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
    setSavedAt(null);
  };

  // Prefill from the project's saved recipients.
  //
  // Keyed on `open`, not on mount: the reports list renders one of these buttons
  // per row, so fetching on mount would fire a request per row on every page
  // load to populate a dialog nobody has opened.
  //
  // A project with no saved recipients is the ordinary case, not a failure — the
  // endpoint returns null and the form simply stays blank.
  useEffect(() => {
    if (!open || !projectId) return;
    let cancelled = false;
    setLoadingSaved(true);
    api(`/projects/${projectId}/recipients`)
      .then((res) => {
        if (cancelled || !res.recipients) return;
        const { primaryEmail, ccEmails = [], updatedAt } = res.recipients;
        setEmails(primaryEmail ? [primaryEmail] : []);
        setCc(ccEmails);
        setShowCc(ccEmails.length > 0);
        setSavedAt(updatedAt || null);
      })
      .catch(() => {})
      .finally(() => {
        if (!cancelled) setLoadingSaved(false);
      });
    // Guards against the dialog being closed mid-flight: without it the chips
    // land in state after reset() has run and reappear on the next open.
    return () => {
      cancelled = true;
    };
  }, [open, projectId]);

  const close = () => {
    // Also blocked mid-save: closing then would leave the user unsure whether
    // the default was stored.
    if (sending || savingDefault) return;
    setOpen(false);
    reset();
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

  /**
   * Store the addresses currently on screen as this project's default.
   *
   * The table holds exactly one primary, so if the To line has several the first
   * becomes the primary and the rest fold into Cc. The toast says so rather than
   * silently reshuffling what the user typed.
   *
   * Sending and saving stay separate on purpose: editing the list for a one-off
   * send shouldn't quietly rewrite the default for every future report.
   */
  const saveAsDefault = async () => {
    const to = foldDraft(emails, draft, cc);
    if (to.error) { setError(to.error); return; }
    const copies = foldDraft(cc, ccDraft, to.values);
    if (copies.error) { setError(copies.error); return; }

    setEmails(to.values);
    setDraft("");
    setCc(copies.values);
    setCcDraft("");

    if (to.values.length === 0) { setError("Add a primary email address first."); return; }

    const extras = to.values.slice(1);
    setSavingDefault(true);
    setError(null);
    try {
      const res = await api(`/projects/${projectId}/recipients`, {
        method: "PUT",
        body: {
          primaryEmail: to.values[0],
          ccEmails: [...extras, ...copies.values],
        },
      });
      const saved = res.recipients?.ccEmails?.length ?? 0;
      toast.success(
        extras.length
          ? `${to.values[0]} saved as primary, ${saved} on Cc.`
          : `Saved for next time — ${to.values[0]}${saved ? ` and ${saved} on Cc` : ""}.`,
        { title: "Default recipients saved" }
      );
      setSavedAt("just now");
    } catch (e) {
      const msg = e.message || "Couldn't save these as the default.";
      setError(msg);
      toast.error(msg, { title: "Save failed" });
    } finally {
      setSavingDefault(false);
    }
  };

  const totalAddresses = emails.length + cc.length;
  const busy = sending || savingDefault;

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
              <button onClick={close} disabled={busy} className="text-stone-400 hover:text-stone-700 disabled:opacity-40">
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
              {loadingSaved
                ? "Loading this project's saved recipients…"
                : "Press Enter, comma, or space to add each address. Add as many as you like."}
            </p>

            {savedAt && !loadingSaved && (
              // Worth surfacing the date: a list nobody has touched in a year
              // deserves a glance before it goes out again.
              <p className="text-[11px] text-stone-500 mt-1 inline-flex items-center gap-1">
                <Bookmark size={11} className="text-stone-400" />
                Filled in from this project&apos;s saved recipients
                {savedAt === "just now" ? "." : ` · last updated ${savedAt}`}
              </p>
            )}

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
              {projectId && (
                // mr-auto parks this on the far left, well away from Send, so
                // it can't be hit by accident on the way to the primary action.
                <button
                  onClick={saveAsDefault}
                  disabled={busy || (emails.length === 0 && !draft.trim())}
                  title="Remember these addresses for this project's future reports"
                  className={`${BTN_GHOST} px-3 py-1.5 mr-auto`}
                >
                  {savingDefault ? (
                    <LoaderCircle size={14} className="animate-spin" />
                  ) : (
                    <Save size={14} />
                  )}
                  Save as default
                </button>
              )}
              <button onClick={close} disabled={busy} className={`${BTN_GHOST} px-3 py-1.5`}>
                Cancel
              </button>
              <button
                onClick={send}
                disabled={busy || (emails.length === 0 && !draft.trim())}
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
