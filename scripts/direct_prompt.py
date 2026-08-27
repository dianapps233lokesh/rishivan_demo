"""Print the exact prompt the direct lane would send. Make no call.

This is how the comparison set gets built: generate a prompt, paste it into
ChatGPT, Gemini and Claude, grade the four answers side by side. No credentials,
no network, no model - so it runs anywhere.

    python -m scripts.direct_prompt \
        --question "when will I marry?" \
        --dob 1990-01-01 --tob 12:00 --place "New Delhi" \
        --lat 28.6139 --lon 77.2090

`--when` fixes the moment the chart is read at, and defaults to now. Fix it when
generating a set you intend to keep: the running dasha and the transiting Moon
both move, so two prompts generated a week apart are not the same prompt.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime


def prompt_for(
    question: str,
    *,
    dob: str | None,
    tob: str | None,
    place: str = "",
    lat: float | None = None,
    lon: float | None = None,
    tz_offset: float = 5.5,
    when: str | None = None,
) -> str:
    """The prompt, from plain strings.

    Runs the same nodes the graph would, in the same order, rather than calling
    the graph: `intake` needs a model to classify, and this script exists
    precisely for the case where there is no model. `hierarchy_node` is
    deterministic and keyword-driven, so the routed domain here is the one the
    app would reach.
    """
    from rishivan.council.direct_prompt import build_direct_prompt
    from rishivan.graph.nodes.hierarchy import hierarchy_node
    from rishivan.graph.nodes.varga import varga_select_node
    from rishivan.graph.state import initial_state

    moment = datetime.fromisoformat(when) if when else datetime.now()

    birth = None
    if dob and tob:
        date = datetime.fromisoformat(dob)
        time = datetime.strptime(tob, "%H:%M")
        from rishivan.chart.ephemeris import BirthData

        birth = BirthData(
            year=date.year, month=date.month, day=date.day,
            hour=time.hour, minute=time.minute,
            tz_offset_hours=tz_offset,
            lat=lat or 0.0, lon=lon or 0.0, place=place,
        )

    state = initial_state(
        question, birth_data=birth, query_time=moment,
        lat=lat, lon=lon, tz_offset=tz_offset, place=place,
    )

    if birth is not None:
        from rishivan.chart.ephemeris import compute_chart
        from rishivan.chart.facts import derive_facts
        from rishivan.chartstate.build import build_chart_state

        chart = compute_chart(birth)
        state["chart"] = chart
        state["chart_facts"] = derive_facts(chart, when=moment)
        state["chart_state"] = build_chart_state(chart, when=moment)

    # `dasha_windows_node` is deliberately not run. It times a promise, and the
    # promise comes from a rule engine this lane does not use; the prompt derives
    # its own antardasha boundaries from the chart.
    state.update(hierarchy_node(state))
    state.update(varga_select_node(state))

    return build_direct_prompt(state)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.direct_prompt",
        description="Print the direct lane's prompt for one question.",
    )
    parser.add_argument("--question", required=True)
    parser.add_argument("--dob", help="birth date, YYYY-MM-DD")
    parser.add_argument("--tob", help="birth time, HH:MM (24h, local)")
    parser.add_argument("--place", default="")
    parser.add_argument("--lat", type=float)
    parser.add_argument("--lon", type=float)
    parser.add_argument("--tz-offset", type=float, default=5.5,
                        dest="tz_offset", help="hours from UT (default IST)")
    parser.add_argument("--when", help="read the chart at this date "
                                      "(YYYY-MM-DD), default now")
    args = parser.parse_args(argv)

    print(prompt_for(
        args.question, dob=args.dob, tob=args.tob, place=args.place,
        lat=args.lat, lon=args.lon, tz_offset=args.tz_offset, when=args.when,
    ))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
