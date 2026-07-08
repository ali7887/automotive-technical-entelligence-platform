"use client";

import { ChevronLeft, ChevronRight, CircleAlert, Loader2 } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { Document, Page, pdfjs } from "react-pdf";

import { Button } from "@/components/ui/button";
import { API_BASE_URL } from "@/lib/api/client";

import "react-pdf/dist/Page/AnnotationLayer.css";
import "react-pdf/dist/Page/TextLayer.css";

pdfjs.GlobalWorkerOptions.workerSrc = new URL(
  "pdfjs-dist/build/pdf.worker.min.mjs",
  import.meta.url,
).toString();

/** Matches the verification layer: whitespace-collapsed, case-insensitive. */
const normalize = (value: string) => value.toLowerCase().replace(/\s+/g, " ").trim();

const escapeHtml = (value: string) =>
  value.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

// Minimum verified-quote length; shorter fragments are too ambiguous to mark.
const MIN_OVERLAP = 12;

/** True when the end of `item` continues into the quote, or its start finishes it. */
function edgeOverlap(item: string, quote: string): boolean {
  const max = Math.min(item.length, quote.length);
  for (let length = max; length >= MIN_OVERLAP; length--) {
    if (item.endsWith(quote.slice(0, length))) return true;
    if (item.startsWith(quote.slice(quote.length - length))) return true;
  }
  return false;
}

function itemMatchesQuote(item: string, quote: string): boolean {
  if (item.length >= 4 && quote.includes(item)) return true;
  if (item.includes(quote)) return true;
  return edgeOverlap(item, quote);
}

export function PdfViewer({
  documentId,
  initialPage,
  quote,
}: {
  documentId: string;
  initialPage: number;
  quote?: string;
}) {
  const fileUrl = `${API_BASE_URL}/api/documents/${documentId}/file`;
  const [numPages, setNumPages] = useState<number | null>(null);
  const [pageNumber, setPageNumber] = useState(Math.max(1, initialPage));
  const containerRef = useRef<HTMLDivElement>(null);
  const [pageWidth, setPageWidth] = useState<number | null>(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    const measure = () => setPageWidth(Math.min(container.clientWidth - 2, 1000));
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(container);
    return () => observer.disconnect();
  }, []);

  const quoteNorm = quote ? normalize(quote) : "";
  // pdf.js text-layer items are line fragments; chunks carry no coordinates, so the
  // verified quote is located by text matching and marked at fragment granularity.
  const highlightQuote = useCallback(
    (textItem: { str: string }) => {
      const safe = escapeHtml(textItem.str);
      if (quoteNorm.length < MIN_OVERLAP) return safe;
      const itemNorm = normalize(textItem.str);
      if (itemNorm.length === 0 || !itemMatchesQuote(itemNorm, quoteNorm)) return safe;
      return `<mark class="rounded-xs bg-yellow-300/70 text-transparent dark:bg-yellow-400/50">${safe}</mark>`;
    },
    [quoteNorm],
  );

  const clampPage = (page: number) =>
    Math.min(Math.max(1, page), numPages ?? Number.MAX_SAFE_INTEGER);

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex items-center justify-center gap-2 border-b px-4 py-2">
        <Button
          variant="outline"
          size="icon"
          onClick={() => setPageNumber((page) => clampPage(page - 1))}
          disabled={pageNumber <= 1}
          aria-label="Previous page"
        >
          <ChevronLeft className="size-4" />
        </Button>
        <span className="min-w-24 text-center text-sm tabular-nums text-muted-foreground">
          Page {pageNumber}
          {numPages != null && ` of ${numPages}`}
        </span>
        <Button
          variant="outline"
          size="icon"
          onClick={() => setPageNumber((page) => clampPage(page + 1))}
          disabled={numPages != null && pageNumber >= numPages}
          aria-label="Next page"
        >
          <ChevronRight className="size-4" />
        </Button>
      </div>

      <div ref={containerRef} className="min-h-0 flex-1 overflow-auto bg-muted/40 p-3">
        <Document
          file={fileUrl}
          onLoadSuccess={(pdf) => {
            setNumPages(pdf.numPages);
            setPageNumber((page) => Math.min(page, pdf.numPages));
          }}
          loading={<ViewerStatus icon="loading" message="Loading document…" />}
          error={
            <ViewerStatus icon="error" message="Could not load the PDF from the server." />
          }
          noData={<ViewerStatus icon="error" message="No document to display." />}
        >
          {pageWidth != null && (
            <Page
              pageNumber={pageNumber}
              width={pageWidth}
              customTextRenderer={highlightQuote}
              className="mx-auto w-fit border shadow-sm"
              loading={<ViewerStatus icon="loading" message="Rendering page…" />}
            />
          )}
        </Document>
      </div>
    </div>
  );
}

function ViewerStatus({ icon, message }: { icon: "loading" | "error"; message: string }) {
  return (
    <p className="flex items-center justify-center gap-2 p-10 text-sm text-muted-foreground">
      {icon === "loading" ? (
        <Loader2 className="size-4 animate-spin" />
      ) : (
        <CircleAlert className="size-4 text-destructive" />
      )}
      {message}
    </p>
  );
}
