import { useRef, useEffect } from "react";
import type { Message } from "@/types/chat";
import { MessageBubble } from "./MessageBubble";
import { TypingIndicator } from "./TypingIndicator";
import { ChatInput } from "./ChatInput";
import { Shield } from "lucide-react";

interface ChatAreaProps {
  messages: Message[];
  isLoading: boolean;
  onSend: (message: string) => void;
  onDateRangeUpdate?: (messageId: string, startDate: string, endDate: string) => void;
}

export function ChatArea({ messages, isLoading, onSend, onDateRangeUpdate }: ChatAreaProps) {
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, isLoading]);

  return (
    <div className="flex flex-1 min-h-0 flex-col bg-background">
      {/* Messages */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto scrollbar-thin px-4 py-6">
        <div className="mx-auto max-w-3xl space-y-4">
          {messages.length === 0 && (
            <div className="flex flex-col items-center justify-center py-16 text-center text-muted-foreground">
              <Shield className="mb-3 h-10 w-10 opacity-20" />
              <p className="text-base font-medium">Ask a question about PM-JAY data</p>
              <p className="mt-1 text-sm opacity-70">
                e.g. "How many claims were filed in Lucknow last quarter?"
              </p>
            </div>
          )}
          {messages.map((msg) => (
            <MessageBubble key={msg.id} message={msg} onDateRangeUpdate={onDateRangeUpdate} />
          ))}
          {isLoading && <TypingIndicator />}
        </div>
      </div>

      <ChatInput onSend={onSend} disabled={isLoading} />
    </div>
  );
}
