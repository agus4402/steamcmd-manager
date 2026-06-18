import * as React from "react";
import { Inbox, TriangleAlert, Hammer, RotateCw, type LucideIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

function Shell({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center rounded-lg border border-dashed border-border bg-card/40 px-6 py-14 text-center",
        className,
      )}
    >
      {children}
    </div>
  );
}

export function EmptyState({
  icon: Icon = Inbox,
  title,
  hint,
  action,
}: {
  icon?: LucideIcon;
  title: string;
  hint?: string;
  action?: React.ReactNode;
}) {
  return (
    <Shell>
      <div className="mb-3 flex size-12 items-center justify-center rounded-full bg-secondary text-muted-foreground">
        <Icon className="size-6" />
      </div>
      <p className="font-medium">{title}</p>
      {hint && <p className="mt-1 max-w-sm text-sm text-muted-foreground">{hint}</p>}
      {action && <div className="mt-4">{action}</div>}
    </Shell>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <Shell className="border-destructive/30 bg-destructive/5">
      <div className="mb-3 flex size-12 items-center justify-center rounded-full bg-destructive/15 text-danger">
        <TriangleAlert className="size-6" />
      </div>
      <p className="font-medium">Something went wrong</p>
      <p className="mt-1 max-w-sm text-sm text-muted-foreground">{message}</p>
      {onRetry && (
        <Button variant="outline" size="sm" className="mt-4" onClick={onRetry}>
          <RotateCw className="size-4" /> Retry
        </Button>
      )}
    </Shell>
  );
}

export function ComingSoon({
  title,
  description,
  backend,
}: {
  title: string;
  description?: string;
  backend?: string;
}) {
  return (
    <Shell>
      <div className="mb-3 flex size-12 items-center justify-center rounded-full bg-primary/15 text-primary">
        <Hammer className="size-6" />
      </div>
      <p className="font-medium">{title}</p>
      {description && <p className="mt-1 max-w-md text-sm text-muted-foreground">{description}</p>}
      {backend && (
        <p className="mt-3 max-w-md rounded-md border border-border bg-secondary/50 px-3 py-2 text-xs text-muted-foreground">
          <span className="font-semibold text-foreground">Backend work:</span> {backend}
        </p>
      )}
    </Shell>
  );
}
