"use client";

import { Search } from "lucide-react";
import { useCallback, useState, useSyncExternalStore } from "react";

import { CommandPalette } from "@/components/search/command-palette";
import { isMac, useKeyboardShortcut } from "@/hooks/use-keyboard-shortcut";

// Platform never changes at runtime; a no-op subscribe gives us an SSR-safe
// value (false on the server, resolved on the client) without a setState effect.
const NOOP_SUBSCRIBE = () => () => {};

/**
 * Header entry point for the global command palette, and owner of the
 * Cmd/Ctrl-K shortcut. Renders as a faux search bar on ≥sm and collapses to an
 * icon-only button on mobile. Kept as one client component so the server
 * layout only imports a single interactive piece.
 */
export function GlobalSearchTrigger() {
  const [open, setOpen] = useState(false);
  // navigator is client-only; useSyncExternalStore returns the server snapshot
  // (false) during SSR and the client value after hydration — no setState effect.
  const mac = useSyncExternalStore(NOOP_SUBSCRIBE, isMac, () => false);

  const toggle = useCallback((event: KeyboardEvent) => {
    event.preventDefault();
    setOpen((o) => !o);
  }, []);

  useKeyboardShortcut("k", toggle, { meta: true, ctrl: true, allowInInput: true });

  return (
    <>
      {/* Full search bar (sm+) */}
      <button
        type="button"
        onClick={() => setOpen(true)}
        aria-label="Open command palette"
        aria-keyshortcuts={mac ? "Meta+K" : "Control+K"}
        className="hidden h-9 min-w-56 items-center gap-2 rounded-lg border bg-background/60 px-3 text-sm text-muted-foreground transition-colors hover:bg-muted hover:text-foreground sm:flex"
      >
        <Search className="size-4 shrink-0" aria-hidden />
        <span className="flex-1 text-left">Ask AI or search...</span>
        <kbd className="inline-flex items-center gap-0.5 rounded border bg-muted px-1.5 py-0.5 font-mono text-[10px] font-medium">
          {mac ? "⌘" : "Ctrl"} K
        </kbd>
      </button>

      {/* Icon-only trigger (mobile) */}
      <button
        type="button"
        onClick={() => setOpen(true)}
        aria-label="Open command palette"
        className="inline-flex size-8 items-center justify-center rounded-lg text-muted-foreground transition-colors hover:bg-muted hover:text-foreground sm:hidden"
      >
        <Search className="size-4" aria-hidden />
      </button>

      <CommandPalette open={open} onOpenChange={setOpen} />
    </>
  );
}
