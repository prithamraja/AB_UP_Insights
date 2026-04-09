import { useState, useCallback } from "react";
import { sendMessage } from "@/services/api";
import { ChatArea } from "@/components/chat/ChatArea";
import { AppHeader } from "@/components/layout/AppHeader";
import { InsightsPlaceholder } from "@/components/insights/InsightsPlaceholder";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import type { Message } from "@/types/chat";

function generateId() {
  return crypto.randomUUID();
}

const Index = () => {
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
        <Tabs defaultValue="chatbot" className="flex flex-1 flex-col min-h-0">
          <TabsList className="w-full justify-start rounded-none border-b border-border bg-background px-6 h-11">
            <TabsTrigger
              value="chatbot"
              className="data-[state=active]:bg-[#0f4c5c] data-[state=active]:text-white data-[state=active]:shadow-none"
            >
              Chatbot
            </TabsTrigger>
            <TabsTrigger
              value="insights"
              className="data-[state=active]:bg-[#0f4c5c] data-[state=active]:text-white data-[state=active]:shadow-none"
            >
              Insights
            </TabsTrigger>
          </TabsList>
          <TabsContent value="chatbot" className="flex flex-col flex-1 min-h-0 mt-0">
            <ChatArea
              messages={messages}
              isLoading={isLoading}
              onSend={handleSend}
              onDateRangeUpdate={handleDateRangeUpdate}
            />
          </TabsContent>
          <TabsContent value="insights" className="flex-1 min-h-0 mt-0 flex">
            <InsightsPlaceholder />
          </TabsContent>
        </Tabs>
      </main>
    </div>
  );
};

export default Index;
