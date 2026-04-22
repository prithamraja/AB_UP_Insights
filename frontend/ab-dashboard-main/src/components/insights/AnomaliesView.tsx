import { useState, useMemo } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";

import gamma05Raw from "@/data/metainsights/gamma_0.5_report.md?raw";

// --- Types ---

interface Insight {
  leadline: string;
  bullets: string[];
  category: Category;
}

type Category = "all" | "claims" | "hospital" | "beneficiary";

const CATEGORIES: { key: Category; label: string }[] = [
  { key: "all", label: "All" },
  { key: "claims", label: "Claims & Treatment" },
  { key: "hospital", label: "Hospital Infrastructure" },
  { key: "beneficiary", label: "Beneficiary Enrolment" },
];

// Map section headings to categories
const SECTION_CATEGORY: Record<string, Category> = {
  "Claims Processing & Treatment Patterns": "claims",
  "District-Level Monthly Performance Trends": "beneficiary",
  "Hospital Infrastructure & Specialty Capacity": "hospital",
  "Beneficiary Enrolment & Scheme Uptake": "beneficiary",
};

// --- Parser ---

/** Parse a report that uses bold leadlines (**...**) + numbered bullets */
function parseReport(md: string): Insight[] {
  const insights: Insight[] = [];
  let currentCategory: Category = "claims";

  const lines = md.split("\n");
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];

    // Section header (## level)
    if (line.startsWith("## ") && !line.startsWith("### ")) {
      const heading = line.replace(/^## /, "").trim();
      if (SECTION_CATEGORY[heading]) {
        currentCategory = SECTION_CATEGORY[heading];
      }
      i++;
      continue;
    }

    // Bold leadline: **...**
    if (line.startsWith("**") && line.trimEnd().endsWith("**")) {
      const leadline = line.trim().replace(/^\*\*/, "").replace(/\*\*\s*$/, "").trim();
      const bullets: string[] = [];
      i++;

      // Collect numbered bullets
      while (i < lines.length) {
        const bLine = lines[i].trim();
        if (/^\d+\.\s/.test(bLine)) {
          bullets.push(bLine.replace(/^\d+\.\s*/, ""));
          i++;
        } else if (bLine === "") {
          i++;
          if (i < lines.length && /^\d+\.\s/.test(lines[i].trim())) {
            continue;
          }
          break;
        } else {
          break;
        }
      }

      if (leadline) {
        insights.push({ leadline, bullets, category: currentCategory });
      }
      continue;
    }

    // Also handle ### heading + paragraph + dash-bullet format (overview style)
    if (line.startsWith("### ")) {
      const heading = line.replace(/^### /, "").trim();
      i++;

      const bullets: string[] = [];
      let paragraph = "";

      while (i < lines.length) {
        const bLine = lines[i].trim();
        if (bLine.startsWith("## ") || bLine.startsWith("### ") || bLine.startsWith("---")) {
          break;
        }
        if (bLine.startsWith("- ")) {
          bullets.push(bLine.replace(/^- /, ""));
          i++;
        } else if (/^\d+\.\s/.test(bLine)) {
          bullets.push(bLine.replace(/^\d+\.\s*/, ""));
          i++;
        } else if (bLine !== "" && !paragraph) {
          paragraph = bLine;
          i++;
        } else {
          i++;
        }
      }

      const allBullets: string[] = [];
      if (paragraph) allBullets.push(paragraph);
      allBullets.push(...bullets);

      if (heading) {
        insights.push({ leadline: heading, bullets: allBullets, category: currentCategory });
      }
      continue;
    }

    i++;
  }

  return insights;
}

// --- Formatted headline: wrap numbers in bold ---
function FormattedHeadline({ text }: { text: string }) {
  // Bold numbers that look like percentages, counts, or years
  const parts = text.split(/(\b\d[\d,.]*%?\b)/g);
  return (
    <span>
      {parts.map((part, i) => {
        if (/^\d[\d,.]*%?$/.test(part)) {
          return (
            <span key={i} className="font-semibold text-ink">
              {part}
            </span>
          );
        }
        return <span key={i}>{part}</span>;
      })}
    </span>
  );
}

