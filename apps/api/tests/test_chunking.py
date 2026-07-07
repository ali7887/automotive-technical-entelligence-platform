import hashlib
import uuid

from atip_api.processing.chunking import (
    MAX_CHUNK_TOKENS,
    ChunkDraft,
    chunk_pages,
    detect_clause,
    estimate_tokens,
)

_CLAUSE_BODY = (
    "The lamp shall be designed and constructed so that in normal conditions of use, "
    "and notwithstanding the vibration to which it may be subjected, its satisfactory "
    "operation remains assured and it retains the characteristics prescribed herein. "
)


def _regulation_pages() -> list[str]:
    page1 = "\n".join(
        [
            "6.1 General specifications",
            *[_CLAUSE_BODY.strip()] * 12,
            "6.1.4.2 Colour of light emitted",
            *[_CLAUSE_BODY.strip()] * 12,
        ]
    )
    page2 = "\n".join(
        [
            "S5.1.2 Photometric requirements",
            *[_CLAUSE_BODY.strip()] * 12,
        ]
    )
    return [page1, page2]


def test_chunking_is_deterministic():
    pages = _regulation_pages()
    first = chunk_pages(pages)
    second = chunk_pages(pages)
    assert first == second
    assert [draft.content_hash for draft in first] == [draft.content_hash for draft in second]


def test_chunk_ids_stable_per_document():
    pages = _regulation_pages()
    document_id = uuid.UUID("00000000-0000-0000-0000-000000000001")
    ids_a = [draft.chunk_id(document_id) for draft in chunk_pages(pages)]
    ids_b = [draft.chunk_id(document_id) for draft in chunk_pages(pages)]
    assert ids_a == ids_b
    other_document = uuid.UUID("00000000-0000-0000-0000-000000000002")
    assert ids_a != [draft.chunk_id(other_document) for draft in chunk_pages(pages)]


def test_detects_unece_and_fmvss_clauses():
    assert detect_clause("6.4.3.1 Test procedure") == ("6.4.3.1", "Test procedure")
    assert detect_clause("S5.1.2 Photometric requirements") == (
        "S5.1.2",
        "Photometric requirements",
    )
    assert detect_clause("S4. Definitions") == ("S4", "Definitions")


def test_does_not_invent_clause_ids():
    assert detect_clause("The lamp shall operate normally") is None
    assert detect_clause("2026 model year vehicles") is None  # bare number is not a clause
    drafts = chunk_pages(["Plain prose with no numbering at all.\nAnother line of prose."])
    assert all(draft.clause_id is None for draft in drafts)
    assert all(draft.heading is None for draft in drafts)


def test_clause_metadata_assigned_to_chunks():
    drafts = chunk_pages(_regulation_pages())
    assert drafts[0].clause_id == "6.1"
    assert drafts[0].heading == "General specifications"
    assert any(draft.clause_id == "6.1.4.2" for draft in drafts)
    assert any(draft.clause_id == "S5.1.2" for draft in drafts)


def test_page_ranges_are_preserved():
    drafts = chunk_pages(_regulation_pages())
    assert drafts[0].page_start == 1
    assert drafts[-1].page_end == 2
    for draft in drafts:
        assert 1 <= draft.page_start <= draft.page_end <= 2
    # a chunk spanning few short pages keeps the full range
    tiny = chunk_pages(["line one", "line two", "line three"])
    assert len(tiny) == 1
    assert (tiny[0].page_start, tiny[0].page_end) == (1, 3)


def test_chunk_sizes_are_bounded():
    drafts = chunk_pages(_regulation_pages())
    assert len(drafts) > 1
    line_tokens = estimate_tokens(_CLAUSE_BODY.strip())
    for draft in drafts:
        assert draft.token_count <= MAX_CHUNK_TOKENS + line_tokens
    assert [draft.chunk_index for draft in drafts] == list(range(len(drafts)))


def test_empty_pages_produce_no_chunks():
    assert chunk_pages([]) == []
    assert chunk_pages(["", "   \n  ", ""]) == []


def test_hash_matches_text():
    drafts = chunk_pages(_regulation_pages())
    for draft in drafts:
        assert draft.content_hash == hashlib.sha256(draft.text.encode("utf-8")).hexdigest()
        assert isinstance(draft, ChunkDraft)
