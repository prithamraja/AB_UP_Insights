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
  { key: "hospital", label: "Hospital Infrastructure & Speciality" },
  { key: "beneficiary", label: "Beneficiary Enrolment & Uptake" },
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

// --- Component ---

function InsightCard({ insight }: { insight: Insight }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <button
      onClick={() => setExpanded(!expanded)}
      className="w-full text-left rounded-lg border border-border bg-card p-4 hover:shadow-sm transition-shadow"
    >
      <div className="flex items-start gap-2">
        <div className="shrink-0 mt-0.5 text-muted-foreground">
          {expanded ? (
            <ChevronDown className="h-4 w-4" />
          ) : (
            <ChevronRight className="h-4 w-4" />
          )}
        </div>
        <p className="text-sm text-foreground leading-relaxed">
          {insight.leadline}
        </p>
      </div>

      {expanded && insight.bullets.length > 0 && (
        <ol className="mt-3 ml-6 space-y-1.5 list-decimal list-outside text-sm text-muted-foreground leading-relaxed">
          {insight.bullets.map((b, j) => (
            <li key={j} className="pl-1">
              {b}
            </li>
          ))}
        </ol>
      )}
    </button>
  );
}

export function AnomaliesView() {
  const [category, setCategory] = useState<Category>("all");

  const insights = useMemo(() => {
    const parsed = parseReport(gamma05Raw);
    if (category === "all") return parsed;
    return parsed.filter((ins) => ins.category === category);
  }, [category]);

  return (
    <div className="flex flex-1 flex-col min-h-0">
      {/* Category filter */}
      <div className="shrink-0 border-b border-border bg-[hsl(var(--sidebar-bg))]">
        <div className="flex items-center justify-center gap-1.5 px-6 py-2">
          {CATEGORIES.map((c) => (
            <button
              key={c.key}
              onClick={() => setCategory(c.key)}
              className={`px-3 py-1 text-xs font-medium rounded-md transition-colors ${
                category === c.key
                  ? "bg-[#0f4c5c] text-white"
                  : "bg-muted text-muted-foreground hover:bg-background"
              }`}
            >
              {c.label}
            </button>
          ))}
        </div>
      </div>

      {/* Insights list */}
      <div className="flex-1 overflow-y-auto scrollbar-thin px-6 py-4">
        <div className="max-w-4xl mx-auto space-y-3">
          <p className="text-xs text-muted-foreground mb-2">
            {insights.length} insight{insights.length !== 1 ? "s" : ""}
          </p>
          {insights.map((ins, i) => (
            <InsightCard key={`${category}-${i}`} insight={ins} />
          ))}
        </div>
      </div>
    </div>
  );
}
