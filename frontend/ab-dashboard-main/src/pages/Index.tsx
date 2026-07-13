import { useState, useCallback } from "react";
import {
  sendMessage,
  popContext,
  resetContext,
} from "@/services/api";
import { ChatArea } from "@/components/chat/ChatArea";
import { AppHeader } from "@/components/layout/AppHeader";
import { AnomaliesView } from "@/components/insights/AnomaliesView";
import { InsightsPlaceholder } from "@/components/insights/InsightsPlaceholder";
import type { ContextFrame, Message } from "@/types/chat";

type ActiveView = "ask" | "discover" | "track";

function generateId() {
  return crypto.randomUUID();
}

const SESSION_STORAGE_KEY = "ask-session-id";

function getOrCreateSessionId() {
  const existing = sessionStorage.getItem(SESSION_STORAGE_KEY);
  if (existing) return existing;
  const sessionId = crypto.randomUUID();
  sessionStorage.setItem(SESSION_STORAGE_KEY, sessionId);
  return sessionId;
}

const Index = () => {
  const [activeView, setActiveView] = useState<ActiveView>("ask");
  const [messages, setMessages] = useState<Message[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [currentFrame, setCurrentFrame] = useState<ContextFrame | null>(null);

  const [sessionId] = useState(getOrCreateSessionId);
  const handleSend = useCallback(
    async (content: string, fromChip?: boolean) => {
      const userMsg: Message = {
        id: generateId(),
        role: "user",
        content,
        timestamp: Date.now(),
      };
      setMessages((prev) => [...prev, userMsg]);
      setIsLoading(true);

      try {
        const res = await sendMessage(content, {
          session_id: sessionId,
          from_chip: fromChip,
        });
        const botMsg: Message = {
          id: generateId(),
          role: "assistant",
          content: res.answer,
          timestamp: Date.now(),
          tier: res.tier,
          result: res.result,
          context_frame: res.context_frame,
          date_range: res.date_range,
          date_filter_applied: res.date_filter_applied,
          originalQuery: content,
          clarification: res.clarification,
          suggestions: res.suggestions,
        };
        setMessages((prev) => [...prev, botMsg]);
        setCurrentFrame(res.context_frame ?? null);
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
    [sessionId]
  );

  const handleContextBack = useCallback(async () => {
    setIsLoading(true);
    try {
      const res = await popContext(sessionId);
      const botMsg: Message = {
        id: generateId(),
        role: "assistant",
        content: res.answer,
        timestamp: Date.now(),
        tier: res.tier,
        result: res.result,
        context_frame: res.context_frame,
        suggestions: res.suggestions,
      };
      setMessages((prev) => [...prev, botMsg]);
      setCurrentFrame(res.context_frame ?? null);
    } catch {
      // No earlier frame — leave the conversation as is
    } finally {
      setIsLoading(false);
    }
  }, [sessionId]);

  const handleContextReset = useCallback(async () => {
    try {
      await resetContext(sessionId);
    } catch {
      // Reset is best-effort; the next question replaces the frame anyway
    }
    setCurrentFrame(null);
  }, [sessionId]);

  const handleDateRangeUpdate = useCallback(
    async (messageId: string, startDate: string, endDate: string) => {
      const targetMsg = messages.find((m) => m.id === messageId);
      if (!targetMsg?.originalQuery) return;

      setIsLoading(true);
      try {
        const res = await sendMessage(targetMsg.originalQuery, {
          session_id: sessionId,
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
                  context_frame: res.context_frame,
                  result: res.result,
                  date_range: res.date_range,
                  timestamp: Date.now(),
                }
              : m
          )
        );
        setCurrentFrame(res.context_frame ?? null);
      } catch (err) {
        // Keep existing message on error
      } finally {
        setIsLoading(false);
      }
    },
    [messages, sessionId]
  );

  return (
    <div className="flex h-screen overflow-hidden bg-ivory">
      <main className="flex flex-1 flex-col min-w-0">
        <AppHeader activeView={activeView} onViewChange={setActiveView} />
        <div className="flex-1 min-h-0 flex flex-col">
          {activeView === "ask" ? (
            <ChatArea
              messages={messages}
              isLoading={isLoading}
              onSend={handleSend}
              onDateRangeUpdate={handleDateRangeUpdate}
              currentFrame={currentFrame}
              onContextBack={handleContextBack}
              onContextReset={handleContextReset}
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
