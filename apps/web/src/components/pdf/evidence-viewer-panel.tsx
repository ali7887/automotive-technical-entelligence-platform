"use client";

import { ExternalLink, Loader2, X } from "lucide-react";
import dynamic from "next/dynamic";
import { useEffect } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { API_BASE_URL } from "@/lib/api/client";
import { useEvidenceViewer } from "@/lib/store";

// pdf.js touches browser-only APIs (DOMMatrix, canvas); never render it on the server.
const PdfViewer = dynamic(() => import("./pdf-viewer").then((m) => m.PdfViewer), {
  ssr: false,
  loading: () => (
    <p className="flex items-center justify-center gap-2 p-10 text-sm text-muted-foreground">
      <Loader2 className="size-4 animate-spin" />
      Loading viewer…
    </p>
  ),
});

/** Slide-over PDF viewer opened from citations and evidence cards. */
export function EvidenceViewerPanel() {
  const target = useEvidenceViewer((state) => state.target);
  const closeEvidence = useEvidenceViewer((state) => state.closeEvidence);

  useEffect(() => {
    if (!target) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") closeEvidence();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [target, closeEvidence]);

  if (!target) return null;

  return (
    <div className="fixed inset-0 z-50">
      <button
        type="button"
        aria-label="Close document viewer"
        onClick={closeEvidence}
        className="absolute inset-0 bg-black/50"
      />
      <aside
        role="dialog"
        aria-modal="true"
        aria-label={`Evidence in ${target.documentName}`}
        className="absolute inset-y-0 right-0 flex w-full max-w-3xl flex-col border-l bg-background shadow-xl"
      >
        <header className="flex items-center gap-2 border-b px-4 py-3">
          <div className="min-w-0 flex-1">
            <p className="truncate font-medium">{target.documentName}</p>
            <div className="mt-0.5 flex items-center gap-2">
              {target.clauseId && <Badge variant="outline">{target.clauseId}</Badge>}
              <span className="text-xs text-muted-foreground">
                Evidence on page {target.page}
              </span>
            </div>
          </div>
          <Button
            variant="ghost"
            size="icon"
            aria-label="Open original PDF in a new tab"
            render={
              <a
                href={`${API_BASE_URL}/api/documents/${target.documentId}/file`}
                target="_blank"
                rel="noreferrer"
              />
            }
          >
            <ExternalLink className="size-4" />
          </Button>
          <Button variant="ghost" size="icon" aria-label="Close" onClick={closeEvidence}>
            <X className="size-4" />
          </Button>
        </header>

        {target.quote && (
          <blockquote className="border-b bg-muted/50 px-4 py-2 text-xs text-muted-foreground">
            Looking for: <span className="italic">“{target.quote}”</span>
          </blockquote>
        )}

        <PdfViewer
          key={`${target.documentId}:${target.page}:${target.quote ?? ""}`}
          documentId={target.documentId}
          initialPage={target.page}
          quote={target.quote}
        />
      </aside>
    </div>
  );
}
