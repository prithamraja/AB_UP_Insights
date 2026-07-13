import { useState } from "react";
import { History, PanelLeftClose, X } from "lucide-react";
import type { ContextFrame, ContextFrameSnapshot } from "@/types/chat";

interface ContextHistoryProps {
  frame: ContextFrame;
  disabled?: boolean;
  // Steps back from the current frame (1 = the immediately previous question).
  onJumpBack?: (steps: number) => void;
  onReset?: () => void;
}

function timeLabel(snapshot: ContextFrameSnapshot) {
  const tr = snapshot.time_range;
  if (tr.start && tr.end) return `${tr.start} – ${tr.end}`;
  return tr.grain === "all_time" ? "All available data" : tr.grain;
}

function Chips({ snapshot }: { snapshot: ContextFrameSnapshot }) {
  return (
    <div className="mt-1 flex flex-wrap gap-1">
      <span className="rounded-full border border-line bg-ivory px-1.5 py-px text-[10px] text-muted-design">
        {timeLabel(snapshot)}
      </span>
      {snapshot.active_filters.map((f, i) => (
        <span
          key={i}
          className="rounded-full border border-line bg-ivory px-1.5 py-px text-[10px] text-muted-design"
        >
          {f.dimension.replace(/_/g, " ")}: {f.value}
        </span>
      ))}
    </div>
  );
}

// The analytical trail, as a rail rather than a band: collapsed to a thin strip
// by default, expanded on demand into the stack of frames the user drilled
// through. Tapping an earlier frame pops back to it (and its exact rows).
export function ContextHistory({ frame, disabled, onJumpBack, onReset }: ContextHistoryProps) {
  const [open, setOpen] = useState(false);

  const { history_stack, ...current } = frame;
  const entries: ContextFrameSnapshot[] = [...history_stack, current];
  const currentIndex = entries.length - 1;

  if (!open) {
    return (
      <div className="w-11 shrink-0 border-r border-line bg-white flex flex-col items-center py-3 gap-2">
        <button
          onClick={() => setOpen(true)}
          className="relative rounded-md p-1.5 text-muted-design hover:text-ink hover:bg-ivory transition-colors"
          aria-label="Show question history"
          title="Question history"
        >
          <History size={16} />
          {entries.length > 1 && (
            <span className="absolute -top-0.5 -right-0.5 min-w-[14px] h-[14px] rounded-full bg-teal-deep text-ivory text-[9px] leading-[14px] text-center px-0.5">
              {entries.length}
            </span>
          )}
        </button>
      </div>
    );
  }

  return (
    <div className="w-64 shrink-0 border-r border-line bg-white flex flex-col">
      <div className="flex items-center justify-between border-b border-line px-3 py-2.5">
        <span className="text-[10px] font-semibold uppercase tracking-[0.12em] text-muted-design">
          PM-JAY UP
        </span>
        <button
          onClick={() => setOpen(false)}
          className="rounded-md p-1 text-muted-design hover:text-ink hover:bg-ivory transition-colors"
          aria-label="Collapse question history"
        >
          <PanelLeftClose size={14} />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto scrollbar-thin px-2 py-2">
        {entries.map((snapshot, i) => {
          const isCurrent = i === currentIndex;
          // A follow-up re-queries the template it was asked against (entity swap,
          // time change, requery operation) and sits one level in. Anything that
          // lands on a different template is a new question, back at the root.
          const isFollowUp = i > 0 && entries[i - 1].template_id === snapshot.template_id;
          return (
            <button
              key={i}
              onClick={() => !isCurrent && onJumpBack?.(currentIndex - i)}
              disabled={disabled || isCurrent}
              style={{ marginLeft: isFollowUp ? 12 : 0 }}
              className={`w-full text-left rounded-md border-l-2 px-2 py-1.5 mb-1 transition-colors ${
                isCurrent
                  ? "border-teal-deep bg-ivory cursor-default"
                  : "border-line hover:border-ink/40 hover:bg-ivory disabled:opacity-40"
              }`}
            >
              <span className="block text-[12px] leading-snug text-ink line-clamp-2">
                {snapshot.template_question ?? snapshot.template_id}
              </span>
              <Chips snapshot={snapshot} />
            </button>
          );
        })}
      </div>

      {onReset && (
        <div className="border-t border-line px-2 py-2">
          <button
            onClick={onReset}
            disabled={disabled}
            className="inline-flex w-full items-center justify-center gap-1 rounded-md border border-line bg-white px-2 py-1 text-[11px] text-muted-design hover:text-ink hover:border-ink/30 transition-colors disabled:opacity-40"
          >
            <X size={11} />
            New question
          </button>
        </div>
      )}
    </div>
  );
}
