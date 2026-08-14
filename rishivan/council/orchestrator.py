"""Council Orchestrator — the main pipeline for the Rishi Council POC.

Flow:
  1. Classify query → pick primary Rishi + query domain
  2. Compute chart (natal/muhurta/prashna) if needed
  3. Translate & enrich search query
  4. Retrieve from Qdrant filtered by Rishi's book domains
  5. Build Rishi-voiced prompt (natural flowing prose)
  6. Stream answer via Gemini (Vertex or API key backend)
"""
from __future__ import annotations

import logging
from collections.abc import Generator
from datetime import datetime, timedelta

from rishivan.chart.panchang import mentions_panchang, relative_day_offset
from rishivan.council.classifier import classify_query
from rishivan.council.domains import RISHI_BOOK_DOMAINS, QueryDomain
from rishivan.council.prompts import build_rishi_prompt

logger = logging.getLogger(__name__)

# Retrieval budget. A full natal chart yields ~30 facts; using every one as a
# search query cost ~14s of embedding plus ~4s of vector search per request.
MAX_FACT_QUERIES = 8
MAX_PAGES = 4


def council_consult(
    client,
    store,
    question: str,
    *,
    rishi_override: str | None = None,
    birth_data=None,
    query_time: datetime | None = None,
    target_time: datetime | None = None,
    lat: float | None = None,
    lon: float | None = None,
    tz_offset: float = 5.5,
    place: str = "",
    backend: str = "vertex",   # "vertex" | "gemini"
    conversation=None,         # poc.council.conversation.Conversation
) -> dict:
    """Full Council consultation pipeline.

    Returns a dict with keys:
      primary_rishi, rishi_title, query_domain, classification,
      chart_summary, chart_facts, sources, search_query, answer_stream
    """
    from rishivan.council.client import model_name
    _model = model_name(backend, "flash")
    _embed_model = model_name(backend, "embed")

    result = {
        "primary_rishi": rishi_override or "vyom",
        "rishi_title": "",
        "query_domain": QueryDomain.GENERAL,
        "classification": {},
        "chart_summary": None,
        "chart_facts": None,
        "sources": [],
        "search_query": question,
        "answer_stream": None,
    }

    # ── Step 1: Classify ──────────────────────────────────────────────────────
    classification = classify_query(
        client, question, model=_model, conversation=conversation
    )
    if rishi_override:
        # Explicit Rishi chosen — still use the classified domain.
        classification["primary_rishi"] = rishi_override

    rishi = classification["primary_rishi"]
    domain = classification["query_domain"]

    # If natal but no birth data, fall back to prashna
    if domain == QueryDomain.NATAL and birth_data is None:
        logger.info("Natal query but no birth data — falling back to PRASHNA")
        domain = QueryDomain.PRASHNA
        classification["query_domain"] = domain

    result["primary_rishi"] = rishi
    result["query_domain"] = domain
    result["classification"] = classification

    # Attach Rishi title from personas
    from rishivan.council.personas import get_persona
    persona = get_persona(rishi)
    result["rishi_title"] = persona.title

    # ── Step 2: Chart computation ─────────────────────────────────────────────
    chart = None
    chart_facts = None

    if domain == QueryDomain.NATAL and birth_data is not None:
        from rishivan.chart.ephemeris import compute_chart, summarize
        from rishivan.chart.facts import derive_facts
        from rishivan.chart import p1_bridge

        # Real P1 backend first — all 16 vargas, not just D1 — falling back
        # to this demo's own D1-only Swiss Ephemeris calc when it's not
        # configured or the request fails for any reason.
        real_facts = p1_bridge.fetch_real_chart_facts()
        chart = compute_chart(birth_data)
        result["chart_summary"] = summarize(chart)
        if real_facts:
            chart_facts = real_facts
        else:
            chart_facts = derive_facts(chart)
        result["chart_facts"] = chart_facts

    # Daily timing windows are pure arithmetic on sunrise/sunset, so compute
    # them rather than letting the model deflect ("check a local almanac") or
    # invent clock times.
    panchang_summary = None
    if mentions_panchang(question):
        from rishivan.chart.panchang import compute_panchang
        base = (query_time or datetime.now()).date()
        target = base + timedelta(days=relative_day_offset(question))
        pan = compute_panchang(
            target,
            lat=lat if lat is not None else 28.6139,
            lon=lon if lon is not None else 77.2090,
            tz_offset=tz_offset,
            place=place or "New Delhi",
        )
        panchang_summary = pan.summary()
        result["panchang"] = panchang_summary

    if domain in (QueryDomain.MUHURTA, QueryDomain.PRASHNA):
        from rishivan.chart.ephemeris import summarize
        from rishivan.chart.facts import derive_muhurta_facts
        from rishivan.chart.transit import chart_for_moment
        now = query_time or datetime.now()
        if domain == QueryDomain.MUHURTA:
            # Without an explicit target, honour the day the question names —
            # "is tomorrow good?" must not be answered from today's sky.
            moment = target_time or (
                now + timedelta(days=relative_day_offset(question))
            )
        else:
            moment = now
        chart = chart_for_moment(
            moment,
            lat=lat or 28.6139,
            lon=lon or 77.2090,
            place=place or "Query location",
            tz_offset=tz_offset,
        )
        chart_facts = derive_muhurta_facts(chart)
        result["chart_summary"] = summarize(chart)
        result["chart_facts"] = chart_facts

    # Computed windows are ground truth, so they lead the fact list.
    if panchang_summary:
        chart_facts = panchang_summary.splitlines() + (chart_facts or [])
        result["chart_facts"] = chart_facts

    # ── Step 3: Search query ──────────────────────────────────────────────────
    # The classifier returns this alongside the routing decision; it used to be
    # a second serial LLM round-trip costing ~5s on every consultation.
    search_query = classification.get("search_query") or question
    result["search_query"] = search_query

    # ── Step 4: Domain-filtered RAG retrieval ────────────────────────────────
    from rishivan.rag.retrieve import collect_chart_context, expand_to_page_window

    def embed_fn(texts):
        if backend == "gemini":
            # gemini-embedding-exp-03-07 supports output_dimensionality.
            # Set to 768 to match Qdrant collection built from text-embedding-004.
            from google.genai import types as _gt
            r = client.models.embed_content(
                model=_embed_model,
                contents=texts,
                config=_gt.EmbedContentConfig(output_dimensionality=768),
            )
        else:
            r = client.models.embed_content(model=_embed_model, contents=texts)
        return [e.values for e in r.embeddings]

    # Use this Rishi's book domain filter
    domain_filter = [d.value for d in RISHI_BOOK_DOMAINS.get(rishi, [])]
    # Fallback: remove filter if store has no tagged docs (POC compatibility)
    def _search_with_fallback(emb, n=5):
        if domain_filter:
            hits = store.search_filtered(emb, n_results=n, domain_filter=domain_filter)
            if hits:
                return hits
        return store.search(emb, n_results=n)

    if chart_facts:
        # Chart-grounded retrieval.
        # MAX_FACT_QUERIES / MAX_PAGES are tuned for demo latency: embedding and
        # vector search scale with the query count, and every extra page inflates
        # the prompt (and so time-to-first-token) for a ~50-word answer.
        try:
            context_text, page_groups = collect_chart_context(
                store, embed_fn, search_query, chart_facts,
                domain_filter=domain_filter if domain_filter else None,
                max_queries=MAX_FACT_QUERIES,
                max_pages=MAX_PAGES,
            )
        except Exception:  # noqa: BLE001
            qe = embed_fn([search_query])[0]
            hits = _search_with_fallback(qe)
            context_text, page_groups = (
                expand_to_page_window(store, [h["metadata"] for h in hits])
                if hits else ("", [])
            )
    else:
        qe = embed_fn([search_query])[0]
        hits = _search_with_fallback(qe)
        if not hits:
            return result
        context_text, page_groups = expand_to_page_window(store, [h["metadata"] for h in hits])

    result["sources"] = page_groups
    if not page_groups:
        return result

    # ── Step 5: Build Rishi-voiced prompt ────────────────────────────────────
    prompt = build_rishi_prompt(
        rishi_name=rishi,
        domain=domain,
        question=question,
        context=context_text,
        chart_facts=chart_facts,
        conversation=conversation,
    )

    # ── Step 6: Stream answer ─────────────────────────────────────────────────
    def answer_stream() -> Generator[str, None, None]:
        for chunk in client.models.generate_content_stream(
            model=_model,
            contents=prompt,
        ):
            if chunk.text:
                yield chunk.text

    result["answer_stream"] = answer_stream()
    return result
