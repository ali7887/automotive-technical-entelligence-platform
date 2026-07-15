import * as React from "react"

import { cn } from "@/lib/utils"

/** Styled native `<select>`; matches Input sizing/focus without a popover dependency. */
function NativeSelect({ className, ...props }: React.ComponentProps<"select">) {
  return (
    <select
      data-slot="native-select"
      className={cn(
        "h-8 rounded-lg border border-input bg-card px-2.5 text-sm text-foreground transition-colors outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 disabled:pointer-events-none disabled:cursor-not-allowed disabled:bg-muted disabled:opacity-50",
        className
      )}
      {...props}
    />
  )
}

export { NativeSelect }
