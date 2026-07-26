/**
 * Static seed data for the API-less demo (NEXT_PUBLIC_DEMO_MODE=true).
 *
 * The platform is deployed frontend-only (e.g. Vercel) with no live API, so the
 * demo transport (./transport.ts) answers read requests from these fixtures
 * instead of the network. Everything is typed against the real OpenAPI schema
 * (@/lib/api/types), so shapes cannot drift from the API contract.
 *
 * Provenance is kept internally consistent (golden rule 5): every citation and
 * evidence quote points at a real fixture document with plausible clause/page
 * numbers. IDs and timestamps are fixed constants so server and client render
 * identically (no hydration mismatch from Date.now()/Math.random()).
 *
 * Delete this directory and the demo branch in client.ts/stream.ts to remove
 * the demo entirely; the real-backend path is untouched.
 */
import type {
  AskResponse,
  Document,
  EvidenceItem,
  HealthResponse,
  SearchResponse,
  User,
  Workspace,
} from "@/lib/api/types";

// Fixed instant so KPIs like "updated" are stable across SSR/CSR.
const SEEDED_AT = "2026-06-18T09:24:00Z";

// --- identity -------------------------------------------------------------
export const DEMO_USER: User = {
  id: "00000000-0000-4000-8000-000000000001",
  email: "demo@atip.app",
  display_name: "Demo User",
  role: "ORG_ADMIN",
  organization: {
    id: "00000000-0000-4000-8000-0000000000a1",
    name: "ATIP Demo Organization",
  },
};

// --- workspaces -----------------------------------------------------------
const WS_R155 = "10000000-0000-4000-8000-000000000001";
const WS_ISO26262 = "10000000-0000-4000-8000-000000000002";
const WS_R156 = "10000000-0000-4000-8000-000000000003";

export const DEMO_WORKSPACES: Workspace[] = [
  {
    id: WS_R155,
    name: "UN R155 — Cybersecurity & CSMS",
    description:
      "Vehicle cybersecurity type approval and the Cyber Security Management System.",
    created_at: "2026-05-02T10:00:00Z",
  },
  {
    id: WS_ISO26262,
    name: "ISO 26262 — Functional Safety",
    description: "Road vehicles functional safety across the safety lifecycle (ASIL).",
    created_at: "2026-05-11T14:30:00Z",
  },
  {
    id: WS_R156,
    name: "UN R156 — Software Update & SUMS",
    description: "Software update processes and the Software Update Management System.",
    created_at: "2026-05-20T08:15:00Z",
  },
];

// --- documents ------------------------------------------------------------
const DOC_R155_REG = "20000000-0000-4000-8000-000000000001";
const DOC_R155_CSMS = "20000000-0000-4000-8000-000000000002";
const DOC_ISO_PART6 = "20000000-0000-4000-8000-000000000003";
const DOC_ISO_PART9 = "20000000-0000-4000-8000-000000000004";
const DOC_R156_REG = "20000000-0000-4000-8000-000000000005";

function doc(
  id: string,
  workspace_id: string,
  name: string,
  page_count: number,
  created_at: string,
): Document {
  return {
    id,
    workspace_id,
    name,
    status: "READY",
    // Deterministic pseudo-hash; only used for display/dedup, never verified.
    sha256: id.replace(/-/g, "").padEnd(64, "0"),
    page_count,
    created_at,
  };
}

export const DEMO_DOCUMENTS: Record<string, Document[]> = {
  [WS_R155]: [
    doc(DOC_R155_REG, WS_R155, "UN R155 — Uniform provisions (full text).pdf", 41, "2026-05-02T10:05:00Z"),
    doc(DOC_R155_CSMS, WS_R155, "CSMS process manual v3.pdf", 68, "2026-05-04T16:20:00Z"),
  ],
  [WS_ISO26262]: [
    doc(DOC_ISO_PART6, WS_ISO26262, "ISO 26262-6 — Product development: software.pdf", 132, "2026-05-11T14:35:00Z"),
    doc(DOC_ISO_PART9, WS_ISO26262, "ISO 26262-9 — ASIL-oriented and safety analyses.pdf", 54, "2026-05-12T09:10:00Z"),
  ],
  [WS_R156]: [
    doc(DOC_R156_REG, WS_R156, "UN R156 — Software update & SUMS (full text).pdf", 33, "2026-05-20T08:20:00Z"),
  ],
};

