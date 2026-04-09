import { useState } from "react";
import { Building2, MapPin, Activity } from "lucide-react";
import { GeographicCoverage } from "./GeographicCoverage";

const subpages = [
  { key: "resource-constraints", label: "Resource Constraints", icon: Building2 },
  { key: "geographic-coverage", label: "Geographic Coverage", icon: MapPin },
  { key: "hospital-performance", label: "Hospital Performance", icon: Activity },
] as const;

type SubpageKey = (typeof subpages)[number]["key"];

export function InsightsPlaceholder() {
  const [activePage, setActivePage] = useState<SubpageKey>("resource-constraints");

  return (
    <div className="flex flex-1 min-h-0">
      {/* Sidebar */}
      <nav className="w-56 shrink-0 border-r border-border bg-[hsl(var(--sidebar-bg))] flex flex-col">
        <div className="px-4 py-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
          Reports
        </div>
        <div className="flex-1 overflow-y-auto px-2 space-y-5">
          {subpages.map(({ key, label, icon: Icon }) => (
            <button
              key={key}
              onClick={() => setActivePage(key)}
              className={`flex w-full items-center gap-2.5 rounded-md px-3 py-2 text-sm transition-colors ${
                activePage === key
                  ? "bg-[hsl(var(--sidebar-active))] text-[hsl(var(--sidebar-primary))] font-medium"
                  : "text-[hsl(var(--sidebar-fg))] hover:bg-[hsl(var(--sidebar-hover))]"
              }`}
            >
              <Icon className="h-4 w-4 shrink-0" />
              {label}
            </button>
          ))}
        </div>
      </nav>

      {/* Content area */}
      {activePage === "geographic-coverage" ? (
        <GeographicCoverage />
      ) : (
        <div className="flex-1 min-w-0 flex flex-col items-center justify-center text-center text-muted-foreground">
          <p className="text-base font-medium">
            {subpages.find((p) => p.key === activePage)?.label}
          </p>
          <p className="mt-1 text-sm opacity-70">Coming soon.</p>
        </div>
      )}
    </div>
  );
}
