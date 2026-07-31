import { useEffect, useRef, useState } from "react";
import { ChevronLeft, ChevronRight, Calendar } from "lucide-react";

const MONTH_SHORT = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
];
const MONTH_NAMES = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];

/**
 * Custom month/year calendar picker.
 * value:    "YYYY-MM" string (same format as <input type="month">)
 * onChange: (nextValue: "YYYY-MM") => void
 */
export function MonthPicker({ value, onChange, className = "" }) {
  const [open, setOpen] = useState(false);
  const [viewYear, setViewYear] = useState(() =>
    value ? Number(value.split("-")[0]) : new Date().getFullYear()
  );
  const wrapRef = useRef(null);

  const [selYear, selMonthIdx] = value
    ? [Number(value.split("-")[0]), Number(value.split("-")[1]) - 1]
    : [null, null];

  // Close on outside click
  useEffect(() => {
    if (!open) return;
    const onDocClick = (e) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target)) setOpen(false);
    };
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, [open]);

  // Reset the visible year to match the selected value each time it opens
  useEffect(() => {
    if (open) setViewYear(selYear ?? new Date().getFullYear());
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const pick = (monthIdx) => {
    const mm = String(monthIdx + 1).padStart(2, "0");
    onChange(`${viewYear}-${mm}`);
    setOpen(false);
  };

  const label = value
    ? `${MONTH_NAMES[Number(value.split("-")[1]) - 1]} ${value.split("-")[0]}`
    : "Select month";

  return (
    <div ref={wrapRef} className={`relative ${className}`}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center justify-between gap-2 rounded-lg border border-stone-200 bg-white px-3 py-2 text-sm text-stone-800 hover:border-stone-300 focus:outline-none focus:ring-2 focus:ring-orange-200"
      >
        <span className="truncate">{label}</span>
        <Calendar size={15} className="text-stone-400 shrink-0" />
      </button>

      {open && (
        <div className="absolute z-20 mt-1 w-64 rounded-xl border border-stone-200 bg-white shadow-lg p-3">
          <div className="flex items-center justify-between mb-2">
            <button
              type="button"
              onClick={() => setViewYear((y) => y - 1)}
              className="p-1 rounded-md hover:bg-stone-100 text-stone-500"
              aria-label="Previous year"
            >
              <ChevronLeft size={16} />
            </button>
            <span className="text-sm font-semibold text-stone-800 font-display">{viewYear}</span>
            <button
              type="button"
              onClick={() => setViewYear((y) => y + 1)}
              className="p-1 rounded-md hover:bg-stone-100 text-stone-500"
              aria-label="Next year"
            >
              <ChevronRight size={16} />
            </button>
          </div>

          <div className="grid grid-cols-4 gap-1.5">
            {MONTH_SHORT.map((m, idx) => {
              const isSelected = viewYear === selYear && idx === selMonthIdx;
              return (
                <button
                  key={m}
                  type="button"
                  onClick={() => pick(idx)}
                  className={`text-xs font-medium rounded-md py-2 transition-colors ${
                    isSelected
                      ? "bg-orange-600 text-white"
                      : "text-stone-600 hover:bg-orange-50 hover:text-orange-700"
                  }`}
                >
                  {m}
                </button>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}