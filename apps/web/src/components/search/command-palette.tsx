"use client";

import { useQuery } from "@tanstack/react-query";
import {
  ArrowRight,
  FileText,
  LayoutDashboard,
  Network,
  Search,
  Sparkles,
  type LucideIcon,
} from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useId, useMemo, useRef, useState } from "react";
import { toast } from "sonner";

import { Dialog, DialogContent } from "@/components/ui/dialog";
import { api } from "@/lib/api/client";
import type { Workspace } from "@/lib/api/types";
import { cn } from "@/lib/utils";

interface CommandItem {
  id: string;
  label: string;
  hint?: string;
  icon: LucideIcon;
  group: string;
  /** Ranked first and always shown; used for the "Ask AI" action. */
  keywords?: string;
  run: () => void;
}

/**
 * Global command palette (Cmd/Ctrl-K). Built on the app's Base UI Dialog, so
 * the portal, blur backdrop, focus trap, and Esc-to-close are handled for us.
 * Results are a flat, ranked list (for keyboard nav) rendered in labeled groups.
 */
export function CommandPalette({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [activeIndex, setActiveIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const listboxId = useId();
  const optionIdBase = useId();

  // Real search data: the same workspaces query the dashboard uses (cached).
  const { data: workspaces = [] } = useQuery<Workspace[]>({
    queryKey: ["workspaces"],
    queryFn: async () => {
      const { data, error } = await api.GET("/api/workspaces");
      if (!data) throw new Error(String(error ?? "Failed to load workspaces"));
      return data;
    },
    enabled: open, // only fetch once the palette is actually opened
  });

  // Query changes come only from the input, so reset the highlight there rather
  // than in an effect. On close we also clear the query.
  const handleOpenChange = (next: boolean) => {
    if (!next) {
      setQuery("");
      setActiveIndex(0);
    }
    onOpenChange(next);
  };

  const handleQueryChange = (value: string) => {
    setQuery(value);
    setActiveIndex(0); // new results — highlight the first row
  };

  const close = () => handleOpenChange(false);

  // Route a question into a workspace's Ask tab (mirrors the dashboard AskBar).
  const askAi = (q: string) => {
    const question = q.trim();
    if (!question) return;
    if (workspaces.length === 0) {
      toast.info("Create a workspace first — answers cite your documents.");
      return;
    }
    router.push(
      `/workspaces/${workspaces[0].id}?tab=ask&q=${encodeURIComponent(question)}`,
    );
    close();
  };

  const goToWorkspace = (id: string, tab?: string) => {
    router.push(tab ? `/workspaces/${id}?tab=${tab}` : `/workspaces/${id}`);
    close();
  };

  const trimmed = query.trim();
  const needle = trimmed.toLowerCase();

  // Build the ranked, flat item list. "Ask AI" leads whenever there is a query.
  const items = useMemo<CommandItem[]>(() => {
    const list: CommandItem[] = [];

    if (trimmed) {
      list.push({
        id: "ask-ai",
        label: `Ask AI: ${trimmed}`,
        hint: "Verified answer with citations",
        icon: Sparkles,
        group: "AI",
        run: () => askAi(trimmed),
      });
    }

    const matchedWorkspaces = workspaces.filter((w) =>
      needle ? w.name.toLowerCase().includes(needle) : true,
    );
    for (const w of matchedWorkspaces.slice(0, 6)) {
      list.push({
        id: `ws-${w.id}`,
        label: w.name,
        hint: "Open workspace",
        icon: FileText,
        group: "Workspaces",
        run: () => goToWorkspace(w.id),
      });
    }

    // Static navigation / AI tools, filtered by the query.
    const nav: CommandItem[] = [
      {
        id: "nav-dashboard",
        label: "Go to Dashboard",
        icon: LayoutDashboard,
        group: "Navigation",
        run: () => {
          router.push("/");
          close();
        },
      },
    ];
    if (workspaces[0]) {
      nav.push({
        id: "nav-evidence",
        label: "Open Evidence Map",
        hint: workspaces[0].name,
        icon: Network,
        group: "AI Tools",
        run: () => goToWorkspace(workspaces[0].id, "evidence"),
      });
    }
    for (const item of nav) {
      if (!needle || item.label.toLowerCase().includes(needle)) list.push(item);
    }

    return list;
    // askAi/goToWorkspace close over router+workspaces which are in deps
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [trimmed, needle, workspaces, router]);

  // Focus the input when the palette opens (DOM side-effect only). next tick so
  // the dialog popup is mounted and focus-trapped first.
  useEffect(() => {
    if (!open) return;
    const t = setTimeout(() => inputRef.current?.focus(), 0);
    return () => clearTimeout(t);
  }, [open]);

  const onKeyDown = (event: React.KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setActiveIndex((i) => (items.length ? (i + 1) % items.length : 0));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setActiveIndex((i) => (items.length ? (i - 1 + items.length) % items.length : 0));
    } else if (event.key === "Enter") {
      event.preventDefault();
      items[activeIndex]?.run();
    }
    // Esc is handled by the Dialog.
  };

  // Group the flat list for display while preserving the flat index for nav.
  let flatIndex = -1;
  const groups = items.reduce<Record<string, { item: CommandItem; index: number }[]>>(
    (acc, item) => {
      flatIndex += 1;
      (acc[item.group] ??= []).push({ item, index: flatIndex });
      return acc;
    },
    {},
  );

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent
        showCloseButton={false}
        aria-label="Command palette"
        className="top-[15%] max-w-xl translate-y-0 gap-0 overflow-hidden p-0 sm:max-w-xl"
      >
        {/* Search input row */}
        <div className="flex items-center gap-2.5 border-b px-4">
          <Search className="size-4 shrink-0 text-muted-foreground" aria-hidden />
          <input
            ref={inputRef}
            value={query}
            onChange={(e) => handleQueryChange(e.target.value)}
            onKeyDown={onKeyDown}
            placeholder="Ask AI or search workspaces..."
            className="h-12 w-full bg-transparent text-sm outline-none placeholder:text-muted-foreground"
            role="combobox"
            aria-expanded
            aria-controls={listboxId}
            aria-activedescendant={
              items[activeIndex] ? `${optionIdBase}-${activeIndex}` : undefined
            }
            aria-label="Ask AI or search workspaces"
            autoComplete="off"
            spellCheck={false}
          />
        </div>

        {/* Results */}
        <div
          id={listboxId}
          role="listbox"
          aria-label="Results"
          className="max-h-[min(24rem,60vh)] overflow-y-auto p-2"
        >
          {items.length === 0 ? (
            <p className="px-3 py-6 text-center text-sm text-muted-foreground">
              No results{trimmed ? ` for “${trimmed}”` : ""}.
            </p>
          ) : (
            Object.entries(groups).map(([group, rows]) => (
              <div key={group} className="mb-1 last:mb-0">
                <p className="px-2 py-1.5 text-xs font-medium text-muted-foreground">
                  {group}
                </p>
                {rows.map(({ item, index }) => {
                  const active = index === activeIndex;
                  const Icon = item.icon;
                  return (
                    <button
                      key={item.id}
                      id={`${optionIdBase}-${index}`}
                      role="option"
                      aria-selected={active}
                      type="button"
                      onMouseMove={() => setActiveIndex(index)}
                      onClick={() => item.run()}
                      className={cn(
                        "flex w-full items-center gap-3 rounded-lg px-3 py-2 text-left text-sm transition-colors",
                        active
                          ? "bg-accent text-accent-foreground"
                          : "text-foreground hover:bg-muted",
                      )}
                    >
                      <Icon
                        className={cn(
                          "size-4 shrink-0",
                          active ? "text-accent-foreground" : "text-muted-foreground",
                        )}
                        aria-hidden
                      />
                      <span className="min-w-0 flex-1 truncate">{item.label}</span>
                      {item.hint && (
                        <span className="hidden shrink-0 truncate text-xs text-muted-foreground sm:inline">
                          {item.hint}
                        </span>
                      )}
                      {active && (
                        <ArrowRight
                          className="size-3.5 shrink-0 text-muted-foreground"
                          aria-hidden
                        />
                      )}
                    </button>
                  );
                })}
              </div>
            ))
          )}
        </div>

        {/* Footer hint */}
        <div className="flex items-center gap-4 border-t px-4 py-2.5 text-xs text-muted-foreground">
          <Hint keys={["↑", "↓"]} label="navigate" />
          <Hint keys={["↵"]} label="select" />
          <Hint keys={["esc"]} label="close" />
        </div>
      </DialogContent>
    </Dialog>
  );
}

function Hint({ keys, label }: { keys: string[]; label: string }) {
  return (
    <span className="flex items-center gap-1.5">
      {keys.map((k) => (
        <kbd
          key={k}
          className="inline-flex min-w-5 items-center justify-center rounded border bg-muted px-1 py-0.5 font-mono text-[10px] font-medium"
        >
          {k}
        </kbd>
      ))}
      <span>{label}</span>
    </span>
  );
}
