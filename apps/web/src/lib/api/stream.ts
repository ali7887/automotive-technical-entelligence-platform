import { z } from "zod";

import { API_BASE_URL } from "./client";
import type { AskResponse, RetrievedSource } from "./types";

// SSE payloads are outside the OpenAPI-typed surface, so they are validated
// with zod at the stream boundary (event order: sources -> token* -> final | error).

const sourceSchema = z.object({
  index: z.number(),
  chunk_id: z.string(),
  document_id: z.string(),
  document_name: z.string(),
  clause_id: z.string().nullable(),
  page_start: z.number(),
  page_end: z.number(),
});

const sourcesEventSchema = z.object({ sources: z.array(sourceSchema) });
const tokenEventSchema = z.object({ text: z.string() });
const errorEventSchema = z.object({ code: z.string(), message: z.string() });

const citationSchema = z.object({
  citation_id: z.number(),
  postgres_chunk_id: z.string(),
  document_id: z.string(),
  document_name: z.string(),
  clause_id: z.string().nullable(),
  page_start: z.number(),
  page_end: z.number(),
  source_text_snippet: z.string(),
  status: z.enum(["validated", "weak"]),
});

const finalEventSchema = z.object({
  question: z.string(),
  workspace_id: z.string(),
  document_id: z.string().nullable(),
  answer_md: z.string(),
  not_found: z.boolean(),
  confidence: z.number().nullable(),
  citations: z.array(citationSchema),
  verification: z.object({
    status: z.enum(["verified", "partial", "unsupported", "not_found"]),
    claims_total: z.number(),
    claims_validated: z.number(),
    citations_dropped: z.number(),
    warnings: z.array(z.string()),
  }),
  sources: z.array(sourceSchema),
  semantic_used: z.boolean(),
  model: z.string(),
});

function parseJson(data: string): unknown {
  try {
    return JSON.parse(data);
  } catch {
    return undefined;
  }
}

export interface ChatStreamHandlers {
  onSources: (sources: RetrievedSource[]) => void;
  onToken: (text: string) => void;
  onFinal: (response: AskResponse) => void;
  onError: (message: string, code?: string) => void;
}

/** Open the verified-RAG SSE stream; returns a function that closes it. */
export function openChatStream(
  args: { workspaceId: string; question: string; documentId?: string },
  handlers: ChatStreamHandlers,
): () => void {
  const url = new URL(`/api/workspaces/${args.workspaceId}/chat`, API_BASE_URL);
  url.searchParams.set("question", args.question);
  if (args.documentId) url.searchParams.set("document_id", args.documentId);

  const source = new EventSource(url);
  let settled = false;
  const close = () => {
    settled = true;
    source.close();
  };
  const fail = (message: string, code?: string) => {
    if (!settled) handlers.onError(message, code);
    close();
  };

  source.addEventListener("sources", (event) => {
    const parsed = sourcesEventSchema.safeParse(parseJson(event.data));
    if (parsed.success) handlers.onSources(parsed.data.sources);
  });

  source.addEventListener("token", (event) => {
    const parsed = tokenEventSchema.safeParse(parseJson(event.data));
    if (parsed.success) handlers.onToken(parsed.data.text);
  });

  source.addEventListener("final", (event) => {
    const parsed = finalEventSchema.safeParse(parseJson(event.data));
    if (!settled) {
      if (parsed.success) handlers.onFinal(parsed.data);
      else handlers.onError("The server sent a malformed answer payload.");
    }
    close();
  });

  // a MessageEvent named "error" is a structured server error; a bare Event of
  // the same name is an EventSource connection failure
  source.addEventListener("error", (event) => {
    if (event instanceof MessageEvent) {
      const parsed = errorEventSchema.safeParse(parseJson(event.data));
      if (parsed.success) fail(parsed.data.message, parsed.data.code);
      else fail("The server reported an error.");
    } else {
      fail("Connection to the server was lost.");
    }
  });

  return close;
}
