"use client";

import Console from "@/components/Console";
import { useServerCtx } from "../server-context";

export default function ServerConsolePage() {
  const { server, setLiveProgress } = useServerCtx();
  return <Console serverId={server.id} serverStatus={server.status} onProgress={setLiveProgress} />;
}
