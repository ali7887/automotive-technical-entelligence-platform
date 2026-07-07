"use client";

import { useQuery } from "@tanstack/react-query";
import { CircleAlert, Loader2, SendHorizontal, ShieldCheck } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api/client";
import { openChatStream } from "@/lib/api/stream";
import type { AskResponse, Citation, RetrievedSource } from "@/lib/api/types";
import { cn } from "@/lib/utils";

interface Exchange {
  id: number;
  question: string;
  status: "streaming" | "done" | "error";
  draft: string;
  sources: RetrievedSource[];
  result?: AskResponse;
  error?: string;
  errorCode?: string;
}

export function ChatPanel({ workspaceId }: { workspaceId: string }) {
  const [question, setQuestion] = useState("");
  const [documentId, setDocumentId] = useState("");
  const [exchanges, setExchanges] = useState<Exchange[]>([]);
  const closeRef = useRef<(() => void) | null>(null);
  const nextId = useRef(0);

  const { data: documents } = useQuery({
    queryKey: ["documents", workspaceId],
    queryFn: async () => {
      const { data, error } = await api.GET("/api/workspaces/{workspace_id}/documents", {
        params: { path: { workspace_id: workspaceId } },
      });
      if (!data) throw new Error(String(error ?? "Failed to load documents"));
      return data;
    },
  });
  const readyDocuments = documents?.filter((document) => document.status === "READY") ?? [];

  // close any in-flight stream when the panel unmounts
  useEffect(() => () => closeRef.current?.(), []);

  const streaming = exchanges.some((exchange) => exchange.status === "streaming");

  const patch = (id: number, update: (exchange: Exchange) => Exchange) => {
    setExchanges((current) =>
      current.map((exchange) => (exchange.id === id ? update(exchange) : exchange)),
    );
  };

  const ask = (submitted: string) => {
    const id = nextId.current++;
    setExchanges((current) => [
      ...current,
      { id, question: submitted, status: "streaming", draft: "", sources: [] },
    ]);
    closeRef.current = openChatStream(
      {
        workspaceId,
        question: submitted,
        documentId: documentId || undefined,
      },
      {
        onSources: (sources) => patch(id, (exchange) => ({ ...exchange, sources })),
        onToken: (text) =>
          patch(id, (exchange) => ({ ...exchange, draft: exchange.draft + text })),
        onFinal: (result) =>
          patch(id, (exchange) => ({ ...exchange, status: "done", result })),
        onError: (message, code) =>
          patch(id, (exchange) => ({
            ...exchange,
            status: "error",
            error: message,
            errorCode: code,
          })),
      },
    );
  };

  const onSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    const submitted = question.trim();
    if (!submitted || streaming) return;
    setQuestion("");
    ask(submitted);
  };

  return (
    <section className="space-y-4">
      <div>
        <h2 className="text-lg font-semibold tracking-tight">Ask</h2>
        <p className="text-sm text-muted-foreground">
          Verified answers with clause and page citations, checked against the retrieved text.
        </p>
      </div>

      {exchanges.length === 0 ? (
        <div className="rounded-xl border border-dashed p-6 text-center">
          <p className="font-medium">Ask a question about this workspace</p>
          <p className="mt-1 text-sm text-muted-foreground">
            e.g. &ldquo;What photometric requirements apply to headlamps?&rdquo;
          </p>
        </div>
      ) : (
        <ol className="space-y-4">
          {exchanges.map((exchange) => (
            <li key={exchange.id} className="space-y-2">
              <p className="ml-auto w-fit max-w-[85%] rounded-xl bg-primary px-4 py-2 text-sm text-primary-foreground">
                {exchange.question}
              </p>
              <ExchangeAnswer exchange={exchange} />
            </li>
          ))}
        </ol>
      )}

      <form onSubmit={onSubmit} className="flex flex-wrap gap-2">
        <Input
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          placeholder="Ask about requirements, limits, test procedures…"
          maxLength={500}
          aria-label="Question"
          className="min-w-48 flex-1"
        />
        <select
          value={documentId}
          onChange={(event) => setDocumentId(event.target.value)}
          aria-label="Restrict to document"
          className="h-9 max-w-56 rounded-md border border-input bg-transparent px-3 text-sm shadow-xs focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50"
        >
          <option value="">All documents</option>
          {readyDocuments.map((document) => (
            <option key={document.id} value={document.id}>
              {document.name}
            </option>
          ))}
        </select>
        <Button type="submit" disabled={streaming || !question.trim()}>
          {streaming ? (
            <Loader2 className="size-4 animate-spin" />
          ) : (
            <SendHorizontal className="size-4" />
          )}
          Ask
        </Button>
      </form>
    </section>
  );
}

function ExchangeAnswer({ exchange }: { exchange: Exchange }) {
  if (exchange.status === "error") {
    return (
      <div className="rounded-xl border border-destructive/50 p-4 text-sm">
        <p className="flex items-center gap-2 font-medium">
          <CircleAlert className="size-4 text-destructive" />
          {exchange.errorCode === "generation_disabled"
            ? "Answer generation is disabled"
            : "Could not answer"}
        </p>
        <p className="mt-1 text-muted-foreground">{exchange.error}</p>
      </div>
    );
  }

  if (exchange.status === "streaming") {
    return (
      <div className="rounded-xl border p-4">
        {exchange.draft ? (
          <p className="whitespace-pre-line text-sm">
            {exchange.draft}
            <span className="ml-0.5 inline-block h-4 w-2 animate-pulse bg-foreground/60 align-text-bottom" />
          </p>
        ) : (
          <p className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="size-4 animate-spin" />
            {exchange.sources.length > 0
              ? `Generating from ${exchange.sources.length} retrieved source${exchange.sources.length === 1 ? "" : "s"}…`
              : "Retrieving sources…"}
          </p>
        )}
      </div>
    );
  }

  return <VerifiedAnswer result={exchange.result!} />;
}

