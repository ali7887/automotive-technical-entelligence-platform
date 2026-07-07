"""Unit tests for LLM output parsing and citation verification.

Includes the adversarial cases from prompts/03_verified_rag_strict.md:
fake citations, malformed JSON, and unanswerable questions.
"""

import json
import uuid

from atip_api.services.verification import (
    CLAIMS_SENTINEL,
    NOT_FOUND_ANSWER,
    RetrievedSource,
    parse_llm_output,
    verify_answer,
)

_TEXT = (
    "S14.8.7 Photometry test. Each headlamp shall be designed to conform to the "
    "photometric requirements of Table XIX when tested according to the procedure "
    "of this section. The luminous intensity shall not exceed 125 candela at test "
    "point H-V."
)


def _source(index: int = 1, text: str = _TEXT) -> RetrievedSource:
    return RetrievedSource(
        index=index,
        chunk_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        document_name="fmvss108.pdf",
        clause_id="S14.8.7",
        page_start=93,
        page_end=94,
        text=text,
    )


def _raw(answer: str, claims: object) -> str:
    return f"{answer}\n{CLAIMS_SENTINEL}\n{json.dumps(claims)}"


def _claims(*citations_per_claim: list[dict], not_found: bool = False, confidence: float = 0.9):
    return {
        "not_found": not_found,
        "confidence": confidence,
        "claims": [
            {"text": f"claim {i}", "citations": citations}
            for i, citations in enumerate(citations_per_claim)
        ],
    }


# --- parsing ---


def test_parse_well_formed_output():
    raw = _raw("The limit is 125 candela [1]", _claims([{"source": 1, "quote": "125 candela"}]))
    parsed = parse_llm_output(raw)
    assert parsed.parse_error is None
    assert parsed.answer_md == "The limit is 125 candela [1]"
    assert parsed.claims is not None
    assert parsed.claims.claims[0].citations[0].source == 1


def test_parse_missing_sentinel():
    parsed = parse_llm_output("Just an answer with no claims block [1]")
    assert parsed.claims is None
    assert parsed.parse_error == "missing claims block"


def test_parse_malformed_json():
    parsed = parse_llm_output(f"Answer [1]\n{CLAIMS_SENTINEL}\n{{not valid json!!")
    assert parsed.claims is None
    assert parsed.parse_error == "malformed claims JSON"


def test_parse_tolerates_code_fence():
    payload = json.dumps(_claims([{"source": 1, "quote": "125 candela"}]))
    parsed = parse_llm_output(f"Answer [1]\n{CLAIMS_SENTINEL}\n```json\n{payload}\n```")
    assert parsed.parse_error is None
    assert parsed.claims is not None


def test_parse_clamps_confidence():
    parsed = parse_llm_output(_raw("Answer [1]", _claims([], confidence=3.5)))
    assert parsed.claims is not None
    assert parsed.claims.confidence == 1.0


# --- verification: supported answers ---


def test_verified_when_quote_matches_exactly():
    source = _source()
    quote = "The luminous intensity shall not exceed 125 candela at test point H-V."
    parsed = parse_llm_output(
        _raw("The maximum is 125 candela [1]", _claims([{"source": 1, "quote": quote}]))
    )
    verified = verify_answer(parsed, [source])
    assert verified.status == "verified"
    assert verified.not_found is False
    assert verified.answer_md == "The maximum is 125 candela [1]"
    assert len(verified.citations) == 1
    citation = verified.citations[0]
    assert citation.citation_id == 1
    assert citation.status == "validated"
    assert citation.source.chunk_id == source.chunk_id
    assert citation.snippet == quote


def test_first_validated_quote_wins_per_source():
    first = "The luminous intensity shall not exceed 125 candela at test point H-V."
    second = "photometric requirements of Table XIX"
    parsed = parse_llm_output(
        _raw(
            "125 candela [1]. Table XIX applies [1].",
            _claims([{"source": 1, "quote": first}], [{"source": 1, "quote": second}]),
        )
    )
    verified = verify_answer(parsed, [_source()])
    assert verified.status == "verified"
    assert len(verified.citations) == 1
    assert verified.citations[0].snippet == first


def test_quote_matching_ignores_whitespace_and_case():
    quote = "the LUMINOUS   intensity\nshall not exceed 125 candela"
    parsed = parse_llm_output(_raw("125 candela [1]", _claims([{"source": 1, "quote": quote}])))
    verified = verify_answer(parsed, [_source()])
    assert verified.status == "verified"
    assert verified.citations[0].status == "validated"


# --- verification: adversarial cases ---


def test_fabricated_quote_yields_not_found():
    parsed = parse_llm_output(
        _raw(
            "The limit is 500 candela [1]",
            _claims([{"source": 1, "quote": "The limit shall be 500 candela at H-V."}]),
        )
    )
    verified = verify_answer(parsed, [_source()])
    assert verified.status == "unsupported"
    assert verified.not_found is True
    assert verified.answer_md == NOT_FOUND_ANSWER
    assert verified.claims_validated == 0
    # the weak citation is surfaced with a real chunk excerpt, not the fake quote
    assert verified.citations[0].status == "weak"
    assert "500 candela" not in verified.citations[0].snippet


def test_citation_to_nonexistent_source_is_dropped():
    quote = "photometric requirements of Table XIX"
    parsed = parse_llm_output(
        _raw(
            "Table XIX applies [1]. Also see [7].",
            _claims([{"source": 1, "quote": quote}, {"source": 7, "quote": quote}]),
        )
    )
    verified = verify_answer(parsed, [_source()])
    assert verified.status == "partial"
    assert verified.citations_dropped >= 1
    assert [citation.citation_id for citation in verified.citations] == [1]
    # the [7] marker is stripped from the answer, [1] survives
    assert "[7]" not in verified.answer_md
    assert "[1]" in verified.answer_md


def test_too_short_quote_is_not_validation():
    parsed = parse_llm_output(_raw("Answer [1]", _claims([{"source": 1, "quote": "of the"}])))
    verified = verify_answer(parsed, [_source()])
    assert verified.not_found is True
    assert verified.citations[0].status == "weak"


def test_marker_without_claim_is_weak_evidence():
    quote = "photometric requirements of Table XIX"
    parsed = parse_llm_output(
        _raw("Table XIX [1], see also [2]", _claims([{"source": 1, "quote": quote}]))
    )
    verified = verify_answer(parsed, [_source(1), _source(2)])
    assert verified.status == "partial"
    statuses = {citation.citation_id: citation.status for citation in verified.citations}
    assert statuses == {1: "validated", 2: "weak"}


def test_malformed_claims_never_produce_an_answer():
    parsed = parse_llm_output(f"Confident hallucination [1]\n{CLAIMS_SENTINEL}\nnot json")
    verified = verify_answer(parsed, [_source()])
    assert verified.not_found is True
    assert verified.status == "unsupported"
    assert verified.answer_md == NOT_FOUND_ANSWER
    assert verified.citations == []
    assert any("could not be verified" in warning for warning in verified.warnings)


def test_model_not_found_is_respected():
    parsed = parse_llm_output(
        _raw("The retrieved sources do not cover this question.", _claims(not_found=True))
    )
    verified = verify_answer(parsed, [_source()])
    assert verified.status == "not_found"
    assert verified.not_found is True
    assert verified.citations == []
    assert "not cover" in verified.answer_md
