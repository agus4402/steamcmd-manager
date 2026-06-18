"use client";

import { useEffect, useState } from "react";
import { toast } from "sonner";
import { api, ApiError } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input, Label } from "@/components/ui/input";
import { Card, CardContent } from "@/components/ui/card";
import { EmptyState } from "@/components/common/states";
import { useServerCtx } from "../server-context";

export default function ServerConfigPage() {
  const { server, mutate } = useServerCtx();
  const [vars, setVars] = useState<Record<string, string>>(server.variables);
  const [saving, setSaving] = useState(false);

  // Re-seed if the server's variables change underneath us (e.g. first load).
  useEffect(() => {
    setVars(server.variables);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [server.id]);

  const keys = Object.keys(vars);

  async function save() {
    setSaving(true);
    try {
      await api.patch(server.id, { variables: vars });
      toast.success("Configuration saved", { description: "Changes apply on next start." });
      await mutate();
    } catch (e) {
      toast.error("Failed to save", { description: e instanceof ApiError ? e.message : String(e) });
    } finally {
      setSaving(false);
    }
  }

  if (keys.length === 0) {
    return <EmptyState title="No variables" hint="This template doesn't expose any editable variables." />;
  }

  return (
    <Card className="max-w-2xl">
      <CardContent className="grid gap-4 pt-5">
        {keys.map((k) => (
          <div key={k}>
            <Label htmlFor={`var-${k}`}>{k}</Label>
            <Input
              id={`var-${k}`}
              value={vars[k]}
              onChange={(e) => setVars({ ...vars, [k]: e.target.value })}
            />
          </div>
        ))}
        <div className="flex items-center gap-3">
          <Button onClick={save} disabled={saving}>
            {saving ? "Saving…" : "Save changes"}
          </Button>
          <p className="text-xs text-muted-foreground">Changes apply on next start.</p>
        </div>
      </CardContent>
    </Card>
  );
}
