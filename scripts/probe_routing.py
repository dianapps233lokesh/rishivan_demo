"""Print how each test question routes. No model, no network, no credentials.

Exists because the routing claims in `docs/client/test-questions.md` were wrong
the first time they were written from reading the tables. Run this instead:

    PYTHONPATH=. ./.venv/bin/python scripts/probe_routing.py
"""

from __future__ import annotations

QUESTIONS = (
    "What is my personality like?",
    "What are my real strengths and weaknesses?",
    "When will I get married?",
    "Will my marriage last?",
    "What will my spouse be like?",
    "When will I get promoted in my job?",
    "Should I switch jobs or stay where I am?",
    "Will I be wealthy?",
    "When will I buy my own house?",
    "Will I have children?",
    "How is my health going forward?",
    "Will I settle abroad?",
    "Can I travel foreign tomorrow?",
    "Is tomorrow good for signing a contract?",
    "Is the day after tomorrow good to start a new job?",
    "What is the Rahu Kaal today?",
    "Shaadi kab hogi?",
    "Kal travel karna theek rahega?",
    "Should I take the Delhi offer or the Pune offer?",
    "What is my spiritual path?",
    "Will I finish my studies?",
    "What is a nakshatra?",
)


def main() -> int:
    from rishivan.council.direct_prompt import constitution_for
    from rishivan.council.question_profile import profile_for
    from rishivan.koonji.router import parse

    print(f"{'KIND':16s} {'OFF':>3s} {'BUNDLES':>7s} {'DOMAIN':22s} "
          f"{'PROTOCOL':9s} QUESTION")
    for question in QUESTIONS:
        domains = parse(question).routing.domains
        domain = domains[0] if domains else ""
        profile = profile_for(question, koonji_domain=domain)
        print(
            f"{profile.kind.value:16s} {profile.day_offset:3d} "
            f"{len(profile.bundles):7d} {domain or '(none)':22s} "
            f"{constitution_for(domain).domain:9s} {question}"
        )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
