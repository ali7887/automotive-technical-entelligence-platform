"use client";

import { useMutation } from "@tanstack/react-query";
import { Loader2, Search } from "lucide-react";
import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api/client";
import { errorMessage, type SearchResult } from "@/lib/api/types";

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

      {search.isError && (
        <div className="rounded-xl border border-dashed p-6 text-center">
          <p className="font-medium">Search failed</p>
          <p className="mt-1 text-sm text-muted-foreground">
            {errorMessage(search.error, "Please try again.")}
          </p>
        </div>
      )}

      {search.isSuccess && (
        <div className="space-y-3">
          {!search.data.semantic_used && search.data.results.length > 0 && (
            <p className="text-xs text-muted-foreground">
              Keyword-only results — semantic search is not configured.
            </p>
          )}
          {search.data.results.length === 0 ? (
            <div className="rounded-xl border border-dashed p-6 text-center">
              <p className="font-medium">No matches</p>
              <p className="mt-1 text-sm text-muted-foreground">
                Nothing in this workspace matched &ldquo;{search.data.query}&rdquo;.
              </p>
            </div>
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
  const pages =
    result.page_start === result.page_end
      ? `p. ${result.page_start}`
      : `pp. ${result.page_start}–${result.page_end}`;
  return (
    <li className="rounded-xl border p-4">
      <div className="flex flex-wrap items-center gap-2">
        {result.clause_id && <Badge variant="outline">{result.clause_id}</Badge>}
        <span className="truncate text-sm font-medium">{result.document_name}</span>
        <span className="text-xs text-muted-foreground">{pages}</span>
        <span className="ml-auto text-xs tabular-nums text-muted-foreground">
          RRF {result.scores.rrf.toFixed(4)}
          {result.scores.keyword_rank != null && ` · kw #${result.scores.keyword_rank}`}
          {result.scores.semantic_rank != null && ` · sem #${result.scores.semantic_rank}`}
        </span>
      </div>
      {result.heading && (
        <p className="mt-2 text-sm font-medium text-muted-foreground">{result.heading}</p>
      )}
      <p className="mt-2 line-clamp-4 whitespace-pre-line text-sm text-muted-foreground">
        {result.text}
      </p>
    </li>
  );
}
