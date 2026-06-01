import React, { useState } from "react";
import { ChevronDown, ChevronRight, Send, Search, Download, Code2, Sparkles, Shield, TrendingUp, MapPin, Clock, ArrowUpRight, Filter, Activity, Users, FileText, Plus, Minus } from "lucide-react";

// ============================================================
// PM-JAY Assistant — Redesigned Mockup
// Design direction: refined institutional.
// - Typography: Fraunces (display serif) + Inter (body, tabular nums)
// - Palette: warm ivory base, deep ink, single saffron accent, teal as structure
// - Layout: consistent left-sidebar nav across all modes, dense but breathable
// ============================================================

const insights = [
  {
    id: 1,
    category: "Claims & Treatment",
    priority: true,
    districts: "74 of 75",
    updated: "2 days ago",
    headline: "NORMAL discharges account for {85.6%} of paid PM-JAY value statewide",
    tail: "except Hamirpur, where LAMA/DAMA exits overtake the usual pattern.",
    detail: null,
  },
  {
    id: 2,
    category: "Claims & Treatment",
    priority: true,
    districts: "74 of 75",
    updated: "2 days ago",
    headline: "Cardiology and Orthopaedics drive {65.6%} of claim value",
    tail: "only Shamli swaps Orthopaedics for Obstetrics-Gynaecology (OBG).",
    detail: null,
  },
  {
    id: 3,
    category: "Beneficiary Enrolment & Uptake",
    priority: false,
    districts: "74 of 75",
    updated: "5 days ago",
    headline: "Ayushman card issuance spiked in {2023} across 74 of 75 districts",
    tail: "except Mahoba, which shifted its timing to 2024.",
    detail: null,
  },
  {
    id: 4,
    category: "Claims & Treatment",
    priority: false,
    districts: "74 of 75",
    updated: "2 days ago",
    headline: "LAMA and DAMA make up {100%} of the non-NORMAL exit mix",
    tail: "except Shamli, where the balance leans differently.",
    detail: [
      "Across districts, the two against-medical-advice categories account for all recorded non-NORMAL exits in 74 of 75 districts.",
      "LAMA contributes 891 cases (65.5%), while DAMA contributes 470 cases (34.5%), out of 1,361 total such exits.",
      "Shamli is the lone district that does not follow this split, indicating a different discharge profile from the rest of UP.",
      "Implication: LAMA/DAMA management should be treated as a statewide operational issue, with a targeted review in Shamli.",
    ],
  },
  {
    id: 5,
    category: "Hospital Infrastructure & Speciality",
    priority: false,
    districts: "All 75",
    updated: "1 week ago",
    headline: "{62%} of empanelled beds are concentrated in 12 districts",
    tail: "with Lucknow, Kanpur Nagar, and Gautam Buddha Nagar leading capacity.",
    detail: null,
  },
  {
    id: 6,
    category: "Hospital Infrastructure & Speciality",
    priority: false,
    districts: "42 districts",
    updated: "1 week ago",
    headline: "Private empanelment grew {18.3%} YoY",
    tail: "while public empanelment stayed effectively flat across the same period.",
    detail: null,
  },
];

const categories = [
  { id: "all", label: "All", count: 75 },
  { id: "claims", label: "Claims & Treatment", count: 28 },
  { id: "infra", label: "Hospital Infrastructure", count: 22 },
  { id: "enrol", label: "Beneficiary Enrolment", count: 25 },
];

const suggestedQueries = [
  "How many hospitals are empanelled in Lucknow?",
  "Top 5 specialties by claim value in 2024",
  "Which districts have the lowest card issuance rate?",
  "Show LAMA trend over the last 12 months",
];

// Sample chart data for Ask view
const chartData = [
  { label: "Private NGO", value: 9, type: "private" },
  { label: "Public CHC", value: 7, type: "public" },
  { label: "Public Med. College", value: 5, type: "public" },
  { label: "Public Dist. Hosp.", value: 2, type: "public" },
  { label: "Private", value: 2, type: "private" },
  { label: "Public PHC", value: 2, type: "public" },
  { label: "Private Trust", value: 1, type: "private" },
];

