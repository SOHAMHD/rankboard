/* ════════════════════════════════════════════════════════════════════
   PROJECTS — the landing page after login. Every signed-in role sees
   the list (provisional); mutation buttons render only for roles the
   server granted them to, and the API re-checks regardless.
   ════════════════════════════════════════════════════════════════════ */
import { useEffect, useState } from "react";
import { LoaderCircle, Pencil, Plus, Trash2 } from "lucide-react";
import { api } from "../api";
import { TopBar, Modal, ErrorNote, Toggle, can, INPUT_CLS, BTN_PRIMARY } from "../ui";

/* Per-project Google country for rank checks → DataForSEO location_code.
   "Server default" (null) means fall back to RANK_LOCATION_CODE on the server. */
const COUNTRIES = [
  { code: 2356, label: "India" },
  { code: 2036, label: "Australia" },
  { code: 2840, label: "United States" },
  { code: 2826, label: "United Kingdom" },
  { code: 2124, label: "Canada" },
];

const countryLabel = (code) => COUNTRIES.find((c) => c.code === code)?.label ?? null;

// Best-effort guess from a domain's TLD; null when there's no confident
// match (e.g. .com), so the caller leaves the current selection alone.
function codeFromDomain(domain) {
  const d = (domain || "").trim().toLowerCase();
  if (d.endsWith(".au")) return 2036; // covers .au and .com.au
  if (d.endsWith(".in")) return 2356;
  if (d.endsWith(".uk")) return 2826; // covers .uk and .co.uk
  if (d.endsWith(".ca")) return 2124;
  return null;
}

function CountrySelect({ value, onChange }) {
  // Keep an unrecognised but set code visible rather than silently dropping it.
  const known = value == null || COUNTRIES.some((c) => c.code === value);
  return (
    <select
      value={value ?? ""}
      onChange={(e) => onChange(e.target.value === "" ? null : Number(e.target.value))}
      className={INPUT_CLS}
    >
      <option value="">Server default</option>
      {COUNTRIES.map((c) => (
        <option key={c.code} value={c.code}>
          {c.label}
        </option>
      ))}
      {!known && <option value={value}>{`Code ${value}`}</option>}
    </select>
  );
}

export function ProjectsView({ user, onOpenProject, onPeople, onLogout }) {
  const [projects, setProjects] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [showAdd, setShowAdd] = useState(false);
  const [editProject, setEditProject] = useState(null);
  const [confirmId, setConfirmId] = useState(null);

  const refresh = async () => {
    try {
      const d = await api("/projects");
      setProjects(d.projects);
      setError(null);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refresh();
  }, []);

  const toggleProject = async (p) => {
    try {
      await api(`/projects/${p.id}`, { method: "PATCH", body: { active: !p.active } });
      await refresh();
    } catch (err) {
      setError(err.message);
    }
  };

  const deleteProject = async (id) => {
    try {
      await api(`/projects/${id}`, { method: "DELETE" });
      setConfirmId(null);
      await refresh();
    } catch (err) {
      setError(err.message);
    }
  };

  const activeCount = projects.filter((p) => p.active).length;

  return (
    <div className="min-h-screen bg-stone-100">
      <TopBar user={user} onLogout={onLogout} onPeople={onPeople} />

      <main className="max-w-5xl mx-auto px-4 sm:px-6 py-8 sm:py-10">
        <div className="flex flex-wrap items-end justify-between gap-4 mb-6">
          <div>
            <h1 className="text-2xl font-bold text-stone-900 tracking-tight font-display">Projects</h1>
            <p className="text-sm text-stone-500 mt-0.5">
              {projects.length} total · {activeCount} active
            </p>
          </div>
          {can(user, "addProject") && (
            <button onClick={() => setShowAdd(true)} className={`${BTN_PRIMARY} px-4 py-2`}>
              <Plus size={16} /> Add project
            </button>
          )}
        </div>

        <ErrorNote>{error}</ErrorNote>

        {loading ? (
          <div className="py-20 flex justify-center">
            <LoaderCircle size={22} className="text-orange-600 animate-spin" />
          </div>
        ) : projects.length === 0 ? (
          <div className="bg-white rounded-xl border border-dashed border-stone-300 py-16 text-center px-6 mt-2">
            <h3 className="font-semibold text-stone-800 font-display">No projects yet</h3>
            {can(user, "addProject") ? (
              <>
                <p className="text-sm text-stone-500 mt-1 mb-5">A project is one website or client you do SEO for.</p>
                <button onClick={() => setShowAdd(true)} className={`${BTN_PRIMARY} px-4 py-2`}>
                  <Plus size={15} /> Add your first project
                </button>
              </>
            ) : (
              <p className="text-sm text-stone-500 mt-1">An admin will add the first project.</p>
            )}
          </div>
        ) : (
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4 mt-2">
            {projects.map((p) => (
              <ProjectCard
                key={p.id}
                project={p}
                user={user}
                confirming={confirmId === p.id}
                onOpen={() => onOpenProject(p.id)}
                onEdit={(e) => {
                  e.stopPropagation();
                  setEditProject(p);
                  setConfirmId(null);
                }}
                onToggle={(e) => {
                  e.stopPropagation(); // the card itself is clickable
                  toggleProject(p);
                  setConfirmId(null);
                }}
                onDelete={(e) => {
                  e.stopPropagation();
                  confirmId === p.id ? deleteProject(p.id) : setConfirmId(p.id);
                }}
              />
            ))}
          </div>
        )}
      </main>

      {showAdd && (
        <AddProjectModal
          onClose={() => setShowAdd(false)}
          onAdded={() => {
            setShowAdd(false);
            refresh();
          }}
        />
      )}

      {editProject && (
        <EditProjectModal
          project={editProject}
          onClose={() => setEditProject(null)}
          onSaved={() => {
            setEditProject(null);
            refresh();
          }}
        />
      )}
    </div>
  );
}

