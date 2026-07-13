import { useState, type ReactNode } from "react";
import { motion } from "framer-motion";
import { Pencil, Check, X, Download, ArrowUp, ArrowDown, ArrowUpDown, BarChart3, CalendarDays, Shield } from "lucide-react";
import { BarChart, Bar, XAxis as ReXAxis, YAxis as ReYAxis, CartesianGrid, Tooltip as ReTooltip, ResponsiveContainer } from "recharts";
import { format, parse } from "date-fns";
import type { Chip, Message } from "@/types/chat";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Calendar } from "@/components/ui/calendar";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { cn } from "@/lib/utils";

interface MessageBubbleProps {
  message: Message;
  onDateRangeUpdate?: (messageId: string, startDate: string, endDate: string) => void;
  // Sends a chip's text as a new user message (clarifications, suggestions).
  // fromChip=true tells the backend the text is a generated catalog question,
  // so it skips the follow-up classifier and routes straight to matching.
  onSend?: (text: string, fromChip?: boolean) => void;
}

function ChipRow({
  heading,
  chips,
  onSend,
}: {
  heading?: string;
  chips: Chip[];
  onSend: (text: string, fromChip?: boolean) => void;
}) {
  if (chips.length === 0) return null;
  return (
    <div className="flex items-center gap-2 flex-wrap">
      {heading && (
        <span className="text-[10px] uppercase tracking-[0.1em] text-muted-design">
          {heading}
        </span>
      )}
      {chips.map((chip, i) => (
        <button
          key={i}
          onClick={() => onSend(chip.send_text, true)}
          className="rounded-full border border-line bg-white px-3 py-1 text-xs text-ink hover:border-ink/40 hover:bg-ivory transition-colors text-left"
        >
          {chip.label}
        </button>
      ))}
    </div>
  );
}