const STATUS_LABELS: Record<AskResponse["verification"]["status"], string> = {
  verified: "Verified",
  partial: "Partially verified",
  unsupported: "Unsupported",
  not_found: "Not found",
};

function VerifiedAnswer({ result }: { result: AskResponse }) {
  const [activeCitation, setActiveCitation] = useState<number | null>(null);
  const ok = result.verification.status === "verified";

  return (
    <div className="space-y-3 rounded-xl border p-4">
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant={ok ? "default" : "outline"} className="gap-1">
          {ok ? <ShieldCheck className="size-3" /> : <CircleAlert className="size-3" />}
          {STATUS_LABELS[result.verification.status]}
        </Badge>
        {result.confidence != null && !result.not_found && (
          <span className="text-xs tabular-nums text-muted-foreground">
            confidence {result.confidence.toFixed(2)}
          </span>
        )}
        {!result.semantic_used && (
          <span className="text-xs text-muted-foreground">keyword-only retrieval</span>
        )}
      </div>

      <p className="whitespace-pre-line text-sm">
        <AnswerText
          text={result.answer_md}
          citations={result.citations}
          activeCitation={activeCitation}
          onCitation={setActiveCitation}
        />
      </p>

      {result.verification.warnings.length > 0 && (
        <ul className="space-y-1 text-xs text-muted-foreground">
          {result.verification.warnings.map((warning, index) => (
            <li key={index} className="flex gap-1.5">
              <CircleAlert className="mt-0.5 size-3 shrink-0" />
              {warning}
            </li>
          ))}
        </ul>
      )}

      {result.citations.length > 0 && (
        <div className="space-y-2 border-t pt-3">
          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            Sources
          </p>
          <ul className="space-y-2">
            {result.citations.map((citation) => (
              <CitationCard
                key={citation.citation_id}
                citation={citation}
                active={activeCitation === citation.citation_id}
                onHover={setActiveCitation}
              />
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

const MARKER_SPLIT = /(\[\d{1,3}\])/g;
const MARKER = /^\[(\d{1,3})\]$/;

function AnswerText({
  text,
  citations,
  activeCitation,
  onCitation,
}: {
  text: string;
  citations: Citation[];
  activeCitation: number | null;
  onCitation: (id: number | null) => void;
}) {
  return text.split(MARKER_SPLIT).map((part, index) => {
    const match = MARKER.exec(part);
    const citationId = match ? Number(match[1]) : null;
    if (citationId != null && citations.some((c) => c.citation_id === citationId)) {
      return (
        <button
          key={index}
          type="button"
          onClick={() => onCitation(citationId)}
          onMouseEnter={() => onCitation(citationId)}
          onMouseLeave={() => onCitation(null)}
          className={cn(
            "mx-0.5 inline-flex -translate-y-px items-center rounded border px-1 text-[11px] font-medium tabular-nums transition-colors",
            activeCitation === citationId
              ? "border-primary bg-primary text-primary-foreground"
              : "bg-muted text-muted-foreground hover:border-primary hover:text-foreground",
          )}
          aria-label={`Show source ${citationId}`}
        >
          {citationId}
        </button>
      );
    }
    return <span key={index}>{part}</span>;
  });
}

function CitationCard({
  citation,
  active,
  onHover,
}: {
  citation: Citation;
  active: boolean;
  onHover: (id: number | null) => void;
}) {
  const ref = useRef<HTMLLIElement>(null);
  useEffect(() => {
    if (active) ref.current?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [active]);

  const pages =
    citation.page_start === citation.page_end
      ? `p. ${citation.page_start}`
      : `pp. ${citation.page_start}–${citation.page_end}`;

  return (
    <li
      ref={ref}
      onMouseEnter={() => onHover(citation.citation_id)}
      onMouseLeave={() => onHover(null)}
      className={cn(
        "rounded-lg border p-3 text-sm transition-colors",
        active && "border-primary ring-[3px] ring-primary/20",
      )}
    >
      <div className="flex flex-wrap items-center gap-2">
        <span className="inline-flex items-center rounded border bg-muted px-1 text-[11px] font-medium tabular-nums text-muted-foreground">
          {citation.citation_id}
        </span>
        <span className="truncate font-medium">{citation.document_name}</span>
        {citation.clause_id && <Badge variant="outline">{citation.clause_id}</Badge>}
        <span className="text-xs text-muted-foreground">{pages}</span>
        {citation.status === "weak" && (
          <Badge variant="outline" className="text-amber-600 dark:text-amber-500">
            unverified quote
          </Badge>
        )}
      </div>
      <blockquote className="mt-2 border-l-2 pl-3 text-sm text-muted-foreground">
        {citation.source_text_snippet}
      </blockquote>
    </li>
  );
}
