import { useEffect, useState } from "react";
import { LoaderCircle, Mail, Save, Trash2 } from "lucide-react";
import { api } from "../api";
import { BTN_GHOST, INPUT_CLS } from "../ui";
import AddressInput, { foldDraft, isEmail } from "./AddressInput";


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
  // Distinct from `error`, which is about the last save. Until a load succeeds
  // we don't know what's stored, so saving would overwrite a list we never saw.
  const [loadFailed, setLoadFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setLoadFailed(false);
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
      .catch(() => {
        if (!cancelled) setLoadFailed(true);
      })
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
        {!loading && loadFailed && (
          <span className="text-[11px] text-amber-700 ml-auto">Couldn&apos;t load</span>
        )}
        {!loading && !loadFailed && !existed && (
          <span className="text-[11px] text-stone-400 ml-auto">None saved yet</span>
        )}
        {!loading && !loadFailed && existed && updatedAt && (
          <span className="text-[11px] text-stone-400 ml-auto">
            {updatedAt === "just now" ? "Updated just now" : `Updated ${updatedAt}`}
          </span>
        )}
      </div>
      <p className="text-xs text-stone-400 mt-1">
        Prefilled into the send dialog for this project's reports. Editable there too.
      </p>

      {loadFailed && (
        <p className="text-sm text-amber-800 bg-amber-50 border border-amber-100 rounded-lg px-3 py-2 mt-3">
          Couldn&apos;t load this project&apos;s saved recipients. Saving is disabled until we
          know what&apos;s stored — reopen this panel to try again.
        </p>
      )}

      <label
        htmlFor={`project-${projectId}-primary`}
        className="block text-xs font-semibold uppercase tracking-wider text-stone-400 mb-1.5 mt-3"
      >
        Primary address
      </label>
      <input
        id={`project-${projectId}-primary`}
        type="email"
        value={primary}
        onChange={(e) => setPrimary(e.target.value)}
        placeholder="accounts@client.com"
        disabled={loading || loadFailed}
        className={INPUT_CLS}
      />

      <label
        htmlFor={`project-${projectId}-cc`}
        className="block text-xs font-semibold uppercase tracking-wider text-stone-400 mb-1.5 mt-3"
      >
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
        <button onClick={save} disabled={busy || loading || loadFailed} className={`${BTN_GHOST} px-3 py-1.5`}>
          {busy ? <LoaderCircle size={14} className="animate-spin" /> : <Save size={14} />}
          Save recipients
        </button>
        {existed && (
          <button
            onClick={clear}
            disabled={busy || loading || loadFailed}
            className={`${BTN_GHOST} px-3 py-1.5 text-red-600 hover:bg-red-50`}
          >
            <Trash2 size={14} /> Remove
          </button>
        )}
      </div>
    </div>
  );
}
