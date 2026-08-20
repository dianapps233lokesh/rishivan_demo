"""Council Orchestrator — the main pipeline for the Rishi Council POC.

Structured as a small node graph (P4's council-graph shape, scaled to a
single-process demo with no billing/persistence infra): intake decides
whether this is even an astrology question before anything else runs.

Flow:
  0. Intake/guardrail bypass → smalltalk or gibberish gets a warm, LLM-only
     reply (rishivan.council.warmth) with no chart computation and no
     retrieval at all.
  1. Classify query → pick primary Rishi + query domain
  2. Compute chart (natal/muhurta/prashna) if needed — always local
     (Swiss Ephemeris + the vendored varga/dasha/numerology/ashtakavarga
     engines), never a network call to another service.
  3. Translate & enrich search query
  4. Retrieve from Qdrant filtered by Rishi's book domains, ranked by
     specificity x source authority (rishivan.rag.authority)
  5. Build Rishi-voiced prompt (natural flowing prose)
  6. Stream answer via Vertex AI
  7. Supporting Rishis contribute COMPUTED evidence, never a second voice
     (rishivan.council.contributors) -- gathered in step 4b and labelled in
     the primary's prompt.
"""
from __future__ import annotations

import logging
from collections.abc import Generator
from datetime import datetime, timedelta

from rishivan.chart.local_numerology import numerology_table_markdown
from rishivan.chart.local_varga import varga_table_markdown
from rishivan.chart.panchang import mentions_panchang, relative_day_offset
from rishivan.council.classifier import classify_query
from rishivan.council.domains import QueryDomain
from rishivan.council.prompts import build_rishi_prompt

logger = logging.getLogger(__name__)

