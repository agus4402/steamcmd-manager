import { ComingSoon } from "@/components/common/states";

export default function ServerMetricsPage() {
  return (
    <ComingSoon
      title="Metrics & monitoring"
      description="Time-series CPU, memory, disk and network usage with threshold alerts."
      backend="Expose docker stats from the agent, add /api/servers/{id}/stats (+ a short history ring buffer), then render Recharts graphs."
    />
  );
}
