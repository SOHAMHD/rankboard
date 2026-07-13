/* ════════════════════════════════════════════════════════════════════
   POSTS — per-project content links (blog posts + LinkedIn posts). The
   SEO team pastes links here; they also flow into the report. One view,
   parameterised by `kind` ("blog" | "linkedin"), for both nav subsections.
   Reads are open to anyone who can see the project; add/delete are author-only.
   ════════════════════════════════════════════════════════════════════ */
import { useEffect, useState } from "react";
import { ExternalLink, LoaderCircle, Plus, Trash2 } from "lucide-react";
import { api } from "../api";
import { ErrorNote, INPUT_CLS, BTN_PRIMARY, isAuthor } from "../ui";

const KIND_META = {
  blog: { title: "Blogs", noun: "blog", placeholder: "https://yoursite.com/blog/post" },
  linkedin: { title: "LinkedIn Posts", noun: "LinkedIn post", placeholder: "https://www.linkedin.com/posts/…" },
};

export function PostsView({ user, project, kind }) {
  const meta = KIND_META[kind] || KIND_META.blog;
  const [posts, setPosts] = useState(null); // null = loading
  const [url, setUrl] = useState("");
  const [title, setTitle] = useState("");
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const canEdit = isAuthor(user);

  const load = async () => {
    try {
      const d = await api(`/projects/${project.id}/posts?kind=${kind}`);
      setPosts(d.posts);
      setError(null);
    } catch (err) {
      setError(err.message);
    }
  };

  useEffect(() => {
    setPosts(null);
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
        body: { kind, url: u, title: title.trim() || null },
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
    try {
      await api(`/projects/${project.id}/posts/${id}`, { method: "DELETE" });
      await load();
    } catch (err) {
      setError(err.message);
    }
  };

  return (
    <div className="w-full">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-stone-900 tracking-tight font-display">{meta.title}</h1>
        <p className="text-sm text-stone-500 mt-1">
          Add links to your {meta.noun}s. These also appear in the report.
        </p>
      </div>

      <ErrorNote>{error}</ErrorNote>

      {canEdit && (
        <div className="bg-white rounded-xl border border-stone-200 p-4 mb-6 flex flex-col sm:flex-row gap-2">
          <input
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && add()}
            placeholder={meta.placeholder}
            className={`${INPUT_CLS} sm:flex-1`}
          />
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && add()}
            placeholder="Title (optional)"
            className={`${INPUT_CLS} sm:w-56`}
          />
          <button onClick={add} disabled={busy || !url.trim()} className={`${BTN_PRIMARY} px-4 py-2 shrink-0`}>
            {busy ? <LoaderCircle size={15} className="animate-spin" /> : (<><Plus size={16} /> Add</>)}
          </button>
        </div>
      )}

      {posts === null ? (
        <div className="py-16 flex justify-center">
          <LoaderCircle size={22} className="text-orange-600 animate-spin" />
        </div>
      ) : posts.length === 0 ? (
        <div className="bg-white rounded-xl border border-dashed border-stone-300 py-14 text-center text-sm text-stone-500 px-6">
          No {meta.noun}s added yet.{canEdit ? " Add your first link above." : ""}
        </div>
      ) : (
        <div className="bg-white rounded-xl border border-stone-200 divide-y divide-stone-100">
          {posts.map((p) => (
            <div key={p.id} className="flex items-center gap-3 px-4 py-3 hover:bg-stone-50">
              <div className="min-w-0 flex-1">
                {p.title && <p className="text-sm font-medium text-stone-800 truncate">{p.title}</p>}
                <a
                  href={p.url}
                  target="_blank"
                  rel="noreferrer"
                  className="text-xs text-orange-700 hover:underline font-data break-all inline-flex items-center gap-1"
                >
                  {p.url} <ExternalLink size={12} className="shrink-0" />
                </a>
              </div>
              {canEdit && (
                <button
                  onClick={() => remove(p.id)}
                  aria-label="Remove link"
                  title="Remove link"
                  className="p-1.5 rounded-md text-stone-300 hover:text-red-500 hover:bg-red-50 transition-colors shrink-0"
                >
                  <Trash2 size={15} />
                </button>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
