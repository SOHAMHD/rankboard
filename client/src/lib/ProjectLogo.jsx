import { BarChart3 } from "lucide-react";

/** The client's logo, or the chart tile when there isn't one.
 *
 * Shared by the projects list and the sidebar block inside a project so the two
 * can't drift apart. `object-contain` on a white tile because a client logo can
 * be any aspect ratio and any background — cropping to a square would cut the
 * wordmark off half of them.
 */
export default function ProjectLogo({ project, size, className = "" }) {
  const box = { width: size, height: size };
  if (project?.clientLogo) {
    return (
      <div
        style={box}
        className={`shrink-0 overflow-hidden rounded-xl border border-stone-200 bg-white p-1 ${className}`}
      >
        <img
          src={project.clientLogo}
          alt=""
          aria-hidden="true"
          className="h-full w-full object-contain"
        />
      </div>
    );
  }
  return (
    <div
      style={box}
      className={`shrink-0 rounded-xl bg-orange-600 flex items-center justify-center shadow-sm ${className}`}
    >
      <BarChart3 size={Math.round(size * 0.45)} className="text-white" />
    </div>
  );
}
