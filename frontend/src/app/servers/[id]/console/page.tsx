"use client";

import ServerConsole from "@/components/console/ServerConsole";
import { useServerCtx } from "../server-context";

export default function ServerConsolePage() {
  const { server, setLiveProgress } = useServerCtx();
  return <ServerConsole serverId={server.id} serverName={server.name} onProgress={setLiveProgress} />;
}
