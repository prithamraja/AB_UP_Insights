import { ChevronRight, CornerUpLeft, X } from "lucide-react";
import type { ContextFrame } from "@/types/chat";

interface BreadcrumbProps {
  frame: ContextFrame;
  disabled?: boolean;
  onBack?: () => void;
  onReset?: () => void;
}

// Always-visible rendering of the current analytical state: what the user is
// looking at (the transcript scrolls away; this doesn't), with time range and
// filters as chips and the escape hatches (back / new question) beside them.
export function Breadcrumb({ frame, disabled, onBack, onReset }: BreadcrumbProps) {
  const tr = frame.time_range;
  const timeLabel =
    tr.start && tr.end
      ? `${tr.start} – ${tr.end}`
      : tr.grain === "all_time"
        ? "All available data"
        : tr.grain;

  return (
    <div className="border-b border-line bg-white px-10 py-2">
      <div className="max-w-[820px] mx-auto flex items-center gap-2 flex-wrap text-xs">
        <span className="text-muted-design font-medium shrink-0">PM-JAY UP</span>
        <ChevronRight size={12} className="text-muted-design shrink-0" />
        <span className="text-ink truncate max-w-[320px]">
          {frame.template_question ?? frame.template_id}
        </span>

        <span className="rounded-full border border-line bg-ivory px-2.5 py-0.5 text-[11px] text-muted-design">
          {timeLabel}
        </span>
        {frame.active_filters.map((f, i) => (
          <span
            key={i}
            className="rounded-full border border-line bg-ivory px-2.5 py-0.5 text-[11px] text-muted-design"
          >
            {f.dimension.replace(/_/g, " ")}: {f.value}
          </span>
        ))}

        <span className="flex-1" />

        {frame.history_stack.length > 0 && onBack && (
          <button
            onClick={onBack}
            disabled={disabled}
            className="inline-flex items-center gap-1 rounded-md border border-line bg-white px-2 py-0.5 text-[11px] text-muted-design hover:text-ink hover:border-ink/30 transition-colors disabled:opacity-40"
          >
            <CornerUpLeft size={11} />
            Back
          </button>
        )}
        {onReset && (
          <button
            onClick={onReset}
            disabled={disabled}
            className="inline-flex items-center gap-1 rounded-md border border-line bg-white px-2 py-0.5 text-[11px] text-muted-design hover:text-ink hover:border-ink/30 transition-colors disabled:opacity-40"
          >
            <X size={11} />
            New question
          </button>
        )}
      </div>
    </div>
  );
}
