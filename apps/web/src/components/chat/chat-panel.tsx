"use client";

import { useQuery } from "@tanstack/react-query";
import {
  CircleAlert,
  FileSearch,
  KeyRound,
  Loader2,
  MessageSquareText,
  SendHorizontal,
  ShieldCheck,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { api } from "@/lib/api/client";
import { openChatStream } from "@/lib/api/stream";
import type { AskResponse, Citation, RetrievedSource } from "@/lib/api/types";
import { useGenerationEnabled } from "@/lib/api/use-health";
import { formatPages } from "@/lib/format";
import { useEvidenceViewer } from "@/lib/store";
import { cn } from "@/lib/utils";

/** Open a citation in the PDF evidence viewer at its cited page and quote. */
function citationTarget(citation: Citation) {
  return {
    documentId: citation.document_id,
    documentName: citation.document_name,
    page: citation.page_start,
    quote: citation.source_text_snippet,
    clauseId: citation.clause_id,
  };
}

// Static suggestions only — clicking prefills the input and never auto-submits,
// matching the initialQuestion contract.
const SAMPLE_QUESTIONS = [
  "What photometric requirements apply to headlamps?",
  "Which clauses define required test procedures?",
  "What documentation must the manufacturer provide?",
];

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

export function ChatPanel({
  workspaceId,
  initialQuestion,
}: {
  workspaceId: string;
  /** Prefills the input (e.g. from the dashboard ask bar); never auto-submits. */
  initialQuestion?: string;
}) {
  const [question, setQuestion] = useState(initialQuestion ?? "");
  const [documentId, setDocumentId] = useState("");
  const [exchanges, setExchanges] = useState<Exchange[]>([]);
  const closeRef = useRef<(() => void) | null>(null);
  const nextId = useRef(0);

  // undefined while health is unknown — only lock the panel on a definite "no key"
  const generationEnabled = useGenerationEnabled();
  const generationOff = generationEnabled === false;

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
    if (!submitted || streaming || generationOff) return;
    setQuestion("");
    ask(submitted);
  };

  return (
    <section className="space-y-4">
      <div>
        <h2 className="text-lg font-semibold tracking-tight">Ask AI</h2>
        <p className="text-sm text-muted-foreground">
          Verified answers with clause and page citations, checked against the retrieved text.
        </p>
      </div>

      {generationOff && (
        <div className="flex items-start gap-3 rounded-xl border border-warning/30 bg-warning-soft p-4">
          <KeyRound className="mt-0.5 size-4 shrink-0 text-warning-strong" />
          <div className="text-sm">
            <p className="font-medium text-warning-strong">Answer generation is unavailable</p>
            <p className="mt-0.5 text-muted-foreground">
              No model API key is configured on the server, so asking questions is disabled.
              Keyword search and existing evidence remain fully available. Set{" "}
              <code className="rounded bg-card px-1 py-0.5 font-mono text-xs">
                OPENAI_API_KEY
              </code>{" "}
              on the API to enable verified Q&amp;A.
            </p>
          </div>
        </div>
      )}

      {exchanges.length === 0 ? (
        <EmptyState
          icon={MessageSquareText}
          title={
            generationOff
              ? "Questions will be available once generation is enabled"
              : "Ask a question about this workspace"
          }
          description={
            generationOff
              ? "Meanwhile, use the Search tab to find clauses by keyword."
              : "Every answer cites the clauses and pages it came from."
          }
          action={
            generationOff ? undefined : (
              <div className="flex flex-wrap justify-center gap-1.5">
                {SAMPLE_QUESTIONS.map((sample) => (
                  <Button
                    key={sample}
                    type="button"
                    variant="outline"
                    size="xs"
                    className="rounded-full font-normal text-muted-foreground"
                    onClick={() => setQuestion(sample)}
                  >
                    {sample}
                  </Button>
                ))}
              </div>
            )
          }
        />
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
          placeholder={
            generationOff
              ? "Answer generation is disabled"
              : "Ask about requirements, limits, test procedures…"
          }
          maxLength={500}
          aria-label="Question"
          className="min-w-48 flex-1"
          disabled={generationOff}
        />
        <NativeSelect
          value={documentId}
          onChange={(event) => setDocumentId(event.target.value)}
          aria-label="Restrict to document"
          className="max-w-56"
          disabled={generationOff}
        >
          <option value="">All documents</option>
          {readyDocuments.map((document) => (
            <option key={document.id} value={document.id}>
              {document.name}
            </option>
          ))}
        </NativeSelect>
        <Button type="submit" disabled={streaming || !question.trim() || generationOff}>
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
    // generation_disabled / not_found are expected outcomes, not failures —
    // they get a calm neutral/amber treatment; only real errors read as errors.
    const tone =
      exchange.errorCode === "generation_disabled"
        ? "warning"
        : exchange.errorCode === "not_found"
          ? "neutral"
          : "error";
    return (
      <div
        className={cn("rounded-xl border bg-card p-4 text-sm", {
          "border-warning/30 bg-warning-soft": tone === "warning",
          "border-destructive/30 bg-destructive-soft": tone === "error",
        })}
      >
        <p
          className={cn("flex items-center gap-2 font-medium", {
            "text-warning-strong": tone === "warning",
            "text-destructive-strong": tone === "error",
          })}
        >
          <CircleAlert className="size-4" />
          {exchange.errorCode === "generation_disabled"
            ? "Answer generation is disabled"
            : exchange.errorCode === "not_found"
              ? "No verified answer"
              : "Could not answer"}
        </p>
        <p className="mt-1 text-muted-foreground">{exchange.error}</p>
      </div>
    );
  }

  if (exchange.status === "streaming") {
    return (
      <div className="rounded-xl border bg-card p-4">
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

const STATUS_META: Record<
  AskResponse["verification"]["status"],
  { label: string; variant: "success" | "warning" | "destructive" | "neutral" }
> = {
  verified: { label: "Verified", variant: "success" },
  partial: { label: "Partially verified", variant: "warning" },
  unsupported: { label: "Unsupported", variant: "destructive" },
  not_found: { label: "Not found", variant: "neutral" },
};

function VerifiedAnswer({ result }: { result: AskResponse }) {
  const [activeCitation, setActiveCitation] = useState<number | null>(null);
  const openEvidence = useEvidenceViewer((state) => state.openEvidence);
  const status = STATUS_META[result.verification.status];
  const ok = result.verification.status === "verified";

  return (
    <div className="space-y-3 rounded-xl border bg-card p-4 shadow-2xs">
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant={status.variant} className="gap-1">
          {ok ? <ShieldCheck className="size-3" /> : <CircleAlert className="size-3" />}
          {status.label}
        </Badge>
        {result.confidence != null && !result.not_found && (
          <span className="font-mono text-xs tabular-nums text-muted-foreground">
            confidence {result.confidence.toFixed(2)}
          </span>
        )}
        {!result.semantic_used && (
          <span className="text-xs text-muted-foreground">keyword-only retrieval</span>
        )}
      </div>

      <p className="whitespace-pre-line text-sm leading-relaxed">
        <AnswerText
          text={result.answer_md}
          citations={result.citations}
          activeCitation={activeCitation}
          onHover={setActiveCitation}
          onOpen={(citation) => openEvidence(citationTarget(citation))}
        />
      </p>

      {result.verification.warnings.length > 0 && (
        <ul className="space-y-1 rounded-lg border border-warning/30 bg-warning-soft p-3 text-xs text-muted-foreground">
          {result.verification.warnings.map((warning, index) => (
            <li key={index} className="flex gap-1.5">
              <CircleAlert className="mt-0.5 size-3 shrink-0 text-warning-strong" />
              {warning}
            </li>
          ))}
        </ul>
      )}

      {result.citations.length > 0 && (
        <div className="space-y-2 border-t pt-3">
          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            Supporting evidence
          </p>
          <ul className="space-y-2">
            {result.citations.map((citation) => (
              <CitationCard
                key={citation.citation_id}
                citation={citation}
                active={activeCitation === citation.citation_id}
                onHover={setActiveCitation}
                onOpen={() => openEvidence(citationTarget(citation))}
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
  onHover,
  onOpen,
}: {
  text: string;
  citations: Citation[];
  activeCitation: number | null;
  onHover: (id: number | null) => void;
  onOpen: (citation: Citation) => void;
}) {
  return text.split(MARKER_SPLIT).map((part, index) => {
    const match = MARKER.exec(part);
    const citationId = match ? Number(match[1]) : null;
    const citation =
      citationId != null ? citations.find((c) => c.citation_id === citationId) : undefined;
    if (citation) {
      return (
        <button
          key={index}
          type="button"
          onClick={() => onOpen(citation)}
          onMouseEnter={() => onHover(citation.citation_id)}
          onMouseLeave={() => onHover(null)}
          className={cn(
            "mx-0.5 inline-flex -translate-y-px items-center rounded border px-1 font-mono text-[11px] font-medium tabular-nums transition-colors",
            activeCitation === citationId
              ? "border-info bg-info-soft text-info-strong"
              : "bg-muted text-muted-foreground hover:border-info hover:text-foreground",
          )}
          aria-label={`Show evidence ${citationId} on the document`}
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
  onOpen,
}: {
  citation: Citation;
  active: boolean;
  onHover: (id: number | null) => void;
  onOpen: () => void;
}) {
  const ref = useRef<HTMLLIElement>(null);
  useEffect(() => {
    if (active) ref.current?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [active]);

  return (
    <li
      ref={ref}
      onMouseEnter={() => onHover(citation.citation_id)}
      onMouseLeave={() => onHover(null)}
      className={cn(
        "rounded-lg border p-3 text-sm transition-colors",
        active && "border-info ring-3 ring-info/20",
      )}
    >
      <div className="flex flex-wrap items-center gap-2">
        <span className="inline-flex items-center rounded border bg-muted px-1 font-mono text-[11px] font-medium tabular-nums text-muted-foreground">
          {citation.citation_id}
        </span>
        <span className="truncate font-medium">{citation.document_name}</span>
        {citation.clause_id && (
          <Badge variant="outline" className="font-mono">
            {citation.clause_id}
          </Badge>
        )}
        <span className="font-mono text-xs tabular-nums text-muted-foreground">
          {formatPages(citation.page_start, citation.page_end)}
        </span>
        {citation.status === "weak" && <Badge variant="warning">unverified quote</Badge>}
      </div>
      <blockquote className="mt-2 border-l-2 pl-3 text-sm text-muted-foreground">
        {citation.source_text_snippet}
      </blockquote>
      <Button variant="outline" size="sm" className="mt-2" onClick={onOpen}>
        <FileSearch className="size-3.5" />
        Verify on document
      </Button>
    </li>
  );
}