const tableData = [
  { type: "PRIVATE", sub: "NGO", count: 9, beds: 1227 },
  { type: "PUBLIC", sub: "CHC", count: 7, beds: 876 },
  { type: "PUBLIC", sub: "Medical College", count: 5, beds: 593 },
  { type: "PUBLIC", sub: "District Hospital", count: 2, beds: 93 },
  { type: "PRIVATE", sub: "Private", count: 2, beds: 511 },
  { type: "PUBLIC", sub: "PHC", count: 2, beds: 160 },
  { type: "PRIVATE", sub: "Trust", count: 1, beds: 259 },
];

// Formatted headline: wraps {text} in emphasized span
function FormattedHeadline({ text }) {
  const parts = text.split(/(\{[^}]+\})/g);
  return (
    <span>
      {parts.map((part, i) => {
        if (part.startsWith("{") && part.endsWith("}")) {
          return (
            <span key={i} className="font-semibold text-ink tabular-nums">
              {part.slice(1, -1)}
            </span>
          );
        }
        return <span key={i}>{part}</span>;
      })}
    </span>
  );
}

// ============================================================
// Shell: top bar with inline nav (consistent across modes)
// ============================================================
function Shell({ mode, setMode, children }) {
  const navItems = [
    { id: "ask", label: "Ask" },
    { id: "discover", label: "Discover" },
    { id: "track", label: "Track" },
  ];

  return (
    <div className="min-h-screen bg-ivory font-sans text-ink">
      {/* Top bar with brand + nav */}
      <header className="h-14 border-b border-line bg-white flex items-center px-6 sticky top-0 z-10">
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
          <div className="text-xs text-muted">
            <span className="font-medium text-ink/70">Uttar Pradesh</span>
            <span className="mx-1.5 text-line">·</span>
            Ayushman Bharat PMJAY
          </div>
        </div>

        {/* Inline tab nav, centered — pill container with clear active state */}
        <nav className="absolute left-1/2 -translate-x-1/2 flex items-center gap-0.5 bg-ivory border border-line rounded-lg p-1">
          {navItems.map((item) => {
            const active = mode === item.id;
            return (
              <button
                key={item.id}
                onClick={() => setMode(item.id)}
                className={`px-4 py-1.5 text-sm rounded-md transition-all ${
                  active
                    ? "bg-white text-ink font-medium shadow-sm border border-line"
                    : "text-muted hover:text-ink hover:bg-white/60"
                }`}
              >
                {item.label}
              </button>
            );
          })}
        </nav>

        <div className="ml-auto flex items-center gap-4">
          <button className="text-xs text-muted hover:text-ink transition-colors">
            Docs
          </button>
        </div>
      </header>

      {/* Main content */}
      <main className="min-w-0">{children}</main>
    </div>
  );
}

// ============================================================
// DISCOVER view
// ============================================================
function DiscoverView() {
  const [activeCategory, setActiveCategory] = useState("all");
  const [expanded, setExpanded] = useState(4);

  const filtered = activeCategory === "all"
    ? insights
    : insights.filter((i) => {
        if (activeCategory === "claims") return i.category === "Claims & Treatment";
        if (activeCategory === "infra") return i.category === "Hospital Infrastructure & Speciality";
        if (activeCategory === "enrol") return i.category === "Beneficiary Enrolment & Uptake";
        return true;
      });

  return (
    <div className="max-w-[860px] mx-auto px-10 py-10">
      {/* Page head */}
      <div className="mb-8 pb-6 border-b border-line">
        <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-accent mb-2">
          Discover
        </div>
        <h1 className="font-display text-[34px] leading-[1.1] tracking-tight text-ink">
          What the data is telling us
        </h1>
        <p className="text-sm text-muted mt-2 max-w-xl">
          Priority insights across claims, infrastructure, and enrolment — refreshed weekly.
        </p>
      </div>

      {/* Category filter */}
      <div className="flex items-center gap-1.5 mb-8 overflow-x-auto">
        {categories.map((cat) => {
          const active = activeCategory === cat.id;
          return (
            <button
              key={cat.id}
              onClick={() => setActiveCategory(cat.id)}
              className={`px-3 py-1.5 rounded-full text-[13px] transition-colors whitespace-nowrap flex items-center gap-1.5 ${
                active
                  ? "bg-ink text-ivory"
                  : "bg-white border border-line text-ink hover:border-ink/30"
              }`}
            >
              {cat.label}
              <span className={`text-[11px] tabular-nums ${active ? "text-ivory/60" : "text-muted"}`}>
                {cat.count}
              </span>
            </button>
          );
        })}
      </div>

      {/* Insights list */}
      <div className="divide-y divide-line border-y border-line">
        {filtered.map((insight) => (
          <InsightRow
            key={insight.id}
            insight={insight}
            isOpen={expanded === insight.id}
            onToggle={() => setExpanded(expanded === insight.id ? null : insight.id)}
          />
        ))}
      </div>
    </div>
  );
}

