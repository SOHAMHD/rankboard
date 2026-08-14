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
  ConfirmModal,
  ErrorNote,
  ROLES,
  CONTACT_ONLY,
  ROLE_DESCRIPTIONS,
  roleLabel,
  can,
  INPUT_CLS,
  BTN_PRIMARY,
  BTN_GHOST,
} from "../ui";
import AddressInput, { foldDraft, isEmail } from "../lib/AddressInput";
import { useToast } from "../toast.jsx";

export function AdminPanelView({ user, onBack, onEmailLog, onLogout }) {
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [showWizard, setShowWizard] = useState(false);
  const [emailModal, setEmailModal] = useState(null);
  // The whole user, so the dialog can name them and say what is removed.
  const [confirmUser, setConfirmUser] = useState(null);
  const [removing, setRemoving] = useState(false);
  const [manageUser, setManageUser] = useState(null);
  const canManage = can(user, "manageUsers");
  const toast = useToast();

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
      // The dropdown looks the same whether the change saved or silently didn't,
      // so say so — this one alters what somebody can do to every project.
      const who = users.find((u) => u.id === id);
      toast.success(
        `${who?.name || "This user"} is now ${roleLabel(role)}.`,
        { title: "Role updated" }
      );
    } catch (err) {
      setError(err.message);
    }
  };

  const removeUser = async (id) => {
    setRemoving(true);
    try {
      await api(`/users/${id}`, { method: "DELETE" });
      setConfirmUser(null);
      await refresh();
    } catch (err) {
      setError(err.message);
    } finally {
      setRemoving(false);
    }
  };

  const resendInvite = async (u) => {
    if (
      u.status === "active" &&
      !window.confirm(
        `${u.name} has already activated their account.\n\n` +
          "Resending will email a NEW temporary password and their current " +
          "password will stop working. They'll have to set a new one on next sign-in.\n\n" +
          "Continue?"
      )
    ) {
      return;
    }
    try {
      const d = await api(`/users/${u.id}/resend-invite`, { method: "POST" });
      setEmailModal(d.email);
    } catch (err) {
      setError(err.message);
    }
  };

  const invitedCount = users.filter((u) => u.status === "invited").length;

  return (
    <div className="min-h-screen bg-stone-100">
      <TopBar user={user} onLogout={onLogout} onHome={onBack} onEmailLog={onEmailLog} />

      {/* max-w-5xl, matching TopBar. At 4xl the five columns below — with a role
          <select> sized to its longest option — overflowed into a horizontal
          scrollbar that cut off the row actions. */}
      <main className="max-w-5xl mx-auto px-4 sm:px-6 py-8 sm:py-10">
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
          {canManage && (
            <button onClick={() => setShowWizard(true)} className={`${BTN_PRIMARY} px-4 py-2`}>
              <UserPlus size={16} /> Onboard someone
            </button>
          )}
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
                      {/* Capped and truncating: these are full work addresses,
                          and letting the column size to the longest one is what
                          pushed the actions off the right edge. */}
                      <td className="px-5 py-3 max-w-0 w-[45%]">
                        <span className="flex items-center gap-2.5">
                          <span className="h-8 w-8 rounded-full bg-slate-900 text-white flex items-center justify-center text-xs font-semibold shrink-0">
                            {u.name?.charAt(0) || "?"}
                          </span>
                          <span className="min-w-0">
                            <span className="flex items-center gap-2 font-medium text-stone-800 truncate">
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
                        {canManage ? (
                          /* Fixed width on the select below. A native select
                             sizes itself to its longest option, and "Client with
                             dashboard access" made every one of these ~250px
                             wide — the single biggest contributor to the table
                             overflowing. The open dropdown still shows each
                             label in full. */
                          <select
                            value={u.role}
                            disabled={isSelf}
                            title={isSelf ? "You can't change your own role" : "Change role"}
                            onChange={(e) => changeRole(u.id, e.target.value)}
                            className="w-40 text-xs font-medium rounded-md border border-stone-200 bg-white px-2 py-1.5 text-stone-700 focus:outline-none focus:ring-2 focus:ring-orange-500 disabled:opacity-50 disabled:cursor-not-allowed"
                          >
                            {ROLES.map((r) => (
                              <option key={r} value={r}>
                                {roleLabel(r)}
                              </option>
                            ))}
                          </select>
                        ) : (
                          <span className="text-sm font-medium text-stone-700">{roleLabel(u.role)}</span>
                        )}
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
                          {(u.role === "Team" || u.role === "Client") && (
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
                          {canManage && (
                            <button
                              onClick={() => resendInvite(u)}
                              title={
                                u.status === "active"
                                  ? "Re-send invite email — issues a NEW temporary password and invalidates their current one"
                                  : "Resend invite (generates a new temporary password)"
                              }
                              aria-label={`Resend invite to ${u.name}`}
                              className={`p-1.5 rounded-md transition-colors ${
                                u.status === "active"
                                  ? "text-stone-500 hover:text-amber-600 hover:bg-amber-50"
                                  : "text-stone-400 hover:text-stone-700 hover:bg-stone-100"
                              }`}
                            >
                              <Mail size={15} />
                            </button>
                          )}
                          {/* One click opens a dialog. This used to swap the trash
                              icon for a "Confirm" button in the same position, so
                              a double-click removed a person outright. */}
                          {canManage && !isSelf && (
                            <button
                              onClick={() => setConfirmUser(u)}
                              title="Remove person"
                              aria-label={`Remove ${u.name}`}
                              className="p-1.5 rounded-md text-stone-500 hover:text-red-500 hover:bg-red-50 transition-colors"
                            >
                              <Trash2 size={15} />
                            </button>
                          )}
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

      {canManage && showWizard && <OnboardWizard onClose={() => setShowWizard(false)} onCreated={refresh} />}

      {confirmUser && (
        <ConfirmModal
          title={`Remove ${confirmUser.name}?`}
          confirmLabel="Remove person"
          busy={removing}
          onCancel={() => setConfirmUser(null)}
          onConfirm={() => removeUser(confirmUser.id)}
        >
          <span className="block">
            {confirmUser.email} loses access immediately and any project assignments
            are cleared.
          </span>
          <span className="block mt-2">
            Reports and emails they created stay in the log, attributed to them.
          </span>
        </ConfirmModal>
      )}

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

function ProjectChecklist({ projects, selected, onToggle, loading, error }) {
  if (loading) {
    return (
      <div className="py-8 flex justify-center">
        <LoaderCircle size={20} className="text-orange-600 animate-spin" />
      </div>
    );
  }
  // Distinguish "couldn't load" from "none exist". Conflating them told the admin
  // there were no projects and let them finish the invite with no access granted.
  if (error) {
    return (
      <p className="text-sm text-red-600 rounded-xl border border-red-200 bg-red-50 px-4 py-6 text-center">
        Couldn&apos;t load the project list — {error} Close this and try again;
        don&apos;t send the invite until you can pick projects.
      </p>
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
            className="relative flex items-center gap-3 px-4 py-3 cursor-pointer hover:bg-stone-50 transition-colors"
          >
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
      <ProjectChecklist projects={projects} selected={selected} onToggle={toggleProject} loading={loading} error={error} />
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

const STEP_LABELS = {
  role: "Role",
  details: "Details",
  projects: "Projects",
  client: "Recipients",
  review: "Review",
};

/**
 * Step order per role.
 *
 * Role comes first so every later step is conditional on something already
 * known — asking for a name and email before the role meant those fields meant
 * subtly different things depending on an answer not yet given.
 *
 * CONTACT_ONLY has no `details` step: there is no login to name and no invite
 * to send. Their name and email are collected on the client step instead, where
 * they mean "who the report is addressed to" rather than "who signs in".
 */
const FLOWS = {
  "Super Admin": ["role", "details", "review"],
  "Admin": ["role", "details", "review"],
  "Team": ["role", "details", "projects", "review"],
  "Client": ["role", "details", "projects", "client", "review"],
  [CONTACT_ONLY]: ["role", "projects", "client", "review"],
};

const blankRecipients = () => ({ clientName: "", useLogin: true, primary: "", cc: [] });

function OnboardWizard({ onClose, onCreated }) {
  const [step, setStep] = useState("role");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [role, setRole] = useState("Team");
  const [projects, setProjects] = useState([]);
  const [projectsLoading, setProjectsLoading] = useState(true);
  const [selected, setSelected] = useState(new Set());
  const [sentEmail, setSentEmail] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  // Recipients are keyed by project id, because project_recipients is. Selecting
  // three projects means three separate lists, not one list copied three times —
  // copies would drift the first time someone edited one of them.
  const [recipients, setRecipients] = useState({});
  const [ccDraft, setCcDraft] = useState("");
  const [clientIndex, setClientIndex] = useState(0);

  // Was `catch {}`. On a network failure `projects` stayed empty and the
  // checklist rendered "No projects exist yet. Create one first" — a factual lie,
  // after which the admin sent the invite with no project access.
  const [projectsError, setProjectsError] = useState(null);

  useEffect(() => {
    (async () => {
      try {
        const d = await api("/projects");
        setProjects(d.projects);
        setProjectsError(null);
      } catch (err) {
        setProjectsError(err.message);
      } finally {
        setProjectsLoading(false);
      }
    })();
  }, []);

  const isContactOnly = role === CONTACT_ONLY;
  const isScoped = role === "Client" || role === "Team" || isContactOnly;
  const flow = FLOWS[role] || FLOWS.Team;
  const stepIndex = flow.indexOf(step);

  const selectedIds = [...selected];
  const clientProjectId = selectedIds[clientIndex];
  const clientProject = projects.find((p) => p.id === clientProjectId);
  const current = recipients[clientProjectId] || blankRecipients();

  const patchCurrent = (patch) =>
    setRecipients((prev) => ({
      ...prev,
      [clientProjectId]: { ...(prev[clientProjectId] || blankRecipients()), ...patch },
    }));

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
    setStep(flow[flow.indexOf("details") + 1]);
  };

  /** Seed the client step from the project and, for a login client, their email. */
  const enterClientStep = () => {
    if (selectedIds.length === 0) {
      return setError(
        isContactOnly
          ? "Pick the project whose reports they should receive."
          : "Pick at least one project before setting up recipients."
      );
    }
    setError(null);
    setCcDraft("");
    setRecipients((prev) => {
      const next = { ...prev };
      for (const pid of selectedIds) {
        if (next[pid]) continue;
        const proj = projects.find((p) => p.id === pid);
        next[pid] = {
          ...blankRecipients(),
          clientName: proj?.clientName || "",
          // A login client's address is usually the right default; contact-only
          // has no login, so there is nothing to prefill from.
          useLogin: !isContactOnly,
          primary: isContactOnly ? "" : email.trim(),
        };
      }
      return next;
    });
    setClientIndex(0);
    setStep("client");
  };

  /** The address that will actually be saved as primary for the current project. */
  const effectivePrimary = () =>
    (current.useLogin && !isContactOnly ? email.trim() : current.primary.trim());

  const nextFromClient = () => {
    const folded = foldDraft(current.cc, ccDraft, [effectivePrimary()]);
    if (folded.error) return setError(folded.error);
    if (folded.values !== current.cc) patchCurrent({ cc: folded.values });
    setCcDraft("");

    const primary = effectivePrimary();
    if (!primary) {
      return setError(
        isContactOnly
          ? "Enter the address their reports should go to."
          : "Enter a primary report address, or tick \"same as their login\"."
      );
    }
    if (!isEmail(primary)) return setError(`Not a valid email: ${primary}`);
    if (isContactOnly && !current.clientName.trim()) {
      return setError("Enter the client's name — it's used in the report greeting.");
    }

    setError(null);
    if (clientIndex < selectedIds.length - 1) {
      setClientIndex(clientIndex + 1);
      setCcDraft("");
    } else {
      setStep("review");
    }
  };

  /** Leave this project without saving anything for it. */
  const skipClientStep = () => {
    setError(null);
    setRecipients((prev) => {
      const next = { ...prev };
      delete next[clientProjectId];
      return next;
    });
    setCcDraft("");
    if (clientIndex < selectedIds.length - 1) setClientIndex(clientIndex + 1);
    else setStep("review");
  };

  const backFromClient = () => {
    setError(null);
    setCcDraft("");
    if (clientIndex > 0) setClientIndex(clientIndex - 1);
    else setStep("projects");
  };

  /** Only projects the user actually filled in get written. */
  const recipientPayload = () =>
    selectedIds
      .filter((pid) => {
        const r = recipients[pid];
        return r && (r.useLogin ? email.trim() : r.primary.trim());
      })
      .map((pid) => {
        const r = recipients[pid];
        return {
          projectId: pid,
          clientName: r.clientName.trim() || undefined,
          primaryEmail: (r.useLogin && !isContactOnly ? email.trim() : r.primary.trim()),
          ccEmails: r.cc,
        };
      });

  /**
   * Contact-only path: no user account, no invite.
   *
   * Writes straight to the endpoints that already exist — the recipients upsert
   * and, where the project has no client name yet, a project patch. Nothing
   * touches the `users` table, so nobody gets a password they never asked for.
   */
  const saveContactOnly = async () => {
    setBusy(true);
    setError(null);
    try {
      for (const r of recipientPayload()) {
        await api(`/projects/${r.projectId}/recipients`, {
          method: "PUT",
          body: { primaryEmail: r.primaryEmail, ccEmails: r.ccEmails },
        });
        const proj = projects.find((p) => p.id === r.projectId);
        if (r.clientName && r.clientName !== proj?.clientName) {
          await api(`/projects/${r.projectId}`, {
            method: "PATCH",
            body: { clientName: r.clientName },
          });
        }
      }
      setSentEmail(null);
      setStep("sent");
      onCreated();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const send = async () => {
    if (isContactOnly) return saveContactOnly();

    setBusy(true);
    setError(null);
    try {
      const d = await api("/users", {
        method: "POST",
        body: {
          name: name.trim(),
          email: email.trim(),
          role,
          project_ids: isScoped ? selectedIds : [],
          // The server writes these in the same transaction as the user, then
          // sends the invite last — so a failure here can't leave someone
          // holding a password for a half-built account.
          recipients: role === "Client" ? recipientPayload() : [],
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
    // dismissOnBackdrop={false}: this is a multi-step form, and a stray click on
    // the backdrop used to discard the name, email, project selection and every
    // per-project recipient list with no confirmation.
    <Modal
      title={step === "sent" ? (sentEmail ? "Invite sent" : "Recipients saved") : "Onboard someone"}
      onClose={onClose}
      wide
      dismissOnBackdrop={step === "sent"}
    >
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
          <label htmlFor="onboard-name" className="block text-xs font-semibold uppercase tracking-wider text-stone-400 mb-1.5">
            Full name
          </label>
          <input
            id="onboard-name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. Kavya Nair"
            autoFocus
            className={`${INPUT_CLS} mb-4`}
          />
          <label htmlFor="onboard-email" className="block text-xs font-semibold uppercase tracking-wider text-stone-400 mb-1.5">
            Email address
          </label>
          <input
            id="onboard-email"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && nextFromDetails()}
            placeholder="kavya@company.com"
            className={INPUT_CLS}
          />
          <ErrorNote>{error}</ErrorNote>
          <button onClick={nextFromDetails} className={`${BTN_PRIMARY} w-full mt-5 py-2.5`}>
            {flow[flow.indexOf("details") + 1] === "projects" ? "Next: pick projects" : "Next: review"}
          </button>
        </div>
      )}

      {step === "role" && (
        <div>
          <h3 className="text-sm font-semibold text-stone-900 mb-0.5">What kind of access do they need?</h3>
          <p className="text-xs text-stone-500 mb-3">
            This decides what we ask for next.
          </p>
          <div className="space-y-2">
            {/*
              ROLES, not ONBOARD_ROLES — the "Client contact only" pseudo-role is
              deliberately no longer offered. The wizard still knows how to handle
              it (FLOWS, saveContactOnly, the isContactOnly branches below), so
              putting it back is a one-word change here; it just isn't a choice
              anyone can make. Contacts who should receive reports without an
              account are set up per project instead, through the recipients
              dialog backed by GET/PUT /api/projects/{id}/recipients.
            */}
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
          <ErrorNote>{error}</ErrorNote>
          <div className="flex gap-2 mt-5">
            <button onClick={onClose} className={`${BTN_GHOST} px-4 py-2.5`}>
              Cancel
            </button>
            <button
              onClick={() => {
                setError(null);
                setStep(flow[1]);
              }}
              className={`${BTN_PRIMARY} flex-1 py-2.5`}
            >
              {flow[1] === "details" ? "Next: their details" : "Next: pick projects"}
            </button>
          </div>
        </div>
      )}

      {step === "client" && (
        <div>
          {selectedIds.length > 1 && (
            <div className="flex items-center gap-2 rounded-lg bg-stone-50 border border-stone-200 px-3 py-2 mb-4 text-xs">
              <FolderCog size={14} className="text-stone-400 shrink-0" />
              <span className="text-stone-500">Project</span>
              <span className="font-medium text-stone-800 truncate">{clientProject?.name}</span>
              <span className="ml-auto text-stone-400 shrink-0">
                {clientIndex + 1} of {selectedIds.length}
              </span>
            </div>
          )}
          {selectedIds.length === 1 && (
            <p className="text-xs text-stone-500 mb-4">
              Reports for <span className="font-medium text-stone-700">{clientProject?.name}</span>
            </p>
          )}

          <label htmlFor="onboard-client-name" className="block text-xs font-semibold uppercase tracking-wider text-stone-400 mb-1.5">
            Client name
          </label>
          <input
            id="onboard-client-name"
            value={current.clientName}
            onChange={(e) => patchCurrent({ clientName: e.target.value })}
            placeholder="e.g. Dr. Anuranjan"
            className={INPUT_CLS}
          />
          <p className="text-[11px] text-stone-400 mt-1">
            Used in the report greeting and subject line.
            {clientProject?.clientName ? ` Currently "${clientProject.clientName}".` : ""}
          </p>

          <label htmlFor="onboard-primary-email" className="block text-xs font-semibold uppercase tracking-wider text-stone-400 mt-4 mb-1.5">
            Primary report email
          </label>
          {!isContactOnly && (
            <label className="flex items-center gap-2 text-sm text-stone-700 mb-2 cursor-pointer">
              <input
                type="checkbox"
                checked={current.useLogin}
                onChange={(e) => patchCurrent({ useLogin: e.target.checked })}
                className="h-4 w-4 accent-orange-600"
              />
              Same as their login — <span className="font-data">{email.trim() || "not set"}</span>
            </label>
          )}
          {(isContactOnly || !current.useLogin) && (
            <input
              id="onboard-primary-email"
              type="email"
              value={current.primary}
              onChange={(e) => patchCurrent({ primary: e.target.value })}
              placeholder="accounts@company.com"
              className={INPUT_CLS}
            />
          )}

          <label htmlFor="onboard-cc" className="block text-xs font-semibold uppercase tracking-wider text-stone-400 mt-4 mb-1.5">
            Cc <span className="normal-case tracking-normal font-normal text-stone-400">(optional)</span>
          </label>
          <AddressInput
            id="onboard-cc"
            values={current.cc}
            onChange={(v) => patchCurrent({ cc: v })}
            draft={ccDraft}
            onDraftChange={setCcDraft}
            taken={[effectivePrimary()].filter(Boolean)}
            placeholder="colleague@company.com"
            onError={setError}
          />

          <p className="text-[11px] text-stone-500 bg-stone-50 border border-stone-200 rounded-lg px-2.5 py-2 mt-3 flex gap-1.5">
            <Mail size={13} className="shrink-0 mt-0.5 text-stone-400" />
            <span>
              These people receive the report PDF. They do not get an account and cannot sign in.
            </span>
          </p>

          <ErrorNote>{error}</ErrorNote>

          <div className="flex items-center gap-2 mt-5">
            <button onClick={skipClientStep} className={`${BTN_GHOST} px-3 py-2.5 mr-auto`}>
              Skip for now
            </button>
            <button onClick={backFromClient} className={`${BTN_GHOST} px-4 py-2.5`}>
              <ChevronLeft size={15} /> Back
            </button>
            <button onClick={nextFromClient} className={`${BTN_PRIMARY} px-5 py-2.5`}>
              {clientIndex < selectedIds.length - 1 ? "Next project" : "Next: review"}
            </button>
          </div>
        </div>
      )}

      {step === "projects" && (
        <div>
          <h3 className="text-sm font-semibold text-stone-900">
            {isContactOnly ? "Whose reports should they receive?" : "Which projects can this person see?"}
          </h3>
          <p className="text-xs text-stone-500 mt-0.5 mb-3">
            {isContactOnly
              ? "You'll set the addresses for each project you pick — you can change them later."
              : "They'll only see the projects you select here — you can change this later."}
          </p>
          <ProjectChecklist
            projects={projects}
            selected={selected}
            onToggle={toggleProject}
            loading={projectsLoading}
            error={projectsError}
          />
          <p className="text-xs text-stone-500 mt-2">{selected.size} selected</p>
          <ErrorNote>{error}</ErrorNote>
          <div className="flex justify-end gap-2 mt-5">
            <button
              onClick={() => {
                setError(null);
                setStep(flow[flow.indexOf("projects") - 1]);
              }}
              className={`${BTN_GHOST} px-4 py-2.5`}
            >
              <ChevronLeft size={15} /> Back
            </button>
            <button
              onClick={() => {
                if (flow.includes("client")) return enterClientStep();
                setError(null);
                setStep("review");
              }}
              className={`${BTN_PRIMARY} px-5 py-2.5`}
            >
              {flow.includes("client") ? "Next: recipients" : "Next"}
            </button>
          </div>
        </div>
      )}

      {step === "review" && (
        <div>
          <div className="rounded-xl border border-stone-200 divide-y divide-stone-100 text-sm">
            {!isContactOnly && (
              <>
                <div className="px-4 py-2.5 flex justify-between gap-4">
                  <span className="text-stone-400">Name</span>
                  <span className="font-medium text-stone-800 text-right">{name.trim()}</span>
                </div>
                <div className="px-4 py-2.5 flex justify-between gap-4">
                  <span className="text-stone-400">Email</span>
                  <span className="font-data text-stone-800 text-right">{email.trim()}</span>
                </div>
              </>
            )}
            <div className="px-4 py-2.5 flex justify-between gap-4">
              <span className="text-stone-400">Role</span>
              <span className="font-medium text-stone-800 text-right">
                {roleLabel(role)}
              </span>
            </div>
            {isScoped && (
              <div className="px-4 py-2.5 flex justify-between gap-4">
                <span className="text-stone-400">Projects</span>
                <span className="font-medium text-stone-800 text-right">
                  {selected.size === 0 ? "None" : `${selected.size} selected`}
                </span>
              </div>
            )}
            {recipientPayload().map((r) => {
              const proj = projects.find((p) => p.id === r.projectId);
              return (
                <div key={r.projectId} className="px-4 py-2.5 flex justify-between gap-4">
                  <span className="text-stone-400 shrink-0">{proj?.name || `Project ${r.projectId}`}</span>
                  <span className="text-stone-800 text-right min-w-0">
                    <span className="font-data break-all">{r.primaryEmail}</span>
                    {r.ccEmails.length > 0 && (
                      <span className="text-stone-500"> +{r.ccEmails.length} cc</span>
                    )}
                  </span>
                </div>
              );
            })}
          </div>
          <p className="text-xs text-stone-400 mt-3">
            {isContactOnly
              ? "Saves the report recipients for the projects above. No account is created and nobody is emailed."
              : "Sending creates their account and emails them the website link, their email, and a temporary password generated by the server."}
          </p>
          <ErrorNote>{error}</ErrorNote>
          <div className="flex gap-2 mt-4">
            <button
              onClick={() => {
                setError(null);
                setStep(flow[flow.indexOf("review") - 1]);
                if (flow.includes("client")) setClientIndex(Math.max(selectedIds.length - 1, 0));
              }}
              className={`${BTN_GHOST} px-4 py-2.5`}
            >
              <ChevronLeft size={15} /> Back
            </button>
            <button onClick={send} disabled={busy} className={`${BTN_PRIMARY} flex-1 py-2.5`}>
              {busy ? (
                <LoaderCircle size={15} className="animate-spin" />
              ) : isContactOnly ? (
                <><Check size={15} /> Save recipients</>
              ) : (
                <><Send size={15} /> Create &amp; send invite</>
              )}
            </button>
          </div>
        </div>
      )}

      {step === "sent" && (
        <div>
          <div className="flex items-center gap-2 text-sm text-emerald-700 bg-emerald-50 border border-emerald-100 rounded-lg px-3 py-2 mb-4">
            <Check size={15} />
            {sentEmail ? "Account created and invite sent." : "Recipients saved."}
          </div>
          {sentEmail ? (
            <>
              <EmailPreview email={sentEmail} />
              <p className="text-xs text-stone-400 mt-3">
                This temporary password is shown once — only its hash is stored. If it's lost, use "resend invite" to
                generate a new one.
              </p>
            </>
          ) : (
            <p className="text-xs text-stone-500">
              Reports for the selected projects will go to these addresses. No account was created and nobody was
              emailed. You can change the list any time from the send dialog.
            </p>
          )}
          <button onClick={onClose} className={`${BTN_PRIMARY} w-full py-2.5 mt-4`}>
            Done
          </button>
        </div>
      )}
    </Modal>
  );
}

export function EmailPreview({ email }) {
  return (
    <div className="rounded-xl border border-stone-200 overflow-hidden">
      <div className="bg-stone-50 border-b border-stone-200 px-4 py-3 text-xs text-stone-500 space-y-1">
        <p className="flex items-center gap-1.5">
          <Mail size={13} className="text-stone-400" />
          <span className="font-medium text-stone-600">From:</span> InfyApp SEO Portal &lt;info@infyappseodashboard.website&gt;
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