// --- Components ---

function InsightRow({
  insight,
  isOpen,
  onToggle,
}: {
  insight: Insight;
  isOpen: boolean;
  onToggle: () => void;
}) {
  return (
    <div className="py-4 group">
      <button
        onClick={onToggle}
        aria-expanded={isOpen}
        className="w-full text-left flex items-start gap-3"
      >
        <div className="mt-1 text-muted-design group-hover:text-ink transition-colors">
          {isOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        </div>
        <div className="flex-1 min-w-0">
          <div className="text-[15px] leading-snug text-ink">
            <FormattedHeadline text={insight.leadline} />
          </div>
        </div>
      </button>
      {isOpen && insight.bullets.length > 0 && (
        <div className="ml-7 mt-4 pl-4 border-l-2 border-accent-saffron/40 space-y-2">
          {insight.bullets.map((line, i) => (
            <div key={i} className="flex gap-3 text-[13px] text-ink/80 leading-relaxed">
              <span className="text-muted-design mt-0.5">
                {String(i + 1).padStart(2, "0")}
              </span>
              <span>{line}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export function AnomaliesView() {
  const [category, setCategory] = useState<Category>("all");
  const [expanded, setExpanded] = useState<number | null>(null);

  const insights = useMemo(() => {
    const parsed = parseReport(gamma05Raw);
    if (category !== "all") {
      return parsed.filter((ins) => ins.category === category);
    }

    // Round-robin interleave across categories
    const buckets: Record<Exclude<Category, "all">, Insight[]> = {
      claims: [],
      hospital: [],
      beneficiary: [],
    };
    for (const ins of parsed) {
      if (ins.category !== "all") buckets[ins.category].push(ins);
    }

    const rotation: Array<Exclude<Category, "all">> = ["claims", "hospital", "beneficiary"];
    const ordered: Insight[] = [];
    const cursors = { claims: 0, hospital: 0, beneficiary: 0 };
    let progressed = true;
    while (progressed) {
      progressed = false;
      for (const cat of rotation) {
        if (cursors[cat] < buckets[cat].length) {
          ordered.push(buckets[cat][cursors[cat]]);
          cursors[cat]++;
          progressed = true;
        }
      }
    }
    return ordered;
  }, [category]);


  return (
    <div className="flex-1 overflow-y-auto scrollbar-thin bg-ivory">
      <div className="max-w-[860px] mx-auto px-10 py-10">
        {/* Page head */}
        <div className="mb-8 pb-6 border-b border-line">
          <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-accent-saffron mb-2">
            Discover
          </div>
          <h1 className="font-display text-[34px] leading-[1.1] tracking-tight text-ink">
            What the data is telling us
          </h1>
          <p className="text-sm text-muted-design mt-2 max-w-xl">
            Priority insights across claims, infrastructure, and enrolment — refreshed weekly.
          </p>
        </div>

        {/* Category chips */}
        <div className="flex items-center gap-1.5 mb-8 overflow-x-auto">
          {CATEGORIES.map((cat) => {
            const active = category === cat.key;
            return (
              <button
                key={cat.key}
                onClick={() => { setCategory(cat.key); setExpanded(null); }}
                className={`px-3 py-1.5 rounded-full text-[13px] transition-colors whitespace-nowrap flex items-center gap-1.5 ${
                  active
                    ? "bg-ink text-ivory"
                    : "bg-white border border-line text-ink hover:border-ink/30"
                }`}
              >
                {cat.label}
              </button>
            );
          })}
        </div>

        {/* Insights list */}
        <div className="divide-y divide-line border-y border-line">
          {insights.map((insight, i) => (
            <InsightRow
              key={`${category}-${i}`}
              insight={insight}
              isOpen={expanded === i}
              onToggle={() => setExpanded(expanded === i ? null : i)}
            />
          ))}
        </div>
      </div>
    </div>
  );
}
