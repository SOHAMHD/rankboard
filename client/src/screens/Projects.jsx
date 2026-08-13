import { memo, useCallback, useEffect, useState } from "react";
import { LoaderCircle, Pencil, Plus, Trash2 } from "lucide-react";
import { api } from "../api";
import { TopBar, Modal, ConfirmModal, ErrorNote, Toggle, can, INPUT_CLS, BTN_PRIMARY } from "../ui";
import ProjectRecipients from "../lib/ProjectRecipients";

export function ProjectsView({ user, onOpenProject, onPeople, onEmailLog, onLogout }) {
  const [projects, setProjects] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [showAdd, setShowAdd] = useState(false);
  const [editProject, setEditProject] = useState(null);
  // The whole project, not just an id: the dialog names what's being destroyed.
  const [confirmProject, setConfirmProject] = useState(null);
  const [deleting, setDeleting] = useState(false);

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
    const next = !p.active;
    setProjects((list) => list.map((x) => (x.id === p.id ? { ...x, active: next } : x)));
    setError(null);
    try {
      await api(`/projects/${p.id}`, { method: "PATCH", body: { active: next } });
    } catch (err) {
      setProjects((list) => list.map((x) => (x.id === p.id ? { ...x, active: p.active } : x)));
      setError(err.message);
    }
  };

  const deleteProject = async (id) => {
    setDeleting(true);
    try {
      await api(`/projects/${id}`, { method: "DELETE" });
      setConfirmProject(null);
      await refresh();
    } catch (err) {
      setError(err.message);
    } finally {
      setDeleting(false);
    }
  };

  const activeCount = projects.filter((p) => p.active).length;

  return (
    <div className="min-h-screen bg-stone-100">
      <TopBar user={user} onLogout={onLogout} onPeople={onPeople} onEmailLog={onEmailLog} />

      <main className="max-w-5xl mx-auto px-4 sm:px-6 py-8 sm:py-10">
        <div className="flex flex-wrap items-end justify-between gap-4 mb-6">
          <div>
            <h1 className="text-2xl font-bold text-stone-900 tracking-tight font-display">Projects</h1>
            <p className="text-sm text-stone-500 mt-0.5">
              {projects.length} total · {activeCount} active
            </p>
          </div>
          {can(user, "addProject") && (
            <button onClick={() => setShowAdd(true)} className={`${BTN_PRIMARY} px-4 py-2 `}>
              <Plus size={16} /> Add project
            </button>
          )}
        </div>

      
        {/* Without this the screen lied: a failed load left `projects` empty and
            rendered "No projects yet", so a network error was indistinguishable
            from a genuinely empty account — and a failed delete or toggle did
            nothing visible at all. */}
        <ErrorNote>{error}</ErrorNote>

        {loading ? (
          <div className="py-20 flex justify-center">
            <LoaderCircle size={22} className="text-orange-600 animate-spin" />
          </div>
        ) : error && projects.length === 0 ? (
          <div className="bg-white rounded-xl border border-dashed border-stone-300 py-16 text-center px-6 mt-2">
            <h3 className="font-semibold text-stone-800 font-display">Couldn&apos;t load projects</h3>
            <p className="text-sm text-stone-500 mt-1 mb-5">
              The list above is empty because the request failed, not because there are none.
            </p>
            <button onClick={refresh} className={`${BTN_PRIMARY} px-4 py-2`}>Try again</button>
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
                onOpen={() => onOpenProject(p.id)}
                onEdit={(e) => {
                  e.stopPropagation();
                  setEditProject(p);
                }}
                onToggle={(e) => {
                  e.stopPropagation();
                  toggleProject(p);
                }}
                onDelete={(e) => {
                  e.stopPropagation();
                  setConfirmProject(p);
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

      {confirmProject && (
        <ConfirmModal
          title={`Delete “${confirmProject.name}”?`}
          confirmLabel="Delete project"
          busy={deleting}
          onCancel={() => setConfirmProject(null)}
          onConfirm={() => deleteProject(confirmProject.id)}
        >
          This permanently deletes the project and everything recorded against it —
          every keyword and its full rank history, backlinks, posts and saved
          recipients. Reports already generated keep their own frozen copy.
          <span className="block mt-2 font-medium text-stone-700">This can&apos;t be undone.</span>
        </ConfirmModal>
      )}
    </div>
  );
}

/** Which Search Console property a domain resolves to, asked of the server.
 *
 * Replaces a second free-text field that asked for the same site in Google's
 * notation. That field is where both of this install's misconfigurations came
 * from — one project carried a spurious `www.`, another was missing the trailing
 * slash a URL-prefix property always has — and neither showed a symptom beyond
 * an empty Search Console panel.
 *
 * `override` is only surfaced when the domain can't decide on its own: no
 * property matches, or several do (a site with both a bare and a www property,
 * where guessing would report the wrong numbers).
 */
function useGscProperty(domain, initialOverride = "") {
  const [state, setState] = useState({ status: "idle", matches: [], properties: [], error: null });
  const [override, setOverride] = useState(initialOverride);

  const trimmed = (domain || "").trim();

  useEffect(() => {
    if (!trimmed) {
      setState({ status: "idle", matches: [], properties: [], error: null });
      return;
    }
    let live = true;
    setState((s) => ({ ...s, status: "loading" }));
    // Debounced: this fires per keystroke in the domain field, and each call is
    // a round trip to Google's API on the server.
    const t = setTimeout(() => {
      api(`/projects/gsc-properties/match?domain=${encodeURIComponent(trimmed)}`)
        .then((d) => {
          if (!live) return;
          setState({
            status: "done",
            matches: d.matches || [],
            properties: d.properties || [],
            error: d.error || null,
          });
        })
        .catch((err) => live && setState({ status: "done", matches: [], properties: [], error: err.message }));
    }, 500);
    return () => {
      live = false;
      clearTimeout(t);
    };
  }, [trimmed]);

  const auto = state.matches.length === 1 ? state.matches[0] : null;

  // A stored value that happens to equal the automatic match isn't an override.
  // Collapsing it keeps the dialog honest ("matched automatically") and lets the
  // server re-resolve if the property is later renamed.
  useEffect(() => {
    if (auto && override === auto) setOverride("");
  }, [auto, override]);

  const needsChoice = state.status === "done" && !state.error && !auto && !override && !!trimmed;

  return { ...state, auto, needsChoice, override, setOverride, resolved: override || auto };
}

function GscPropertyField({ gsc }) {
  const { status, auto, needsChoice, properties, error, override, setOverride } = gsc;

  return (
    <div className="mt-4">
      <span className="block text-xs font-semibold uppercase tracking-wider text-stone-400 mb-1.5">
        Search Console property
      </span>

      {status === "loading" && (
        <p className="flex items-center gap-2 text-sm text-stone-500">
          <LoaderCircle size={14} className="animate-spin" /> Looking up the property…
        </p>
      )}

      {status === "idle" && (
        <p className="text-sm text-stone-400">Enter a domain above and it'll be matched automatically.</p>
      )}

      {override ? (
        <p className="text-sm text-stone-700">
          <span className="font-data">{override}</span>{" "}
          <span className="text-xs text-stone-400">— set explicitly</span>
        </p>
      ) : status === "done" && auto ? (
        <p className="text-sm text-stone-700">
          <span className="font-data">{auto}</span>{" "}
          <span className="text-xs text-stone-400">— matched automatically</span>
        </p>
      ) : null}

      {status === "done" && error && (
        // Not fatal: the server saves the project either way and re-resolves the
        // property the next time it can reach Google.
        <p className="text-xs text-stone-500">
          Couldn't reach Search Console to check ({error}). The project will save, and the
          property gets matched on the next attempt.
        </p>
      )}

      {needsChoice && (
        <div className="space-y-2">
          <p className="text-xs text-stone-500">
            {properties.length
              ? "No single property matches that domain — pick one, or leave it blank to set it later."
              : "The service account can't see any properties yet. Add it as a user in Search Console, then reopen this."}
          </p>
          {properties.length > 0 && (
            <select
              value={override}
              onChange={(e) => setOverride(e.target.value)}
              className={INPUT_CLS}
            >
              <option value="">— none —</option>
              {properties.map((p) => (
                <option key={p} value={p}>{p}</option>
              ))}
            </select>
          )}
        </div>
      )}

      {override && (
        <button
          type="button"
          onClick={() => setOverride("")}
          className="mt-2 text-xs text-orange-600 hover:underline"
        >
          Clear and match from the domain instead
        </button>
      )}
    </div>
  );
}

function ProjectCard({ project, user, onOpen, onEdit, onToggle, onDelete }) {
  const showToggle = can(user, "toggleProject");
  const showEdit = can(user, "toggleProject");
  const showDelete = can(user, "deleteProject");

  // An inactive project can't be opened — the API refuses GET /projects/{id} with
  // a 409. Reflecting that here means the card doesn't invite a click that will
  // only produce an error.
  const openable = project.active;

  return (
    // The card stays clickable as an affordance, but the title below is a real
    // button — this was a bare <div onClick>, which made opening a project
    // impossible without a mouse.
    <div
      onClick={openable ? onOpen : undefined}
      className={`group bg-white rounded-xl border p-5 transition-all border-stone-200 focus-within:border-orange-400 ${
        openable
          ? "cursor-pointer hover:shadow-md hover:border-orange-400"
          : "opacity-75 hover:opacity-100"
      }`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="font-semibold text-stone-900 truncate font-display">
            {openable ? (
              <button
                type="button"
                onClick={(e) => { e.stopPropagation(); onOpen(); }}
                className="text-left hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-orange-500 rounded"
              >
                {project.name}
              </button>
            ) : (
              <span title="Inactive — reactivate it to open" className="text-stone-600">
                {project.name}
              </span>
            )}
          </h3>
          {project.clientName && <p className="text-xs text-stone-600 truncate mt-0.5">{project.clientName}</p>}
          {project.domain && <p className="text-xs text-stone-500 font-data truncate mt-0.5">{project.domain}</p>}
          <p className="text-xs text-stone-400 mt-0.5">
            Added {project.createdAt?.slice(0, 10)}
          </p>
        </div>
        <span
          className={`shrink-0 text-xs font-medium px-2 py-0.5 rounded-full ${
            project.active ? "bg-blue-100 text-blue-700" : "bg-stone-200 text-stone-600"
          }`}
          title={project.active ? undefined : "Inactive — can't be opened, and reports can't be generated or sent"}
        >
          {project.active ? "Active" : "Inactive"}
        </span>
      </div>

      <p className="text-sm text-stone-500 mt-4">
        <span className="font-semibold text-stone-700 font-data">{project.keywordCount}</span>{" "}
        keyword{project.keywordCount === 1 ? "" : "s"} tracked
      </p>

      {/* Says what the toggle does. It used to be purely cosmetic — an inactive
          project opened normally and could still have a report emailed to the
          client — so nothing on screen explained what turning it off achieved. */}
      {!openable && (
        <p className="text-xs text-stone-500 mt-2 rounded-lg bg-stone-50 border border-stone-200 px-2.5 py-2">
          Archived. It can&apos;t be opened, and reports can&apos;t be generated or sent
          until it&apos;s switched back on. Existing reports stay readable.
        </p>
      )}

      {(showToggle || showEdit || showDelete) && (
        <div className="mt-4 pt-4 border-t border-stone-100 flex items-center justify-between">
          {showToggle ? <Toggle on={project.active} onClick={onToggle} /> : <span />}
          <span className="flex items-center gap-0.5">
            {/* stone-500, not stone-300: at ~1.4:1 against white these icon
                buttons were effectively invisible, and they're interactive. */}
            {showEdit && (
              <button
                onClick={onEdit}
                aria-label={`Edit ${project.name}`}
                title="Edit project (domain, location & integrations)"
                className="p-1.5 rounded-md text-stone-500 hover:text-orange-600 hover:bg-orange-50 transition-colors"
              >
                <Pencil size={16} />
              </button>
            )}
            {/* One click opens a dialog that names what's destroyed. This used to
                swap the trash icon for a "Confirm delete" button in the same
                position, so a double-click permanently deleted a project and all
                its keyword history. */}
            {showDelete && (
              <button
                onClick={onDelete}
                aria-label={`Delete ${project.name}`}
                title="Delete project"
                className="p-1.5 rounded-md text-stone-500 hover:text-red-500 hover:bg-red-50 transition-colors"
              >
                <Trash2 size={16} />
              </button>
            )}
          </span>
        </div>
      )}
    </div>
  );
}

function AddProjectModal({ onClose, onAdded }) {
  const [name, setName] = useState("");
  const [clientName, setClientName] = useState("");
  const [domain, setDomain] = useState("");
  const [gaPropertyId, setGaPropertyId] = useState("");
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const gsc = useGscProperty(domain);

  const submit = async () => {
    if (!name.trim()) return;
    setBusy(true);
    setError(null);
    try {
      await api("/projects", {
        method: "POST",
        body: {
          name: name.trim(),
          clientName: clientName.trim() || null,
          domain: domain.trim() || null,
          gaPropertyId: gaPropertyId.trim() || null,
          // Only sent when the domain couldn't decide on its own; otherwise the
          // server matches the property itself, from the list Google gives it.
          gscSiteUrl: gsc.override || null,
        },
      });
      onAdded();
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  };

  return (
    <Modal title="Add project" onClose={onClose} wide>
      <p className="text-sm text-stone-500 mb-4">One website or client you're doing SEO for.</p>

      <label className="block text-xs font-semibold uppercase tracking-wider text-stone-400 mb-1.5">
        Project name
      </label>
      <input
        value={name}
        onChange={(e) => setName(e.target.value)}
        onKeyDown={(e) => e.key === "Enter" && submit()}
        placeholder="e.g. Sattva Connect"
        autoFocus
        className={INPUT_CLS}
      />

      <label className="block text-xs font-semibold uppercase tracking-wider text-stone-400 mb-1.5 mt-4">
        Client name <span className="normal-case font-normal">(optional)</span>
      </label>
      <input
        value={clientName}
        onChange={(e) => setClientName(e.target.value)}
        onKeyDown={(e) => e.key === "Enter" && submit()}
        placeholder="e.g. John Jacobs"
        className={INPUT_CLS}
      />
      <p className="text-xs text-stone-400 mt-2">Who the work is for — the person or company behind this project.</p>

      <label className="block text-xs font-semibold uppercase tracking-wider text-stone-400 mb-1.5 mt-4">
        Website domain <span className="normal-case font-normal">(optional)</span>
      </label>
      <input
        value={domain}
        onChange={(e) => setDomain(e.target.value)}
        onKeyDown={(e) => e.key === "Enter" && submit()}
        placeholder="e.g. sattvaconnect.com"
        className={INPUT_CLS}
      />
      <p className="text-xs text-stone-400 mt-2">The client's website — used for Moz Authority, Search Console and Analytics.</p>

      <GscPropertyField gsc={gsc} />

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

      {/* Was set on failure and never rendered, so "Create project" spun, stopped,
          and nothing happened — server validation was invisible. */}
      <ErrorNote>{error}</ErrorNote>

      <button onClick={submit} disabled={!name.trim() || busy} className={`${BTN_PRIMARY} w-full mt-4 py-2.5`}>
        {busy ? <LoaderCircle size={15} className="animate-spin" /> : "Create project"}
      </button>
    </Modal>
  );
}

function EditProjectModal({ project, onClose, onSaved }) {
  const [clientName, setClientName] = useState(project.clientName || "");
  const [domain, setDomain] = useState(project.domain || "");
  const [gaPropertyId, setGaPropertyId] = useState(project.gaPropertyId || "");
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  // Seeded with what's stored: if the saved property isn't what this domain
  // resolves to, that's a deliberate override and reopening the dialog must not
  // quietly replace it.
  const gsc = useGscProperty(domain, project.gscSiteUrl || "");

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      await api(`/projects/${project.id}`, {
        method: "PATCH",
        body: {
          clientName: clientName.trim() || null,
          domain: domain.trim() || null,
          gaPropertyId: gaPropertyId.trim() || null,
          gscSiteUrl: gsc.override || null,
        },
      });
      onSaved();
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  };

  return (
    <Modal title="Edit project" onClose={onClose} wide>
      <p className="text-sm text-stone-500 mb-4">
        Settings for <span className="font-medium text-stone-800">{project.name}</span>.
      </p>

      <label className="block text-xs font-semibold uppercase tracking-wider text-stone-400 mb-1.5">
        Client name <span className="normal-case font-normal">(optional)</span>
      </label>
      <input
        value={clientName}
        onChange={(e) => setClientName(e.target.value)}
        onKeyDown={(e) => e.key === "Enter" && submit()}
        placeholder="e.g. John Jacobs"
        autoFocus
        className={INPUT_CLS}
      />
      <p className="text-xs text-stone-400 mt-2">Who the work is for — the person or company behind this project.</p>

      <label className="block text-xs font-semibold uppercase tracking-wider text-stone-400 mb-1.5 mt-4">
        Website domain <span className="normal-case font-normal">(optional)</span>
      </label>
      <input
        value={domain}
        onChange={(e) => setDomain(e.target.value)}
        onKeyDown={(e) => e.key === "Enter" && submit()}
        placeholder="e.g. sattvaconnect.com"
        className={INPUT_CLS}
      />
      <p className="text-xs text-stone-400 mt-2">The client's website — used for Moz Authority, Search Console and Analytics.</p>

      <GscPropertyField gsc={gsc} />

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

      {/* Its own endpoint and its own save button — a rejected address here
          shouldn't stop you changing the domain above. */}
      <div className="mt-5">
        <ProjectRecipients projectId={project.id} />
      </div>

      <ErrorNote>{error}</ErrorNote>
      <button onClick={submit} disabled={busy} className={`${BTN_PRIMARY} w-full mt-4 py-2.5`}>
        {busy ? <LoaderCircle size={15} className="animate-spin" /> : "Save changes"}
      </button>
    </Modal>
  );
}
