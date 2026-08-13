import { useEffect, useState } from "react";
import { RefreshCw, LoaderCircle, ShieldCheck, Globe, Link as LinkIcon } from "lucide-react";
import { api } from "../api";
import { ErrorNote, BTN_PRIMARY, can } from "../ui";

function formatCompact(value) {
  if (value == null) return "—";
  const n = Number(value);
  if (!Number.isFinite(n)) return "—";
  const abs = Math.abs(n);
  if (abs < 1000) return n.toLocaleString();
  const trim = (x) => x.toFixed(1).replace(/\.0$/, "");
  if (abs < 1_000_000) return `${trim(n / 1000)}k`;
  if (abs < 1_000_000_000) return `${trim(n / 1_000_000)}M`;
  return `${trim(n / 1_000_000_000)}B`;
}

function formatFetchedAt(iso) {
  if (!iso) return null;
  const then = new Date(iso);
  if (Number.isNaN(then.getTime())) return iso;
  const mins = Math.round((Date.now() - then.getTime()) / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins} min${mins === 1 ? "" : "s"} ago`;
  const hrs = Math.round(mins / 60);
  if (hrs < 24) return `${hrs} hour${hrs === 1 ? "" : "s"} ago`;
  const days = Math.round(hrs / 24);
  if (days < 30) return `${days} day${days === 1 ? "" : "s"} ago`;
  return then.toLocaleDateString();
}

function AuthorityRing({ value }) {
  const has = value != null && Number.isFinite(Number(value));
  const v = Math.max(0, Math.min(100, Number(value) || 0));
  const r = 30;
  const circumference = 2 * Math.PI * r;
  const offset = circumference * (1 - v / 100);
  return (
    <svg viewBox="0 0 80 80" className="h-20 w-20" role="img" aria-label={`Domain Authority ${has ? Math.round(v) : "unknown"}`}>
      <g transform="rotate(-90 40 40)">
        <circle cx="40" cy="40" r={r} fill="none" stroke="#f1f5f9" strokeWidth="8" />
        {has && (
          <circle
            cx="40"
            cy="40"
            r={r}
            fill="none"
            stroke="#ea580c"
            strokeWidth="8"
            strokeLinecap="round"
            strokeDasharray={circumference}
            strokeDashoffset={offset}
          />
        )}
      </g>
      <text x="40" y="40" textAnchor="middle" dominantBaseline="central" className="fill-stone-900 font-data" fontSize="22" fontWeight="600">
        {has ? Math.round(v) : "—"}
      </text>
    </svg>
  );
}

function NumberTile({ icon: Icon, label, value }) {
  return (
    <div className="bg-white rounded-xl border border-stone-200 px-4 py-3">
      <p className="text-xs uppercase tracking-wider text-stone-400 flex items-center gap-1.5">
        <Icon size={13} /> {label}
      </p>
      <p className="text-2xl font-semibold mt-1 font-data text-stone-900">{formatCompact(value)}</p>
    </div>
  );
}

export function MozOverview({ project, user }) {
  const mayRefresh = can(user, "addKeyword");
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    api(`/projects/${project.id}/moz`)
      .then((d) => !cancelled && setData(d.data))
      .catch((err) => !cancelled && setError(err.message))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [project.id]);

  const refresh = async () => {
    setRefreshing(true);
    setError(null);
    try {
      const d = await api(`/projects/${project.id}/moz/refresh`, { method: "POST" });
      setData(d.data);
    } catch (err) {
      setError(err.message);
    } finally {
      setRefreshing(false);
    }
  };

  const hasData = !!data;
  const lastUpdated = hasData ? formatFetchedAt(data.fetchedAt) : null;

  return (
    <div className="w-full">
      <div className="flex flex-wrap items-end justify-between gap-4 mb-6">
        <div>
          <h1 className="text-2xl font-bold text-stone-900 tracking-tight font-display flex items-center gap-2">
            <ShieldCheck size={22} className="text-orange-600" /> Authority
          </h1>
          <p className="text-sm text-stone-500 mt-1">
            Domain authority and link metrics for{" "}
            <span className="font-data text-stone-700">{project.domain || "this project"}</span>, from Moz.
          </p>
        </div>
        {mayRefresh && (
          <button
            onClick={refresh}
            disabled={refreshing}
            title="Pull the latest metrics from the Moz API (uses quota)"
            className={`${BTN_PRIMARY} px-4 py-2`}
          >
            {refreshing ? <LoaderCircle size={15} className="animate-spin" /> : <RefreshCw size={15} />} Refresh from Moz
          </button>
        )}
      </div>

      <ErrorNote>{error}</ErrorNote>

      {loading ? (
        <div className="flex justify-center py-16">
          <LoaderCircle size={22} className="text-orange-600 animate-spin" />
        </div>
      ) : !hasData ? (
        <div className="bg-white rounded-xl border border-dashed border-stone-300 py-16 flex flex-col items-center text-center px-6 mt-2">
          <div className="h-12 w-12 rounded-full bg-stone-100 flex items-center justify-center mb-4">
            <ShieldCheck size={20} className="text-stone-400" />
          </div>
          <h3 className="font-semibold text-stone-800 font-display">No Moz data yet</h3>
          <p className="text-sm text-stone-500 mt-1 max-w-xs">
            {mayRefresh ? "Click Refresh to pull from Moz." : "No authority metrics have been pulled for this project yet."}
          </p>
        </div>
      ) : (
        <>
          <div className="grid grid-cols-2 lg:grid-cols-3 gap-3">
            <div className="bg-white rounded-xl border border-stone-200 px-4 py-3 flex items-center gap-4">
              <AuthorityRing value={data.domainAuthority} />
              <div>
                <p className="text-xs uppercase tracking-wider text-stone-400 flex items-center gap-1.5">
                  <ShieldCheck size={13} /> Domain Authority
                </p>
                <p className="text-xs text-stone-400 mt-1">Moz score, 0–100</p>
              </div>
            </div>

            <NumberTile icon={Globe} label="Linking Domains" value={data.linkingDomains} />
            <NumberTile icon={LinkIcon} label="Inbound Links" value={data.inboundLinks} />
          </div>

          <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 mt-4 text-xs text-stone-400">
            <span className="flex flex-wrap items-center gap-x-3 gap-y-1">
              {lastUpdated && <span>Last updated: {lastUpdated}</span>}
              {data.spamScore != null && (
                <span className="text-stone-500">
                  Spam score: <span className="font-data">{data.spamScore}</span>
                </span>
              )}
            </span>
            <a
              href="https://moz.com/"
              target="_blank"
              rel="noopener noreferrer"
              className="text-stone-400 hover:text-orange-600 transition-colors"
            >
              Data by Moz
            </a>
          </div>
        </>
      )}
    </div>
  );
}
