"""The assembled prompt, pinned.

The prompt wording will be iterated on — that is the point of the experiment.
This is what makes an iteration visible instead of silent: a diff here is either
the change you meant or the one you did not.

Regenerate deliberately, never reflexively:

    ./.venv/bin/python -m pytest tests/council/test_direct_prompt_golden.py \
        --golden-update
"""

from datetime import datetime
from pathlib import Path

import pytest

from rishivan.chart.ephemeris import BirthData, compute_chart
from rishivan.chart.facts import derive_facts
from rishivan.council.direct_prompt import build_direct_prompt
from rishivan.graph.state import initial_state

GOLDEN = Path(__file__).parent.parent / "golden" / "direct_prompt_marriage.txt"

BIRTH = BirthData(
    year=1990, month=1, day=1, hour=12, minute=0,
    tz_offset_hours=5.5, lat=28.6139, lon=77.2090, place="New Delhi",
)
WHEN = datetime(2026, 8, 25, 12, 0)


@pytest.fixture
def prompt():
    """As close to a real prompt as the fixture can get.

    `chart_state` is included deliberately: it carries the §6 diagnosis, and a
    snapshot that omitted it would not cover the block most likely to be
    reworded — the computed dignity, combustion and aspect lines.
    """
    from rishivan.chartstate.build import build_chart_state

    state = initial_state("when will I marry?", query_time=WHEN)
    state["koonji_domain"] = "domain.relationship"
    state["chart"] = compute_chart(BIRTH)
    state["chart_facts"] = derive_facts(state["chart"], when=WHEN)
    state["chart_state"] = build_chart_state(state["chart"], when=WHEN)
    return build_direct_prompt(state)


def test_the_prompt_matches_the_golden_file(prompt, request):
    if request.config.getoption("--golden-update"):
        GOLDEN.parent.mkdir(parents=True, exist_ok=True)
        GOLDEN.write_text(prompt)
        pytest.skip(f"golden file rewritten: {GOLDEN}")
    assert GOLDEN.exists(), (
        f"{GOLDEN} missing — generate it with --golden-update"
    )
    assert prompt == GOLDEN.read_text()