// --- ask (verified RAG) ---------------------------------------------------
// One strong answer surfaced whatever the question, so the Ask AI experience is
// visibly working in the demo. The citations resolve to real fixture documents.
export const DEMO_ASK: AskResponse = {
  question: "What does UN R155 require for the Cyber Security Management System?",
  workspace_id: WS_R155,
  document_id: null,
  answer_md:
    "UN R155 requires the vehicle manufacturer to establish, implement and " +
    "maintain a **Cyber Security Management System (CSMS)** and to demonstrate " +
    "it through a valid Certificate of Compliance before type approval [1].\n\n" +
    "The CSMS must cover the full vehicle lifecycle — development, production " +
    "and post-production — and include processes to **identify, assess and " +
    "manage cyber security risks** across the supply chain [2]. Manufacturers " +
    "must also monitor for, detect and respond to cyber attacks and report the " +
    "effectiveness of their CSMS through periodic assessment [1].",
  not_found: false,
  confidence: 0.94,
  citations: [
    {
      citation_id: 1,
      postgres_chunk_id: "30000000-0000-4000-8000-000000000001",
      document_id: DOC_R155_REG,
      document_name: "UN R155 — Uniform provisions (full text).pdf",
      clause_id: "7.2.1",
      page_start: 12,
      page_end: 12,
      source_text_snippet:
        "The vehicle manufacturer shall demonstrate that they have a Cyber " +
        "Security Management System and that it applies to the vehicle types concerned.",
      status: "validated",
    },
    {
      citation_id: 2,
      postgres_chunk_id: "30000000-0000-4000-8000-000000000002",
      document_id: DOC_R155_REG,
      document_name: "UN R155 — Uniform provisions (full text).pdf",
      clause_id: "7.2.2.2",
      page_start: 14,
      page_end: 15,
      source_text_snippet:
        "The processes used within the Cyber Security Management System shall " +
        "ensure that security is adequately considered, including the risks and " +
        "mitigations listed in Annex 5.",
      status: "validated",
    },
  ],
  verification: {
    status: "verified",
    claims_total: 3,
    claims_validated: 3,
    citations_dropped: 0,
    warnings: [],
  },
  sources: [
    {
      index: 1,
      chunk_id: "30000000-0000-4000-8000-000000000001",
      document_id: DOC_R155_REG,
      document_name: "UN R155 — Uniform provisions (full text).pdf",
      clause_id: "7.2.1",
      page_start: 12,
      page_end: 12,
    },
    {
      index: 2,
      chunk_id: "30000000-0000-4000-8000-000000000002",
      document_id: DOC_R155_REG,
      document_name: "UN R155 — Uniform provisions (full text).pdf",
      clause_id: "7.2.2.2",
      page_start: 14,
      page_end: 15,
    },
  ],
  semantic_used: true,
  model: "demo",
};

// --- search ---------------------------------------------------------------
export function demoSearchResponse(workspaceId: string, query: string): SearchResponse {
  return {
    query,
    workspace_id: workspaceId,
    document_id: null,
    top_k: 10,
    semantic_used: true,
    rerank_used: false,
    results: [
      {
        chunk_id: "30000000-0000-4000-8000-000000000001",
        document_id: DOC_R155_REG,
        workspace_id: workspaceId,
        version_id: null,
        document_name: "UN R155 — Uniform provisions (full text).pdf",
        chunk_index: 42,
        page_start: 12,
        page_end: 12,
        clause_id: "7.2.1",
        heading: "Cyber Security Management System",
        section_path: "7 > 7.2 > 7.2.1",
        text:
          "The vehicle manufacturer shall demonstrate that they have a Cyber " +
          "Security Management System and that it applies to the vehicle types concerned.",
        scores: { rrf: 0.031, keyword_rank: 1, semantic_rank: 1 },
      },
    ],
  };
}

