import { X } from "lucide-react";

/**
 * Mirror of the server's `_valid_email` (services/email_service.py).
 *
 * Deliberately the same shape of check on both sides: this one exists to give
 * immediate feedback while typing, the server's is the one that decides. Keep
 * them in step — an address the form accepts but the server rejects is a
 * confusing round trip.
 */
export function isEmail(s) {
  const v = (s || "").trim();
  if (!v || (v.match(/@/g) || []).length !== 1) return false;
  const [local, domain] = v.split("@");
  return !!local && domain.includes(".") && !domain.startsWith(".") && !domain.endsWith(".");
}

/**
 * An address chip input: type or paste addresses, they become removable chips.
 *
 * Lives in its own file because three screens now need it — the send dialog's
 * Recipients and Cc lines, and the onboarding wizard's Cc list. The
 * paste-splitting, backspace-to-remove and commit-on-blur behaviour is fiddly
 * enough that copies would drift apart silently.
 *
 * `taken` holds addresses already used by a sibling field, so the same person
 * can't be put on two lines. The server drops that duplicate anyway; saying so
 * here is clearer than letting it vanish on save.
 */
export default function AddressInput({
  id,
  values,
  onChange,
  draft,
  onDraftChange,
  taken = [],
  placeholder,
  onError,
}) {
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

/**
 * Fold a typed-but-not-yet-committed draft into the committed list.
 *
 * Someone who types an address and hits the primary button straight away means
 * for it to count, so callers run this before validating. `other` is the
 * sibling field's values, checked so the fold can't create a cross-field
 * duplicate.
 */
export function foldDraft(values, pending, other = []) {
  const clean = (pending || "").trim();
  if (!clean) return { values, error: null };
  if (!isEmail(clean)) return { values, error: `Not a valid email: ${clean}` };
  const seen = new Set([...values, ...other].map((e) => e.toLowerCase()));
  if (seen.has(clean.toLowerCase())) return { values, error: null };
  return { values: [...values, clean], error: null };
}
