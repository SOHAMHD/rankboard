/* ════════════════════════════════════════════════════════════════════
   PEOPLE (ADMIN PANEL) — reachable from the top bar by anyone whose
   permissions include manageUsers (today: Super Admin only). The
   server gates every /api/users route with the same permission.
   ════════════════════════════════════════════════════════════════════ */
import { Fragment, useEffect, useState } from "react";
import {
  Check,
  ChevronLeft,
  FolderCog,
  LoaderCircle,
  Mail,
  Send,
  Trash2,
  UserPlus,
} from "lucide-react";
import { api } from "../api";
import {
  TopBar,
  Modal,
  ErrorNote,
  ROLES,
  ROLE_DESCRIPTIONS,
  roleLabel,
  INPUT_CLS,
  BTN_PRIMARY,
  BTN_GHOST,
} from "../ui";

export function AdminPanelView({ user, onBack, onLogout }) {
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [showWizard, setShowWizard] = useState(false);
  const [emailModal, setEmailModal] = useState(null);
  const [confirmId, setConfirmId] = useState(null);
  const [manageUser, setManageUser] = useState(null); // Client whose projects are being edited

  const refresh = async () => {
    try {
      const d = await api("/users");
      setUsers(d.users);
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

  const changeRole = async (id, role) => {
    try {
      await api(`/users/${id}`, { method: "PATCH", body: { role } });
      await refresh();
    } catch (err) {
      setError(err.message);
    }
  };

  const removeUser = async (id) => {
    try {
      await api(`/users/${id}`, { method: "DELETE" });
      setConfirmId(null);
      await refresh();
    } catch (err) {
      setError(err.message);
    }
  };

  const resendInvite = async (id) => {
    try {
      const d = await api(`/users/${id}/resend-invite`, { method: "POST" });
      setEmailModal(d.email); // contains the NEW temp password
    } catch (err) {
      setError(err.message);
    }
  };

  const invitedCount = users.filter((u) => u.status === "invited").length;

  return (
    <div className="min-h-screen bg-stone-100">
      <TopBar user={user} onLogout={onLogout} onHome={onBack} />

      <main className="max-w-4xl mx-auto px-4 sm:px-6 py-8 sm:py-10">
        <button
          onClick={onBack}
          className="flex items-center gap-1 text-xs text-stone-500 hover:text-stone-800 mb-4 transition-colors"
        >
          <ChevronLeft size={14} /> Back to projects
        </button>

        <div className="flex flex-wrap items-end justify-between gap-4 mb-6">
          <div>
            <h1 className="text-2xl font-bold text-stone-900 tracking-tight font-display">People</h1>
            <p className="text-sm text-stone-500 mt-0.5">
              {users.length} total · {invitedCount} invited, waiting on first sign-in
            </p>
          </div>
          <button onClick={() => setShowWizard(true)} className={`${BTN_PRIMARY} px-4 py-2`}>
            <UserPlus size={16} /> Onboard someone
          </button>
        </div>

        <ErrorNote>{error}</ErrorNote>

        {loading ? (
          <div className="py-20 flex justify-center">
            <LoaderCircle size={22} className="text-orange-600 animate-spin" />
          </div>
        ) : (
          <div className="bg-white rounded-xl border border-stone-200 overflow-x-auto mt-2">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs uppercase tracking-wider text-stone-400 border-b border-stone-200">
                  <th className="px-5 py-3 font-medium">Person</th>
                  <th className="px-5 py-3 font-medium">Role</th>
                  <th className="px-5 py-3 font-medium">Status</th>
                  <th className="px-5 py-3 font-medium">Added</th>
                  <th className="px-2 py-3" />
                </tr>
              </thead>
              <tbody className="divide-y divide-stone-100">
                {users.map((u) => {
                  const isSelf = u.id === user.id;
                  return (
                    <tr key={u.id} className="hover:bg-stone-50">
                      <td className="px-5 py-3">
                        <span className="flex items-center gap-2.5">
                          <span className="h-8 w-8 rounded-full bg-slate-900 text-white flex items-center justify-center text-xs font-semibold shrink-0">
                            {u.name.charAt(0)}
                          </span>
                          <span className="min-w-0">
                            <span className="flex items-center gap-2 font-medium text-stone-800">
                              {u.name}
                              {isSelf && (
                                <span className="text-xs font-medium px-1.5 py-0.5 rounded bg-orange-100 text-orange-700">
                                  You
                                </span>
                              )}
                            </span>
                            <span className="block text-xs text-stone-400 font-data truncate">{u.email}</span>
                          </span>
                        </span>
                      </td>
                      <td className="px-5 py-3">
                        <select
                          value={u.role}
                          disabled={isSelf}
                          title={isSelf ? "You can't change your own role" : "Change role"}
                          onChange={(e) => changeRole(u.id, e.target.value)}
                          className="text-xs font-medium rounded-md border border-stone-200 bg-white px-2 py-1.5 text-stone-700 focus:outline-none focus:ring-2 focus:ring-orange-500 disabled:opacity-50 disabled:cursor-not-allowed"
                        >
                          {ROLES.map((r) => (
                            <option key={r} value={r}>
                              {roleLabel(r)}
                            </option>
                          ))}
                        </select>
                      </td>
                      <td className="px-5 py-3">
                        <span
                          className={`text-xs font-medium px-2 py-0.5 rounded-full ${
                            u.status === "active" ? "bg-emerald-100 text-emerald-700" : "bg-amber-100 text-amber-700"
                          }`}
                        >
                          {u.status === "active" ? "Active" : "Invited"}
                        </span>
                      </td>
                      <td className="px-5 py-3 text-stone-400 text-xs whitespace-nowrap">{u.createdAt?.slice(0, 10)}</td>
                      <td className="px-3 py-3">
                        <span className="flex items-center justify-end gap-1">
                          {u.role === "Client" && (
                            <button
                              onClick={() => setManageUser(u)}
                              title="Manage assigned projects"
                              aria-label={`Manage projects for ${u.name}`}
                              className="flex items-center gap-1 px-2 py-1 rounded-md text-xs font-medium text-stone-500 hover:text-stone-800 hover:bg-stone-100 transition-colors"
                            >
                              <FolderCog size={15} />
                              {u.projectIds?.length || 0}
                            </button>
                          )}
                          {u.status === "invited" && (
                            <button
                              onClick={() => resendInvite(u.id)}
                              title="Resend invite (generates a new temporary password)"
                              aria-label={`Resend invite to ${u.name}`}
                              className="p-1.5 rounded-md text-stone-400 hover:text-stone-700 hover:bg-stone-100 transition-colors"
                            >
                              <Mail size={15} />
                            </button>
                          )}
                          {!isSelf &&
                            (confirmId === u.id ? (
                              <button
                                onClick={() => removeUser(u.id)}
                                className="text-xs font-semibold text-white bg-red-500 hover:bg-red-600 px-2.5 py-1 rounded-md transition-colors whitespace-nowrap"
                              >
                                Confirm
                              </button>
                            ) : (
                              <button
                                onClick={() => setConfirmId(u.id)}
                                title="Remove person"
                                aria-label={`Remove ${u.name}`}
                                className="p-1.5 rounded-md text-stone-300 hover:text-red-500 hover:bg-red-50 transition-colors"
                              >
                                <Trash2 size={15} />
                              </button>
                            ))}
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}

        <p className="text-xs text-stone-400 mt-4">
          Invited people sign in with the temporary password from their invite email, then set their own. Resending an
          invite generates a fresh temporary password — the old one can't be recovered because only its hash is stored.
        </p>
      </main>

      {showWizard && <OnboardWizard onClose={() => setShowWizard(false)} onCreated={refresh} />}

      {manageUser && (
        <ManageProjectsModal user={manageUser} onClose={() => setManageUser(null)} onSaved={refresh} />
      )}

      {emailModal && (
        <Modal title="Invite email" onClose={() => setEmailModal(null)} wide>
          <EmailPreview email={emailModal} />
        </Modal>
      )}
    </div>
  );
}

/* ── Shared project picker: a scrollable checkbox list of projects.
   Reused by the onboarding wizard and the "Manage projects" modal so the
   two stay visually identical. `selected` is a Set of project ids. ── */

function ProjectChecklist({ projects, selected, onToggle, loading }) {
  if (loading) {
    return (
      <div className="py-8 flex justify-center">
        <LoaderCircle size={20} className="text-orange-600 animate-spin" />
      </div>
    );
  }
  if (!projects.length) {
    return (
      <p className="text-sm text-stone-500 rounded-xl border border-stone-200 px-4 py-6 text-center">
        No projects exist yet. Create one first, then assign it here.
      </p>
    );
  }
  return (
    <div className="max-h-64 overflow-y-auto rounded-xl border border-stone-200 divide-y divide-stone-100">
      {projects.map((p) => {
        const checked = selected.has(p.id);
        return (
          <label
            key={p.id}
            className="flex items-center gap-3 px-4 py-3 cursor-pointer hover:bg-stone-50 transition-colors"
          >
            {/* Native control kept for keyboard/AT; the square below is the visual. */}
            <input
              type="checkbox"
              checked={checked}
              onChange={() => onToggle(p.id)}
              className="sr-only peer"
            />
            <span
              className={`h-5 w-5 shrink-0 rounded-md border flex items-center justify-center transition-colors peer-focus-visible:ring-2 peer-focus-visible:ring-orange-500 peer-focus-visible:ring-offset-1 ${
                checked ? "bg-orange-600 border-orange-600 text-white" : "bg-white border-stone-300"
              }`}
            >
              {checked && <Check size={13} strokeWidth={3} />}
            </span>
            <span className="min-w-0">
              <span className="block text-sm font-medium text-stone-800 truncate">{p.name}</span>
              {p.domain && <span className="block text-xs text-stone-400 font-data truncate">{p.domain}</span>}
            </span>
          </label>
        );
      })}
    </div>
  );
}

/* ── Manage projects: edit an existing client's assignments. Loads all
   projects, pre-checks the client's current set (from GET /api/users), and
   PATCHes the chosen set as a full replacement. ── */

function ManageProjectsModal({ user, onClose, onSaved }) {
  const [projects, setProjects] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState(new Set(user.projectIds || []));
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const d = await api("/projects");
        setProjects(d.projects);
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const toggleProject = (id) =>
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const save = async () => {
    setBusy(true);
    setError(null);
    try {
      await api(`/users/${user.id}`, { method: "PATCH", body: { project_ids: [...selected] } });
      onSaved();
      onClose();
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  };

  return (
    <Modal title="Manage projects" onClose={onClose} wide>
      <p className="text-sm text-stone-500 -mt-0.5 mb-4">
        {user.name} · <span className="text-stone-400">{user.role}</span>
      </p>
      <p className="text-xs font-medium text-stone-400 mb-2">
        {selected.size} of {projects.length} assigned
      </p>
      <ProjectChecklist projects={projects} selected={selected} onToggle={toggleProject} loading={loading} />
      <ErrorNote>{error}</ErrorNote>
      <div className="flex justify-end gap-2 mt-5">
        <button onClick={onClose} className={`${BTN_GHOST} px-4 py-2.5`}>
          Cancel
        </button>
        <button onClick={save} disabled={busy || loading} className={`${BTN_PRIMARY} px-5 py-2.5`}>
          {busy ? <LoaderCircle size={15} className="animate-spin" /> : "Save"}
        </button>
      </div>
    </Modal>
  );
}

/* ── Onboarding wizard: add person → choose role → [Client: pick
   projects] → send invite. The project step is inserted into the flow
   only when the chosen role is "Client". ── */

const STEP_LABELS = {
  details: "Details",
  role: "Role",
  projects: "Projects",
  review: "Review",
};

function OnboardWizard({ onClose, onCreated }) {
  const [step, setStep] = useState("details"); // details | role | projects | review | sent
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [role, setRole] = useState("Team");
  const [projects, setProjects] = useState([]);
  const [projectsLoading, setProjectsLoading] = useState(true);
  const [selected, setSelected] = useState(new Set()); // project ids
  const [sentEmail, setSentEmail] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  // Load the project list once up front so the Client step is instant.
  useEffect(() => {
    (async () => {
      try {
        const d = await api("/projects");
        setProjects(d.projects);
      } catch {
        // Non-fatal: the picker simply shows "no projects" on failure.
      } finally {
        setProjectsLoading(false);
      }
    })();
  }, []);

  const isClient = role === "Client";
  // The project step only exists in the Client flow.
  const flow = isClient ? ["details", "role", "projects", "review"] : ["details", "role", "review"];
  const stepIndex = flow.indexOf(step);

  const toggleProject = (id) =>
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const nextFromDetails = () => {
    if (!name.trim()) return setError("Please enter their full name.");
    if (!/\S+@\S+\.\S+/.test(email.trim())) return setError("That doesn't look like a valid email address.");
    setError(null);
    setStep("role");
  };

  const send = async () => {
    setBusy(true);
    setError(null);
    try {
      const d = await api("/users", {
        method: "POST",
        body: {
          name: name.trim(),
          email: email.trim(),
          role,
          // Only Clients carry assignments; staff roles send none.
          project_ids: isClient ? [...selected] : [],
        },
      });
      setSentEmail(d.email);
      setStep("sent");
      onCreated();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal title={step === "sent" ? "Invite sent" : "Onboard someone"} onClose={onClose} wide>
      {step !== "sent" && (
        <div className="flex items-center mb-6 mt-1">
          {flow.map((key, i) => {
            const done = i < stepIndex;
            const current = i === stepIndex;
            return (
              <Fragment key={key}>
                <div className="flex items-center gap-1.5">
                  <span
                    className={`h-6 w-6 rounded-full flex items-center justify-center text-xs font-semibold transition-colors ${
                      done || current
                        ? "bg-orange-600 text-white"
                        : "border-2 border-stone-300 text-stone-400 bg-white"
                    }`}
                  >
                    {done ? <Check size={13} strokeWidth={3} /> : i + 1}
                  </span>
                  <span
                    className={`text-xs ${
                      current ? "font-semibold text-stone-900" : done ? "font-medium text-stone-600" : "font-medium text-stone-400"
                    }`}
                  >
                    {STEP_LABELS[key]}
                  </span>
                </div>
                {i < flow.length - 1 && (
                  <span className={`flex-1 h-px mx-2 ${done ? "bg-orange-300" : "bg-stone-200"}`} />
                )}
              </Fragment>
            );
          })}
        </div>
      )}

      {step === "details" && (
        <div>
          <label className="block text-xs font-semibold uppercase tracking-wider text-stone-400 mb-1.5">
            Full name
          </label>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. Kavya Nair"
            autoFocus
            className={`${INPUT_CLS} mb-4`}
          />
          <label className="block text-xs font-semibold uppercase tracking-wider text-stone-400 mb-1.5">
            Email address
          </label>
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && nextFromDetails()}
            placeholder="kavya@company.com"
            className={INPUT_CLS}
          />
          <ErrorNote>{error}</ErrorNote>
          <button onClick={nextFromDetails} className={`${BTN_PRIMARY} w-full mt-5 py-2.5`}>
            Next: choose role
          </button>
        </div>
      )}

      {step === "role" && (
        <div>
          <div className="space-y-2">
            {ROLES.map((r) => (
              <button
                key={r}
                onClick={() => setRole(r)}
                className={`w-full text-left p-3 rounded-xl border transition-colors focus:outline-none focus:ring-2 focus:ring-orange-500 ${
                  role === r ? "border-orange-500 bg-orange-50" : "border-stone-200 hover:border-stone-300"
                }`}
              >
                <span className="flex items-center justify-between">
                  <span className="text-sm font-semibold text-stone-900">{roleLabel(r)}</span>
                  <span
                    className={`h-4 w-4 rounded-full border-2 ${
                      role === r ? "border-orange-600 bg-orange-600" : "border-stone-300"
                    }`}
                  />
                </span>
                <span className="block text-xs text-stone-500 mt-0.5">{ROLE_DESCRIPTIONS[r]}</span>
              </button>
            ))}
          </div>
          <div className="flex gap-2 mt-5">
            <button onClick={() => setStep("details")} className={`${BTN_GHOST} px-4 py-2.5`}>
              <ChevronLeft size={15} /> Back
            </button>
            <button onClick={() => setStep(isClient ? "projects" : "review")} className={`${BTN_PRIMARY} flex-1 py-2.5`}>
              {isClient ? "Next: pick projects" : "Next: review"}
            </button>
          </div>
        </div>
      )}

      {step === "projects" && (
        <div>
          <h3 className="text-sm font-semibold text-stone-900">Which projects can this client see?</h3>
          <p className="text-xs text-stone-500 mt-0.5 mb-3">
            They'll only see the projects you select here — you can change this later.
          </p>
          <ProjectChecklist projects={projects} selected={selected} onToggle={toggleProject} loading={projectsLoading} />
          <p className="text-xs text-stone-400 mt-2">{selected.size} selected</p>
          <div className="flex justify-end gap-2 mt-5">
            <button onClick={() => setStep("role")} className={`${BTN_GHOST} px-4 py-2.5`}>
              <ChevronLeft size={15} /> Back
            </button>
            <button onClick={() => setStep("review")} className={`${BTN_PRIMARY} px-5 py-2.5`}>
              Next
            </button>
          </div>
        </div>
      )}

      {step === "review" && (
        <div>
          <div className="rounded-xl border border-stone-200 divide-y divide-stone-100 text-sm">
            <div className="px-4 py-2.5 flex justify-between gap-4">
              <span className="text-stone-400">Name</span>
              <span className="font-medium text-stone-800 text-right">{name.trim()}</span>
            </div>
            <div className="px-4 py-2.5 flex justify-between gap-4">
              <span className="text-stone-400">Email</span>
              <span className="font-data text-stone-800 text-right">{email.trim()}</span>
            </div>
            <div className="px-4 py-2.5 flex justify-between gap-4">
              <span className="text-stone-400">Role</span>
              <span className="font-medium text-stone-800 text-right">
                {roleLabel(role)}
              </span>
            </div>
            {isClient && (
              <div className="px-4 py-2.5 flex justify-between gap-4">
                <span className="text-stone-400">Projects</span>
                <span className="font-medium text-stone-800 text-right">
                  {selected.size === 0 ? "None" : `${selected.size} selected`}
                </span>
              </div>
            )}
          </div>
          <p className="text-xs text-stone-400 mt-3">
            Sending creates their account and emails them the website link, their email, and a temporary password
            generated by the server.
          </p>
          <ErrorNote>{error}</ErrorNote>
          <div className="flex gap-2 mt-4">
            <button onClick={() => setStep(isClient ? "projects" : "role")} className={`${BTN_GHOST} px-4 py-2.5`}>
              <ChevronLeft size={15} /> Back
            </button>
            <button onClick={send} disabled={busy} className={`${BTN_PRIMARY} flex-1 py-2.5`}>
              {busy ? <LoaderCircle size={15} className="animate-spin" /> : <><Send size={15} /> Create &amp; send invite</>}
            </button>
          </div>
        </div>
      )}

      {step === "sent" && sentEmail && (
        <div>
          <div className="flex items-center gap-2 text-sm text-emerald-700 bg-emerald-50 border border-emerald-100 rounded-lg px-3 py-2 mb-4">
            <Check size={15} /> Account created and invite sent.
          </div>
          <EmailPreview email={sentEmail} />
          <p className="text-xs text-stone-400 mt-3">
            This temporary password is shown once — only its hash is stored. If it's lost, use "resend invite" to
            generate a new one.
          </p>
          <button onClick={onClose} className={`${BTN_PRIMARY} w-full py-2.5 mt-4`}>
            Done
          </button>
        </div>
      )}
    </Modal>
  );
}

/* Renders an email record exactly as the server composed it. */
export function EmailPreview({ email }) {
  return (
    <div className="rounded-xl border border-stone-200 overflow-hidden">
      <div className="bg-stone-50 border-b border-stone-200 px-4 py-3 text-xs text-stone-500 space-y-1">
        <p className="flex items-center gap-1.5">
          <Mail size={13} className="text-stone-400" />
          <span className="font-medium text-stone-600">From:</span> RankBoard &lt;no-reply@rankboard.com&gt;
        </p>
        <p>
          <span className="font-medium text-stone-600">To:</span> <span className="font-data">{email.to_email}</span>
        </p>
        <p>
          <span className="font-medium text-stone-600">Subject:</span> {email.subject}
        </p>
      </div>
      <pre className="px-4 py-4 text-sm text-stone-700 whitespace-pre-wrap" style={{ fontFamily: "inherit" }}>
        {email.body}
      </pre>
    </div>
  );
}
