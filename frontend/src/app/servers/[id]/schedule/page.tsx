import { ComingSoon } from "@/components/common/states";

export default function ServerSchedulePage() {
  return (
    <ComingSoon
      title="Scheduled tasks"
      description="Cron-style scheduled restarts, updates, backups and cleanup for this server."
      backend="Add a ScheduledAction model + APScheduler in the backend, and /api/servers/{id}/schedule endpoints."
    />
  );
}
