import { Badge } from "@/components/ui/badge";
import type { DocumentStatus } from "@/lib/api/types";
import { cn } from "@/lib/utils";

const STATUS_STYLES: Record<DocumentStatus, { label: string; className: string }> = {
  PENDING: { label: "Queued", className: "bg-muted text-muted-foreground" },
  PROCESSING: { label: "Processing", className: "bg-amber-100 text-amber-900 animate-pulse" },
  READY: { label: "Ready", className: "bg-emerald-100 text-emerald-900" },
  FAILED: { label: "Failed", className: "bg-red-100 text-red-900" },
};

export function StatusBadge({ status }: { status: DocumentStatus }) {
  const { label, className } = STATUS_STYLES[status];
  return (
    <Badge variant="outline" className={cn("border-transparent", className)}>
      {label}
    </Badge>
  );
}
