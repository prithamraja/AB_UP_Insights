import { useState } from "react";
import { motion } from "framer-motion";
import { AlertCircle, AlertTriangle, Pencil, Check, X, Download, ArrowUp, ArrowDown, ArrowUpDown, BarChart3 } from "lucide-react";
import { BarChart, Bar, XAxis as ReXAxis, YAxis as ReYAxis, CartesianGrid, Tooltip as ReTooltip, ResponsiveContainer } from "recharts";
import { format, parse } from "date-fns";
import type { Message } from "@/types/chat";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Calendar } from "@/components/ui/calendar";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { cn } from "@/lib/utils";

interface MessageBubbleProps {
  message: Message;
  onDateRangeUpdate?: (messageId: string, startDate: string, endDate: string) => void;
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

function ResultTable({ rows }: { rows: Record<string, unknown>[] }) {
  const [sortKey, setSortKey] = useState<string | null>(null);
  const [sortDir, setSortDir] = useState<SortDir>(null);
  const [showChart, setShowChart] = useState(false);

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
    <div className="space-y-1.5">
      <div className={`flex gap-3 ${showChart ? "flex-row" : "flex-col"}`}>
        {/* Table */}
        <div className={`rounded-lg border border-border overflow-hidden ${showChart ? "flex-1 min-w-0" : ""}`}>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="bg-muted/60">
                  {headers.map((key) => (
                    <th
                      key={key}
                      className="px-3 py-2 text-left font-semibold text-muted-foreground whitespace-nowrap"
                    >
                      {numericCols.has(key) ? (
                        <button
                          onClick={() => handleSort(key)}
                          className="inline-flex items-center gap-1 hover:text-foreground transition-colors"
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
                {sortedRows.map((row, i) => (
                  <tr key={i} className="border-t border-border">
                    {Object.values(row).map((val, j) => (
                      <td
                        key={j}
                        className="px-3 py-1.5 text-foreground/80 whitespace-nowrap"
                      >
                        {val == null ? "—" : String(val)}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* Chart section — right side */}
        {showChart && (
          <div className="flex-1 min-w-[300px] space-y-2">
            <div className="flex items-center gap-3 flex-wrap">
              <div className="flex items-center gap-1.5">
                <span className="text-xs text-muted-foreground">X:</span>
                <Select value={xAxis} onValueChange={setXAxis}>
                  <SelectTrigger className="h-7 w-[120px] text-xs">
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
                <span className="text-xs text-muted-foreground">Y:</span>
                <Select value={yAxis} onValueChange={setYAxis}>
                  <SelectTrigger className="h-7 w-[120px] text-xs">
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
            <div className="rounded-lg border border-border bg-background p-3">
              <ResponsiveContainer width="100%" height={250}>
                <BarChart data={sortedRows.map((row) => ({ ...row, [yAxis]: Number(row[yAxis]) || 0 }))}>
                  <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
                  <ReXAxis dataKey={xAxis} tick={{ fontSize: 11 }} className="text-muted-foreground" />
                  <ReYAxis tick={{ fontSize: 11 }} className="text-muted-foreground" />
                  <ReTooltip
                    contentStyle={{ fontSize: 12, borderRadius: 8, border: '1px solid hsl(var(--border))' }}
                  />
                  <Bar dataKey={yAxis} fill="#0f4c5c" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        )}
      </div>

      <div className="flex items-center gap-2">
        <button
          onClick={() => setShowChart(!showChart)}
          className="inline-flex items-center gap-1.5 rounded-md border border-border bg-muted/50 px-2.5 py-1 text-xs text-muted-foreground hover:bg-muted transition-colors"
        >
          <BarChart3 className="h-3 w-3" />
          {showChart ? "Hide Chart" : "Bar Chart"}
        </button>
        <button
          onClick={() => downloadCsv(sortedRows)}
          className="inline-flex items-center gap-1.5 rounded-md border border-border bg-muted/50 px-2.5 py-1 text-xs text-muted-foreground hover:bg-muted transition-colors"
        >
          <Download className="h-3 w-3" />
          Download CSV
        </button>
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
        className="inline-flex items-center gap-1.5 rounded-full border border-border bg-muted/50 px-3 py-1 text-xs text-muted-foreground hover:bg-muted transition-colors"
      >
        <span>{label}</span>
        <Pencil className="h-3 w-3" />
      </button>
    );
  }

  return (
    <div className="flex flex-wrap items-center gap-2">
      <Popover>
        <PopoverTrigger asChild>
          <Button variant="outline" size="sm" className="h-7 text-xs">
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
      <span className="text-xs text-muted-foreground">–</span>
      <Popover>
        <PopoverTrigger asChild>
          <Button variant="outline" size="sm" className="h-7 text-xs">
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
        <Check className="h-3.5 w-3.5 text-primary" />
      </Button>
      <Button size="sm" variant="ghost" className="h-7 w-7 p-0" onClick={handleCancel}>
        <X className="h-3.5 w-3.5 text-muted-foreground" />
      </Button>
    </div>
  );
}

export function MessageBubble({ message, onDateRangeUpdate }: MessageBubbleProps) {
  const isUser = message.role === "user";
  const isFallback = message.tier === "fallback";

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2 }}
      className={`flex ${isUser ? "justify-end" : "justify-start"}`}
    >
      <div className="max-w-[90%] space-y-2">
        {/* Error state */}
        {message.error && (
          <div className="flex items-start gap-2 rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive">
            <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
            <p>{message.error}</p>
          </div>
        )}

        {/* Main bubble */}
        {message.content && (
          <div
            className={`rounded-2xl px-4 py-2.5 text-sm leading-relaxed shadow-sm ${
              isUser
                ? "bg-chat-user text-chat-user-foreground rounded-br-md"
                : isFallback
                  ? "bg-amber-50 text-amber-900 border border-amber-200 rounded-bl-md"
                  : "bg-chat-bot text-chat-bot-foreground rounded-bl-md"
            }`}
          >
            {isFallback && (
              <div className="flex items-center gap-1.5 mb-1.5 text-amber-600">
                <AlertTriangle className="h-3.5 w-3.5" />
                <span className="text-[11px] font-medium">Approximate answer</span>
              </div>
            )}
            <p className="whitespace-pre-wrap break-words">{message.content}</p>
            <span
              className={`mt-1 block text-[10px] ${
                isUser
                  ? "text-primary-foreground/60"
                  : isFallback
                    ? "text-amber-500"
                    : "text-muted-foreground"
              }`}
            >
              {new Date(message.timestamp).toLocaleTimeString([], {
                hour: "2-digit",
                minute: "2-digit",
              })}
            </span>
          </div>
        )}

        {/* Result table */}
        {message.result && message.result.length > 0 && (
          <ResultTable rows={message.result} />
        )}

        {/* Date range pill */}
        {!isUser && message.date_filter_applied && message.date_range && (
          <DateRangePill message={message} onDateRangeUpdate={onDateRangeUpdate} />
        )}
      </div>
    </motion.div>
  );
}
