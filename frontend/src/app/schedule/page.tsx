import PageHeader from "@/components/common/PageHeader";
import { ComingSoon } from "@/components/common/states";

export default function SchedulePage() {
  return (
    <div className="mx-auto max-w-7xl">
      <PageHeader title="Schedule" description="Automated tasks across all servers" />
      <ComingSoon
        title="Scheduler & automation"
        description="Cron jobs for scheduled restarts, updates, backups and cleanup — global and per-server."
        backend="Add a ScheduledAction model + APScheduler in the backend and /api/schedule endpoints."
      />
    </div>
  );
}