// --- evidence map ---------------------------------------------------------
export const DEMO_EVIDENCE: Record<string, EvidenceItem[]> = {
  [WS_R155]: [
    {
      id: "40000000-0000-4000-8000-000000000001",
      workspace_id: WS_R155,
      document_id: DOC_R155_REG,
      document_name: "UN R155 — Uniform provisions (full text).pdf",
      requirement_text:
        "The manufacturer shall maintain a Cyber Security Management System " +
        "covering development, production and post-production phases.",
      status: "COMPLIANT",
      risk: "MEDIUM",
      review_status: "APPROVED",
      archived_at: null,
      version: 2,
      citations: [
        {
          id: "50000000-0000-4000-8000-000000000001",
          chunk_id: "30000000-0000-4000-8000-000000000001",
          clause_id: "7.2.1",
          page_start: 12,
          page_end: 12,
          quote:
            "The vehicle manufacturer shall demonstrate that they have a Cyber " +
            "Security Management System.",
        },
      ],
      created_at: SEEDED_AT,
      updated_at: SEEDED_AT,
    },
    {
      id: "40000000-0000-4000-8000-000000000002",
      workspace_id: WS_R155,
      document_id: DOC_R155_REG,
      document_name: "UN R155 — Uniform provisions (full text).pdf",
      requirement_text:
        "Cyber security risks arising from suppliers and service providers shall " +
        "be identified and managed.",
      status: "IN_REVIEW",
      risk: "HIGH",
      review_status: "IN_REVIEW",
      archived_at: null,
      version: 1,
      citations: [
        {
          id: "50000000-0000-4000-8000-000000000002",
          chunk_id: "30000000-0000-4000-8000-000000000002",
          clause_id: "7.2.2.2",
          page_start: 14,
          page_end: 15,
          quote:
            "The processes used within the Cyber Security Management System shall " +
            "ensure that security is adequately considered, including the supply chain.",
        },
      ],
      created_at: SEEDED_AT,
      updated_at: SEEDED_AT,
    },
  ],
  [WS_ISO26262]: [
    {
      id: "40000000-0000-4000-8000-000000000003",
      workspace_id: WS_ISO26262,
      document_id: DOC_ISO_PART6,
      document_name: "ISO 26262-6 — Product development: software.pdf",
      requirement_text:
        "Software unit design and implementation shall use notations and design " +
        "principles appropriate to the ASIL.",
      status: "OPEN",
      risk: "UNRATED",
      review_status: "NEW",
      archived_at: null,
      version: 1,
      citations: [
        {
          id: "50000000-0000-4000-8000-000000000003",
          chunk_id: "30000000-0000-4000-8000-000000000003",
          clause_id: "8.4.3",
          page_start: 22,
          page_end: 23,
          quote:
            "The software unit design shall be developed using the methods listed " +
            "in Table 3 in accordance with the ASIL.",
        },
      ],
      created_at: SEEDED_AT,
      updated_at: SEEDED_AT,
    },
  ],
  [WS_R156]: [],
};

// --- health ---------------------------------------------------------------
export const DEMO_HEALTH: HealthResponse = {
  status: "ok",
  version: "demo",
  services: {
    postgres: { status: "ok" },
    qdrant: { status: "ok" },
    redis: { status: "ok" },
  },
  // Generation is disabled in the demo (no API/LLM); the chat stream is
  // synthesized locally from DEMO_ASK, and the Ask bar stays enabled because
  // the UI reads generation_enabled only to gate live generation.
  generation_enabled: true,
};
