import { useEffect, useState } from "react";
import { LoaderCircle, Mail, Save, Trash2 } from "lucide-react";
import { api } from "../api";
import { BTN_GHOST, INPUT_CLS } from "../ui";
import AddressInput, { foldDraft, isEmail } from "./AddressInput";

/**
 * Edit a project's saved report recipients, outside the send dialog.
 *
 * Until this existed the only way to change an address was to open a report and
 * use "Save as default" — impossible for a project with no reports yet, and
 * awkward when you just want to fix a typo without going near a send button.
 * Clearing the list wasn't possible from the UI at all.
 *
 * Saves on its own button rather than joining the parent form's submit: the two
 * write to different endpoints, and a rejected address shouldn't block an
 * unrelated change to the project's domain.
 */
export default function ProjectRecipients({ projectId, onSaved }) {
  const [loading, setLoading] = useState(true);
  const [primary, setPrimary] = useState("");
  const [cc, setCc] = useState([]);
  const [ccDraft, setCcDraft] = useState("");
  const [updatedAt, setUpdatedAt] = useState(null);
  const [existed, setExisted] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [note, setNote] = useState(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    api(`/projects/${projectId}/recipients`)
      .then((res) => {
        if (cancelled) return;
        if (!res.recipients) {
          setExisted(false);
          return;
        }
        setPrimary(res.recipients.primaryEmail || "");
        setCc(res.recipients.ccEmails || []);
        setUpdatedAt(res.recipients.updatedAt || null);
        setExisted(true);
      })
      .catch(() => {})
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [projectId]);

  const save = async () => {
    const folded = foldDraft(cc, ccDraft, [primary.trim()]);
    if (folded.error) return setError(folded.error);
    setCc(folded.values);
    setCcDraft("");

    const addr = primary.trim();
    if (!addr) return setError("Enter a primary address, or remove the saved recipients.");
    if (!isEmail(addr)) return setError(`Not a valid email: ${addr}`);

    setBusy(true);
    setError(null);
    setNote(null);
    try {
      const res = await api(`/projects/${projectId}/recipients`, {
        method: "PUT",
        body: { primaryEmail: addr, ccEmails: folded.values },
      });
      setPrimary(res.recipients.primaryEmail);
      setCc(res.recipients.ccEmails);
      setExisted(true);
      setUpdatedAt("just now");
      setNote("Saved.");
      onSaved?.();
    } catch (e) {
      setError(e.message || "Couldn't save the recipients.");
    } finally {
      setBusy(false);
    }
  };

  const clear = async () => {
    setBusy(true);
    setError(null);
    setNote(null);
    try {
      await api(`/projects/${projectId}/recipients`, { method: "DELETE" });
      setPrimary("");
      setCc([]);
      setCcDraft("");
      setExisted(false);
      setUpdatedAt(null);
      setNote("Removed. The send dialog will open blank for this project.");
      onSaved?.();
    } catch (e) {
      setError(e.message || "Couldn't remove the recipients.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="rounded-xl border border-stone-200 p-4">
      <div className="flex items-center gap-2">
        <Mail size={15} className="text-stone-400" />
        <h4 className="text-sm font-semibold text-stone-800">Report recipients</h4>
        {loading && <LoaderCircle size={13} className="animate-spin text-stone-400" />}
        {!loading && !existed && (
          <span className="text-[11px] text-stone-400 ml-auto">None saved yet</span>
        )}
        {!loading && existed && updatedAt && (
          <span className="text-[11px] text-stone-400 ml-auto">
            {updatedAt === "just now" ? "Updated just now" : `Updated ${updatedAt}`}
          </span>
        )}
      </div>
      <p className="text-xs text-stone-400 mt-1">
        Prefilled into the send dialog for this project's reports. Editable there too.
      </p>

      <label className="block text-xs font-semibold uppercase tracking-wider text-stone-400 mb-1.5 mt-3">
        Primary address
      </label>
      <input
        type="email"
        value={primary}
        onChange={(e) => setPrimary(e.target.value)}
        placeholder="accounts@client.com"
        disabled={loading}
        className={INPUT_CLS}
      />

      <label className="block text-xs font-semibold uppercase tracking-wider text-stone-400 mb-1.5 mt-3">
        Cc <span className="normal-case tracking-normal font-normal text-stone-400">(optional)</span>
      </label>
      <AddressInput
        id={`project-${projectId}-cc`}
        values={cc}
        onChange={setCc}
        draft={ccDraft}
        onDraftChange={setCcDraft}
        taken={[primary.trim()].filter(Boolean)}
        placeholder="colleague@client.com"
        onError={setError}
      />

      {error && (
        <p className="text-sm text-red-600 bg-red-50 border border-red-100 rounded-lg px-3 py-2 mt-3">
          {error}
        </p>
      )}
      {note && !error && <p className="text-xs text-emerald-700 mt-2">{note}</p>}

      <div className="flex items-center gap-2 mt-3">
        <button onClick={save} disabled={busy || loading} className={`${BTN_GHOST} px-3 py-1.5`}>
          {busy ? <LoaderCircle size={14} className="animate-spin" /> : <Save size={14} />}
          Save recipients
        </button>
        {existed && (
          <button
            onClick={clear}
            disabled={busy || loading}
            className={`${BTN_GHOST} px-3 py-1.5 text-red-600 hover:bg-red-50`}
          >
            <Trash2 size={14} /> Remove
          </button>
        )}
      </div>
    </div>
  );
}