# Retrieval budget. None = no cap: every chart fact (a full natal chart
# yields ~30) is used as a search query against the corpus.
MAX_FACT_QUERIES = None
MAX_PAGES = 20
MAX_MATCHED_RULES = 10
"""Matched rules to put in the prompt.

Bounded because a rule block is prose the model must read before it answers, and because
one verse can fan out into siblings that share a condition: BPHS 26.1 produced six rules
for one placement, so an unbounded list would spend the prompt on near-duplicates."""


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
    conversation=None,         # rishivan.council.conversation.Conversation
) -> dict:
    """Full Council consultation pipeline.

    Returns a dict with keys:
      primary_rishi, rishi_title, query_domain, classification,
      chart_summary, chart_facts, sources, search_query, answer_stream
    """
    from rishivan.council.client import model_name
    _model = model_name("flash")
    _embed_model = model_name("embed")

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
        "is_warmth": False,
        "matched_rules": [],
        "contributors": [],
        "chart_tokens": {},
        "rules_true_of_chart": 0,
        "routing": {},
    }

    # ── Step 0/1: Intake — classify, and bypass everything else for small
    # talk or gibberish ─────────────────────────────────────────────────────
    classification = classify_query(
        client, question, model=_model, conversation=conversation
    )
    if rishi_override:
        # Explicit Rishi chosen — still use the classified domain.
        classification["primary_rishi"] = rishi_override

    result["classification"] = classification

    if classification.get("is_smalltalk_or_gibberish"):
        # A greeting, thanks, or gibberish never needs a chart, a Qdrant
        # search, or a persona costume — just a warm human reply. Stay with
        # whoever the seeker was already speaking to for continuity; default
        # to Vyom (a neutral, collective-feeling voice) otherwise.
        from rishivan.council.warmth import respond_warmly

        warmth_rishi = (
            conversation.current_rishi
            if conversation is not None and not conversation.is_empty
            else "vyom"
        )
        from rishivan.council.personas import get_persona

        persona = get_persona(warmth_rishi)
        result["primary_rishi"] = warmth_rishi
        result["rishi_title"] = persona.title
        result["is_warmth"] = True
        result["answer_stream"] = respond_warmly(
            client, question, model=_model, conversation=conversation
        )
        return result

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

        # Pure local computation, always — Swiss Ephemeris + the vendored
        # varga engine (rishivan.chart.vendor.varga), the same pure-arithmetic
        # formulas the main backend uses, with zero network calls. This is
        # also more correct than calling out to a shared backend would be:
        # it computes for the birth details just typed into this demo's own
        # form, not for some other fixed identity.
        chart = compute_chart(birth_data)
        result["chart_summary"] = summarize(chart)
        chart_facts = derive_facts(chart)
        covered_vargas = {"D1"}

        # Every divisional chart governs a specific life area, and only the
        # ones this SPECIFIC question actually touches should ground the
        # reading — the classifier (same LLM call as intent/domain routing)
        # already decided this as "relevant_vargas". Add whichever of those
        # aren't already covered above, computed locally via the same
        # zero-IO engine as the chart-table feature.
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

    # ── Step 3b: which Rishis own this question ───────────────────────────────
    # Eight Rishis §1 puts this between the classifier and retrieval, and §12 makes the
    # QUESTION own the domain rather than the persona: a persona like `medhan` spans
    # prema + vansh + aarogya, whose §4-11 coverage sets together reach eleven of twelve
    # houses, so persona-scoped relevance cannot discriminate. Routing once here serves
    # both page ranking (§15) and rule relevance (§4-11).
    from rishivan.council.domains import primary_rishi_for
    from rishivan.council.routing import merge_supporting, route_question

    routing = merge_supporting(
        route_question(question), classification.get("supporting_rishis") or []
    )
    # The routed life domain, not the classifier, decides who speaks: the coverage gate
    # keys off the domain, so letting the LLM pick the voice independently allowed a
    # persona with no coverage of the subject to answer.
    rishi = primary_rishi_for(routing.primary, classifier_pick=rishi)
    persona = get_persona(rishi)
    result["primary_rishi"] = rishi
    result["rishi_title"] = persona.title
    result["life_domain"] = routing.primary
    result["routing"] = {
        "primary": routing.primary,
        "secondary": list(routing.secondary),
        "matched": {k: list(v) for k, v in routing.matched.items()},
        "unsupported": routing.unsupported,
    }

    # ── Step 4: Domain-filtered RAG retrieval ────────────────────────────────
    from rishivan.rag.retrieve import collect_chart_context, expand_to_page_window

    def embed_fn(texts):
        r = client.models.embed_content(model=_embed_model, contents=texts)
        return [e.values for e in r.embeddings]

    # Blueprint §4 level 1: retrieve within the universes this question invokes.
    # Replaces a filter on ten hand-invented `book_domain` tags that appear in neither
    # client document and flattened three of §4's levels into one list -- and which was
    # also broken, since `book_domain` was written both as `'foundation'` and as the
    # stringified list `"['numerology']"`, so `MatchAny` silently missed about a quarter
    # of the corpus. `book_slug` is written consistently and already indexed.
    #
    # School is deliberately NOT filtered: §8 rule 5 asks for labelling, and every
    # §4-11 protocol ends in "cross-school confirmation".
    from rishivan.council.source_matrix import slugs_for_universe

    domain_filter = sorted(
        slug
        for universe in routing.universes
        for slug in slugs_for_universe(universe)
    )
    # Fallback: remove filter if store has no tagged docs (POC compatibility)
    def _search_with_fallback(emb, n=10):
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
                domain=routing.primary,
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

    # ── Step 4b: Koonji rule matching ────────────────────────────────────────
    #
    # Rules run ALONGSIDE page retrieval rather than instead of it. Only chapter 26
    # of one book is approved so far, so most questions still match nothing, and a
    # reading that silently returned less because the rule base is thin would be a
    # regression on the page search that already works.
    #
    # The order of operations is the load-bearing decision. Every approved rule is
    # exact-matched against the chart FIRST, and only the survivors are ranked by
    # relevance to the question. Nominating by similarity first was measured losing
    # 11 to 14 of the 21 rules true of a test chart, because a similarity window
    # cannot prefer what it has no way of knowing is true. Matching first makes
    # recall total by construction; ranking 21 known-true rules is the easy half.
    matched_rules = []
    contributors: tuple = ()
    if chart is not None:
        try:
            from rishivan.chart.tokens import all_chart_tokens
            from rishivan.config import settings as _settings
            from rishivan.rag.rules import rule_collection_name, rules_for_question
            from rishivan.rag.vector_store import get_vector_store

            rule_store = get_vector_store(
                rule_collection_name(_settings.VECTOR_COLLECTION)
            )
            from rishivan.rag.rules import rank_true_rules, true_rules

            tokens = all_chart_tokens(chart)
            result["chart_tokens"] = tokens
            # Split rather than calling `rules_for_question`, so the UI can report how
            # many rules were TRUE of the chart alongside how many this Rishi was shown.
            # The gap between the two numbers is the specialisation doing its job, and it
            # should be visible rather than implied.
            applicable = true_rules(rule_store, tokens)
            result["rules_true_of_chart"] = len(applicable)
            matched_rules = rank_true_rules(
                applicable,
                embed_fn([search_query])[0],
                routing=routing,
                limit=MAX_MATCHED_RULES,
                # The question's own words gate what may be shown. Eight Rishis §9
                # forbids predicting death as certainty, and gating on the answering
                # Rishi's domains instead was circular: Medhan owns health, so every
                # Medhan question admitted every death rule. Measured -- "will my
                # marriage be happy and will my wife be healthy?" returned four rules
                # predicting the manner of the querent's death.
                question=question,
            )

            from rishivan.council.contributors import gather

            contributors = gather(
                chart, applicable, routing=routing,
                question=question, when=query_time,
            )
            result["contributors"] = [
                {"rishi": r.rishi, "computed": r.computed,
                 "rules": len(r.rules), "note": r.note}
                for r in contributors
            ]
        except Exception:  # noqa: BLE001 - a missing rule base must not break an answer
            matched_rules = []
    result["matched_rules"] = matched_rules

    result["sources"] = page_groups
    # Kept for Step 7 (the caller runs it only after the primary answer has
    # finished streaming, so an extra generation call never delays the first
    # token the seeker sees).
    result["_context_text"] = context_text
    if not page_groups and not matched_rules:
        return result

    # ── Step 5: Build Rishi-voiced prompt ────────────────────────────────────
    from rishivan.council.prompts import rule_context

    prompt = build_rishi_prompt(
        rishi_name=rishi,
        domain=domain,
        question=question,
        context=context_text,
        chart_facts=chart_facts,
        conversation=conversation,
        rules=rule_context(matched_rules),
        life_domain=routing.primary,
        contributors=contributors,
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

    # Step 7 needs no deferral any more. The supporting Rishis contributed in step 4b
    # (rishivan.council.contributors) and every one of them is deterministic, so their
    # evidence is already inside the prompt above rather than arriving as a second
    # generation call the caller had to run after the primary answer finished.
    return result
