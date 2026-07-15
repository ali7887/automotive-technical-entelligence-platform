import { CircleAlert, type LucideIcon } from "lucide-react"
import * as React from "react"

import { cn } from "@/lib/utils"

/**
 * Deliberate empty/error surface: states the situation and always offers the
 * next step (upload, retry, extract…) via the `action` slot.
 */
function EmptyState({
  icon,
  title,
  description,
  action,
  variant = "default",
  className,
}: {
  icon?: LucideIcon
  title: string
  description?: React.ReactNode
  action?: React.ReactNode
  variant?: "default" | "error"
  className?: string
}) {
  // error surfaces always carry an icon so they read as errors at a glance
  const Icon = icon ?? (variant === "error" ? CircleAlert : undefined)
  return (
    <div
      className={cn(
        "flex flex-col items-center rounded-xl border border-dashed bg-card px-6 py-10 text-center",
        variant === "error" && "border-destructive/30 bg-destructive-soft/40",
        className
      )}
    >
      {Icon && (
        <div
          className={cn(
            "mb-3 flex size-9 items-center justify-center rounded-lg border bg-muted text-muted-foreground",
            variant === "error" && "border-destructive/20 bg-card text-destructive-strong"
          )}
        >
          <Icon className="size-4" />
        </div>
      )}
      <p className="text-sm font-medium">{title}</p>
      {description && (
        <p className="mt-1 max-w-md text-sm text-muted-foreground">{description}</p>
      )}
      {action && <div className="mt-4">{action}</div>}
    </div>
  )
}

export { EmptyState }
