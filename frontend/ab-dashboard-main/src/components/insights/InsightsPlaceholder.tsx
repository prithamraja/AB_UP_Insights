import { BarChart3 } from "lucide-react";

export function InsightsPlaceholder() {
  return (
    <div className="flex flex-1 flex-col items-center justify-center py-16 text-center text-muted-foreground">
      <BarChart3 className="mb-3 h-10 w-10 opacity-20" />
      <p className="text-base font-medium">Insights Dashboard</p>
      <p className="mt-1 text-sm opacity-70">
        Analytics and visualizations coming soon.
      </p>
    </div>
  );
}
