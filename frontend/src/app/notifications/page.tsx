import PageHeader from "@/components/common/PageHeader";
import { ComingSoon } from "@/components/common/states";

export default function NotificationsPage() {
  return (
    <div className="mx-auto max-w-7xl">
      <PageHeader title="Notifications" description="Alerts and notification channels" />
      <ComingSoon
        title="Notification center"
        description="Real-time alerts on crashes and lifecycle events, with Discord, Telegram and email channels."
        backend="Emit events on status changes, add a notifications/preferences model and provider integrations."
      />
    </div>
  );
}
