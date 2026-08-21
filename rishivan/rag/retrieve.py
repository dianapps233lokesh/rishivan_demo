"""Shared RAG retrieval helpers: page-window expansion + answer prompt.

Vector search finds the relevant *region*; page-window expansion then widens
each hit to its neighbouring pages so lists, tables, or shlokas that straddle a
page break arrive whole (the top-k alone often truncates them).
"""

from __future__ import annotations

from itertools import groupby

from rishivan.council.source_matrix import source_weight
from rishivan.rag.authority import authority_for_slug
from rishivan.rag.books import title_for_slug

PAGE_WINDOW = 1          # pages to include on either side of each hit

# Chart-grounded retrieval: look each placement up in BPHS rather than the
# question wording. Tunable POC defaults.
FACT_PER_QUERY_K = 2     # BPHS hits to pull per chart fact
FACT_MAX_PAGES = 10     # cap on distinct source pages fed to the model


def expand_to_page_window(store, hit_metadatas: list[dict], window: int = PAGE_WINDOW):
    """Widen retrieval hits to full neighbouring pages.

    `store` is a VectorStore (see rishivan.rag.vector_store). Returns
    (context_text, page_groups) where page_groups is an ordered list of
    {"page_number", "text", "n_elements"} for display.
    """
    # Pages needed per document: each hit's page +/- window (page numbers >= 1).
    per_doc: dict[int, set[int]] = {}
    for m in hit_metadatas:
        pages = per_doc.setdefault(m["document_id"], set())
        for p in range(m["page_number"] - window, m["page_number"] + window + 1):
            if p >= 1:
                pages.add(p)
    if not per_doc:
        return "", []

    pages_by_doc = {doc: sorted(pages) for doc, pages in per_doc.items()}
    rows = store.fetch_pages(pages_by_doc)
    # Reading order: document, then page, then element position on the page.
    rows.sort(
        key=lambda r: (
            r["metadata"]["document_id"],
            r["metadata"]["page_number"],
            r["metadata"]["element_index"],
        )
    )

    context_parts: list[str] = []
    page_groups: list[dict] = []
    for (_doc, page), grp in groupby(
        rows,
        key=lambda r: (r["metadata"]["document_id"], r["metadata"]["page_number"]),
    ):
        grp = list(grp)
        body = "\n".join(r["document"] for r in grp)
        # Name the book in the header. Without it the model knows only a page
        # number and invents the title when asked to cite — and a given page
        # number exists in most of the corpus, so the guess is rarely right.
        slug = grp[0]["metadata"].get("book_slug")
        title = title_for_slug(slug)
        context_parts.append(f"--- Source: {title}, Page {page} ---\n{body}")
        page_groups.append({
            "page_number": page,
            "text": body,
            "n_elements": len(grp),
            "book_slug": slug,
            "book_title": title,
        })

    return "\n\n".join(context_parts), page_groups


def _fact_queries(
    question: str, facts: list[str], max_queries: int | None = None
) -> list[str]:
    """Retrieval queries from the chart: the question + interpretable facts.

    The daśā line is dropped (BPHS Vol 1 does not cover daśā effects); it still
    reaches the model as ground truth, just not as a search query.

    ``max_queries`` caps the total. Embedding and vector search both scale
    linearly with this count, and a full chart yields ~30 facts, so an
    uncapped call dominates request latency. The question is always kept.
    """
    queries = [q for q in (question,) if q]
    queries += [f for f in facts if not f.startswith("Currently running")]
    if max_queries is not None and len(queries) > max_queries:
        queries = queries[:max_queries]
    return queries


def collect_chart_context(
    store,
    embed_fn,
    question: str,
    facts: list[str],
    per_query_k: int = FACT_PER_QUERY_K,
    max_pages: int = FACT_MAX_PAGES,
    domain_filter: list[str] | None = None,
    max_queries: int | None = None,
    domain: str | None = None,
):
    """Retrieve context by looking each chart fact up in the corpus.

    `embed_fn` maps a list of texts to a list of embedding vectors (one batch
    call). Pages are ranked by how many facts point to them (a page many
    placements share is central to the reading), capped at `max_pages`, then
    fetched whole. Returns (context_text, page_groups) like expand_to_page_window.

    When ``domain_filter`` is provided (e.g. ``["core", "prediction"]``), only
    books tagged with those domains are searched.

    ``domain`` is the client life domain the question routed to. It weights each page by
    Eight Rishis §15's Book × Rishi matrix, which is the only signal available here: a
    page carries no per-rule affinity, so without §15 a Muhurta text ranks the same for
    a question about identity as for one about timing an event.
    """
    queries = _fact_queries(question, facts, max_queries)
    if not queries:
        return "", []

    embeddings = embed_fn(queries)

    # Use domain-filtered search when a filter is specified.
    if domain_filter:
        all_hits = store.search_batch_filtered(embeddings, per_query_k, domain_filter)
    else:
        all_hits = store.search_batch(embeddings, per_query_k)

    # Ranking score per page: specificity (how many distinct chart facts hit
    # it) x source authority (see rishivan.rag.authority) — a demo-scaled
    # echo of the main backend's P3 retrieval philosophy
    # (score = specificity x source_authority x confidence), adapted here
    # since this page-based POC has no per-hit confidence to multiply by.
    page_score: dict[tuple[int, int], float] = {}
    first_seen: dict[tuple[int, int], int] = {}
    order = 0

    # Force-include the top-ranked page specifically matching the user's main question
    question_pages = []
    if all_hits:
        for h in all_hits[0]:
            m = h["metadata"]
            question_pages.append((m["document_id"], m["page_number"]))

    # Rank the rest of the pages by specificity x authority
    for hits in all_hits[1:]:
        seen_this_query: set[tuple[int, int]] = set()
        for h in hits:
            m = h["metadata"]
            key = (m["document_id"], m["page_number"])
            if key in seen_this_query:
                continue
            seen_this_query.add(key)
            slug = m.get("book_slug")
            # authority x §15 relevance: how authoritative this book is, and how
            # relevant it is to what was actually asked.
            page_score[key] = page_score.get(key, 0.0) + authority_for_slug(
                slug
            ) * source_weight(slug, domain)
            if key not in first_seen:
                first_seen[key] = order
                order += 1

    # Combine: start with the top question page, then fill with the highest-ranked fact pages
    final_pages = []
    if question_pages:
        final_pages.append(question_pages[0])  # Force-include user's question match

    # Add other high-scoring fact pages up to max_pages
    for fp in sorted(page_score, key=lambda k: (-page_score[k], first_seen[k])):
        if len(final_pages) >= max_pages:
            break
        if fp not in final_pages:
            final_pages.append(fp)

    if not final_pages:
        return "", []

    hit_metadatas = [{"document_id": d, "page_number": p} for d, p in final_pages]

    # window=0: these pages already give breadth; no neighbour expansion needed.
    return expand_to_page_window(store, hit_metadatas, window=0)
