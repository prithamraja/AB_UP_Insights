import { motion } from "framer-motion";
import { Shield } from "lucide-react";

export function TypingIndicator() {
  return (
    <div className="flex justify-start">
      <div className="space-y-3">
        <div className="flex items-center gap-2">
          <div className="w-5 h-5 rounded-sm bg-teal-deep flex items-center justify-center">
            <Shield size={10} className="text-ivory" strokeWidth={2.5} />
          </div>
          <div className="text-[11px] text-muted-design">Assistant</div>
        </div>
        <div className="flex items-center gap-1 ml-7">
          {[0, 1, 2].map((i) => (
            <motion.span
              key={i}
              className="block h-2 w-2 rounded-full bg-muted-design/50"
              animate={{ y: [0, -4, 0] }}
              transition={{
                duration: 0.6,
                repeat: Infinity,
                delay: i * 0.15,
              }}
            />
          ))}
        </div>
      </div>
    </div>
  );
}
