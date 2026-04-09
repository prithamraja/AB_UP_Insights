

## Add Bar Chart with Selectable Axes to ResultTable

### Changes — `src/components/chat/MessageBubble.tsx`

1. **New imports**: `BarChart3` from lucide-react; `BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer` from recharts; `Select, SelectContent, SelectItem, SelectTrigger, SelectValue` from existing select component.

2. **New state in `ResultTable`**: `showChart` (boolean), `xAxis` (string, default `headers[0]`), `yAxis` (string, default `headers[1]`).

3. **Chart uses `sortedRows`**: The bar chart renders from the same `sortedRows` array the table uses, so when the user sorts a column, the chart's X-axis order updates to match.

4. **Axis dropdowns**: Two `<Select>` dropdowns (X Axis, Y Axis) shown above the chart when visible. Options are all column names.

5. **Toggle button**: A "Bar Chart" button with `BarChart3` icon next to the existing "Download CSV" button.

6. **Chart**: `ResponsiveContainer` (height 250px) with `BarChart` using `sortedRows`. X-axis = `xAxis` column value, Y-axis = `yAxis` column value cast to `Number()`. Bar fill = `hsl(var(--primary))`.

### UI layout when chart is on

```text
┌─────────────────────────────┐
│  Table (sortable headers)   │
└─────────────────────────────┘
  X Axis: [dropdown]  Y Axis: [dropdown]
┌─────────────────────────────┐
│  Bar Chart (follows sort)   │
└─────────────────────────────┘
  [📊 Bar Chart] [⬇ Download CSV]
```

No new files or dependencies needed.

