import { useEffect, useRef, useState } from "react";
import { ExternalLink, LoaderCircle, Plus, Trash2 } from "lucide-react";
import { api } from "../api";
import { ConfirmModal, ErrorNote, INPUT_CLS, BTN_PRIMARY, isAuthor } from "../ui";

const KIND_META = {
  blog: { title: "Blogs", noun: "blog", placeholder: "https://yoursite.com/blog/post" },
  linkedin: { title: "LinkedIn Posts", noun: "LinkedIn post", placeholder: "https://www.linkedin.com/posts/…" },
};

const MONTH_NAMES = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];

function monthLabel(key) {
  const m = String(key).split("-");
  const idx = Number(m[1]) - 1;
  return m.length === 2 && idx >= 0 && idx < 12 ? `${MONTH_NAMES[idx]} ${m[0]}` : String(key);
}

export function PostsView({ user, project, kind }) {
  const meta = KIND_META[kind] || KIND_META.blog;
  const currentMonth = `${new Date().getFullYear()}-${String(
  new Date().getMonth() + 1
).padStart(2, "0")}`;

const [month, setMonth] = useState(currentMonth);
  const [posts, setPosts] = useState(null);
  const [url, setUrl] = useState("");
  const [title, setTitle] = useState("");

  const [monthFilter, setMonthFilter] = useState("all");
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  // Deleting a link was a single unguarded click, unlike every other delete in
  // the app — and the row it sits on is the one you click to open the post.
  const [confirmPost, setConfirmPost] = useState(null);
  const canEdit = isAuthor(user);

  // Bumped per request: the effect below re-runs on `kind`, so switching
  // Blogs↔LinkedIn quickly could let the slower first response land last and
  // show the wrong list under the new heading. Same guard as Keywords uses.
  const loadSeq = useRef(0);

  const load = async () => {
    const seq = ++loadSeq.current;
    try {
      const d = await api(`/projects/${project.id}/posts?kind=${kind}`);
      if (seq !== loadSeq.current) return;
      setPosts(d.posts);
      setError(null);
    } catch (err) {
      if (seq === loadSeq.current) setError(err.message);
    }
  };

  useEffect(() => {
    setPosts(null);
    setMonthFilter("all");
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [project.id, kind]);

  const add = async () => {
    const u = url.trim();
    if (!/^https?:\/\//i.test(u)) return setError("Enter a full URL starting with http:// or https://.");
    setBusy(true);
    setError(null);
    try {
      await api(`/projects/${project.id}/posts`, {
        method: "POST",
        body: { kind, url: u, month, title: title.trim() || null },
      });
      setUrl("");
      setTitle("");
      await load();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const remove = async (id) => {
    setConfirmPost(null);
    try {
      await api(`/projects/${project.id}/posts/${id}`, { method: "DELETE" });
      await load();
    } catch (err) {
      setError(err.message);
    }
  };

  const monthCounts = new Map();
  (posts || []).forEach((p) => {
    const key = p.month || "";
    monthCounts.set(key, (monthCounts.get(key) || 0) + 1);
  });
  const monthOptions = [...monthCounts.keys()].sort((a, b) => (a < b ? 1 : a > b ? -1 : 0));

  const visible =
    posts && (monthFilter === "all" ? posts : posts.filter((p) => (p.month || "") === monthFilter));

  const groups = [];
  if (visible) {
    const byMonth = new Map();
    visible.forEach((p) => {
      const key = p.month || "";
      if (!byMonth.has(key)) byMonth.set(key, []);
      byMonth.get(key).push(p);
    });
    [...byMonth.keys()]
      .sort((a, b) => (a === "" ? 1 : b === "" ? -1 : a < b ? 1 : a > b ? -1 : 0))
      .forEach((k) =>
        groups.push({ month: k, label: k ? monthLabel(k) : "No month", posts: byMonth.get(k) })
      );
  }

  return (
    <div className="w-full">
      <div className="flex flex-wrap items-end justify-between gap-4 mb-6">
        <div>
          <h1 className="text-2xl font-bold text-stone-900 tracking-tight font-display">{meta.title}</h1>
          <p className="text-sm text-stone-500 mt-1">
            Add links to your {meta.noun}s. These also appear in the report for the month you tag them with.
          </p>
        </div>

        {posts && posts.length > 0 && (
          <select
            value={monthFilter}
            onChange={(e) => setMonthFilter(e.target.value)}
            aria-label="Filter by month"
            className={`${INPUT_CLS} w-auto`}
          >
            <option value="all">All months ({posts.length})</option>
            {monthOptions.map((m) => (
              <option key={m || "none"} value={m}>
                {m ? monthLabel(m) : "No month"} ({monthCounts.get(m)})
              </option>
            ))}
          </select>
        )}
      </div>

      <ErrorNote>{error}</ErrorNote>

      {canEdit && (
        <div className="bg-white rounded-xl border border-stone-200 p-4 mb-6 flex flex-col sm:flex-row gap-2">
          <input
            aria-label={`${meta.noun} URL`}
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && add()}
            placeholder={meta.placeholder}
            className={`${INPUT_CLS} sm:flex-1`}
          />
          <input
            aria-label="Title"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && add()}
            placeholder="Title"
            className={`${INPUT_CLS} sm:w-56`}
          />
                     <input
              type="month"
              value={month}
              // A post can't have been published in a month that hasn't started.
              max={new Date().toISOString().slice(0, 7)}
              onChange={(e) => setMonth(e.target.value)}
              className={`${INPUT_CLS} sm:w-44`}
              aria-label="Month"
            />
          <button onClick={add} disabled={busy || !url.trim()} className={`${BTN_PRIMARY} px-4 py-2 shrink-0`}>
            {busy ? <LoaderCircle size={15} className="animate-spin" /> : (<><Plus size={16} /> Add</>)}
          </button>
        </div>
      )}

      {posts === null && error ? (
        <div className="bg-white rounded-xl border border-stone-200 py-12 text-center px-6">
          <p className="text-sm text-stone-500">Couldn&apos;t load {meta.noun}s.</p>
          <button onClick={load} className={`${BTN_PRIMARY} mt-4 px-4 py-2`}>
            Try again
          </button>
        </div>
      ) : posts === null ? (
        <div className="py-16 flex justify-center">
          <LoaderCircle size={22} className="text-orange-600 animate-spin" />
        </div>
      ) : posts.length === 0 ? (
        <div className="bg-white rounded-xl border border-dashed border-stone-300 py-14 text-center text-sm text-stone-500 px-6">
          No {meta.noun}s added yet.{canEdit ? " Add your first link above." : ""}
        </div>
      ) : visible.length === 0 ? (
        <p className="text-sm text-stone-400 py-10 text-center">No {meta.noun}s for that month.</p>
      ) : (
        <div className="space-y-5">
          {groups.map((g) => (
            <div key={g.month || "none"} className="bg-white rounded-xl border border-stone-200 overflow-hidden">
              <div className="flex items-center justify-between px-5 py-3 border-b border-stone-100">
                <h2 className="text-sm font-semibold text-stone-800 font-display">{g.label}</h2>
                <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-stone-100 text-stone-500">
                  {g.posts.length} {meta.noun}{g.posts.length === 1 ? "" : "s"}
                </span>
              </div>
              <div className="divide-y divide-stone-100">
                {g.posts.map((p) => (
                  <div key={p.id} className="flex items-center gap-3 px-5 py-3 hover:bg-stone-50">
                    <div className="min-w-0 flex-1">
                      {p.title && <p className="text-sm font-medium text-stone-800 truncate">{p.title}</p>}
                      <a
                        // Same guard as Backlinks and the report document: a
                        // stored value that isn't http(s) must not become a
                        // javascript: link.
                        href={/^https?:\/\//i.test(p.url) ? p.url : undefined}
                        target="_blank"
                        rel="noreferrer"
                        className="text-xs text-orange-700 hover:underline font-data break-all inline-flex items-center gap-1"
                      >
                        {p.url} <ExternalLink size={12} className="shrink-0" />
                      </a>
                    </div>
                    {canEdit && (
                      <button
                        onClick={() => setConfirmPost(p)}
                        aria-label="Remove link"
                        title="Remove link"
                        className="p-1.5 rounded-md text-stone-500 hover:text-red-500 hover:bg-red-50 transition-colors shrink-0"
                      >
                        <Trash2 size={15} />
                      </button>
                    )}
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      {confirmPost && (
        <ConfirmModal
          title={`Remove this ${meta.noun}?`}
          confirmLabel="Remove link"
          onCancel={() => setConfirmPost(null)}
          onConfirm={() => remove(confirmPost.id)}
        >
          {confirmPost.title ? (
            <span className="block font-medium text-stone-700">{confirmPost.title}</span>
          ) : null}
          <span className="block font-data break-all text-xs mt-1">{confirmPost.url}</span>
          <span className="block mt-2">
            It also disappears from the report for {confirmPost.month ? monthLabel(confirmPost.month) : "no month"}.
            Reports already generated keep their own frozen copy.
          </span>
        </ConfirmModal>
      )}
    </div>
  );
}