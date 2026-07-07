Read CLAUDE.md and docs/02_ROADMAP.md, 05_API_CONTRACT.md, 06_RAG_SPEC.md, 08_UI_SPEC.md.

Implement Phase 3 (Verified RAG) ONLY.

Hard rules:
- LLM context = ONLY retrieved chunks + metadata
- Output strict JSON:
  {
    claims[],
    final_answer_md,
    confidence,
    not_found
  }
- claims reference chunk_ids + quote_spans
- add citation validation step (validated/weak/failed)
- weak support → not_found=true
- no hallucinated citations
- add adversarial tests: unanswerable questions, fake citations, malformed JSON output

Before coding: plan first.
Implement with small commits.
