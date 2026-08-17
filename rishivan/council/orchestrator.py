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

from rishivan.chart.local_numerology import numerology_table_markdown
from rishivan.chart.local_varga import varga_table_markdown
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
        "chart_table": None,
        "chart_table_error": None,
        "nakshatra_now": None,
        "relevant_chart_tables": {},
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
            # p1_bridge only ever returns varga placements (D1/D9/D10) — it
            # has no dasha endpoint — so without this, any reading grounded
            # via the real backend lost all Vimshottari dasha facts, even
            # though dasha is pure local arithmetic on the Moon's birth
            # nakshatra and never depended on that backend being reachable.
            from rishivan.chart.facts import derive_dasha_facts
            chart_facts = real_facts + derive_dasha_facts(chart, query_time or datetime.now())
            covered_vargas = set(p1_bridge.VARGAS_FOR_DEMO)  # D1, D9, D10
        else:
            chart_facts = derive_facts(chart)
            covered_vargas = {"D1"}

        # Every divisional chart governs a specific life area, and only the
        # ones this SPECIFIC question actually touches should ground the
        # reading — the classifier (same LLM call as intent/domain routing)
        # already decided this as "relevant_vargas". Add whichever of those
        # aren't already covered above, computed locally via the same
        # zero-IO engine as the chart-table feature, so this works even when
        # the real P1 backend is unreachable.
        extra_codes = [
            c for c in classification.get("relevant_vargas", [])
            if c not in covered_vargas
        ]
        if extra_codes:
            from rishivan.chart.local_varga import varga_facts
            for code in extra_codes:
                extra = varga_facts(chart, code)
                if extra:
                    chart_facts = chart_facts + extra
                    # The "Computed Chart" UI only ever showed D1, so a
                    # marriage reading grounded in D9 (or any other varga)
                    # had no visible chart to check it against — surface the
                    # table for whatever actually grounded this answer.
                    table = varga_table_markdown(chart, code)
                    if table:
                        result["relevant_chart_tables"][code] = table
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

    # "Show me my chart" / "compute d9 chart" / "what's my mulank" is a
    # display request, not an interpretation question — the classifier LLM
    # call above already decided this (intent/chart_type/varga_code), so
    # answer it with a deterministic table and skip retrieval/LLM entirely:
    # no Rishi voice, no closing question. A question ABOUT the chart
    # ("what sign is my moon in?") comes back with intent "fact" and falls
    # through to the normal LLM path below.
    #
    # All three table builders compute locally with the main repo's own
    # pure-arithmetic engines (app.astro.kundli.varga, app.astro.ankshastra
    # .numbers, app.astro.bala.ashtakavarga — same maths the real backend
    # uses), so every divisional chart, numerology number, and ashtakavarga
    # table works straight from the birth data just entered here, without
    # that backend's HTTP server, database, or auth needing to be running.
    if chart is not None and classification.get("intent") == "chart":
        chart_type = classification.get("chart_type", "varga")
        if chart_type == "numerology":
            if birth_data is None:
                result["chart_table_error"] = (
                    "Numerology needs a date of birth, and none was given for "
                    "this reading."
                )
                return result
            table = numerology_table_markdown(birth_data, chart)
            error_subject = "numerology"
        elif chart_type == "ashtakavarga":
            from rishivan.chart.local_ashtakavarga import ashtakavarga_table_markdown
            table = ashtakavarga_table_markdown(chart)
            error_subject = "ashtakavarga"
        elif chart_type == "dasha":
            from rishivan.chart.local_dasha import dasha_table_markdown
            table = dasha_table_markdown(chart, query_time or datetime.now())
            error_subject = "vimshottari dasha"
        else:
            code = classification.get("varga_code", "D1")
            table = varga_table_markdown(chart, code)
            error_subject = f"{code} chart"
        if table:
            result["chart_table"] = table
        else:
            # Never fall back to a different chart/number than what was
            # asked for — an honest "can't compute this" beats a silently
            # wrong table.
            result["chart_table_error"] = (
                f"I can't compute {error_subject} in this environment right now."
            )
        return result

    # Ground-truth nakshatra & dasha, shown in the UI regardless of what the
    # Rishi's prose says: an LLM instruction to "name the nakshatra plainly
    # when asked" is not reliably followed (it gets paraphrased into flavour
    # text like "the star of unshakeable victory" instead of the real name),
    # so the accurate names must be surfaced independently of the voice.
    if chart is not None and domain == QueryDomain.NATAL:
        from rishivan.chart.dasha import current_periods
        from rishivan.chart.transit import transit_chart

        birth_moon = chart.planets["Moon"]
        today_moon = transit_chart().planets["Moon"]
        cur = current_periods(chart, query_time or datetime.now())
        result["nakshatra_now"] = {
            "birth": {
                "nakshatra": birth_moon.nakshatra,
                "pada": birth_moon.pada,
                "rashi": birth_moon.rashi,
            },
            "today": {
                "nakshatra": today_moon.nakshatra,
                "pada": today_moon.pada,
                "rashi": today_moon.rashi,
            },
            "dasha": [
                {"level": level, "lord": p.lord, "ends": p.end.date().isoformat()}
                for level, p in cur.items() if p is not None
            ],
        }

    # ── Step 3: Search query ──────────────────────────────────────────────────
    # The classifier returns this alongside the routing decision; it used to be
    # a second serial LLM round-trip costing ~5s on every consultation.
    search_query = classification.get("search_query") or question
    result["search_query"] = search_query

    # When the seeker specifically named one dasha level (maha/antar/
    # pratyantar), the classifier itself decided that — not a keyword guess
    # — so ground retrieval in exactly that period's ruling planet, the same
    # way the tejan remedy branch below grounds by the Mahadasha lord.
    dasha_level = classification.get("dasha_level", "none")
    if dasha_level != "none" and chart is not None:
        from rishivan.chart.dasha import current_periods
        cur_dasha = current_periods(chart, query_time or datetime.now())
        if dasha_level == "all":
            levels = [(lvl, cur_dasha.get(lvl)) for lvl in ("maha", "antar", "pratyantar")]
            levels = [(lvl, p) for lvl, p in levels if p]
            if levels:
                chain = " → ".join(f"{p.lord} {lvl}dasha" for lvl, p in levels)
                search_query = f"{search_query} — current dasha: {chain}"
                result["search_query"] = search_query
        else:
            p = cur_dasha.get(dasha_level)
            if p:
                search_query = f"{search_query} — current {dasha_level}dasha lord: {p.lord}"
                result["search_query"] = search_query

    # Remedies are grounded by planet, not by the word "remedy" — BPHS titles
    # its remedy chapters by planet name ("Saturn", "Mercury"), so a bare
    # "remedies" query misses them. Tejan (the remedies Rishi) is the signal
    # that this reading needs one; the running Mahadasha lord is who the
    # remedy is actually for.
    if rishi == "tejan" and chart is not None:
        from rishivan.chart.dasha import current_periods
        cur = current_periods(chart, query_time or datetime.now())
        if cur["maha"]:
            search_query = (
                f"{search_query} — remedies for {cur['maha'].lord}: "
                "mantra, gemstone, donation, ritual"
            )
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
