"use client";

import { useEffect, useMemo, useState } from "react";
import dynamic from "next/dynamic";
import useSWR from "swr";
import { StreamLanguage } from "@codemirror/language";
import { lua } from "@codemirror/legacy-modes/mode/lua";
import { properties } from "@codemirror/legacy-modes/mode/properties";
import { api, ApiError } from "@/lib/api";
import type { ConfigFileContent } from "@/lib/types";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState, ErrorState } from "@/components/common/states";
import { SaveBar } from "./SaveBar";
import { useConfigSave } from "./useConfigSave";

// CodeMirror touches the DOM on import; keep it out of the server render.
const CodeMirror = dynamic(() => import("@uiw/react-codemirror"), {
  ssr: false,
  loading: () => <Skeleton className="h-[60vh] w-full" />,
});

function languageFor(path: string) {
  if (path.endsWith(".lua")) return [StreamLanguage.define(lua)];
  if (/\.(ini|cfg|properties|txt)$/i.test(path)) return [StreamLanguage.define(properties)];
  return [];
}

interface RawEditorProps {
  serverId: string;
  path: string;
  running: boolean;
  hasBackup?: boolean;
  onSaved?: () => void;
}

/** Plain-text editor for any whitelisted config file. */
export function RawEditor({ serverId, path, running, hasBackup, onSaved }: RawEditorProps) {
  const { data, error, isLoading, mutate } = useSWR<ConfigFileContent>(
    ["config-file", serverId, path],
    () => api.configFile(serverId, path),
    { revalidateOnFocus: false },
  );
  const [text, setText] = useState<string | null>(null);
  const extensions = useMemo(() => languageFor(path), [path]);
  const { saving, save, restore } = useConfigSave(serverId, path, async () => {
    await mutate();
    setText(null);
    onSaved?.();
  });

  // Reset local edits when switching files.
  useEffect(() => setText(null), [path]);

  if (isLoading) return <Skeleton className="h-[60vh] w-full" />;
  if (error) {
    if (error instanceof ApiError && error.status === 404) {
      return <EmptyState title="File not generated yet" hint={error.message} />;
    }
    return <ErrorState message={error instanceof ApiError ? error.message : String(error)} onRetry={() => mutate()} />;
  }
  if (!data) return null;

  const value = text ?? data.content;
  const dirty = text !== null && text !== data.content;

  return (
    <div className="flex flex-col gap-2">
      <div className="overflow-hidden rounded-md border border-border text-[13px]">
        <CodeMirror
          value={value}
          height="60vh"
          theme="dark"
          extensions={extensions}
          onChange={setText}
          basicSetup={{ foldGutter: true, highlightActiveLine: true }}
          aria-label={`Edit ${path}`}
        />
      </div>
      <SaveBar
        dirty={dirty}
        saving={saving}
        running={running}
        hasBackup={hasBackup}
        onSave={(restart) => save({ content: value, base_mtime: data.mtime }, restart)}
        onDiscard={() => setText(null)}
        onRestore={() => restore(running)}
      />
    </div>
  );
}
