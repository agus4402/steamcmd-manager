import { ComingSoon } from "@/components/common/states";

export default function ServerBackupsPage() {
  return (
    <ComingSoon
      title="Backups & restore"
      description="Snapshot the data volume, browse snapshots and restore or clone from them."
      backend="Add agent volume snapshot/clone endpoints + /api/servers/{id}/backups and a restore route."
    />
  );
}
