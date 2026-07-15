import { Badge } from "@/components/ui/badge";
import type { DocumentStatus } from "@/lib/api/types";
import { cn } from "@/lib/utils";

const STATUS: Record<
  DocumentStatus,
  { label: string; variant: "neutral" | "warning" | "success" | "destructive"; pulse?: boolean }
> = {
  PENDING: { label: "Queued", variant: "neutral" },
  PROCESSING: { label: "Processing", variant: "warning", pulse: true },
  READY: { label: "Ready", variant: "success" },
  FAILED: { label: "Failed", variant: "destructive" },
};

/** Document pipeline state; one badge language across tables and cards. */
export function StatusBadge({ status }: { status: DocumentStatus }) {
  const { label, variant, pulse } = STATUS[status];
  return (
    <Badge variant={variant}>
      <span className={cn("size-1.5 rounded-full bg-current", pulse && "animate-pulse")} />
      {label}
    </Badge>
  );
}
