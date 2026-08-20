"""Run the evaluation set through the rule path and print what to grade.

    uv run python -m scripts.eval_rules
    uv run python -m scripts.eval_rules --csv eval.csv

Costs one embedding call for the chart and nothing else -- no answer is generated, so this
is the cheap half. It reports the mechanical facts a human should not have to work out:
where the question routed, how many rules were true of the chart, which were shown, and
whether the safety gate withheld anything.

Routing accuracy (Eight Rishis §18's first metric) is graded automatically against each
question's `expect_domain`. Everything else needs the answer, which `--answers` generates.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import sys

from rishivan.chart.ephemeris import BirthData, compute_chart
from rishivan.chart.tokens import all_chart_tokens
from rishivan.config import settings
from rishivan.council.domains import primary_rishi_for
from rishivan.council.routing import route_question
from rishivan.knowledge.match.safety import withhold_reasons
from rishivan.rag.rules import (
    group_by_school,
    rank_true_rules,
    rule_collection_name,
    true_rules,
)
from rishivan.rag.vector_store import get_vector_store
from tests.eval.questions import QUESTIONS

# A fixed chart, so runs are comparable. New Delhi, 1 Jan 1990, 06:29 IST.
CHART = BirthData(1990, 1, 1, 6, 29, 0, 5.5, 28.6139, 77.2090, "New Delhi")
SHOWN = 6


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="grade the rule path on the eval set")
    parser.add_argument("--csv", help="also write a row per question here, for grading")
    parser.add_argument(
        "--only-gaps", action="store_true", help="run only the known-gap questions"
    )
    args = parser.parse_args(argv)

    chart = compute_chart(CHART)
    tokens = all_chart_tokens(chart)
    store = get_vector_store(rule_collection_name(settings.VECTOR_COLLECTION))
    if not store.exists():
        print("no rule collection -- run scripts.embed_rules first", file=sys.stderr)
        return 2

    applicable = true_rules(store, tokens, with_vectors=True)
    print(f"chart: {CHART.place} {CHART.year}-{CHART.month:02d}-{CHART.day:02d} "
          f"{CHART.hour:02d}:{CHART.minute:02d}  lagna={chart.lagna_rashi}")
    print(f"rules published: {store.count()}   true of this chart: {len(applicable)}\n")

    questions = [q for q in QUESTIONS if q.known_gap] if args.only_gaps else QUESTIONS
    rows = []
    routed_right = routed_total = 0

    for q in questions:
        routing = route_question(q.question)
        # `merge_supporting` is deliberately NOT called: the eval has no classifier
        # output, so this measures the keyword table alone -- the honest baseline.
        voice = primary_rishi_for(routing.primary)
        hits = rank_true_rules(
            applicable, [0.0] * 768, routing=routing, limit=SHOWN, question=q.question
        )
        # What the safety gate removed, so a silent withhold is visible.
        withheld = [
            (r.rule_key, withhold_reasons(r, q.question))
            for r in applicable
            if withhold_reasons(r, q.question)
        ]

        if q.expect_domain is not None:
            routed_total += 1
            ok = routing.primary == q.expect_domain
            routed_right += ok
            verdict = "OK " if ok else "MISS"
        else:
            verdict = "n/a " if routing.primary is None else "ROUTED"

        print(f"── {q.question}")
        print(f"   probes      : {q.probes}")
        print(f"   routing     : {verdict}  primary={routing.primary} "
              f"voice={voice} "
              f"secondary={list(routing.secondary)} application={routing.application} "
              f"universes={sorted(routing.universes)}")
        print(f"   rules shown : {len(hits)} of {len(applicable)} true   "
              f"withheld_for_safety={len(withheld)}   "
              f"schools={sorted(group_by_school(hits))}")
        for h in hits:
            effect = (h.effects or [{}])[0].get("statement", "")[:52]
            print(f"      {h.citation:<14}{str(h.domain):<9}{h.rule_category:<10}"
                  f"rel={h.relevance:.2f}  {effect}")
        if q.known_gap:
            print(f"   KNOWN GAP   : {q.known_gap}")
        print()

        rows.append({
            "question": q.question,
            "probes": q.probes,
            "expect_domain": q.expect_domain or "",
            "routed_primary": routing.primary or "",
            "voice": voice,
            "routing_ok": verdict.strip(),
            "application": routing.application,
            "rules_true": len(applicable),
            "rules_shown": len(hits),
            "withheld": len(withheld),
            "citations": " ".join(h.citation for h in hits),
            "known_gap": q.known_gap,
            "grade": "",          # a human fills these two in
            "failure_class": "",
        })

    if routed_total:
        print(f"routing accuracy: {routed_right}/{routed_total} "
              f"({routed_right / routed_total:.0%}) — §18's first metric")

    if args.csv:
        with open(args.csv, "w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        print(f"wrote {args.csv} — fill in `grade` and `failure_class` per row")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(asyncio.to_thread(main)))
