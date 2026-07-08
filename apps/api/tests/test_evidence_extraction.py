"""Deterministic unit tests for extraction parsing and citation validation.

No DB or LLM: parse_extraction_output and verify_batch are pure functions over
proposed requirements and retrieved sources.
"""

import json
import uuid

from atip_api.services.evidence import (
    ProposedRequirements,
    export_markdown,
    parse_extraction_output,
    verify_batch,
)
from atip_api.services.verification import RetrievedSource

WORKSPACE_ID = uuid.uuid4()
DOCUMENT_ID = uuid.uuid4()

QUOTE = "The luminous intensity shall not exceed 125 candela at test point H-V."


def _source(index: int = 1, text: str = QUOTE, clause: str | None = "S5.1.2") -> RetrievedSource:
    return RetrievedSource(
        index=index,
        chunk_id=uuid.uuid4(),
        document_id=DOCUMENT_ID,
        document_name="",
        clause_id=clause,
        page_start=3,
        page_end=4,
        text=f"S5.1.2 Photometric requirements. {text} Additional context sentence.",
    )


def _proposed(text: str, citations: list[dict]) -> ProposedRequirements:
    return ProposedRequirements.model_validate(
        {"requirements": [{"text": text, "citations": citations}]}
    )


def _verify(proposed: ProposedRequirements, sources: list[RetrievedSource], seen=None):
    return verify_batch(
        proposed,
        sources,
        workspace_id=WORKSPACE_ID,
        document_id=DOCUMENT_ID,
        seen_requirements=seen if seen is not None else set(),
    )


# --- parse_extraction_output ---


def test_parse_valid_json():
    raw = json.dumps(
        {"requirements": [{"text": "req", "citations": [{"source": 1, "quote": "q"}]}]}
    )
    parsed = parse_extraction_output(raw)
    assert parsed is not None
    assert parsed.requirements[0].text == "req"
    assert parsed.requirements[0].citations[0].source == 1


def test_parse_tolerates_code_fence():
    raw = '```json\n{"requirements": []}\n```'
    parsed = parse_extraction_output(raw)
    assert parsed is not None
    assert parsed.requirements == []


def test_parse_malformed_json_returns_none():
    assert parse_extraction_output("Here are the requirements: ...") is None
    assert parse_extraction_output('{"requirements": [{]}') is None


# --- verify_batch: citation validation ---


def test_validated_quote_is_kept_with_chunk_provenance():
    source = _source()
    outcome = _verify(
        _proposed("Luminous intensity max 125 cd at H-V.", [{"source": 1, "quote": QUOTE}]),
        [source],
    )
    assert len(outcome.items) == 1
    item = outcome.items[0]
    assert item.requirement_text == "Luminous intensity max 125 cd at H-V."
    assert len(item.citations) == 1
    citation = item.citations[0]
    assert citation.chunk_id == source.chunk_id
    assert citation.clause_id == "S5.1.2"
    assert (citation.page_start, citation.page_end) == (3, 4)
    assert citation.quote == QUOTE
    assert outcome.requirements_dropped == 0
    assert outcome.citations_dropped == 0


def test_quote_matching_is_whitespace_and_case_insensitive():
    outcome = _verify(
        _proposed(
            "Requirement text.",
            [{"source": 1, "quote": "  the LUMINOUS   intensity shall not exceed 125 candela"}],
        ),
        [_source()],
    )
    assert len(outcome.items) == 1


def test_fabricated_quote_drops_requirement():
    outcome = _verify(
        _proposed(
            "Fabricated requirement.",
            [{"source": 1, "quote": "The intensity shall not exceed 999 candela."}],
        ),
        [_source()],
    )
    assert outcome.items == []
    assert outcome.requirements_dropped == 1
    assert outcome.citations_dropped == 1
    assert any("unverifiable quote" in warning for warning in outcome.warnings)


def test_nonexistent_source_index_is_dropped():
    outcome = _verify(
        _proposed("Requirement.", [{"source": 7, "quote": QUOTE}]),
        [_source(index=1)],
    )
    assert outcome.items == []
    assert outcome.citations_dropped == 1
    assert any("nonexistent source [7]" in warning for warning in outcome.warnings)


def test_too_short_quote_is_not_evidence():
    outcome = _verify(
        _proposed("Requirement.", [{"source": 1, "quote": "shall not"}]),
        [_source()],
    )
    assert outcome.items == []
    assert outcome.citations_dropped == 1


def test_mixed_citations_keep_only_validated_one():
    sources = [_source(index=1), _source(index=2, text="Different unrelated content here.")]
    outcome = _verify(
        _proposed(
            "Requirement.",
            [
                {"source": 1, "quote": QUOTE},
                {"source": 2, "quote": "This quote does not exist in source two."},
            ],
        ),
        sources,
    )
    assert len(outcome.items) == 1
    assert len(outcome.items[0].citations) == 1
    assert outcome.items[0].citations[0].chunk_id == sources[0].chunk_id
    assert outcome.citations_dropped == 1


def test_duplicate_requirements_are_deduped_across_batches():
    seen: set[str] = set()
    first = _verify(
        _proposed("Same requirement.", [{"source": 1, "quote": QUOTE}]), [_source()], seen
    )
    second = _verify(
        _proposed("  same   REQUIREMENT. ", [{"source": 1, "quote": QUOTE}]), [_source()], seen
    )
    assert len(first.items) == 1
    assert second.items == []


def test_empty_requirement_text_is_dropped():
    outcome = _verify(_proposed("   ", [{"source": 1, "quote": QUOTE}]), [_source()])
    assert outcome.items == []
    assert outcome.requirements_dropped == 1


# --- markdown export rendering ---


def test_export_markdown_renders_items_and_quotes():
    from datetime import UTC, datetime

    from atip_api.models.enums import EvidenceRisk, EvidenceStatus
    from atip_api.schemas.evidence import (
        EvidenceCitationRead,
        EvidenceItemRead,
        EvidenceMapExport,
    )

    now = datetime(2026, 7, 8, tzinfo=UTC)
    export = EvidenceMapExport(
        workspace_id=WORKSPACE_ID,
        workspace_name="Homologation",
        generated_at=now,
        items=[
            EvidenceItemRead(
                id=uuid.uuid4(),
                workspace_id=WORKSPACE_ID,
                document_id=DOCUMENT_ID,
                document_name="fmvss108.pdf",
                requirement_text="Luminous intensity max 125 cd.",
                status=EvidenceStatus.OPEN,
                risk=EvidenceRisk.UNRATED,
                citations=[
                    EvidenceCitationRead(
                        id=uuid.uuid4(),
                        chunk_id=uuid.uuid4(),
                        clause_id="S5.1.2",
                        page_start=3,
                        page_end=4,
                        quote=QUOTE,
                    )
                ],
                created_at=now,
                updated_at=now,
            )
        ],
    )
    markdown = export_markdown(export)
    assert "# Evidence Map — Homologation" in markdown
    assert "## fmvss108.pdf" in markdown
    assert "Luminous intensity max 125 cd." in markdown
    assert QUOTE in markdown
    assert "S5.1.2" in markdown


def test_export_markdown_empty_state():
    from datetime import UTC, datetime

    from atip_api.schemas.evidence import EvidenceMapExport

    markdown = export_markdown(
        EvidenceMapExport(
            workspace_id=WORKSPACE_ID,
            workspace_name="Empty",
            generated_at=datetime(2026, 7, 8, tzinfo=UTC),
            items=[],
        )
    )
    assert "No evidence items" in markdown
