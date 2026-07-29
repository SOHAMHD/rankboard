/* ════════════════════════════════════════════════════════════════════
   TOASTS — app-wide, ephemeral notifications.

   Wrap the app once in <ToastProvider> (see main.jsx). Anywhere below it:

     const toast = useToast();
     toast.success("Signed in");
     toast.error("Something went wrong");
     toast.info("Heads up");

   Each toast auto-dismisses (errors linger a little longer) and can be
   closed by hand. Rendered top-right, stacked newest on top, above
   everything else (z-[100]). No external state, no localStorage.
   ════════════════════════════════════════════════════════════════════ */
import { createContext, useCallback, useContext, useMemo, useRef, useState } from "react";
import { CheckCircle2, AlertCircle, Info, X } from "lucide-react";

const ToastContext = createContext(null);

// Per-kind styling + icon. Kept tiny and Tailwind-only so it matches the rest
// of the UI without a compiler step.
const KIND = {
  success: { icon: CheckCircle2, ring: "border-emerald-200", bar: "bg-emerald-500", iconCls: "text-emerald-600" },
  error:   { icon: AlertCircle,  ring: "border-rose-200",    bar: "bg-rose-500",    iconCls: "text-rose-600" },
  info:    { icon: Info,         ring: "border-sky-200",     bar: "bg-sky-500",     iconCls: "text-sky-600" },
};

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([]);
  const idRef = useRef(0);

  const dismiss = useCallback((id) => {
    setToasts((list) => list.filter((t) => t.id !== id));
  }, []);

  const notify = useCallback(
    (message, kind = "info", opts = {}) => {
      if (!message) return;
      const id = ++idRef.current;
      // Errors stay ~6s (more to read / react to); the rest ~4s.
      const duration = opts.duration ?? (kind === "error" ? 6000 : 4000);
      setToasts((list) => [{ id, message, kind, title: opts.title }, ...list]);
      if (duration > 0) setTimeout(() => dismiss(id), duration);
      return id;
    },
    [dismiss]
  );

  // Stable helper object so consumers can destructure without re-renders.
  const api = useMemo(
    () => ({
      notify,
      dismiss,
      success: (m, o) => notify(m, "success", o),
      error: (m, o) => notify(m, "error", o),
      info: (m, o) => notify(m, "info", o),
    }),
    [notify, dismiss]
  );

  return (
    <ToastContext.Provider value={api}>
      {children}
      <div className="fixed top-4 right-4 z-[100] flex w-[22rem] max-w-[calc(100vw-2rem)] flex-col gap-2">
        {toasts.map((t) => {
          const cfg = KIND[t.kind] || KIND.info;
          const Icon = cfg.icon;
          return (
            <div
              key={t.id}
              role="status"
              aria-live="polite"
              className={`pointer-events-auto flex items-start gap-3 overflow-hidden rounded-xl border ${cfg.ring} bg-white px-4 py-3 shadow-lg`}
            >
              <span className={`mt-0.5 shrink-0 ${cfg.iconCls}`}>
                <Icon size={18} />
              </span>
              <div className="min-w-0 flex-1">
                {t.title && <p className="text-sm font-semibold text-stone-800">{t.title}</p>}
                <p className="text-sm text-stone-600 break-words">{t.message}</p>
              </div>
              <button
                onClick={() => dismiss(t.id)}
                aria-label="Dismiss"
                className="shrink-0 text-stone-400 transition-colors hover:text-stone-700"
              >
                <X size={16} />
              </button>
            </div>
          );
        })}
      </div>
    </ToastContext.Provider>
  );
}

// Safe to call even outside a provider (returns no-op helpers), so a component
// never crashes if it's rendered in isolation (e.g. tests).
export function useToast() {
  const ctx = useContext(ToastContext);
  return (
    ctx || {
      notify: () => {},
      dismiss: () => {},
      success: () => {},
      error: () => {},
      info: () => {},
    }
  );
}
