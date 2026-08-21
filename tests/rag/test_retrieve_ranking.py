"""Page ranking weighted by Eight Rishis §15.

Page retrieval has no per-rule signal to lean on, so §15's Book × Rishi matrix is the
only thing that says a Muhurta text is weak evidence about identity and strong evidence
about timing an event. Applied as a multiplier on source authority: "how authoritative
is this book" x "how relevant is it to what was asked".
"""

from rishivan.rag.retrieve import collect_chart_context


class FakeStore:
    """Returns the same page from two different books for every query."""

    def __init__(self, pages):
        self._pages = pages

    def search_batch(self, embeddings, per_query_k):
        return [list(self._pages) for _ in embeddings]

    def fetch_pages(self, pages_by_doc):
        out = []
        for doc_id, page_numbers in pages_by_doc.items():
            for page in page_numbers:
                out.append({
                    "document": f"text of doc {doc_id} page {page}",
                    "metadata": {
                        "document_id": doc_id,
                        "page_number": page,
                        "element_index": 0,
                        "book_slug": _SLUG_BY_DOC[doc_id],
                    },
                })
        return out


_SLUG_BY_DOC = {1: "bphs-gcsharma-vol1", 2: "muhurtachintamani"}


def _hit(doc_id, page):
    return {
        "document": "x",
        "metadata": {
            "document_id": doc_id,
            "page_number": page,
            "book_slug": _SLUG_BY_DOC[doc_id],
        },
    }


PAGES = [_hit(1, 10), _hit(2, 20)]


def _embed(texts):
    return [[1.0, 0.0] for _ in texts]


def _slugs_in_order(domain):
    _text, groups = collect_chart_context(
        FakeStore(PAGES), _embed, "a question", ["Saturn is in the 7th house."],
        domain=domain, max_pages=2,
    )
    return [g["book_slug"] for g in groups]


def test_an_identity_question_ranks_bphs_above_the_muhurta_text():
    """§15: BPHS is High for Atma, the Muhurta corpus is Low."""
    assert _slugs_in_order("atma")[0] == "bphs-gcsharma-vol1"


def test_both_books_are_still_returned():
    """Weighting reorders; it must not silently drop a source."""
    assert set(_slugs_in_order("atma")) == {"bphs-gcsharma-vol1", "muhurtachintamani"}


def test_ranking_without_a_domain_still_works():
    """An unsupported or unrouted question has no domain, and retrieval must degrade to
    plain authority rather than fail."""
    assert _slugs_in_order(None)
