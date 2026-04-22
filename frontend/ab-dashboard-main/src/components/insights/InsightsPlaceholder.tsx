import { useState } from "react";
import { MapPin, Activity, Users, FileText } from "lucide-react";
import { GeographicCoverage } from "./GeographicCoverage";

const reports = [
  { key: "geographic-coverage", label: "Speciality Coverage", icon: MapPin, desc: "Hospital reach by specialty" },
  { key: "hospital-performance", label: "Hospital Performance", icon: Activity, desc: "Claim volume & outcomes" },
  { key: "beneficiary-enrolment", label: "Beneficiary Enrolment", icon: Users, desc: "Card issuance by geography" },
] as const;

type SubpageKey = (typeof reports)[number]["key"];

export function InsightsPlaceholder() {
  const [activePage, setActivePage] = useState<SubpageKey>("geographic-coverage");

  return (
    <div className="h-[calc(100vh-3.5rem)] flex">
      {/* Reports column */}
      <aside className="w-64 border-r border-line bg-white/60 px-4 py-6 flex flex-col">
        <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-accent-saffron mb-4 px-2">
          Reports
        </div>
        <nav className="space-y-1">
          {reports.map((r) => {
            const Icon = r.icon;
            const active = activePage === r.key;
            return (
              <button
                key={r.key}
                onClick={() => setActivePage(r.key)}
                className={`w-full text-left px-3 py-2.5 rounded-md transition-colors group ${
                  active
                    ? "bg-ink text-ivory"
                    : "hover:bg-ink/[0.04] text-ink"
                }`}
              >
                <div className="flex items-center gap-2.5">
                  <Icon size={14} className={active ? "opacity-80" : "text-muted-design"} strokeWidth={2} />
                  <div className="text-[13px] font-medium">{r.label}</div>
                </div>
                <div className={`text-[11px] mt-0.5 ml-6 leading-snug ${active ? "text-ivory/60" : "text-muted-design"}`}>
                  {r.desc}
                </div>
              </button>
            );
          })}
        </nav>

        <div className="mt-auto pt-4 border-t border-line">
          <button className="w-full text-[11px] text-muted-design hover:text-ink flex items-center gap-1.5 px-3 py-1.5 transition-colors">
            <FileText size={11} />
            Download full report (PDF)
          </button>
        </div>
      </aside>

      {/* Content area */}
      {activePage === "geographic-coverage" ? (
        <GeographicCoverage />
      ) : (
        <div className="flex-1 min-w-0 flex flex-col items-center justify-center text-center bg-ivory">
          <p className="text-base font-medium text-ink font-display">
            {reports.find((p) => p.key === activePage)?.label}
          </p>
          <p className="mt-1 text-sm text-muted-design">Coming soon.</p>
        </div>
      )}
    </div>
  );
}
