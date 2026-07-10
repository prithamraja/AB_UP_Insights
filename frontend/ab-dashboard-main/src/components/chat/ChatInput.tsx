import { useState, useRef, useEffect } from "react";
import { Send, Search } from "lucide-react";

export type QuestionMode = "new" | "followup";

interface ChatInputProps {
  onSend: (message: string, mode: QuestionMode) => void;
  disabled?: boolean;
}

export function ChatInput({ onSend, disabled }: ChatInputProps) {
  const [value, setValue] = useState("");
  const [mode, setMode] = useState<QuestionMode>("new");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
      textareaRef.current.style.height =
        Math.min(textareaRef.current.scrollHeight, 120) + "px";
    }
  }, [value]);

  const handleSubmit = () => {
    const trimmed = value.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed, mode);
    setValue("");
    setMode("new");
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  return (
    <div className="border-t border-line bg-white px-10 py-4">
      <div className="max-w-[820px] mx-auto">
        <div className="flex items-center gap-2 bg-ivory border border-line rounded-lg px-4 py-2.5 focus-within:border-ink/40 transition-colors">
          {/* Mode toggle */}
          <div className="flex items-center bg-line/70 rounded-md p-[3px] shrink-0">
            <button
              type="button"
              onClick={() => setMode("new")}
              className={`text-[11px] font-medium rounded px-2 py-[3px] transition-colors whitespace-nowrap ${
                mode === "new"
                  ? "bg-ink text-ivory"
                  : "text-muted-design hover:text-ink"
              }`}
            >
              New question
            </button>
            <button
              type="button"
              onClick={() => setMode("followup")}
              className={`text-[11px] font-medium rounded px-2 py-[3px] transition-colors whitespace-nowrap ${
                mode === "followup"
                  ? "bg-ink text-ivory"
                  : "text-muted-design hover:text-ink"
              }`}
            >
              Follow-up
            </button>
          </div>

          <div className="w-px h-4 bg-line shrink-0" />

          <Search size={14} className="text-muted-design shrink-0" />
          <textarea
            ref={textareaRef}
            value={value}
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask about enrolment, claims, hospitals, districts..."
            rows={1}
            disabled={disabled}
            className="flex-1 resize-none bg-transparent text-sm text-ink placeholder:text-muted-design outline-none disabled:opacity-50"
          />
          <button
            onClick={handleSubmit}
            disabled={disabled || !value.trim()}
            className="ml-1 w-7 h-7 rounded-md bg-ink hover:bg-ink/90 flex items-center justify-center transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
            aria-label="Send message"
          >
            <Send size={12} className="text-ivory" strokeWidth={2.25} />
          </button>
        </div>
      </div>
    </div>
  );
}
