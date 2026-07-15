"use client";

import { useMutation } from "@tanstack/react-query";
import { FileSearch, Loader2, Search } from "lucide-react";
import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api/client";
import { errorMessage, type SearchResult } from "@/lib/api/types";
import { formatPages } from "@/lib/format";
import { useEvidenceViewer } from "@/lib/store";

export function SearchPanel({ workspaceId }: { workspaceId: string }) {
  const [query, setQuery] = useState("");
  const search = useMutation({
    mutationFn: async (submitted: string) => {
      const { data, error } = await api.POST("/api/workspaces/{workspace_id}/search", {
        params: { path: { workspace_id: workspaceId } },
        body: { query: submitted, top_k: 10 },
      });
      if (!data) throw new Error(errorMessage(error, "Search failed"));
      return data;
    },
  });

  const onSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    const submitted = query.trim();
    if (submitted) search.mutate(submitted);
  };

  return (
    <section className="space-y-4">
      <div>
        <h2 className="text-lg font-semibold tracking-tight">Search</h2>
        <p className="text-sm text-muted-foreground">
          Hybrid retrieval across this workspace&apos;s documents.
        </p>
      </div>

      <form onSubmit={onSubmit} className="flex gap-2">
        <Input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="e.g. photometric requirements for headlamps"
          maxLength={500}
          aria-label="Search query"
        />
        <Button type="submit" disabled={search.isPending || !query.trim()}>
          {search.isPending ? (
            <Loader2 className="size-4 animate-spin" />
          ) : (
            <Search className="size-4" />
          )}
          Search
        </Button>
      </form>

      {search.isIdle && (
        <EmptyState
          icon={Search}
          title="Search this workspace"
          description="Results are ranked with reciprocal rank fusion and carry clause and page provenance, so every hit can be verified on the source document."
        />
      )}

      {search.isError && (
        <EmptyState
          variant="error"
          title="Search failed"
          description={errorMessage(search.error, "Please try again.")}
        />
      )}

      {search.isSuccess && (
        <div className="space-y-3">
          {!search.data.semantic_used && search.data.results.length > 0 && (
            <p className="flex items-center gap-2 text-xs text-muted-foreground">
              <Badge variant="neutral">keyword-only</Badge>
              Semantic search is not configured; results use keyword ranking.
            </p>
          )}
          {search.data.results.length === 0 ? (
            <EmptyState
              icon={Search}
              title="No matches"
              description={`Nothing in this workspace matched “${search.data.query}”. Try different terms, or check that documents have finished processing.`}
            />
          ) : (
            <ul className="space-y-3">
              {search.data.results.map((result) => (
                <SearchResultCard key={result.chunk_id} result={result} />
              ))}
            </ul>
          )}
        </div>
      )}
    </section>
  );
}

function SearchResultCard({ result }: { result: SearchResult }) {
  const openEvidence = useEvidenceViewer((state) => state.openEvidence);
  return (
    <li className="rounded-xl border bg-card p-4 shadow-2xs">
      <div className="flex flex-wrap items-center gap-2">
        {result.clause_id && (
          <Badge variant="outline" className="font-mono">
            {result.clause_id}
          </Badge>
        )}
        <span className="truncate text-sm font-medium">{result.document_name}</span>
        <span className="font-mono text-xs tabular-nums text-muted-foreground">
          {formatPages(result.page_start, result.page_end)}
        </span>
        <span className="ml-auto font-mono text-xs tabular-nums text-muted-foreground">
          RRF {result.scores.rrf.toFixed(4)}
          {result.scores.keyword_rank != null && ` · kw #${result.scores.keyword_rank}`}
          {result.scores.semantic_rank != null && ` · sem #${result.scores.semantic_rank}`}
        </span>
      </div>
      {result.heading && (
        <p className="mt-2 text-sm font-medium text-muted-foreground">{result.heading}</p>
      )}
      {/* chunk text keeps raw PDF line breaks; collapse them for a clean excerpt */}
      <p className="mt-2 line-clamp-4 text-sm text-muted-foreground">
        {result.text.replace(/\s+/g, " ").trim()}
      </p>
      <Button
        variant="outline"
        size="sm"
        className="mt-3"
        onClick={() =>
          openEvidence({
            documentId: result.document_id,
            documentName: result.document_name,
            page: result.page_start,
            quote: result.text,
            clauseId: result.clause_id,
          })
        }
      >
        <FileSearch className="size-3.5" />
        Open in document
      </Button>
    </li>
  );
}
