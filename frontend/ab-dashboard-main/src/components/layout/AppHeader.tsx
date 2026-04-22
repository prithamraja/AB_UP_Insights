import { Shield } from "lucide-react";

type Mode = "ask" | "discover" | "track";

interface AppHeaderProps {
  activeView: Mode;
  onViewChange: (view: Mode) => void;
}

const navItems: { id: Mode; label: string }[] = [
  { id: "ask", label: "Ask" },
  { id: "discover", label: "Discover" },
  { id: "track", label: "Analyze" },
];

export function AppHeader({ activeView, onViewChange }: AppHeaderProps) {
  return (
    <header className="h-14 border-b border-line bg-white flex items-center px-6 sticky top-0 z-10">
      {/* Brand */}
      <div className="flex items-center gap-2.5">
        <div className="w-7 h-7 rounded-sm bg-teal-deep flex items-center justify-center">
          <Shield size={15} className="text-ivory" strokeWidth={2.25} />
        </div>
        <div className="leading-tight">
          <div className="font-display text-[15px] font-medium tracking-tight">
            PM-JAY Assistant
          </div>
        </div>
        <div className="w-px h-5 bg-line mx-3" />
        <div className="text-xs text-muted-design">
          <span className="font-medium text-ink/70">Uttar Pradesh</span>
          <span className="mx-1.5 text-line">·</span>
          Ayushman Bharat PMJAY
        </div>
      </div>

      {/* Segmented nav — centered */}
      <nav
        role="tablist"
        className="absolute left-1/2 -translate-x-1/2 flex items-center gap-0.5 bg-ivory border border-line rounded-lg p-1"
      >
        {navItems.map((item) => {
          const active = activeView === item.id;
          return (
            <button
              key={item.id}
              role="tab"
              aria-selected={active}
              onClick={() => onViewChange(item.id)}
              className={`px-4 py-1.5 text-sm rounded-md transition-all ${
                active
                  ? "bg-white text-ink font-medium shadow-sm border border-line"
                  : "text-muted-design hover:text-ink hover:bg-white/60"
              }`}
            >
              {item.label}
            </button>
          );
        })}
      </nav>

      {/* Right spacer for balance */}
      <div className="ml-auto" />
    </header>
  );
}
