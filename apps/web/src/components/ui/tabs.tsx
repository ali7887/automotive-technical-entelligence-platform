"use client";

import * as React from "react";

import { cn } from "@/lib/utils";

export interface TabItem {
  id: string;
  label: string;
  /** Optional count rendered after the label (e.g. documents in a workspace). */
  count?: number;
}

/**
 * Understated underline tab strip. Panels are kept mounted by the caller
 * (hidden, not unmounted) so in-progress state like a chat thread survives
 * switching tabs.
 */
export function TabList({
  items,
  value,
  onChange,
  className,
}: {
  items: TabItem[];
  value: string;
  onChange: (id: string) => void;
  className?: string;
}) {
  return (
    <div role="tablist" className={cn("flex gap-1 overflow-x-auto border-b", className)}>
      {items.map((item) => {
        const selected = item.id === value;
        return (
          <button
            key={item.id}
            type="button"
            role="tab"
            id={`tab-${item.id}`}
            aria-selected={selected}
            aria-controls={`tabpanel-${item.id}`}
            onClick={() => onChange(item.id)}
            className={cn(
              "-mb-px inline-flex h-9 shrink-0 items-center gap-1.5 border-b-2 px-3 text-sm outline-none transition-colors",
              "focus-visible:rounded-t-md focus-visible:ring-3 focus-visible:ring-ring/50",
              selected
                ? "border-ring font-medium text-foreground"
                : "border-transparent text-muted-foreground hover:border-border hover:text-foreground",
            )}
          >
            {item.label}
            {/* zero adds nothing the empty panel doesn't already say */}
            {item.count != null && item.count > 0 && (
              <span
                className={cn(
                  "rounded-md px-1.5 font-mono text-[11px] tabular-nums",
                  selected ? "bg-info-soft text-info-strong" : "bg-muted text-muted-foreground",
                )}
              >
                {item.count}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}

export function TabPanel({
  id,
  active,
  children,
  className,
}: {
  id: string;
  active: boolean;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      role="tabpanel"
      id={`tabpanel-${id}`}
      aria-labelledby={`tab-${id}`}
      hidden={!active}
      className={className}
    >
      {children}
    </div>
  );
}
