import { useRef, useEffect, useState } from "react";
import type { ContextFrame, Message } from "@/types/chat";
import { MessageBubble } from "./MessageBubble";
import { TypingIndicator } from "./TypingIndicator";
import { ChatInput } from "./ChatInput";
import { ContextHistory } from "./ContextHistory";
import { Shield, Search, Send, ArrowUpRight } from "lucide-react";

interface ChatAreaProps {
  messages: Message[];
  isLoading: boolean;
  onSend: (message: string, fromChip?: boolean) => void;
  onDateRangeUpdate?: (messageId: string, startDate: string, endDate: string) => void;
  currentFrame?: ContextFrame | null;
  onContextJumpBack?: (steps: number) => void;
  onContextReset?: () => void;
}

const landingSuggestions = [
  { category: "HOSPITALS", q: "How many hospitals are empaneled in Lucknow?" },
  { category: "HOSPITALS", q: "What is the hospital bed capacity in Agra?" },
  { category: "CLAIMS", q: "What are the top diagnoses in Sharma Multispeciality Hospital?" },
  { category: "CLAIMS", q: "What is the average claim value by procedure in Ballia?" },
  { category: "CLAIMS", q: "Which district has the most Cardiology cases?" },
  { category: "ENROLMENT", q: "What is the state wide gender split of beneficiaries?" },
  { category: "HINGLISH", q: "Lucknow mein kitney beneficiaries hain?" },
  { category: "HINDI", q: "लखनऊ में कितने लाभार्थी हैं?" },
  { category: "TAMIL", q: "லக்னோவில் எத்தனை பயனாளிகள் உள்ளனர்?" },
];

function EmptyAskState({ onPick }: { onPick: (q: string) => void }) {
  const [input, setInput] = useState("");

  const handleSubmit = () => {
    const trimmed = input.trim();
    if (!trimmed) return;
    onPick(trimmed);
    setInput("");
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  return (
    <div className="min-h-full flex flex-col items-center justify-center px-10 py-16">
      <div className="w-full max-w-[720px]">
        {/* Hero */}
        <div className="text-center mb-10">
          <h1 className="font-display text-[44px] leading-[1.05] tracking-tight text-ink mb-4">
            Ask anything about<br />
            <span className="italic text-muted-design" style={{ fontFamily: "'DM Sans', sans-serif" }}>PM-JAY data.</span>
          </h1>
          <p className="text-[15px] text-muted-design leading-relaxed max-w-md mx-auto">
            Get answers, insights, and visual analysis in seconds — across claims,
            empanelment, enrolment, and specialty coverage.
          </p>
        </div>

        {/* Hero input */}
        <div className="mb-12">
          <div className="flex items-center gap-2 bg-white border border-line rounded-xl px-5 py-3.5 focus-within:border-ink/40 transition-colors shadow-sm">
            <Search size={15} className="text-muted-design" />
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Ask about enrolment, claims, hospitals, districts…"
              className="flex-1 bg-transparent text-[15px] text-ink placeholder:text-muted-design outline-none"
              autoFocus
            />
            <button
              onClick={handleSubmit}
              className="ml-1 w-8 h-8 rounded-lg bg-ink hover:bg-ink/90 flex items-center justify-center transition-colors"
              aria-label="Send message"
            >
              <Send size={13} className="text-ivory" strokeWidth={2.25} />
            </button>
          </div>
        </div>

        {/* Suggestions */}
        <div>
          <div className="flex items-center gap-3 mb-4">
            <span className="text-[11px] font-semibold uppercase tracking-[0.14em] text-muted-design">
              Try asking
            </span>
            <div className="flex-1 h-px bg-line" />
          </div>

          <div className="divide-y divide-line border-y border-line">
            {landingSuggestions.map((s, i) => (
              <button
                key={i}
                onClick={() => onPick(s.q)}
                className="w-full text-left py-3 px-1 flex items-center gap-4 group hover:bg-white/40 transition-colors"
              >
                <span className="text-[10px] uppercase tracking-[0.1em] text-muted-design w-20 shrink-0">
                  {s.category}
                </span>
                <span className="flex-1 text-[14px] text-ink">
                  {s.q}
                </span>
                <ArrowUpRight
                  size={14}
                  className="text-muted-design opacity-0 group-hover:opacity-100 transition-opacity shrink-0"
                />
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

export function ChatArea({
  messages,
  isLoading,
  onSend,
  onDateRangeUpdate,
  currentFrame,
  onContextJumpBack,
  onContextReset,
}: ChatAreaProps) {
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, isLoading]);

  // Landing state — no messages yet
  if (messages.length === 0 && !isLoading) {
    return (
      <div className="h-[calc(100vh-3.5rem)] bg-ivory overflow-y-auto">
        <EmptyAskState onPick={onSend} />
      </div>
    );
  }

  // Active conversation state
  return (
    <div className="flex h-[calc(100vh-3.5rem)]">
      {/* Context history — collapsed rail on the left, expands on click */}
      {currentFrame && (
        <ContextHistory
          frame={currentFrame}
          disabled={isLoading}
          onJumpBack={onContextJumpBack}
          onReset={onContextReset}
        />
      )}

      <div className="flex flex-col flex-1 min-w-0">
        {/* Header strip */}
        <div className="border-b border-line bg-white px-10 py-5">
          <div className="max-w-[820px] mx-auto">
            <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-accent-saffron mb-1">
              Ask
            </div>
            <h1 className="font-display text-[22px] tracking-tight text-ink">
              Query PM-JAY data in your language
            </h1>
          </div>
        </div>

        {/* Conversation area */}
        <div ref={scrollRef} className="flex-1 overflow-y-auto scrollbar-thin px-10 py-8 bg-ivory">
          <div className="max-w-[820px] mx-auto space-y-6">
            {messages.map((msg) => (
              <MessageBubble
                key={msg.id}
                message={msg}
                onDateRangeUpdate={onDateRangeUpdate}
                onSend={isLoading ? undefined : onSend}
              />
            ))}
            {isLoading && <TypingIndicator />}
          </div>
        </div>

        {/* Input bar */}
        <ChatInput onSend={onSend} disabled={isLoading} />
      </div>
    </div>
  );
}
