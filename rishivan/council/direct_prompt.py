"""The direct lane's prompt: classical method, not classical documents.

The retrieval lane answers from twenty topically-similar pages and whatever
rules fired. This one answers from the model's own reading of the classical
literature — which is wider than this corpus and better organised — and spends
the prompt on telling it *which* part of that knowledge to reach for.

`constitution.protocol` is what makes that possible. It already holds the
classical reading order per domain, taken from Eight Rishis §4-11, and until now
it only decided which rules counted as a Rishi's evidence. Here it becomes the
procedure the model works through.

**No persona.** The Rishi voice, the seven movements and the speech example are
deliberately absent: this lane is being graded on astrological accuracy against
three other platforms, and prose quality would confound that. The voice returns
as a narration step over this same material.

Everything in this module is a pure function of state. No client, no network, no
database — which is what makes the golden-snapshot test possible and what
`test_no_network` pins.
"""

from __future__ import annotations

from rishivan.council.constitution import Constitution

DEFAULT_CONSTITUTION_KEY = "atma"
"""Where an unroutable question lands.

Atma's protocol is the whole-chart one (`chart framework → Lagna and Lagna lord
→ Sun and Moon → strength → Nakshatra → major combinations → relevant Vargas →
Jaimini → synthesis → uncertainty`), which is the correct reading order for a
question nobody could place. The alternative — no method block — is a prompt
that has given up the entire point of this lane.
"""


def constitution_for(koonji_domain: str) -> Constitution:
    """The constitution for a `domain.*` symbol.

    Two taxonomies meet here. `hierarchy_node` writes `koonji_domain` as a
    `domain.*` symbol because that is what the rule corpus is tagged with;
    `CONSTITUTIONS` is keyed by the client's eight life-domain keys because that
    is what Eight Rishis §21 names. `LIFE_DOMAIN_OF` is the existing bridge and
    is used rather than duplicated — a second mapping is a second thing to drift.

    First rather than all, matching `hierarchy_node`: a domain that maps to two
    life domains is primarily about the first.
    """
    from rishivan.council.constitution import CONSTITUTIONS
    from rishivan.council.hierarchy import LIFE_DOMAIN_OF

    keys = LIFE_DOMAIN_OF.get(koonji_domain or "", ())
    return CONSTITUTIONS[keys[0] if keys else DEFAULT_CONSTITUTION_KEY]


def framing_block(constitution: Constitution) -> str:
    """Who is answering, from what, and what they may not do.

    `source_families` is rendered rather than hardcoded so the framing tracks
    §4-11 the way the rest of the lane does.

    `unavailable_sources` and `blocked_concepts` are deliberately NOT rendered.
    They record what *this repo's corpus* lacks, which is meaningless to a model
    reading from its own knowledge — and naming them would talk it out of
    knowledge it actually has.
    """
    families = ", ".join(constitution.source_families)
    forbidden = ""
    if constitution.forbidden_claims:
        forbidden = (
            "\n\nYou may not claim any of the following, in any form:\n"
            + "\n".join(f"  - {claim}" for claim in constitution.forbidden_claims)
        )
    return f"""
You are an expert Vedic (Jyotish) astrologer working in the classical tradition.
Read the computed chart below and answer the question at the end.

Draw on the classical literature you know: {families}. Apply it from your own
knowledge of those texts.

DO NOT CITE. No page numbers, no chapter-and-verse references, no book titles in
your answer, no quoted verses, and no stock authority phrases ("the classical
texts say", "the old masters held"). You have not been given any text to quote
from, so a citation you produce cannot be checked by anyone — which makes it
worth less than no citation at all. State what the principle IS. Do not say
where you read it.

Never present a health diagnosis, a treatment, or death as a certainty. These
are traditional interpretations; keep their uncertainty intact.{forbidden}
""".strip()


def method_block(constitution: Constitution) -> str:
    """The classical reading order, as an instruction.

    The steps are `constitution.protocol` verbatim, numbered. Verbatim matters:
    they are §4-11's own words, and paraphrasing them here would make the
    instruction and the coverage gate two different methods with one name.
    """
    steps = "\n".join(
        f"  {index}. {step}"
        for index, step in enumerate(constitution.protocol, start=1)
    )
    last = len(constitution.protocol)
    return f"""
READING METHOD — {constitution.dimension}
{constitution.mission}

Work these steps, in this order:

{steps}

For each step, state the classical principle you are applying and what THIS
chart shows against it. Two sentences per step is usually enough.

Do not skip a step. If the computed facts below do not let you judge a step, say
that the step is unsupported and move to the next one — a step silently dropped
reads as a complete reading, which is the one outcome worse than an admitted gap.

Do not reach your verdict before step {last}. The order is the method: a promise
that was never established cannot be timed, and a window with no promise behind
it is arithmetic pretending to be a prediction.
""".strip()
