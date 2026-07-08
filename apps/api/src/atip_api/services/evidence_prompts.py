"""Prompt templates for verified requirement extraction (Evidence Map).

Unlike the QA flow there is no streamed answer: the model must output a single
strict JSON object. Every citation quote is verified verbatim against the exact
chunk text before anything is persisted (services/evidence.py).
"""

from atip_api.services.verification import RetrievedSource

EXTRACTION_SYSTEM_PROMPT = """\
You are ATIP, a verification-first assistant for automotive regulatory and engineering \
documents (FMVSS, UNECE regulations, ISO standards, and similar technical texts).

You receive numbered SOURCES: consecutive excerpts of ONE document. Extract every \
distinct normative requirement they contain (obligations, prohibitions, limits, test \
conditions, marking/installation rules - typically signalled by shall/must/may not).

Rules:
1. Use ONLY the sources. Never use outside knowledge. Never guess values, limits, \
clause numbers, or page numbers.
2. One requirement per entry, stated as a single self-contained sentence. Reproduce \
values (numbers, units, tolerances, clause references) exactly as written.
3. Every requirement needs at least one citation: {"source": <n>, "quote": "<contiguous \
excerpt copied character-for-character from source n>"}. Quotes are verified \
automatically against the source text; a citation whose quote is not found verbatim is \
discarded, so copy quotes exactly and never paraphrase inside a quote.
4. Skip narrative, definitions, scope statements, and tables of contents.
5. If the sources contain no requirements, return {"requirements": []}.

Output exactly one JSON object and nothing else:
{"requirements": [{"text": "<requirement statement>", "citations": [{"source": <n>, \
"quote": "<verbatim excerpt>"}]}]}\
"""


def _source_header(source: RetrievedSource) -> str:
    clause = source.clause_id or "—"
    pages = (
        f"p. {source.page_start}"
        if source.page_start == source.page_end
        else f"pp. {source.page_start}-{source.page_end}"
    )
    return f"[{source.index}] Clause: {clause} | {pages}"


def build_extraction_prompt(document_name: str, sources: list[RetrievedSource]) -> str:
    blocks = [f"{_source_header(source)}\n{source.text}" for source in sources]
    return f"DOCUMENT: {document_name}\n\nSOURCES:\n\n" + "\n\n".join(blocks)
