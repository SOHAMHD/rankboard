/* ════════════════════════════════════════════════════════════════════
   PROJECTS — the landing page after login. Every signed-in role sees
   the list (provisional); mutation buttons render only for roles the
   server granted them to, and the API re-checks regardless.
   ════════════════════════════════════════════════════════════════════ */
import { useEffect, useState } from "react";
import { LoaderCircle, Pencil, Plus, Trash2 } from "lucide-react";
import { api } from "../api";
import { filterLocal, listCountries, listRegions, locationsStatus, resolveLocation, searchCities } from "../locations";
import { TopBar, Modal, ErrorNote, SmartSearch, Toggle, can, INPUT_CLS, BTN_PRIMARY } from "../ui";

/* ── GEO PICKER ───────────────────────────────────────────────────────────────
   Where a project's rankings are checked, as three search-as-you-type inputs:
   Country → Region → City. Not dropdowns — the lists are every country, region
   and city DataForSEO supports (~100k rows), which no <select> can hold. Each
   keystroke queries our own `locations` table via /api/locations/search (see
   client/src/locations.js), and each input narrows the one below it.

   Region and city are optional; the project stores whichever is most specific,
   because city-level codes are what make local rankings accurate. All three
   empty = the server-wide default (RANK_LOCATION_CODE).                        */

// Best-effort country guess from a domain's TLD; null when there's no confident
// match (e.g. .com), so the caller leaves the current selection alone.
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
  // Matches ".au" and ".com.au" alike — we only look at how the host ends.
  const hit = Object.keys(TLD_COUNTRIES).find((tld) => d.endsWith(tld));
  return hit ? { ...TLD_COUNTRIES[hit], kind: "country" } : null;
}

// Three cascading SmartSearch inputs. State lives in the parent as three items
// ({ code, name } or null) so the form can submit the codes and show the names.
function LocationPicker({ country, region, city, onCountry, onRegion, onCity }) {
  const [status, setStatus] = useState(null);

  // Countries and the chosen country's regions are small enough to hold in
  // memory, so they are fetched ONCE and filtered in the browser: those two
  // inputs cost zero requests per keystroke. Cities stay server-side (116k rows).
  useEffect(() => {
    listCountries().catch(() => {});
    locationsStatus().then(setStatus).catch(() => setStatus(null));
  }, []);

  useEffect(() => {
    if (country) listRegions(country.code).catch(() => {});
  }, [country?.code]);

  // Suggestions carry the parent chain as the dimmed right-hand hint, so two
  // cities called Springfield are told apart at a glance.
  const decorate = (rows) =>
    rows.map((r) => ({
      ...r,
      hint:
        r.fullName && r.fullName !== r.name
          ? r.fullName.split(",").slice(1).join(", ").trim()
          : null,
    }));

  return (
    <div className="space-y-4">
      <SmartSearch
        label="Country"
        value={country}
        onChange={onCountry}
        debounceMs={0}
        onSearch={(q) => listCountries().then((rows) => decorate(filterLocal(rows, q)))}
        placeholder="Type a country — e.g. Aus…"
        emptyText="No country matches that."
        hint="Which Google to check in. Leave all three empty to use the server default."
      />

      <SmartSearch
        label="Region / State"
        optional
        value={region}
        onChange={onRegion}
        debounceMs={0}
        onSearch={(q) => listRegions(country?.code).then((rows) => decorate(filterLocal(rows, q)))}
        disabled={!country}
        disabledHint="Pick a country first"
        placeholder={`Type a region${country ? ` in ${country.name}` : ""}…`}
        emptyText={
          status && !status.imported
            ? "No regions loaded yet — run `python -m scripts.import_locations` on the server."
            : "No region matches that."
        }
        hint="Narrows the city list below, and can be the rank-check target on its own."
      />

      <SmartSearch
        label="City"
        optional
        value={city}
        onChange={onCity}
        onSearch={(q) =>
          searchCities(q, { country: country?.code, region: region?.code }).then(decorate)
        }
        disabled={!country}
        disabledHint="Pick a country first"
        placeholder={`Type a city${region ? ` in ${region.name}` : country ? ` in ${country.name}` : ""}…`}
        emptyText="No city matches that."
        hint="The most accurate target for local SEO — set it whenever the client is a local business."
      />
    </div>
  );
}

/* The picker's three values as one API payload. Sent on both create and update,
   so clearing a field genuinely clears it server-side. */
const geoBody = (country, region, city) => ({
  countryCode: country?.code ?? null,
  regionCode: region?.code ?? null,
  cityCode: city?.code ?? null,
});

/* Shared by both modals: hold the three picker values, seed the country from
   the domain's TLD until the user picks one by hand, and (when editing) load the
   saved code back into the three inputs. */
function useGeoPicker(project) {
  const [country, setCountry] = useState(null);
  const [region, setRegion] = useState(null);
  const [city, setCity] = useState(null);
  // A project that already HAS a target counts as touched from the start, so
  // editing its domain can never quietly overwrite a deliberate choice.
  const [touched, setTouched] = useState(project?.locationCode != null);

  useEffect(() => {
    // Editing: one request turns the stored location_code back into the three
    // rows the inputs display. New project: nothing to load.
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
    setRegion(null); // a new country invalidates both narrower choices
    setCity(null);
  };
  const onRegion = (item) => {
    setTouched(true);
    setRegion(item);
    setCity(null); // ditto: the city must sit inside the chosen region
  };
  const onCity = (item) => {
    setTouched(true);
    setCity(item);
  };

  // Pre-fill from the domain's TLD, unless the user has touched the picker.
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
    // Optimistic: flip the switch in the UI immediately, then persist in the
    // background. Only the `active` flag changes, so there's no need to re-fetch
    // the whole list — we just patch this project's row in local state. On
    // failure we revert and surface the error.
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
            <button onClick={() => setShowAdd(true)} className={`${BTN_PRIMARY} px-4 py-2 `}>
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
  // The server stores a ready-made label ("Australia · Western Australia ·
  // Perth"), so the card needs no lookup. Older rows may only have the code.
  const country = project.locationLabel || (project.locationCode ? `Code ${project.locationCode}` : null);

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
            project.active ? "bg-blue-100 text-blue-700" : "bg-stone-200 text-stone-500"
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
                title="Edit project (domain, location & integrations)"
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

      <ErrorNote>{error}</ErrorNote>
      <button onClick={submit} disabled={!name.trim() || busy} className={`${BTN_PRIMARY} w-full mt-4 py-2.5`}>
        {busy ? <LoaderCircle size={15} className="animate-spin" /> : "Create project"}
      </button>
    </Modal>
  );
}

function EditProjectModal({ project, onClose, onSaved }) {
  const [domain, setDomain] = useState(project.domain || "");
  const [gaPropertyId, setGaPropertyId] = useState(project.gaPropertyId || "");
  const [gscSiteUrl, setGscSiteUrl] = useState(project.gscSiteUrl || "");
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const geo = useGeoPicker(project); // loads the saved code back into the inputs

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
          domain: domain.trim() || null,
          // Always sent, so clearing the picker really does reset the project
          // to the server default (the old API ignored a null locationCode).
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

      <ErrorNote>{error}</ErrorNote>
      <button onClick={submit} disabled={busy} className={`${BTN_PRIMARY} w-full mt-4 py-2.5`}>
        {busy ? <LoaderCircle size={15} className="animate-spin" /> : "Save changes"}
      </button>
    </Modal>
  );
}
