import { memo, useCallback, useEffect, useState } from "react";
import { LoaderCircle, Pencil, Plus, Trash2 } from "lucide-react";
import { api } from "../api";
import {
  filterLocal,
  listCountries,
  listRegions,
  locationsStatus,
  resolveLocation,
  searchCities,
  searchRegions,
} from "../locations";
import { TopBar, Modal, ConfirmModal, ErrorNote, SmartSearch, Toggle, can, INPUT_CLS, BTN_PRIMARY } from "../ui";
import ProjectRecipients from "../lib/ProjectRecipients";

const TLD_COUNTRIES = {
  ".au": { code: 2036, name: "Australia" },
  ".in": { code: 2356, name: "India" },
  ".uk": { code: 2826, name: "United Kingdom" },
  ".ca": { code: 2124, name: "Canada" },
  ".ae": { code: 2784, name: "United Arab Emirates" },
  ".nz": { code: 2554, name: "New Zealand" },
  ".sg": { code: 2702, name: "Singapore" },
  ".za": { code: 2710, name: "South Africa" },
};

function countryFromDomain(domain) {
  const d = (domain || "").trim().toLowerCase();
  const hit = Object.keys(TLD_COUNTRIES).find((tld) => d.endsWith(tld));
  return hit ? { ...TLD_COUNTRIES[hit], kind: "country" } : null;
}

function LocationPicker({ country, region, city, onCountry, onRegion, onCity }) {
  const [status, setStatus] = useState(null);

  useEffect(() => {
    listCountries().catch(() => {});
    locationsStatus().then(setStatus).catch(() => setStatus(null));
  }, []);

  useEffect(() => {
    if (country) listRegions(country.code).catch(() => {});
  }, [country?.code]);

  const decorate = useCallback(
    (rows) =>
      rows.map((r) => ({
        ...r,
        hint:
          r.fullName && r.fullName !== r.name
            ? r.fullName.split(",").slice(1).join(", ").trim()
            : null,
      })),
    []
  );

  // These are stable so SmartSearch's debounce effect never holds a stale
  // closure. Previously a new function identity on every render meant that
  // changing the country while the region box was open kept filtering against
  // the old country until the next keystroke.
  const searchCountry = useCallback(
    (q) => listCountries().then((rows) => decorate(filterLocal(rows, q))),
    [decorate]
  );
  const searchRegion = useCallback(
    (q) => searchRegions(q, { country: country?.code }).then(decorate),
    [country?.code, decorate]
  );
  const searchCity = useCallback(
    (q) => searchCities(q, { country: country?.code, region: region?.code }).then(decorate),
    [country?.code, region?.code, decorate]
  );

  return (
    <div className="space-y-4">
      <SmartSearch
        label="Country"
        value={country}
        onChange={onCountry}
        debounceMs={0}
        onSearch={searchCountry}
        placeholder="Type a country — e.g. Aus…"
        emptyText="No country matches that."
        hint="Which Google to check in. Leave all three empty to use the server default."
      />

      <SmartSearch
        label="Region / State"
        optional
        value={region}
        onChange={onRegion}
        onSearch={searchRegion}
        disabled={!country}
        disabledHint="Pick a country first"
        placeholder={`Type a region${country ? ` in ${country.name}` : ""}…`}
        emptyText={
          status && !status.imported
            ? "No regions loaded yet — run `python -m scripts.import_locations` on the server."
            : "No region matches that."
        }
        hint="Narrows the city list below, and can be the project's location on its own."
      />

      <SmartSearch
        label="City"
        optional
        value={city}
        onChange={onCity}
        onSearch={searchCity}
        disabled={!country}
        disabledHint="Pick a country first"
        placeholder={`Type a city${region ? ` in ${region.name}` : country ? ` in ${country.name}` : ""}…`}
        emptyText="No city matches that."
        hint="The most accurate target for local SEO — set it whenever the client is a local business."
      />
    </div>
  );
}

const geoBody = (country, region, city) => ({
  countryCode: country?.code ?? null,
  regionCode: region?.code ?? null,
  cityCode: city?.code ?? null,
});

function useGeoPicker(project) {
  const [country, setCountry] = useState(null);
  const [region, setRegion] = useState(null);
  const [city, setCity] = useState(null);
  const [touched, setTouched] = useState(project?.locationCode != null);

  useEffect(() => {
    if (project?.locationCode == null) return;
    let live = true;
    resolveLocation(project.locationCode)
      .then((d) => {
        if (!live) return;
        setCountry(d.country);
        setRegion(d.region);
        setCity(d.city);
      })
      .catch(() => {});
    return () => {
      live = false;
    };
  }, [project?.locationCode]);

  const onCountry = (item) => {
    setTouched(true);
    setCountry(item);
    setRegion(null);
    setCity(null);
  };
  const onRegion = (item) => {
    setTouched(true);
    setRegion(item);
    setCity(null);
  };
  const onCity = (item) => {
    setTouched(true);
    setCity(item);
  };

  const guessFromDomain = (domain) => {
    if (touched) return;
    const guess = countryFromDomain(domain);
    if (guess) {
      setCountry(guess);
      setRegion(null);
      setCity(null);
    }
  };

  return { country, region, city, onCountry, onRegion, onCity, guessFromDomain };
}

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

function ProjectCard({ project, user, onOpen, onEdit, onToggle, onDelete }) {
  const showToggle = can(user, "toggleProject");
  const showEdit = can(user, "toggleProject");
  const showDelete = can(user, "deleteProject");
  const country = project.locationLabel || (project.locationCode ? `Code ${project.locationCode}` : null);

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
            {country ? `${country} · ` : ""}Added {project.createdAt?.slice(0, 10)}
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
  const [gscSiteUrl, setGscSiteUrl] = useState("");
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const geo = useGeoPicker(null);

  const onDomainChange = (val) => {
    setDomain(val);
    geo.guessFromDomain(val);
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
          clientName: clientName.trim() || null,
          domain: domain.trim() || null,
          ...geoBody(geo.country, geo.region, geo.city),
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
        onChange={(e) => onDomainChange(e.target.value)}
        onKeyDown={(e) => e.key === "Enter" && submit()}
        placeholder="e.g. sattvaconnect.com"
        className={INPUT_CLS}
      />
      <p className="text-xs text-stone-400 mt-2">The client's website — used for Moz Authority, Search Console and Analytics.</p>

      <div className="mt-4">
        <LocationPicker {...geo} />
      </div>

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
  const [gscSiteUrl, setGscSiteUrl] = useState(project.gscSiteUrl || "");
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const geo = useGeoPicker(project);

  const onDomainChange = (val) => {
    setDomain(val);
    geo.guessFromDomain(val);
  };

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      await api(`/projects/${project.id}`, {
        method: "PATCH",
        body: {
          clientName: clientName.trim() || null,
          domain: domain.trim() || null,
          ...geoBody(geo.country, geo.region, geo.city),
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
        onChange={(e) => onDomainChange(e.target.value)}
        onKeyDown={(e) => e.key === "Enter" && submit()}
        placeholder="e.g. sattvaconnect.com"
        className={INPUT_CLS}
      />
      <p className="text-xs text-stone-400 mt-2">The client's website — used for Moz Authority, Search Console and Analytics.</p>

      <div className="mt-4">
        <LocationPicker {...geo} />
      </div>

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
