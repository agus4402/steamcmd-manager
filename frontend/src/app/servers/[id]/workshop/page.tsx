import { ComingSoon } from "@/components/common/states";

export default function ServerWorkshopPage() {
  return (
    <ComingSoon
      title="Steam Workshop"
      description="Browse a mod catalog and manage installed Workshop items per server."
      backend="Add per-template workshop config + a service calling steamcmd workshop_download_item, and /api/servers/{id}/mods endpoints."
    />
  );
}