function PriorityCard({ insight }) {
  return (
    <div className="group bg-white border border-line rounded-lg p-5 hover:border-ink/30 transition-colors cursor-pointer">
      <div className="flex items-center gap-2 mb-3">
        <span className="text-[10px] font-medium uppercase tracking-wider text-accent bg-accent/10 px-1.5 py-0.5 rounded">
          {insight.category.split(" ")[0]}
        </span>
        <span className="text-[10px] text-muted tabular-nums">
          {insight.districts}
        </span>
      </div>
      <div className="text-[15px] leading-snug text-ink">
        <FormattedHeadline text={insight.headline} />
      </div>
      <div className="text-[13px] text-muted mt-2 leading-snug">{insight.tail}</div>
      <div className="mt-4 pt-3 border-t border-line flex items-center justify-between">
        <span className="text-[11px] text-muted flex items-center gap-1">
          <Clock size={10} />
          {insight.updated}
        </span>
        <span className="text-[11px] text-ink font-medium flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
          Explore <ArrowUpRight size={11} />
        </span>
      </div>
    </div>
  );
}

function InsightRow({ insight, isOpen, onToggle }) {
  return (
    <div className="py-4 group">
      <button onClick={onToggle} className="w-full text-left flex items-start gap-3">
        <div className="mt-1 text-muted group-hover:text-ink transition-colors">
          {isOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        </div>
        <div className="flex-1 min-w-0">
          <div className="text-[15px] leading-snug text-ink">
            <FormattedHeadline text={insight.headline} />
            <span className="text-muted"> — {insight.tail}</span>
          </div>
        </div>
      </button>
      {isOpen && insight.detail && (
        <div className="ml-7 mt-4 pl-4 border-l-2 border-accent/40 space-y-2">
          {insight.detail.map((line, i) => (
            <div key={i} className="flex gap-3 text-[13px] text-ink/80 leading-relaxed">
              <span className="text-muted tabular-nums mt-0.5">{String(i + 1).padStart(2, "0")}</span>
              <span>{line}</span>
            </div>
          ))}
          <div className="pt-2 flex gap-4 text-[11px]">
            <button className="text-accent hover:underline font-medium">
              Open as Track report →
            </button>
            <button className="text-muted hover:text-ink">
              Ask a follow-up question
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

// ============================================================
// ASK view
// ============================================================
function AskView() {
  const [hasQuery, setHasQuery] = useState(false); // toggle this to see empty state
  const [input, setInput] = useState("");

  // Landing state — centered, generous whitespace, input as the hero
  if (!hasQuery) {
    return (
      <div className="h-[calc(100vh-3.5rem)] bg-ivory overflow-y-auto">
        <EmptyAskState
          input={input}
          setInput={setInput}
          onPick={(q) => { setInput(q); setHasQuery(true); }}
        />
      </div>
    );
  }

  // Active conversation state
  return (
    <div className="flex flex-col h-[calc(100vh-3.5rem)]">
      {/* Header strip */}
      <div className="border-b border-line bg-white px-10 py-5">
        <div className="max-w-[820px] mx-auto">
          <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-accent mb-1">
            Ask
          </div>
          <h1 className="font-display text-[22px] tracking-tight">
            Query PM-JAY data in plain English
          </h1>
        </div>
      </div>

      {/* Conversation area */}
      <div className="flex-1 overflow-y-auto px-10 py-8 bg-ivory">
        <div className="max-w-[820px] mx-auto space-y-8">
          <ConversationThread />
        </div>
      </div>

      {/* Input bar */}
      <div className="border-t border-line bg-white px-10 py-4">
        <div className="max-w-[820px] mx-auto">
          <div className="flex items-center gap-2 bg-ivory border border-line rounded-lg px-4 py-2.5 focus-within:border-ink/40 transition-colors">
            <Search size={14} className="text-muted" />
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Ask about enrolment, claims, hospitals, districts..."
              className="flex-1 bg-transparent text-sm text-ink placeholder:text-muted outline-none"
            />
            <div className="flex items-center gap-1 text-[10px] text-muted">
              <kbd className="px-1.5 py-0.5 bg-white border border-line rounded text-[10px]">↵</kbd>
            </div>
            <button className="ml-1 w-7 h-7 rounded-md bg-ink hover:bg-ink/90 flex items-center justify-center transition-colors">
              <Send size={12} className="text-ivory" strokeWidth={2.25} />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

// Suggested questions grouped by the data domain they query
const landingSuggestions = [
  { category: "Hospitals", q: "How many hospitals are empanelled in Lucknow?" },
  { category: "Hospitals", q: "Top 10 districts by hospital bed capacity" },
  { category: "Claims", q: "Which district has the highest claim value in Cardiology?" },
  { category: "Claims", q: "Show total claim amount by month for last year" },
  { category: "Enrolment", q: "How many beneficiaries were enrolled in 2023?" },
  { category: "Performance", q: "Which hospitals have the highest claim rejection rate?" },
];

function EmptyAskState({ input, setInput, onPick }) {
  return (
    <div className="min-h-full flex flex-col items-center justify-center px-10 py-16">
      <div className="w-full max-w-[720px]">

        {/* Hero */}
        <div className="text-center mb-10">
          <h1 className="font-display text-[44px] leading-[1.05] tracking-tight text-ink mb-4">
            Ask anything about<br />
            <span className="italic text-muted">PM-JAY data.</span>
          </h1>
          <p className="text-[15px] text-muted leading-relaxed max-w-md mx-auto">
            Get answers, insights, and visual analysis in seconds — across claims, empanelment, enrolment, and specialty coverage.
          </p>
        </div>

        {/* Hero input */}
        <div className="mb-12">
          <div className="flex items-center gap-2 bg-white border border-line rounded-xl px-5 py-3.5 focus-within:border-ink/40 transition-colors shadow-sm">
            <Search size={15} className="text-muted" />
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Ask about enrolment, claims, hospitals, districts…"
              className="flex-1 bg-transparent text-[15px] text-ink placeholder:text-muted outline-none"
              autoFocus
            />
            <div className="flex items-center gap-1 text-[10px] text-muted">
              <kbd className="px-1.5 py-0.5 bg-ivory border border-line rounded text-[10px] font-sans">↵</kbd>
            </div>
            <button className="ml-1 w-8 h-8 rounded-lg bg-ink hover:bg-ink/90 flex items-center justify-center transition-colors">
              <Send size={13} className="text-ivory" strokeWidth={2.25} />
            </button>
          </div>
        </div>

        {/* Suggestions — listed, grouped by category */}
        <div>
          <div className="flex items-center gap-3 mb-4">
            <span className="text-[11px] font-semibold uppercase tracking-[0.14em] text-muted">
              Try asking
            </span>
            <div className="flex-1 h-px bg-line" />
          </div>

          <div className="divide-y divide-line border-y border-line">
            {landingSuggestions.map((s, i) => (
              <button
                key={i}
                onClick={() => onPick(s.q)}
                className="w-full text-left py-3 px-1 flex items-center gap-4 group hover:bg-white/40 transition-colors"
              >
                <span className="text-[10px] uppercase tracking-[0.1em] text-muted w-20 shrink-0">
                  {s.category}
                </span>
                <span className="flex-1 text-[14px] text-ink group-hover:text-ink">
                  {s.q}
                </span>
                <ArrowUpRight
                  size={14}
                  className="text-muted opacity-0 group-hover:opacity-100 transition-opacity shrink-0"
                />
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

function ConversationThread() {
  const maxVal = Math.max(...chartData.map((d) => d.value));

  return (
    <>
      {/* User bubble */}
      <div className="flex justify-end">
        <div className="max-w-md">
          <div className="bg-ink text-ivory px-4 py-2.5 rounded-lg rounded-br-sm text-sm">
            How many hospitals in Lucknow?
          </div>
          <div className="text-[10px] text-muted text-right mt-1">12:01 PM · you</div>
        </div>
      </div>

      {/* Assistant response */}
      <div className="space-y-3">
        <div className="flex items-center gap-2">
          <div className="w-5 h-5 rounded-sm bg-teal-deep flex items-center justify-center">
            <Shield size={10} className="text-ivory" strokeWidth={2.5} />
          </div>
          <div className="text-[11px] text-muted">Assistant · 12:01 PM</div>
        </div>

        <div className="text-[15px] text-ink leading-relaxed max-w-2xl">
          There are <span className="font-semibold tabular-nums">28 empanelled hospitals</span> in
          Lucknow district, with a total of <span className="font-semibold tabular-nums">3,719 beds</span>.
          Private NGO hospitals lead both by facility count and bed capacity.
        </div>

        {/* Result card */}
        <div className="bg-white border border-line rounded-lg overflow-hidden">
          <div className="border-b border-line px-4 py-2.5 flex items-center gap-3 bg-ivory/40">
            <div className="text-[11px] font-semibold uppercase tracking-[0.1em] text-ink">
              Hospitals in Lucknow
            </div>
            <div className="text-[11px] text-muted">by type · 7 rows</div>
          </div>

          <div className="grid grid-cols-2 divide-x divide-line">
            {/* Table */}
            <div className="p-0">
              <table className="w-full text-[13px] tabular-nums">
                <thead>
                  <tr className="text-[10px] uppercase tracking-wider text-muted">
                    <th className="text-left font-medium px-4 py-2.5">Type</th>
                    <th className="text-left font-medium px-4 py-2.5">Sub-type</th>
                    <th className="text-right font-medium px-4 py-2.5">Count</th>
                    <th className="text-right font-medium px-4 py-2.5">Beds</th>
                  </tr>
                </thead>
                <tbody>
                  {tableData.map((row, i) => (
                    <tr key={i} className="border-t border-line/70 hover:bg-ivory/40">
                      <td className="px-4 py-2 text-ink text-[11px]">{row.type}</td>
                      <td className="px-4 py-2 text-ink">{row.sub}</td>
                      <td className="px-4 py-2 text-right text-ink">{row.count}</td>
                      <td className="px-4 py-2 text-right text-ink">
                        {row.beds.toLocaleString()}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Horizontal bar chart — single color */}
            <div className="p-4">
              <div className="text-[11px] text-muted mb-3">Hospitals by sub-type</div>
              <div className="space-y-1.5">
                {chartData.map((d, i) => (
                  <div key={i} className="flex items-center gap-3 group">
                    <div className="w-28 text-[11px] text-muted text-right truncate">
                      {d.label}
                    </div>
                    <div className="flex-1 relative h-5 bg-ivory/60 rounded-sm overflow-hidden">
                      <div
                        className="h-full bg-teal-deep transition-all group-hover:brightness-110"
                        style={{ width: `${(d.value / maxVal) * 100}%` }}
                      />
                    </div>
                    <div className="w-6 text-[11px] tabular-nums text-ink font-medium">
                      {d.value}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>
    </>
  );
}

// ============================================================
// TRACK view
// ============================================================

const reports = [
  { id: "speciality", label: "Speciality Coverage", icon: MapPin, desc: "Hospital reach by specialty" },
  { id: "performance", label: "Hospital Performance", icon: Activity, desc: "Claim volume & outcomes" },
  { id: "enrolment", label: "Beneficiary Enrolment", icon: Users, desc: "Card issuance by geography" },
];

const specialties = [
  "Cardiology",
  "Oncology",
  "Neurology",
  "Orthopedics",
  "Kidney & Urology",
  "Gastroenterology",
  "Gynecology",
  "General Surgery & Burns",
  "Pediatrics",
  "Ophthalmology",
  "ENT",
  "Pulmonology",
];

const underservedBlocks = [
  { rank: 1, block: "Obra", district: "Sonbhadra", population: "2.1L" },
  { rank: 2, block: "Tindwari", district: "Banda", population: "1.8L" },
  { rank: 3, block: "Nautanwa", district: "Maharajganj", population: "1.6L" },
  { rank: 4, block: "Puranpur", district: "Pilibhit", population: "1.4L" },
  { rank: 5, block: "Chakia", district: "Chandauli", population: "1.3L" },
];

function TrackView() {
  const [activeReport, setActiveReport] = useState("speciality");
  const [activeSpecialty, setActiveSpecialty] = useState("Cardiology");
  const [specialtySearch, setSpecialtySearch] = useState("");

  const filteredSpecialties = specialties.filter((s) =>
    s.toLowerCase().includes(specialtySearch.toLowerCase())
  );

  return (
    <div className="h-[calc(100vh-3.5rem)] flex">
      {/* Reports column */}
      <aside className="w-64 border-r border-line bg-white/60 px-4 py-6 flex flex-col">
        <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-accent mb-4 px-2">
          Reports
        </div>
        <nav className="space-y-1">
          {reports.map((r) => {
            const Icon = r.icon;
            const active = activeReport === r.id;
            return (
              <button
                key={r.id}
                onClick={() => setActiveReport(r.id)}
                className={`w-full text-left px-3 py-2.5 rounded-md transition-colors group ${
                  active
                    ? "bg-ink text-ivory"
                    : "hover:bg-ink/[0.04] text-ink"
                }`}
              >
                <div className="flex items-center gap-2.5">
                  <Icon size={14} className={active ? "opacity-80" : "text-muted"} strokeWidth={2} />
                  <div className="text-[13px] font-medium">{r.label}</div>
                </div>
                <div className={`text-[11px] mt-0.5 ml-6 leading-snug ${active ? "text-ivory/60" : "text-muted"}`}>
                  {r.desc}
                </div>
              </button>
            );
          })}
        </nav>

        <div className="mt-auto pt-4 border-t border-line">
          <button className="w-full text-[11px] text-muted hover:text-ink flex items-center gap-1.5 px-3 py-1.5 transition-colors">
            <FileText size={11} />
            Download full report (PDF)
          </button>
        </div>
      </aside>

      {/* Specialty list column */}
      <div className="w-64 border-r border-line bg-white/40 flex flex-col">
        <div className="px-4 pt-6 pb-3 border-b border-line">
          <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-muted mb-3">
            Specialty
          </div>
          <div className="relative">
            <Search size={12} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-muted" />
            <input
              value={specialtySearch}
              onChange={(e) => setSpecialtySearch(e.target.value)}
              placeholder="Search specialties"
              className="w-full pl-7 pr-3 py-1.5 text-[12px] bg-ivory border border-line rounded-md outline-none focus:border-ink/30 placeholder:text-muted text-ink"
            />
          </div>
        </div>
        <div className="flex-1 overflow-y-auto py-2">
          {filteredSpecialties.length === 0 ? (
            <div className="px-4 py-3 text-[12px] text-muted italic">No matches</div>
          ) : (
            filteredSpecialties.map((s) => {
              const active = activeSpecialty === s;
              return (
                <button
                  key={s}
                  onClick={() => setActiveSpecialty(s)}
                  className={`w-full text-left px-4 py-2 text-[13px] transition-colors flex items-center justify-between group ${
                    active
                      ? "bg-accent/10 text-ink font-medium border-l-2 border-accent"
                      : "text-ink hover:bg-ink/[0.03] border-l-2 border-transparent"
                  }`}
                >
                  <span>{s}</span>
                  {active && <ChevronRight size={12} className="text-accent" />}
                </button>
              );
            })
          )}
        </div>
      </div>

      {/* Map column */}
      <div className="flex-1 relative bg-ivory overflow-hidden">
        {/* Map header */}
        <div className="absolute top-0 left-0 right-0 z-[5] bg-gradient-to-b from-white/90 to-white/0 px-6 pt-5 pb-10">
          <div className="flex items-start justify-between">
            <div>
              <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-accent mb-1">
                Speciality Coverage · {activeSpecialty}
              </div>
              <h1 className="font-display text-[22px] tracking-tight text-ink">
                Where {activeSpecialty} care is reaching Uttar Pradesh
              </h1>
              <p className="text-[12px] text-muted mt-1 max-w-lg leading-snug">
                Each block shaded by population × distance to the nearest empanelled {activeSpecialty.toLowerCase()} hospital.
              </p>
            </div>
          </div>
        </div>

        {/* Simulated map */}
        <SimulatedMap />

        {/* Zoom controls */}
        <div className="absolute left-4 top-28 z-[5] bg-white border border-line rounded-md shadow-sm flex flex-col">
          <button className="w-8 h-8 flex items-center justify-center hover:bg-ivory border-b border-line">
            <Plus size={14} className="text-ink" />
          </button>
          <button className="w-8 h-8 flex items-center justify-center hover:bg-ivory">
            <Minus size={14} className="text-ink" />
          </button>
        </div>

        {/* Underserved panel */}
        <div className="absolute top-28 right-4 z-[5] w-72 bg-white border border-line rounded-lg shadow-sm overflow-hidden">
          <div className="px-4 py-3 border-b border-line bg-ivory/40">
            <div className="text-[11px] font-semibold uppercase tracking-[0.12em] text-ink">
              Most underserved blocks
            </div>
            <div className="text-[11px] text-muted mt-0.5">
              by population × distance to nearest hospital
            </div>
          </div>
          <div className="divide-y divide-line">
            {underservedBlocks.map((b) => (
              <div key={b.rank} className="px-4 py-2.5 hover:bg-ivory/40 cursor-pointer flex items-center gap-3 group">
                <div className="text-[11px] font-semibold tabular-nums text-muted w-4">
                  {b.rank}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="text-[13px] text-ink font-medium leading-tight">{b.block}</div>
                  <div className="text-[11px] text-muted">{b.district}</div>
                </div>
                <div className="text-[11px] tabular-nums text-muted">{b.population}</div>
                <ArrowUpRight size={11} className="text-muted opacity-0 group-hover:opacity-100 transition-opacity" />
              </div>
            ))}
          </div>
        </div>

        {/* Legend — pinned to map corner where it belongs */}
        <div className="absolute bottom-4 right-4 z-[5] bg-white border border-line rounded-md shadow-sm px-3 py-2.5">
          <div className="text-[10px] font-semibold uppercase tracking-[0.1em] text-ink mb-1.5">
            Underservice
          </div>
          <div className="text-[10px] text-muted mb-2 leading-tight">
            Population × distance to nearest hospital
          </div>
          <div className="flex items-center gap-0 h-3 w-40">
            <div className="flex-1 h-full" style={{ background: "#FEF3C7" }} />
            <div className="flex-1 h-full" style={{ background: "#FCD34D" }} />
            <div className="flex-1 h-full" style={{ background: "#F59E0B" }} />
            <div className="flex-1 h-full" style={{ background: "#D97706" }} />
            <div className="flex-1 h-full" style={{ background: "#B45309" }} />
            <div className="flex-1 h-full" style={{ background: "#78350F" }} />
          </div>
          <div className="flex justify-between text-[10px] text-muted mt-1">
            <span>Low</span>
            <span>High</span>
          </div>
        </div>
      </div>
    </div>
  );
}

// Simulated map — SVG with UP shape and heat blocks
function SimulatedMap() {
  // A rough abstraction of Uttar Pradesh outline with simulated heatmap blocks
  return (
    <div className="absolute inset-0 flex items-center justify-center pt-20">
      <svg viewBox="0 0 600 500" className="w-full h-full max-w-3xl opacity-95" style={{ maxHeight: "90%" }}>
        {/* Subtle grid bg to suggest a map */}
        <defs>
          <pattern id="grid" width="30" height="30" patternUnits="userSpaceOnUse">
            <path d="M 30 0 L 0 0 0 30" fill="none" stroke="#E8E4DC" strokeWidth="0.5" />
          </pattern>
          <pattern id="watergrid" width="10" height="10" patternUnits="userSpaceOnUse">
            <circle cx="5" cy="5" r="0.5" fill="#C7DDE8" />
          </pattern>
        </defs>

        {/* Background */}
        <rect width="600" height="500" fill="url(#grid)" />
        <rect width="600" height="500" fill="url(#watergrid)" opacity="0.3" />

        {/* Simplified UP outline */}
        <path
          d="M 80 180 Q 100 130 180 115 Q 240 105 300 120 Q 360 100 420 110 Q 490 120 520 160 Q 540 220 510 270 Q 490 320 440 350 Q 380 380 330 385 Q 270 395 220 375 Q 160 360 120 320 Q 85 280 75 230 Z"
          fill="#FEFCF8"
          stroke="#1F4E5F"
          strokeWidth="1.5"
          opacity="0.95"
        />

        {/* Heatmap blocks — clustered inside UP shape */}
        {/* High intensity clusters (east & south-east) */}
        {[
          { cx: 420, cy: 260, r: 16, c: "#78350F" },
          { cx: 450, cy: 280, r: 13, c: "#B45309" },
          { cx: 390, cy: 290, r: 14, c: "#B45309" },
          { cx: 410, cy: 310, r: 11, c: "#D97706" },
          { cx: 460, cy: 230, r: 10, c: "#78350F" },
          { cx: 440, cy: 320, r: 12, c: "#D97706" },
          // Mid intensity
          { cx: 350, cy: 240, r: 11, c: "#D97706" },
          { cx: 320, cy: 270, r: 10, c: "#F59E0B" },
          { cx: 370, cy: 200, r: 9, c: "#F59E0B" },
          { cx: 300, cy: 220, r: 9, c: "#F59E0B" },
          { cx: 280, cy: 290, r: 10, c: "#D97706" },
          { cx: 340, cy: 330, r: 9, c: "#F59E0B" },
          // Lower intensity (west)
          { cx: 220, cy: 200, r: 8, c: "#FCD34D" },
          { cx: 180, cy: 220, r: 9, c: "#FCD34D" },
          { cx: 240, cy: 250, r: 8, c: "#FCD34D" },
          { cx: 200, cy: 280, r: 7, c: "#FEF3C7" },
          { cx: 160, cy: 260, r: 8, c: "#FEF3C7" },
          { cx: 260, cy: 180, r: 7, c: "#FEF3C7" },
          { cx: 140, cy: 200, r: 7, c: "#FEF3C7" },
          // Scattered
          { cx: 380, cy: 350, r: 8, c: "#F59E0B" },
          { cx: 250, cy: 330, r: 8, c: "#FCD34D" },
          { cx: 480, cy: 200, r: 9, c: "#B45309" },
          { cx: 470, cy: 320, r: 8, c: "#D97706" },
        ].map((b, i) => (
          <circle
            key={i}
            cx={b.cx}
            cy={b.cy}
            r={b.r}
            fill={b.c}
            opacity="0.75"
            style={{
              mixBlendMode: "multiply",
            }}
          />
        ))}

        {/* Three highlighted underserved block markers */}
        {[
          { cx: 455, cy: 340, label: "Obra" },
          { cx: 360, cy: 260, label: "Tindwari" },
          { cx: 470, cy: 240, label: "Nautanwa" },
        ].map((m, i) => (
          <g key={i}>
            <circle cx={m.cx} cy={m.cy} r="6" fill="#1A1A1A" />
            <circle cx={m.cx} cy={m.cy} r="3" fill="#FAF7F2" />
          </g>
        ))}

        {/* Labels for a few cities to ground the map */}
        {[
          { x: 260, y: 240, label: "Lucknow" },
          { x: 200, y: 170, label: "Agra" },
          { x: 430, y: 290, label: "Varanasi" },
          { x: 360, y: 190, label: "Bareilly" },
        ].map((c, i) => (
          <g key={i}>
            <circle cx={c.x} cy={c.y} r="2" fill="#1A1A1A" />
            <text
              x={c.x + 5}
              y={c.y - 4}
              fontSize="9"
              fill="#1A1A1A"
              fontFamily="Inter, sans-serif"
              fontWeight="500"
            >
              {c.label}
            </text>
          </g>
        ))}

        {/* Attribution */}
        <text
          x="590"
          y="492"
          fontSize="8"
          fill="#8A857B"
          textAnchor="end"
          fontFamily="Inter, sans-serif"
        >
          © OpenStreetMap · illustrative
        </text>
      </svg>
    </div>
  );
}

// ============================================================
// Root
// ============================================================
export default function App() {
  const [mode, setMode] = useState("ask");

  return (
    <>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,400;9..144,500;9..144,600&family=Inter:wght@400;500;600&display=swap');
        :root {
          --ivory: #FAF7F2;
          --ink: #1A1A1A;
          --line: #E8E4DC;
          --muted: #8A857B;
          --accent: #C8501E;
          --teal-deep: #1F4E5F;
        }
        body {
          font-feature-settings: 'ss01', 'cv11';
        }
        .font-sans { font-family: 'Inter', -apple-system, system-ui, sans-serif; }
        .font-display { font-family: 'Fraunces', Georgia, serif; font-optical-sizing: auto; }
        .bg-ivory { background-color: var(--ivory); }
        .text-ivory { color: var(--ivory); }
        .bg-ink { background-color: var(--ink); }
        .text-ink { color: var(--ink); }
        .border-line { border-color: var(--line); }
        .bg-line { background-color: var(--line); }
        .divide-line > :not([hidden]) ~ :not([hidden]) { border-color: var(--line); }
        .text-muted { color: var(--muted); }
        .text-accent { color: var(--accent); }
        .bg-accent { background-color: var(--accent); }
        .bg-accent\\/10 { background-color: rgba(200, 80, 30, 0.1); }
        .border-accent\\/40 { border-color: rgba(200, 80, 30, 0.4); }
        .text-teal-deep { color: var(--teal-deep); }
        .bg-teal-deep { background-color: var(--teal-deep); }
        .tabular-nums { font-variant-numeric: tabular-nums; }
      `}</style>
      <Shell mode={mode} setMode={setMode}>
        {mode === "discover" && <DiscoverView />}
        {mode === "ask" && <AskView />}
        {mode === "track" && <TrackView />}
      </Shell>
    </>
  );
}
