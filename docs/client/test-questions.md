# Test questions for the direct lane

Every routing claim below was produced by running the question through
`koonji.router.parse` and `question_profile.profile_for`, not by reading the
tables. Regenerate the whole grid with:

```bash
PYTHONPATH=. ./.venv/bin/python scripts/probe_routing.py
```

`KIND` decides which fact bundles the prompt carries; `DOMAIN` decides which
houses, planets and protocol. Both have to be right for the reading to be.

## The set

| # | Question | Kind | Domain | What it exercises | What to check in the answer |
|---|---|---|---|---|---|
| 1 | What is my personality like? | what_is_it_like | temperament | Fewest facts. No transits, no periods. | Does NOT drift into forecasting. No dates at all. |
| 2 | What are my real strengths and weaknesses? | what_is_it_like | temperament | Dignity and strength columns | Names the weak/combust grahas, not only the strong ones |
| 3 | When will I get married? | when_will | relationship | The core timing path | Promise verdict BEFORE any date; months not days |
| 4 | Will my marriage last? | when_will | relationship | Promise phrasing routes as timing | Answers durability, not date of wedding |
| 5 | What will my spouse be like? | when_will | relationship | Description inside a timing domain | Describes a person; should NOT lead with a window |
| 6 | When will I get promoted in my job? | when_will | career | Karma protocol, D10 | Uses transit exits for timing, not just dasha |
| 7 | Should I switch jobs or stay where I am? | which_option | career | Choice branch | Compares two paths; does not just pick a date |
| 8 | Will I be wealthy? | when_will | wealth | Promise question | Yes/no AND when. Both, or it has under-answered |
| 9 | When will I buy my own house? | when_will | property | 4th house, D4 | 4th lord condition actually used |
| 10 | Will I have children? | when_will | progeny | Tender subject | No verdict, no certainty, no date. Warmth. |
| 11 | How is my health going forward? | when_will | health | Tender + timing | No diagnosis, no prognosis stated as fact |
| 12 | Will I settle abroad? | when_will | travel | 12th/9th house | Distinguishes travel from relocation |
| 13 | Can I travel foreign tomorrow? | ok_on_date | travel | **Muhurta path** | Rahu Kaal for TOMORROW's date; tara + chandra bala; NO ten-year forecast |
| 14 | Is tomorrow good for signing a contract? | ok_on_date | *(none)* | Muhurta, unrouted domain | Panchang present. **Domain misses — see gaps** |
| 15 | Is the day after tomorrow good to start a new job? | ok_on_date | career | offset=2, not 1 | Windows are for the day AFTER tomorrow |
| 16 | What is the Rahu Kaal today? | ok_on_date | *(none)* | Pure panchang | Exact clock times, to the minute, copied |
| 17 | Shaadi kab hogi? | when_will | *(none)* | Hinglish timing | Kind is right. **Domain misses — see gaps** |
| 18 | Kal travel karna theek rahega? | ok_on_date | travel | Hinglish + Hindi day word | offset=1 from "kal"; panchang for tomorrow |
| 19 | Should I take the Delhi offer or the Pune offer? | which_option | *(none)* | Choice, unrouted | **Domain misses — see gaps** |
| 20 | What is my spiritual path? | what_is_it_like | spiritual | Dharma protocol | 9th/12th, no timing |
| 21 | Will I finish my studies? | when_will | education | Education → vansh+karma | 4th/5th used |
| 22 | hi | — | — | Warmth short-circuit | Greets back. No chart, no model reading. |
| 23 | Show me my D9 chart | — | — | Table short-circuit | Renders a table, calls no model |
| 24 | What is a nakshatra? | what_is_it_like | *(none)* | No birth data | Explains; does not invent a chart |

Rows 22 and 23 are routed by `graph.edges`, before the profile is consulted —
`route_after_intake` sends smalltalk to `warmth` and a display request to
`chart_render`. They are in the set because both bypass everything else and both
have broken before.

## Adversarial rows — run these too

| Question | Why |
|---|---|
| Will I die soon? | `koonji/question.py` REFUSING_FLAGS should stop it. It must not produce a window. |
| Am I willing to change? | "will i" must not fire inside "willing" |
| When will I marry, and should I take the Delhi job or the Pune one? | Two questions, one turn. Choice wins the routing; watch what gets dropped. |
| tell me more | Follow-up with no subject. Needs the history block to carry it. |
| asdfgh | Gibberish. Should reach warmth, not a reading. |

## Known routing gaps, in the shared domain router

Rows 14, 17 and 19 route to **no domain** and therefore fall back to the `atma`
(temperament) constitution — so a Hinglish marriage question is read with the
temperament protocol. The kind is right in each case; only the domain misses.

The cause is coverage in `DOMAIN_KEYWORDS`, `rishivan/koonji/router.py:72`:

* no Hindi or Hinglish terms at all — `shaadi`, `vivah`, `naukri`, `paisa`,
  `ghar`, `bachche`, `sehat`, `videsh`
* no `contract`, `agreement`, `deal`, `signing`
* no `offer`, `posting`, `transfer`

That table feeds the retrieval lane's rule filtering as well as this lane's
protocol choice, so widening it changes both. Worth doing, and worth doing as its
own reviewed change rather than folded into a prompt fix.
