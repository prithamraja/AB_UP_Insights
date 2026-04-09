import { Plus, Trash2, MessageSquare } from "lucide-react";
import type { Conversation } from "@/types/chat";
import { motion, AnimatePresence } from "framer-motion";

interface ChatSidebarProps {
  conversations: Conversation[];
  activeId: string | null;
  onSelect: (id: string) => void;
  onCreate: () => void;
  onDelete: (id: string) => void;
  onClose?: () => void;
}

export function ChatSidebar({
  conversations,
  activeId,
  onSelect,
  onCreate,
  onDelete,
}: ChatSidebarProps) {
  return (
    <div className="flex h-full flex-col bg-sidebar">
      <div className="flex items-center justify-between border-b border-sidebar-border px-4 py-3">
        <h2 className="text-sm font-semibold text-sidebar-foreground">Conversations</h2>
        <button
          onClick={onCreate}
          className="rounded-lg p-1.5 text-sidebar-foreground transition-colors hover:bg-sidebar-hover"
          aria-label="New conversation"
        >
          <Plus className="h-5 w-5" />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto scrollbar-thin px-2 py-2 space-y-1">
        <AnimatePresence initial={false}>
          {conversations.map((convo) => {
            const isActive = convo.id === activeId;
            return (
              <motion.button
                key={convo.id}
                initial={{ opacity: 0, x: -12 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -12 }}
                transition={{ duration: 0.15 }}
                onClick={() => onSelect(convo.id)}
                className={`group flex w-full items-center gap-2 rounded-lg px-3 py-2.5 text-left text-sm transition-colors ${
                  isActive
                    ? "bg-sidebar-active text-primary font-medium"
                    : "text-sidebar-foreground hover:bg-sidebar-hover"
                }`}
              >
                <MessageSquare className="h-4 w-4 shrink-0 opacity-60" />
                <div className="flex-1 truncate">
                  <span className="block truncate">{convo.title}</span>
                  <span className="block text-xs text-muted-foreground">
                    {new Date(convo.updatedAt).toLocaleDateString()}
                  </span>
                </div>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    onDelete(convo.id);
                  }}
                  className="rounded p-1 opacity-0 transition-opacity group-hover:opacity-100 hover:bg-destructive/10 hover:text-destructive"
                  aria-label="Delete conversation"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              </motion.button>
            );
          })}
        </AnimatePresence>

        {conversations.length === 0 && (
          <p className="px-3 py-8 text-center text-sm text-muted-foreground">
            No conversations yet
          </p>
        )}
      </div>
    </div>
  );
}