function downloadCsv(rows: Record<string, unknown>[]) {
  const headers = Object.keys(rows[0]);
  const csvRows = [
    headers.join(","),
    ...rows.map((row) =>
      headers.map((h) => {
        const val = row[h];
        const str = val == null ? "" : String(val);
        return str.includes(",") || str.includes('"') || str.includes("\n")
          ? `"${str.replace(/"/g, '""')}"`
          : str;
      }).join(",")
    ),
  ];
  const blob = new Blob([csvRows.join("\n")], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `query-result-${Date.now()}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}

function isNumericColumn(rows: Record<string, unknown>[], key: string) {
  return rows.some((row) => {
    const val = row[key];
    return val != null && !isNaN(Number(val));
  });
}

type SortDir = "asc" | "desc" | null;

function ResultTable({
  rows,
  toolbarExtra,
}: {
  rows: Record<string, unknown>[];
  // Rendered alongside Bar Chart / Download CSV — the date-range control lives here.
  toolbarExtra?: ReactNode;
}) {
  const [sortKey, setSortKey] = useState<string | null>(null);
  const [sortDir, setSortDir] = useState<SortDir>(null);
  const [showChart, setShowChart] = useState(false);
  const [showAll, setShowAll] = useState(false);

  const headers = Object.keys(rows[0]);
  const numericCols = new Set(headers.filter((h) => isNumericColumn(rows, h)));

  const [xAxis, setXAxis] = useState(headers[0]);
  const [yAxis, setYAxis] = useState(() => {
    const firstNumeric = headers.slice(1).find((h) => numericCols.has(h));
    return firstNumeric ?? headers[1] ?? headers[0];
  });

  const handleSort = (key: string) => {
    if (sortKey === key) {
      const next: SortDir = sortDir === "asc" ? "desc" : null;
      setSortDir(next);
      if (next === null) setSortKey(null);
    } else {
      setSortKey(key);
      setSortDir("asc");
    }
  };

  const sortedRows = sortKey && sortDir
    ? [...rows].sort((a, b) => {
        const aVal = Number(a[sortKey]);
        const bVal = Number(b[sortKey]);
        if (isNaN(aVal) || isNaN(bVal)) return 0;
        return sortDir === "asc" ? aVal - bVal : bVal - aVal;
      })
    : rows;

  return (
    <div className="space-y-2">
      {/* Result card */}
      <div className="inline-block max-w-full align-top bg-white border border-line rounded-lg overflow-hidden">
        {/* Card header */}
        <div className="border-b border-line px-4 py-2.5 flex items-center gap-3 bg-ivory/40">
          <div className="text-[11px] font-semibold uppercase tracking-[0.1em] text-ink">
            Query Result
          </div>
          <div className="text-[11px] text-muted-design">
            {rows.length} row{rows.length !== 1 ? "s" : ""}
          </div>
        </div>

        <div className={`${showChart ? "grid grid-cols-2 divide-x divide-line" : ""}`}>
          {/* Table */}
          <div className="p-0">
            <div className="overflow-x-auto">
              <table className="text-[13px]">
                <thead>
                  <tr className="text-[10px] uppercase tracking-wider text-muted-design">
                    {headers.map((key) => (
                      <th
                        key={key}
                        className="text-left font-medium px-4 py-2.5 whitespace-nowrap"
                      >
                        {numericCols.has(key) ? (
                          <button
                            onClick={() => handleSort(key)}
                            className="inline-flex items-center gap-1 hover:text-ink transition-colors"
                          >
                            {key}
                            {sortKey === key && sortDir === "asc" ? (
                              <ArrowUp className="h-3 w-3" />
                            ) : sortKey === key && sortDir === "desc" ? (
                              <ArrowDown className="h-3 w-3" />
                            ) : (
                              <ArrowUpDown className="h-3 w-3 opacity-40" />
                            )}
                          </button>
                        ) : (
                          key
                        )}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {(showAll ? sortedRows : sortedRows.slice(0, 10)).map((row, i) => (
                    <tr key={i} className="border-t border-line/70 hover:bg-ivory/40">
                      {Object.entries(row).map(([key, val], j) => (
                        <td
                          key={j}
                          className={`px-4 py-2 text-ink whitespace-nowrap ${
                            numericCols.has(headers[j]) ? "text-right" : ""
                          }`}
                        >
                          {val == null ? "—" : String(val)}
                        </td>
                      ))}
                    </tr>
                  ))}
                  {!showAll && sortedRows.length > 10 && (
                    <tr>
                      <td colSpan={headers.length} className="px-4 py-2 text-center">
                        <button
                          onClick={() => setShowAll(true)}
                          className="text-[12px] text-muted-design hover:text-ink transition-colors"
                        >
                          Show all {sortedRows.length} rows
                        </button>
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>

          {/* Chart section */}
          {showChart && (
            <div className="p-4">
              <div className="flex items-center gap-3 flex-wrap mb-3">
                <div className="flex items-center gap-1.5">
                  <span className="text-[11px] text-muted-design">X:</span>
                  <Select value={xAxis} onValueChange={setXAxis}>
                    <SelectTrigger className="h-7 w-[120px] text-xs border-line">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {headers.map((h) => (
                        <SelectItem key={h} value={h} className="text-xs">{h}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="flex items-center gap-1.5">
                  <span className="text-[11px] text-muted-design">Y:</span>
                  <Select value={yAxis} onValueChange={setYAxis}>
                    <SelectTrigger className="h-7 w-[120px] text-xs border-line">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {headers.map((h) => (
                        <SelectItem key={h} value={h} className="text-xs">{h}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>
              <ResponsiveContainer width="100%" height={250}>
                <BarChart data={sortedRows.map((row) => ({ ...row, [yAxis]: Number(row[yAxis]) || 0 }))}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#E8E4DC" />
                  <ReXAxis dataKey={xAxis} tick={{ fontSize: 11, fill: '#8A857B' }} />
                  <ReYAxis tick={{ fontSize: 11, fill: '#8A857B' }} />
                  <ReTooltip
                    contentStyle={{ fontSize: 12, borderRadius: 8, border: '1px solid #E8E4DC' }}
                  />
                  <Bar dataKey={yAxis} fill="#1F4E5F" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </div>
      </div>

      {/* Action buttons */}
      <div className="flex items-center gap-2 flex-wrap">
        <button
          onClick={() => setShowChart(!showChart)}
          className="inline-flex items-center gap-1.5 rounded-md border border-line bg-white px-2.5 py-1 text-xs text-muted-design hover:text-ink hover:border-ink/30 transition-colors"
        >
          <BarChart3 className="h-3 w-3" />
          {showChart ? "Hide Chart" : "Bar Chart"}
        </button>
        <button
          onClick={() => downloadCsv(sortedRows)}
          className="inline-flex items-center gap-1.5 rounded-md border border-line bg-white px-2.5 py-1 text-xs text-muted-design hover:text-ink hover:border-ink/30 transition-colors"
        >
          <Download className="h-3 w-3" />
          Download CSV
        </button>
        {toolbarExtra}
      </div>
    </div>
  );
}

function formatDateLabel(dateStr: string) {
  try {
    const d = parse(dateStr, "yyyy-MM-dd", new Date());
    return format(d, "MMM d, yyyy");
  } catch {
    return dateStr;
  }
}

function DateRangePill({
  message,
  onDateRangeUpdate,
}: {
  message: Message;
  onDateRangeUpdate?: (messageId: string, startDate: string, endDate: string) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [startDate, setStartDate] = useState<Date | undefined>(() =>
    message.date_range ? parse(message.date_range.start_date, "yyyy-MM-dd", new Date()) : undefined
  );
  const [endDate, setEndDate] = useState<Date | undefined>(() =>
    message.date_range ? parse(message.date_range.end_date, "yyyy-MM-dd", new Date()) : undefined
  );

  if (!message.date_range) return null;

  const label = `${formatDateLabel(message.date_range.start_date)} – ${formatDateLabel(message.date_range.end_date)}`;

  const handleConfirm = () => {
    if (startDate && endDate && onDateRangeUpdate) {
      onDateRangeUpdate(
        message.id,
        format(startDate, "yyyy-MM-dd"),
        format(endDate, "yyyy-MM-dd")
      );
    }
    setEditing(false);
  };

  const handleCancel = () => {
    setStartDate(parse(message.date_range!.start_date, "yyyy-MM-dd", new Date()));
    setEndDate(parse(message.date_range!.end_date, "yyyy-MM-dd", new Date()));
    setEditing(false);
  };

  if (!editing) {
    return (
      <button
        onClick={() => setEditing(true)}
        className="inline-flex items-center gap-1.5 rounded-md border border-line bg-white px-2.5 py-1 text-xs text-muted-design hover:text-ink hover:border-ink/30 transition-colors"
      >
        <CalendarDays className="h-3 w-3" />
        <span>{label}</span>
        <Pencil className="h-3 w-3" />
      </button>
    );
  }

  return (
    <div className="flex flex-wrap items-center gap-2">
      <Popover>
        <PopoverTrigger asChild>
          <Button variant="outline" size="sm" className="h-7 text-xs border-line">
            {startDate ? format(startDate, "MMM d, yyyy") : "Start"}
          </Button>
        </PopoverTrigger>
        <PopoverContent className="w-auto p-0" align="start">
          <Calendar
            mode="single"
            selected={startDate}
            onSelect={setStartDate}
            initialFocus
            className={cn("p-3 pointer-events-auto")}
          />
        </PopoverContent>
      </Popover>
      <span className="text-xs text-muted-design">–</span>
      <Popover>
        <PopoverTrigger asChild>
          <Button variant="outline" size="sm" className="h-7 text-xs border-line">
            {endDate ? format(endDate, "MMM d, yyyy") : "End"}
          </Button>
        </PopoverTrigger>
        <PopoverContent className="w-auto p-0" align="start">
          <Calendar
            mode="single"
            selected={endDate}
            onSelect={setEndDate}
            initialFocus
            className={cn("p-3 pointer-events-auto")}
          />
        </PopoverContent>
      </Popover>
      <Button size="sm" variant="ghost" className="h-7 w-7 p-0" onClick={handleConfirm}>
        <Check className="h-3.5 w-3.5 text-teal-deep" />
      </Button>
      <Button size="sm" variant="ghost" className="h-7 w-7 p-0" onClick={handleCancel}>
        <X className="h-3.5 w-3.5 text-muted-design" />
      </Button>
    </div>
  );
}

export function MessageBubble({ message, onDateRangeUpdate, onSend }: MessageBubbleProps) {
  const isUser = message.role === "user";
  const hasResult = !!message.result && message.result.length > 0;
  const dateControl =
    !isUser && message.date_filter_applied && message.date_range ? (
      <DateRangePill message={message} onDateRangeUpdate={onDateRangeUpdate} />
    ) : null;

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2 }}
      className={`flex ${isUser ? "justify-end" : "justify-start"}`}
    >
      <div className={`max-w-[90%] space-y-3 ${isUser ? "" : ""}`}>
        {/* Assistant identity row */}
        {!isUser && (
          <div className="flex items-center gap-2">
            <div className="w-5 h-5 rounded-sm bg-teal-deep flex items-center justify-center">
              <Shield size={10} className="text-ivory" strokeWidth={2.5} />
            </div>
            <div className="text-[11px] text-muted-design">
              Assistant ·{" "}
              {new Date(message.timestamp).toLocaleTimeString([], {
                hour: "2-digit",
                minute: "2-digit",
              })}
            </div>
          </div>
        )}

        {/* Error state */}
        {message.error && (
          <div className="text-[15px] text-ink leading-relaxed max-w-2xl">
            <p className="whitespace-pre-wrap break-words">{message.error.replace(/\*/g, "")}</p>
          </div>
        )}

        {/* Main content */}
        {message.content && isUser && (
          <div className="flex justify-end">
            <div>
              <div className="bg-ink text-ivory px-4 py-2.5 rounded-lg rounded-br-sm text-sm leading-relaxed">
                <p className="whitespace-pre-wrap break-words">{message.content.replace(/\*/g, "")}</p>
              </div>
              <div className="text-[10px] text-muted-design text-right mt-1">
                {new Date(message.timestamp).toLocaleTimeString([], {
                  hour: "2-digit",
                  minute: "2-digit",
                })}{" "}
                · you
              </div>
            </div>
          </div>
        )}

        {message.content && !isUser && (
          <div className="text-[15px] text-ink leading-relaxed max-w-2xl">
            <p className="whitespace-pre-wrap break-words">{message.content.replace(/\*/g, "")}</p>
          </div>
        )}

        {/* Result table — the date-range control rides in its toolbar row */}
        {hasResult && (
          <ResultTable rows={message.result!} toolbarExtra={dateControl} />
        )}

        {/* Clarification options: tap-to-pick interpretations */}
        {!isUser && onSend && message.clarification && (
          <ChipRow chips={message.clarification.options} onSend={onSend} />
        )}

        {/* Next-question suggestions (pre-filled catalog templates) */}
        {!isUser && onSend && message.suggestions && message.suggestions.length > 0 && (
          <ChipRow heading="Try next" chips={message.suggestions} onSend={onSend} />
        )}

        {/* Date range pill — standalone only when there's no table to host it */}
        {!hasResult && dateControl}
      </div>
    </motion.div>
  );
}