function ProjectCard({ project, user, confirming, onOpen, onEdit, onToggle, onDelete }) {
  const showToggle = can(user, "toggleProject");
  const showEdit = can(user, "toggleProject"); // same "manage settings" right the API uses
  const showDelete = can(user, "deleteProject");
  const country = countryLabel(project.locationCode);

  return (
    <div
      onClick={onOpen}
      className={`group bg-white rounded-xl border p-5 cursor-pointer transition-all hover:shadow-md border-stone-200 hover:border-orange-400 ${
        project.active ? "" : "opacity-70 hover:opacity-100"
      }`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="font-semibold text-stone-900 truncate font-display">{project.name}</h3>
          {project.domain && <p className="text-xs text-stone-500 font-data truncate mt-0.5">{project.domain}</p>}
          <p className="text-xs text-stone-400 mt-0.5">
            {country ? `${country} · ` : ""}Added {project.createdAt?.slice(0, 10)}
          </p>
        </div>
        <span
          className={`shrink-0 text-xs font-medium px-2 py-0.5 rounded-full ${
            project.active ? "bg-emerald-100 text-emerald-700" : "bg-stone-200 text-stone-500"
          }`}
        >
          {project.active ? "Active" : "Inactive"}
        </span>
      </div>

      <p className="text-sm text-stone-500 mt-4">
        <span className="font-semibold text-stone-700 font-data">{project.keywordCount}</span>{" "}
        keyword{project.keywordCount === 1 ? "" : "s"} tracked
      </p>

      {(showToggle || showEdit || showDelete) && (
        <div className="mt-4 pt-4 border-t border-stone-100 flex items-center justify-between">
          {showToggle ? <Toggle on={project.active} onClick={onToggle} /> : <span />}
          <span className="flex items-center gap-0.5">
            {showEdit && (
              <button
                onClick={onEdit}
                aria-label={`Edit ${project.name}`}
                title="Edit project (domain & country)"
                className="p-1.5 rounded-md text-stone-300 hover:text-orange-600 hover:bg-orange-50 transition-colors"
              >
                <Pencil size={16} />
              </button>
            )}
            {showDelete &&
              (confirming ? (
                <button
                  onClick={onDelete}
                  className="text-xs font-semibold text-white bg-red-500 hover:bg-red-600 px-2.5 py-1 rounded-md transition-colors"
                >
                  Confirm delete
                </button>
              ) : (
                <button
                  onClick={onDelete}
                  aria-label={`Delete ${project.name}`}
                  title="Delete project"
                  className="p-1.5 rounded-md text-stone-300 hover:text-red-500 hover:bg-red-50 transition-colors"
                >
                  <Trash2 size={16} />
                </button>
              ))}
          </span>
        </div>
      )}
    </div>
  );
}

function AddProjectModal({ onClose, onAdded }) {
  const [name, setName] = useState("");
  const [domain, setDomain] = useState("");
  const [locationCode, setLocationCode] = useState(null); // null = server default
  const [gaPropertyId, setGaPropertyId] = useState("");
  const [gscSiteUrl, setGscSiteUrl] = useState("");
  const [countryTouched, setCountryTouched] = useState(false);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  // Pre-fill the country from the domain's TLD, unless the user already
  // picked one by hand (then we leave their choice alone).
  const onDomainChange = (val) => {
    setDomain(val);
    if (!countryTouched) {
      const guess = codeFromDomain(val);
      if (guess !== null) setLocationCode(guess);
    }
  };

  const submit = async () => {
    if (!name.trim()) return;
    setBusy(true);
    setError(null);
    try {
      await api("/projects", {
        method: "POST",
        body: {
          name: name.trim(),
          domain: domain.trim() || null,
          locationCode,
          gaPropertyId: gaPropertyId.trim() || null,
          gscSiteUrl: gscSiteUrl.trim() || null,
        },
      });
      onAdded();
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  };

  return (
    <Modal title="Add project" onClose={onClose}>
      <p className="text-sm text-stone-500 mb-4">One website or client you're doing SEO for.</p>
      <input
        value={name}
        onChange={(e) => setName(e.target.value)}
        onKeyDown={(e) => e.key === "Enter" && submit()}
        placeholder="e.g. Sattva Connect"
        autoFocus
        className={`${INPUT_CLS} mb-4`}
      />
      <label className="block text-xs font-semibold uppercase tracking-wider text-stone-400 mb-1.5">
        Website domain <span className="normal-case font-normal">(optional)</span>
      </label>
      <input
        value={domain}
        onChange={(e) => onDomainChange(e.target.value)}
        onKeyDown={(e) => e.key === "Enter" && submit()}
        placeholder="e.g. sattvaconnect.com"
        className={INPUT_CLS}
      />
      <p className="text-xs text-stone-400 mt-2">Needed for automatic rank checks — the site the checker looks for in Google results.</p>

      <label className="block text-xs font-semibold uppercase tracking-wider text-stone-400 mb-1.5 mt-4">Country</label>
      <CountrySelect
        value={locationCode}
        onChange={(v) => {
          setLocationCode(v);
          setCountryTouched(true);
        }}
      />
      <p className="text-xs text-stone-400 mt-2">Which Google country to check rankings in. "Server default" uses the server-wide setting.</p>

      <label className="block text-xs font-semibold uppercase tracking-wider text-stone-400 mb-1.5 mt-4">
        GA4 Property ID <span className="normal-case font-normal">(optional)</span>
      </label>
      <input
        value={gaPropertyId}
        onChange={(e) => setGaPropertyId(e.target.value)}
        onKeyDown={(e) => e.key === "Enter" && submit()}
        placeholder="e.g. 123456789"
        className={INPUT_CLS}
      />
      <p className="text-xs text-stone-400 mt-2">Google Analytics 4 property ID — powers the Traffic (GA4) panel for this project.</p>

      <label className="block text-xs font-semibold uppercase tracking-wider text-stone-400 mb-1.5 mt-4">
        Search Console Site URL <span className="normal-case font-normal">(optional)</span>
      </label>
      <input
        value={gscSiteUrl}
        onChange={(e) => setGscSiteUrl(e.target.value)}
        onKeyDown={(e) => e.key === "Enter" && submit()}
        placeholder="e.g. https://www.example.com/"
        className={INPUT_CLS}
      />
      <p className="text-xs text-stone-400 mt-2">URL-prefix property like "https://www.example.com/" (with trailing slash), or domain property like "sc-domain:example.com".</p>

      <ErrorNote>{error}</ErrorNote>
      <button onClick={submit} disabled={!name.trim() || busy} className={`${BTN_PRIMARY} w-full mt-4 py-2.5`}>
        {busy ? <LoaderCircle size={15} className="animate-spin" /> : "Create project"}
      </button>
    </Modal>
  );
}

function EditProjectModal({ project, onClose, onSaved }) {
  const [domain, setDomain] = useState(project.domain || "");
  const [locationCode, setLocationCode] = useState(project.locationCode ?? null);
  const [gaPropertyId, setGaPropertyId] = useState(project.gaPropertyId || "");
  const [gscSiteUrl, setGscSiteUrl] = useState(project.gscSiteUrl || "");
  const [countryTouched, setCountryTouched] = useState(false);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  const onDomainChange = (val) => {
    setDomain(val);
    if (!countryTouched) {
      const guess = codeFromDomain(val);
      if (guess !== null) setLocationCode(guess);
    }
  };

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      await api(`/projects/${project.id}`, {
        method: "PATCH",
        body: {
          domain: domain.trim() || null,
          locationCode,
          gaPropertyId: gaPropertyId.trim() || null,
          gscSiteUrl: gscSiteUrl.trim() || null,
        },
      });
      onSaved();
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  };

  return (
    <Modal title="Edit project" onClose={onClose}>
      <p className="text-sm text-stone-500 mb-4">
        Settings for <span className="font-medium text-stone-800">{project.name}</span>.
      </p>

      <label className="block text-xs font-semibold uppercase tracking-wider text-stone-400 mb-1.5">
        Website domain <span className="normal-case font-normal">(optional)</span>
      </label>
      <input
        value={domain}
        onChange={(e) => onDomainChange(e.target.value)}
        onKeyDown={(e) => e.key === "Enter" && submit()}
        placeholder="e.g. sattvaconnect.com"
        autoFocus
        className={INPUT_CLS}
      />
      <p className="text-xs text-stone-400 mt-2">The site the checker looks for in Google results.</p>

      <label className="block text-xs font-semibold uppercase tracking-wider text-stone-400 mb-1.5 mt-4">Country</label>
      <CountrySelect
        value={locationCode}
        onChange={(v) => {
          setLocationCode(v);
          setCountryTouched(true);
        }}
      />
      <p className="text-xs text-stone-400 mt-2">Which Google country to check rankings in. "Server default" uses the server-wide setting.</p>

      <label className="block text-xs font-semibold uppercase tracking-wider text-stone-400 mb-1.5 mt-4">
        GA4 Property ID <span className="normal-case font-normal">(optional)</span>
      </label>
      <input
        value={gaPropertyId}
        onChange={(e) => setGaPropertyId(e.target.value)}
        onKeyDown={(e) => e.key === "Enter" && submit()}
        placeholder="e.g. 123456789"
        className={INPUT_CLS}
      />
      <p className="text-xs text-stone-400 mt-2">Google Analytics 4 property ID — powers the Traffic (GA4) panel for this project.</p>

      <label className="block text-xs font-semibold uppercase tracking-wider text-stone-400 mb-1.5 mt-4">
        Search Console Site URL <span className="normal-case font-normal">(optional)</span>
      </label>
      <input
        value={gscSiteUrl}
        onChange={(e) => setGscSiteUrl(e.target.value)}
        onKeyDown={(e) => e.key === "Enter" && submit()}
        placeholder="e.g. https://www.example.com/"
        className={INPUT_CLS}
      />
      <p className="text-xs text-stone-400 mt-2">URL-prefix property like "https://www.example.com/" (with trailing slash), or domain property like "sc-domain:example.com".</p>

      <ErrorNote>{error}</ErrorNote>
      <button onClick={submit} disabled={busy} className={`${BTN_PRIMARY} w-full mt-4 py-2.5`}>
        {busy ? <LoaderCircle size={15} className="animate-spin" /> : "Save changes"}
      </button>
    </Modal>
  );
}
