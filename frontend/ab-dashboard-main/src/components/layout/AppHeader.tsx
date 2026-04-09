import { Shield } from "lucide-react";

export function AppHeader() {
  return (
    <div className="border-b border-border bg-[#0f4c5c] px-6 py-3">
      <div className="flex items-center gap-2">
        <Shield className="h-5 w-5 text-white/80" />
        <div>
          <h1 className="text-sm font-semibold text-white">
            PM-JAY Assistant — Uttar Pradesh
          </h1>
          <p className="text-[11px] text-white/60">
            Ayushman Bharat Pradhan Mantri Jan Arogya Yojana
          </p>
        </div>
      </div>
    </div>
  );
}
