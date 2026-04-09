import { useState, useCallback } from "react";
import { sendMessage } from "@/services/api";
import { ChatArea } from "@/components/chat/ChatArea";
import { AppHeader } from "@/components/layout/AppHeader";
import { AnomaliesView } from "@/components/insights/AnomaliesView";
import { InsightsPlaceholder } from "@/components/insights/InsightsPlaceholder";
import type { Message } from "@/types/chat";

type ActiveView = "ask" | "discover" | "track";

function generateId() {
  return crypto.randomUUID();
}

const Index = () => {
  const [activeView, setActiveView] = useState<ActiveView>("ask");
  const [messages, setMessages] = useState<Message[]>([]);
  const [isLoading, setIsLoading] = useState(false);

  const handleSend = useCallback(
    async (content: string) => {
      const userMsg: Message = {
        id: generateId(),
        role: "user",
        content,
        timestamp: Date.now(),
      };
      setMessages((prev) => [...prev, userMsg]);
      setIsLoading(true);

      try {
        const res = await sendMessage(content);
        const botMsg: Message = {
          id: generateId(),
          role: "assistant",
          content: res.answer,
          timestamp: Date.now(),
          tier: res.tier,
          result: res.result,
          date_range: res.date_range,
          date_filter_applied: res.date_filter_applied,
          originalQuery: content,
        };
        setMessages((prev) => [...prev, botMsg]);
      } catch (err) {
        const errorMsg: Message = {
          id: generateId(),
          role: "assistant",
          content: "",
          timestamp: Date.now(),
          error:
            err instanceof Error
              ? `Failed to get response: ${err.message}`
              : "Something went wrong. Please try again.",
        };
        setMessages((prev) => [...prev, errorMsg]);
      } finally {
        setIsLoading(false);
      }
    },
    [messages]
  );

  const handleDateRangeUpdate = useCallback(
    async (messageId: string, startDate: string, endDate: string) => {
      const targetMsg = messages.find((m) => m.id === messageId);
      if (!targetMsg?.originalQuery) return;

      setIsLoading(true);
      try {
        const res = await sendMessage(targetMsg.originalQuery, {
          start_date: startDate,
          end_date: endDate,
        });
        setMessages((prev) =>
          prev.map((m) =>
            m.id === messageId
              ? {
                  ...m,
                  content: res.answer,
                  tier: res.tier,
                  result: res.result,
                  date_range: res.date_range,
                  timestamp: Date.now(),
                }
              : m
          )
        );
      } catch (err) {
        // Keep existing message on error
      } finally {
        setIsLoading(false);
      }
    },
    [messages]
  );

  return (
    <div className="flex h-screen overflow-hidden">
      <main className="flex flex-1 flex-col min-w-0">
        <AppHeader />
        <div className="flex justify-center gap-2 border-b border-border bg-background px-6 py-1.5">
          {([["ask", "Ask"], ["discover", "Discover"], ["track", "Track"]] as const).map(
            ([key, label]) => (
              <button
                key={key}
                onClick={() => setActiveView(key)}
                className={`rounded-md px-10 py-1.5 text-sm font-medium transition-colors ${
                  activeView === key
                    ? "bg-[#0f4c5c] text-white"
                    : "text-muted-foreground hover:bg-muted"
                }`}
              >
                {label}
              </button>
            )
          )}
        </div>
        <div className="flex-1 min-h-0 flex flex-col">
          {activeView === "ask" ? (
            <ChatArea
              messages={messages}
              isLoading={isLoading}
              onSend={handleSend}
              onDateRangeUpdate={handleDateRangeUpdate}
            />
          ) : activeView === "discover" ? (
            <AnomaliesView />
          ) : (
            <InsightsPlaceholder />
          )}
        </div>
      </main>
    </div>
  );
};

export default Index;
