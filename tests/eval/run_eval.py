"""Evaluation harness for the Rishivan Council RAG/routing pipeline.

Not a pytest suite — this makes REAL calls to Vertex AI and Qdrant Cloud (see
rishivan.config.settings) and reports how the system actually behaves, which
is what "evaluate the RAG system" means here. Run it directly:

    cd rishivan_demo && .venv/bin/python -m tests.eval.run_eval

Two tiers (see tests/eval/prompts.py):
  - Tier 1 (classification): one Gemini call per case, checks routing/intent/
    domain/the smalltalk-gibberish bypass.
  - Tier 2 (pipeline): the full council_consult() — real chart computation,
    real Qdrant retrieval, real generation. Slower; a smaller, representative
    set of cases.

Writes a JSON results file next to this script and prints a human-readable
report to stdout.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

from rishivan.config import settings
from rishivan.council.classifier import classify_query
from rishivan.council.client import get_gemini_api_client, get_vertex_client, model_name
from rishivan.council.conversation import Conversation
from rishivan.council.lens import maybe_generate_secondary_voice
from rishivan.council.orchestrator import council_consult
from rishivan.rag.vector_store import get_vector_store
from tests.eval.prompts import (
    CLASSIFICATION_CASES,
    FIXED_BIRTH_DATA,
    PIPELINE_CASES,
)

_DEVANAGARI_RE = re.compile(r"[ऀ-ॿ]")

REPORT_PATH = Path(__file__).resolve().parent / "last_run_report.json"


def _seed_conversation(seed: tuple[str, str, str] | None) -> Conversation | None:
    if seed is None:
        return None
    question, answer, rishi = seed
    convo = Conversation()
    convo.add(question, answer, rishi)
    return convo


def _get_client(backend: str):
    return get_gemini_api_client(settings.GEMINI_API_KEY) if backend == "gemini" else get_vertex_client()


# ─────────────────────────────────────────────────────────────────────────
# Tier 1: classification
# ─────────────────────────────────────────────────────────────────────────

def _check_classification(case, result: dict) -> list[str]:
    """Return a list of failure descriptions; empty means the case passed."""
    failures: list[str] = []

    def _domain_str(d):
        return d.value if hasattr(d, "value") else str(d)

    if case.expect_smalltalk is not None:
        actual = result.get("is_smalltalk_or_gibberish")
        if actual != case.expect_smalltalk:
            failures.append(f"is_smalltalk_or_gibberish: expected {case.expect_smalltalk}, got {actual}")

    if case.expect_domain is not None:
        actual = _domain_str(result.get("query_domain"))
        if actual != case.expect_domain:
            failures.append(f"query_domain: expected {case.expect_domain!r}, got {actual!r}")

    if case.expect_intent is not None:
        actual = result.get("intent")
        if actual != case.expect_intent:
            failures.append(f"intent: expected {case.expect_intent!r}, got {actual!r}")

    if case.expect_chart_type is not None:
        actual = result.get("chart_type")
        if actual != case.expect_chart_type:
            failures.append(f"chart_type: expected {case.expect_chart_type!r}, got {actual!r}")

    if case.expect_varga_code is not None:
        actual = result.get("varga_code")
        if actual != case.expect_varga_code:
            failures.append(f"varga_code: expected {case.expect_varga_code!r}, got {actual!r}")

    if case.expect_rishi is not None:
        actual = result.get("primary_rishi")
        if actual != case.expect_rishi:
            failures.append(f"primary_rishi: expected {case.expect_rishi!r}, got {actual!r}")

    if case.expect_rishi_in is not None:
        actual = result.get("primary_rishi")
        if actual not in case.expect_rishi_in:
            failures.append(f"primary_rishi: expected one of {case.expect_rishi_in}, got {actual!r}")

    if case.expect_dasha_level is not None:
        actual = result.get("dasha_level")
        if actual != case.expect_dasha_level:
            failures.append(f"dasha_level: expected {case.expect_dasha_level!r}, got {actual!r}")

    if case.expect_relevant_vargas_include is not None:
        actual = set(result.get("relevant_vargas") or [])
        missing = set(case.expect_relevant_vargas_include) - actual
        if missing:
            failures.append(f"relevant_vargas: expected to include {missing}, got {actual}")

    return failures


def run_classification_tier(backend: str) -> list[dict]:
    client = _get_client(backend)
    model = model_name(backend, "flash")
    results = []

    for case in CLASSIFICATION_CASES:
        convo = _seed_conversation(case.conversation_seed)
        start = time.perf_counter()
        try:
            classification = classify_query(client, case.question, model=model, conversation=convo)
            elapsed = time.perf_counter() - start
            failures = _check_classification(case, classification)
            status = "PASS" if not failures else "FAIL"
            error = None
        except Exception as exc:  # noqa: BLE001 — record and keep going
            elapsed = time.perf_counter() - start
            classification = {}
            failures = []
            status = "ERROR"
            error = f"{type(exc).__name__}: {exc}"

        results.append({
            "id": case.id,
            "category": case.category,
            "question": case.question,
            "status": status,
            "elapsed_s": round(elapsed, 2),
            "failures": failures,
            "error": error,
            "actual": {
                k: (v.value if hasattr(v, "value") else v)
                for k, v in classification.items()
            },
            "notes": case.notes,
        })
        print(f"[tier1] {status:5} {case.id:16} ({elapsed:5.1f}s)  {case.question[:60]}")
        if failures:
            for f in failures:
                print(f"         - {f}")
        if error:
            print(f"         ! {error}")

    return results


# ─────────────────────────────────────────────────────────────────────────
# Tier 2: full pipeline
# ─────────────────────────────────────────────────────────────────────────

def _consume_answer(result: dict) -> str:
    stream = result.get("answer_stream")
    if stream is None:
        return ""
    return "".join(stream)


def _check_pipeline(case, result: dict, answer_text: str) -> list[str]:
    failures: list[str] = []

    def _domain_str(d):
        return d.value if hasattr(d, "value") else str(d)

    if case.expect_is_warmth is not None:
        actual = bool(result.get("is_warmth"))
        if actual != case.expect_is_warmth:
            failures.append(f"is_warmth: expected {case.expect_is_warmth}, got {actual}")

    if case.expect_chart_table is not None:
        has_table = bool(result.get("chart_table"))
        if has_table != case.expect_chart_table:
            failures.append(
                f"chart_table presence: expected {case.expect_chart_table}, got {has_table} "
                f"(chart_table_error={result.get('chart_table_error')!r})"
            )

    if case.expect_sources_nonempty is not None:
        has_sources = bool(result.get("sources"))
        if has_sources != case.expect_sources_nonempty:
            failures.append(f"sources non-empty: expected {case.expect_sources_nonempty}, got {has_sources}")

    if case.expect_domain is not None:
        actual = _domain_str(result.get("query_domain"))
        if actual != case.expect_domain:
            failures.append(f"query_domain: expected {case.expect_domain!r}, got {actual!r}")

    if case.expect_devanagari:
        if not _DEVANAGARI_RE.search(answer_text):
            failures.append("expected Devanagari script in the answer, found none")

    if case.min_answer_chars and len(answer_text) < case.min_answer_chars:
        failures.append(
            f"answer too short: expected >= {case.min_answer_chars} chars, got {len(answer_text)}"
        )

    return failures


def run_pipeline_tier(backend: str, store) -> list[dict]:
    client = _get_client(backend)
    model = model_name(backend, "flash")
    results = []

    for case in PIPELINE_CASES:
        convo = _seed_conversation(case.conversation_seed)
        birth_data = FIXED_BIRTH_DATA if case.needs_birth_data else None
        start = time.perf_counter()
        try:
            result = council_consult(
                client, store, case.question,
                birth_data=birth_data, backend=backend, conversation=convo,
            )
            answer_text = _consume_answer(result)
            # The real app (streamlit_app.py) calls this AFTER the primary
            # answer finishes streaming, which is exactly what we just did
            # above — council_consult() itself never populates
            # result["secondary_voice"] (see orchestrator.py Step 7's
            # comment), so the eval must call this explicitly too, or the
            # earned-voice feature never gets exercised at all.
            if not result.get("is_warmth") and not result.get("chart_table"):
                secondary = maybe_generate_secondary_voice(result, client, model, case.question)
            else:
                secondary = None
            elapsed = time.perf_counter() - start
            failures = _check_pipeline(case, result, answer_text)
            status = "PASS" if not failures else "FAIL"
            error = None
        except Exception as exc:  # noqa: BLE001 — record and keep going
            elapsed = time.perf_counter() - start
            answer_text = ""
            failures = []
            status = "ERROR"
            error = f"{type(exc).__name__}: {exc}"
            result = {}
            secondary = None

        results.append({
            "id": case.id,
            "category": case.category,
            "question": case.question,
            "status": status,
            "elapsed_s": round(elapsed, 2),
            "failures": failures,
            "error": error,
            "is_warmth": result.get("is_warmth"),
            "domain": (result.get("query_domain").value
                       if hasattr(result.get("query_domain"), "value") else result.get("query_domain")),
            "rishi": result.get("primary_rishi"),
            "n_sources": len(result.get("sources") or []),
            "has_chart_table": bool(result.get("chart_table")),
            "has_secondary_voice": bool(secondary),
            "secondary_voice_rishi": (secondary or {}).get("rishi"),
            "answer_chars": len(answer_text),
            "answer_preview": answer_text[:160],
            "notes": case.notes,
        })
        print(f"[tier2] {status:5} {case.id:20} ({elapsed:5.1f}s)  {case.question[:55]}")
        if failures:
            for f in failures:
                print(f"         - {f}")
        if error:
            print(f"         ! {error}")

    return results


# ─────────────────────────────────────────────────────────────────────────
# Reporting
# ─────────────────────────────────────────────────────────────────────────

def _summarize(tier_name: str, results: list[dict]) -> str:
    total = len(results)
    passed = sum(1 for r in results if r["status"] == "PASS")
    failed = sum(1 for r in results if r["status"] == "FAIL")
    errored = sum(1 for r in results if r["status"] == "ERROR")
    avg_s = sum(r["elapsed_s"] for r in results) / total if total else 0.0
    lines = [
        f"\n=== {tier_name}: {passed}/{total} passed, {failed} failed, "
        f"{errored} errored (avg {avg_s:.1f}s/case) ==="
    ]
    for r in results:
        if r["status"] != "PASS":
            lines.append(f"  [{r['status']}] {r['id']} — {r['question'][:60]}")
            for f in r["failures"]:
                lines.append(f"      - {f}")
            if r["error"]:
                lines.append(f"      ! {r['error']}")
    return "\n".join(lines)


def main() -> int:
    import sys

    missing = settings.missing()
    if missing:
        print(f"Cannot run: missing config {missing}")
        return 1

    backend = settings.default_backend
    print(f"Backend: {backend}")

    tier2_only = "--tier2-only" in sys.argv
    if tier2_only:
        tier1_results = []
    else:
        print("\n--- Tier 1: classification/routing ---")
        tier1_results = run_classification_tier(backend)

    print("\n--- Tier 2: full pipeline (real retrieval + generation) ---")
    store = get_vector_store()
    if not store.exists():
        print(
            f"Qdrant collection {settings.VECTOR_COLLECTION!r} does not exist — "
            "skipping Tier 2 (pipeline cases need real retrieval)."
        )
        tier2_results = []
    else:
        tier2_results = run_pipeline_tier(backend, store)

    if tier2_only and REPORT_PATH.exists():
        # Keep the previous (still-valid) Tier 1 results in the merged report
        # rather than discarding them just because this run skipped Tier 1.
        tier1_results = json.loads(REPORT_PATH.read_text(encoding="utf-8")).get("tier1", [])

    if tier1_results:
        print(_summarize("Tier 1 (classification)", tier1_results))
    if tier2_results:
        print(_summarize("Tier 2 (pipeline)", tier2_results))

    REPORT_PATH.write_text(
        json.dumps({"tier1": tier1_results, "tier2": tier2_results}, indent=2, default=str),
        encoding="utf-8",
    )
    print(f"\nFull results written to {REPORT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
