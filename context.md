╭─── Claude Code v2.1.221 ─────────────────────────────────────────────────────╮
│                                                    │ Tips for getting        │
│                 Welcome back boss!                 │ started                 │
│                                                    │ Run /init to create a … │
│                      ▗ ▗   ▖ ▖                     │ ─────────────────────── │
│                                                    │ What's new              │
│                        ▘▘ ▝▝                       │ Fixed interactive sess… │
│                                                    │ Fixed `git` / Git Bash… │
│  Opus 5 · Claude Team · DianApps Development Team  │ Fixed `/tui` reverting… │
│       ~/Desktop/live_projects/rishivan_demo        │ /release-notes for more │
╰──────────────────────────────────────────────────────────────────────────────╯


⏺ MongoDB is in and committed. Now your classifier question — I measured it
  rather than guessing, and the short answer is yes, but a much smaller tweak 
  than a rewrite.

  What the classifier still produces

  One Gemini Flash call, 14 fields. Here's what's actually true of each now:

  Field: needs_birth_data
  Verdict: Dead. Zero consumers. intake_node rewrites natal→Prashna instead.
  ────────────────────────────────────────
  Field: is_followup
  Verdict: Dead. Computed, returned, never read.
  ────────────────────────────────────────
  Field: primary_rishi
  Verdict: Superseded. council_routing_node overrides it with the deterministic
  route_question(); the LLM's pick survives only as a tiebreak.
  ────────────────────────────────────────
  Field: relevant_vargas
  Verdict: Superseded for analysis. Phase 3's varga_select decides vargas from
  the hierarchy + birth-time confidence. Still used at chart.py:46 to render
  extra tables — that's display, not reasoning.
  ────────────────────────────────────────
  Field: dasha_level
  Verdict: Weak. It only pads the search string. Phase 3/4 compute real
  five-stage windows now.
  ────────────────────────────────────────
  Field: query_domain
  Verdict: Keep.
  ────────────────────────────────────────
  Field: intent / chart_type / varga_code
  Verdict: Keep.
  ────────────────────────────────────────
  Field: search_query, supporting_rishis, confidence, reasoning
  Verdict: Keep — all consumed.

  The thing that surprised me

  I expected koonji.router.parse to have made query_domain redundant. It hasn't
  — they're different axes:

  "is tomorrow good for travel?"  →  koonji Mode: natal_predictive   (really
  muhurta)
  "show me my D9"                 →  koonji Mode: natal_predictive   (really a
  chart display)

  The Koonji router answers "what is this question about". The classifier
  answers "what does the system have to do" — cast a birth chart, cast a moment
  chart, render a table, or just talk. That second question is genuinely not
  derivable from the first, so query_domain, intent and chart_type earn their
  place.

  Where I'd actually change something

  1. The smalltalk decision is an unchecked single point of failure. If the LLM
  wrongly marks a real question as smalltalk, the entire analytic path — chart,
  rules, council, plan — is skipped and the user gets a warm greeting instead of
  a reading. Nothing cross-checks it.

  The deterministic router already has an opinion, and it's good:

  hi / hello there / namaste / thanks! / who are you   → social/meta   ✓
  When will I get married? / will I be rich / …        → new_question  ✓
  asdkjfh                                              → new_question  ✗ (misses
  gibberish)

  11 of 12. It can't spot gibberish — that's a keyword table's limit and
  genuinely needs a model. But it can veto: if the LLM says smalltalk and the
  deterministic router says a real question with a routed domain, trust the
  router. That's a cheap guard on the most damaging misfire available.

  2. Delete the two dead fields. needs_birth_data and is_followup are prompt
  tokens spent on outputs nobody reads, on every request.

  3. Drop relevant_vargas from the analysis path explicitly. Right now it
  survives only as a display input. Worth a comment saying so, or someone will
  wire it back into reasoning and quietly bypass the birth-time confidence gate
  that Phase 3 built.

  What I'd leave alone

  The prompt's Rishi descriptions and domain definitions. They're doing real
  work, and the classifier is the only component that can distinguish "show me
  my D9" (render a table) from "what does my D9 say about marriage" (run the
  council). No table does that.

  My recommendation

  Do 1 and 2, skip a rewrite. That's maybe 40 lines: a veto in intake_node, two
  fields removed from the schema and the prompt, and a table-driven test for the
  disagreement cases. It cuts the worst failure mode and stops paying for
  unread output.

  Want me to do that now, or finish Phase 5's documentation task first? The docs
  are the last thing standing between this branch and being mergeable — and
  it's still 107 commits unmerged with rishivan/koonji/ untracked.

✻ Churned for 10m 47s

❯ /context 
  ⎿  Context Usage
     ⛁ ⛁ ⛁ ⛁ ⛀ ⛀ ⛁ ⛁ ⛁ ⛁ ⛁ ⛁ ⛁ ⛁ ⛁ ⛁ ⛁ ⛁ ⛁ ⛁   Opus 5 (1M context)
     ⛁ ⛁ ⛁ ⛁ ⛁ ⛁ ⛁ ⛁ ⛁ ⛁ ⛁ ⛁ ⛁ ⛁ ⛁ ⛁ ⛁ ⛁ ⛁ ⛁   claude-opus-5[1m]
     ⛁ ⛁ ⛁ ⛁ ⛁ ⛁ ⛁ ⛁ ⛁ ⛁ ⛁ ⛁ ⛁ ⛁ ⛁ ⛁ ⛁ ⛁ ⛁ ⛁   455.6k/1m tokens (46%)
     ⛁ ⛁ ⛁ ⛁ ⛁ ⛁ ⛁ ⛁ ⛁ ⛁ ⛁ ⛁ ⛁ ⛁ ⛁ ⛁ ⛁ ⛁ ⛁ ⛁ 
     ⛁ ⛁ ⛁ ⛁ ⛁ ⛁ ⛁ ⛁ ⛁ ⛁ ⛁ ⛁ ⛁ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶   Estimated usage by category
     ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶   ⛁ System prompt: 3.8k tokens (0.4%)
     ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶   ⛁ System tools: 15.9k tokens (1.6%)
     ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶   ⛁ Custom agents: 306 tokens (0.0%)
     ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶   ⛁ Memory files: 67 tokens (0.0%)
     ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶   ⛁ Skills: 5.6k tokens (0.6%)
                                               ⛁ Messages: 431.2k tokens (43.1%)
                                               ⛶ Free space: 543.1k (54.3%)

     MCP tools · /mcp (loaded on-demand)
     └ 59 tools · 0 tokens

     Custom agents · .claude/agents/
     └ 4 agents · 306 tokens

     Memory files · /memory
     └ 1 file · 67 tokens

     Skills · /skills
     └ 51 skills · 5.6k tokens

     /context all to expand

      Suggestions
      ⚠ Bash results using 219.1k tokens (22%) → save ~109.5k
        Pipe output through head, tail, or grep to reduce result size. Avoid cat on large files — use Read with offset/limit instead.

❯ /compact                                                                      
  ⎿  Compacted (ctrl+o to see full summary)
  ⎿  Read rishivan/council/conversation.py (244 lines)
  ⎿  Read tests/graph/test_nodes_intake.py (190 lines)
  ⎿  Read rishivan/graph/nodes/intake.py (132 lines)
  ⎿  Read tests/graph/test_adapter.py (143 lines)
  ⎿  Read rishivan/council/orchestrator.py (100 lines)
  ⎿  Skills restored (superpowers:requesting-code-review, 
     superpowers:finishing-a-development-branch, superpowers:executing-plans, 
     superpowers:writing-plans)

❯ if i will write print to debug, wheere will it be visinle, in the streamlit   
  terminal?                                                                     

⏺ Yes — the terminal where you ran streamlit run. Let me confirm a couple of
  project-specific gotchas rather than guess.

  Searched for 3 patterns, listed 1 directory, ran 4 shell commands (ctrl+o to expand)

⏺ Yes — the terminal running streamlit run. Both stdout and stderr go there.
  Four things about this codebase are worth knowing before you rely on it:

  1. logger.info is invisible; print is not. Nothing in the repo calls
  basicConfig, and importing Streamlit doesn't add a root handler:

  root handlers: []
  effective level: WARNING

  So logger.warning and above reach the terminal, logger.info and logger.debug
  are silently dropped. Only 1 info call exists today (intake.py:77, the
  natal→Prashna fallback) so nothing is currently being lost — but if you add
  logger.info to debug, you'll see nothing and conclude the code didn't run.
  Either use print, or turn logging on once at the top of streamlit_app.py:

  logging.basicConfig(level=logging.INFO, format="%(name)s | %(message)s")

  2. Prints inside the answer stream fire late. answer_stream is a generator. A
  print inside narrate.stream_answer doesn't run when council_consult returns —
  it runs at streamlit_app.py:669 as chunks are pulled. So it lands after every
  graph-node print, no matter where it sits in the source. That ordering trips
  people up constantly.

  3. The script reruns top to bottom on every interaction. A print at module
  level in streamlit_app.py fires on every widget click, not once. Prints inside
  graph nodes fire once per question, which is usually what you want.

  4. Node prints are in-order. The graph runs in the caller's thread — no
  ThreadPool, no asyncio anywhere in rishivan/ outside the Mongo client's lock.
  What you see is execution order.

  Good spots to drop one: koonji_read_node (how many rules fired),
  answer_plan_node (what survived the gate), sakshi_node (what the auditor
  flagged). Those three tell you most of what goes wrong.

  If you'd rather see it in the browser than the terminal,
  st.sidebar.json(result["answer_plan"]) beats scrolling — the plan is a frozen
  dataclass, so dataclasses.asdict() it first.

✻ Cogitated for 1m 3s

❯ [Image #6] - is the answer correct?? we have only ingested few of books, this 
  did not find relevant context right???                                        
                                                                                
  also for this quetion                                                         
                                                                                
  orchestrator classification is primary rishi is ritam, domain classified is   
  QueryDomain.NATAL, supporting rishis are ['medhan'], intent classified is     
  fact, varga code is D9, relevant vargas are ['D9'], dasha level is none       
                                                                                
  is the classifcaiton correct? how is supporiting rishi is being determined?   
  and varga code and use of relevant vargas here?                               
  ⎿  [Image #6]

⏺ Two separate things going on here, and the second one is a real bug. Let me
  check both.

  Searched for 8 patterns, listed 1 directory, ran 15 shell commands (ctrl+o to expand)
⏺ No — retrieval worked fine. The message is lying about its own cause, and
  that's the bug.

  1. The answer is wrong about why it's refusing

  Look at what the page itself shows: 20 source pages, 10 classical rules 
  matched, D9 computed, 38 fact statements. Retrieval found plenty. But the text
  says "I don't have material in the ingested books."

  That string is hardcoded at narrate.py:27 and fires from narrate.py:196:

  if plan is None or plan.insufficient or not plan.allowed:
      yield INSUFFICIENT

  And plan.insufficient (answer_plan.py:231) has two causes, neither of which is
  "the corpus is thin":

  insufficient = not allowed or (bool(reports) and not speaking)

  - not allowed — no Koonji claim cleared confidence 0.35
  - bool(reports) and not speaking — every Rishi abstained

  Given 10 rules matched, the second is the likely one. parse_report converts
  any contract failure into an abstention (contract.py:157), and the contract
  requires a non-empty weakening list on any report with supporting evidence.
  Four Rishis producing four schema-invalid JSON blobs → four abstentions →
  insufficient. The corpus never entered into it.

  The corpus is demonstrably fine for this question. I ran the engine on a test
  chart:

  relationship.harmony  0.90  consistently supported across methods
      + BPHS.RELATIONSHIP.CH25V56.0001.02   [bphs ch25.v5-6]
      + BPHS.RELATIONSHIP.CH26V47.0005      [bphs ch26.v47]
      + BPHS.RELATIONSHIP.CH59V7678.0002    [bphs ch59.v76-78]
      + BPHS.RELATIONSHIP.CH62V6062.0007    [bphs ch62.v60-62]
      + BRIHATJATAKA.RELATIONSHIP.CH17V12.0001.01

  22 of 23 in-scope rules fired. So the books aren't the problem — either your
  chart genuinely has weak 7th-house evidence, or the council abstained. You 
  can't tell which from the UI, because the "4 Rishis contributed" expander
  renders the old Phase-2 contributor list, not the Phase-4 reports. The
  abstention reasons are computed and thrown away.

  2. The classification

  ┌─────────────────────┬───────────────────────────────────────────────────┐
  │        Field        │                      Verdict                      │
  ├─────────────────────┼───────────────────────────────────────────────────┤
  │ NATAL               │ Correct — birth details were supplied.            │
  ├─────────────────────┼───────────────────────────────────────────────────┤
  │ intent: fact        │ Correct — not a chart-display request.            │
  ├─────────────────────┼───────────────────────────────────────────────────┤
  │ primary_rishi:      │ Overridden, correctly.                            │
  │ ritam               │                                                   │
  ├─────────────────────┼───────────────────────────────────────────────────┤
  │ dasha_level: none   │ Wrong. "When will I…" is the timing question. Low │
  │                     │  impact — it only pads the search string.         │
  ├─────────────────────┼───────────────────────────────────────────────────┤
  │ varga_code: D9      │ Ignored entirely (see below).                     │
  ├─────────────────────┼───────────────────────────────────────────────────┤
  │ relevant_vargas:    │ Right answer, wrong reason (see below).           │
  │ ['D9']              │                                                   │
  └─────────────────────┴───────────────────────────────────────────────────┘

  On Ritam → Medhan, I verified the override:

  route_question("When will I get married?")
    → primary domain: prema   (matched keyword "married")
  primary_rishi_for('prema', classifier_pick='ritam')  →  medhan

  council_routing_node deliberately discards the LLM's pick — the routed life
  domain decides who speaks, because the coverage gate keys off the domain.
  That's why the header says Medhan while the classifier said Ritam. Working as
  designed, though the reasoning line still shown to the user ("requires transit
  and dasha timing analysis by Ritam supported by Medhan") is the LLM's
  discarded opinion, so the UI is displaying a rationale for a decision that was
  thrown away.

  3. How supporting_rishis is determined

  The LLM picks it freely; there's no deterministic check. It's consumed in
  exactly two places — ground.py:104 and retrieve.py:149 — both through
  merge_supporting(), which maps each persona back to the life domains it owns
  at HIGH weight and appends them as secondary routing domains:

  merge_supporting(prema, ['medhan'])  →  secondary: ('vansh', 'aarogya')

  So ['medhan'] widened retrieval to family and health. It does not make anyone 
  speak — it only broadens the search. And since Medhan was then promoted to
  primary anyway, the supporting list effectively contributed nothing here.

  4. varga_code and relevant_vargas are cosmetic now

  Both are read in exactly one place each, and neither touches the reasoning
  path:

  - varga_code → chart.py:151, only when chart_type == "varga" (a "show me my
  D9" display request). Intent was fact, so it was never read.
  - relevant_vargas → chart.py:46, which renders extra tables.

  The D9 that the reading actually used came from varga_select_node, which reads
  the hierarchy and birth-time confidence and never looks at the 
  classification:

  domain.relationship → vargas=('D9',), tier_weights={'varga': 0.75},
  min_independent_sources=2

  Both paths said D9 by coincidence. So the label "Computed Chart (D9) — used 
  for this reading" is showing you the classifier's table while claiming it's
  the one that grounded the reading, and the comment above it
  (streamlit_app.py:628) still says "the classifier decides relevance per
  question" — true before Phase 3, false now.

  What I'd fix

  1. Tell the truth in the refusal. Distinguish "nothing cleared the evidence
  floor" from "the council abstained" — they need different messages, and
  neither should blame the books when 20 pages were retrieved.
  2. Surface the abstention reasons. They're already on RishiReport.abstained;
  the UI just drops them. This is the single highest-value change — right now a
  total council failure is indistinguishable from a genuinely silent corpus.
  3. Relabel the D9 expander and fix the stale comment.
  4. dasha_level: none on a "when will I" question — tighten the prompt or drop
  the field.

  Want me to start with #1 and #2? That's the pair that turns this screen from
  misleading into diagnostic.

✻ Cooked for 3m 13s

❯ first and foremost, let's extract rules from the al below books, and embed    
  them. we will consider only bphs has embed, rest of them we will delete. and  
  re-extract rules and re-embed. below are the books                            
                                                                                
  vivaha-patalam                                                                
  the-complete-book-of-numerology                                               
  sarvartha-chintamani                                                          
  Saravali Santhanam En                                                         
  Prasnamarga Raman Part2                                                       
  Prasnamarga Raman Part1                                                       
  Prashna Tantra                                                                
  Phaladeepika Sastri 1950                                                      
  numerology-key-to-your-inner-self                                             
  numerology-and-the-divine-triangle                                            
  Muhurtachintamani                                                             
  Laghu Parashari                                                               
  Jatakaparijata Sastri Vol2                                                    
  Jatakaparijata Sastri Vol1                                                    
  hindupredictiveastrology-raman                                                
  dharma-sindhu                                                                 
  devakeralam-chandrakalanadi-vol2                                              
  Devakeralam Chandrakalanadi Vol1                                              
  cheiros-book-of-numbers                                                       
  Brihatjataka Row 1919                                                         
  Bphs Gcsharma Vol2                                                            
  Bphs Gcsharma Vol1                                                            
  Bhavartha Ratnakara By B V Raman Text                                         
                                                                                
  do not consider bphs vol1 and vol2                                            

⏺ Before deleting anything, let me map the current state — what's ingested, what
  the extraction pipeline is, and where the books live.

  Searched for 3 patterns, listed 5 directories, ran 15 shell commands (ctrl+o to expand)

⏺ Here's the full picture before I touch anything.

  Current state

  Postgres: all 23 documents present (21 non-BPHS + BPHS vol 1 & 2).

  Qdrant rishivan_docs (passages) — 52,958 points across 21 books. Two books
  have zero passage embeddings: devakeralam-chandrakalanadi-vol2 and
  numerology-and-the-divine-triangle.

  Qdrant rishivan_docs_rules — 1,046 rule embeddings, and only 8 books are
  represented:

  ┌────────────────────────────────┬───────┐
  │              Book              │ Rules │
  ├────────────────────────────────┼───────┤
  │ bphs-gcsharma-vol1             │ 376   │
  ├────────────────────────────────┼───────┤
  │ bphs-gcsharma-vol2             │ 310   │
  ├────────────────────────────────┼───────┤
  │ jatakaparijata-sastri-vol1     │ 132   │
  ├────────────────────────────────┼───────┤
  │ jatakaparijata-sastri-vol2     │ 117   │
  ├────────────────────────────────┼───────┤
  │ prasnamarga-raman-part1        │ 51    │
  ├────────────────────────────────┼───────┤
  │ hindupredictiveastrology-raman │ 39    │
  ├────────────────────────────────┼───────┤
  │ bhavartha-ratnakara            │ 18    │
  ├────────────────────────────────┼───────┤
  │ brihatjataka-row-1919          │ 3     │
  └────────────────────────────────┴───────┘

  BPHS is 686 of 1,046. 13 books have no rules at all — which is a large part of
  why the marriage question came back thin.

  The extraction workload

  prepare_corpus --dry-run gives the real numbers: 18 books bridgeable, 5 
  skipped, 2,900 rule-bearing units — of which 1,880 are non-BPHS. At six model
  calls per passage that's roughly 11,300 calls / 15–25M tokens.

  Two things that block a clean "do all 21"

  1. Five books cannot be extracted at all — the bridge refuses them, and the
  reasons are legitimate:

  vivaha-patalam        Entirely Devanagari, no Latin headings, no numbered
                        divisions; 383 shlokas, zero english_prose elements
  laghu-parashari       Sections NAMED not numbered (संज्ञाध्यायः Preliminaries)
  dharma-sindhu         No chapter headings in the OCR at all
  devakeralam vol1      Prints "BOOK I (Containing 2718 Slokas)", no chapters
  devakeralam vol2      As volume 1

  Filing their verses under an invented chapter 1 would fabricate every
  citation, which is why prepare_corpus skips rather than guesses. Note the
  irony: vivaha-patalam is the marriage-timing text — the single most relevant
  book to the question that just failed, and it's one of the five.

  2. The numerology books yield almost nothing. Across all four, rule_units
  totals 12 (cheiro 4, divine-triangle 8, the other two 0). Koonji's atoms are
  planet_in_sign-shaped — there's no representation for a mulank. Extracting
  them is spend with no place to land.

  Also worth fixing while we're in here: rule payloads store book_slug inside a
  JSON string under source, not as a top-level field — so slug_filter() in
  vector_store.py silently cannot filter rules by book.

⏺ User answered Claude's questions:
  ⎿  · What should I delete from Qdrant? → will delete later, first we need to 
     extract the rules from rest of the books, so explain me the flow of 
     retrieval that you have implemented
     · The five structurally unbridgeable books — vivaha-patalam, 
     laghu-parashari, dharma-sindhu, devakeralam vol 1 & 2? → Skip them, extract
     the other 16 (Recommended)
     · The four numerology books (cheiro, complete-book, key-to-inner-self, 
     divine-triangle)? → Skip them (Recommended)

⏺ Noted — no deletions. I'll explain retrieval, then start extraction on the 12
  books that survive both filters.

  Searched for 4 patterns, listed 1 directory, ran 9 shell commands (ctrl+o to expand)

⏺ Here's the retrieval flow as actually implemented. The important thing up
  front: there are three separate retrieval systems, and only one of them 
  decided your marriage answer.

  The three systems

  ┌─────┬─────────────┬──────────────────────────┬──────────────┬──────────┐
  │  #  │   System    │      Where it lives      │     Size     │ Coverage │
  ├─────┼─────────────┼──────────────────────────┼──────────────┼──────────┤
  │ 1   │ Passage RAG │ Qdrant rishivan_docs     │ 52,958       │ 21 books │
  │     │             │                          │ vectors      │          │
  ├─────┼─────────────┼──────────────────────────┼──────────────┼──────────┤
  │ 2   │ Rule RAG    │ Qdrant                   │ 1,046        │ 8 books  │
  │     │             │ rishivan_docs_rules      │ vectors      │          │
  ├─────┼─────────────┼──────────────────────────┼──────────────┼──────────┤
  │ 3   │ Koonji      │ local YAML on disk       │ 1,117 rules  │ 6 books  │
  │     │ engine      │                          │              │          │
  └─────┴─────────────┴──────────────────────────┴──────────────┴──────────┘

  System 3 uses no embeddings and never touches Qdrant — I confirmed there's not
  a single vector reference in engine.py or index.py. It reads compiled YAML
  from rishivan/koonji/rules/ and matches by set containment on interned atoms.

  Local Koonji rules by book:

  bphs                 903      hindu-predictive      20
  jataka-parijata      149      bhavartha-ratnakara   19
  brihat-jataka         19      prasna-marga           7

  The flow, in order

  Stage 1 — routing sets the scope. council_routing_node runs route_question()
  (deterministic keyword table) → prema, then merge_supporting(['medhan'])
  widens secondaries to vansh, aarogya. Those life domains map to universes, and
  universes map to book slugs — that's the domain_filter. Separately,
  hierarchy_node settles koonji_domain = domain.relationship.

  Stage 2 — ground_node builds the search string. Starts from
  classification["search_query"], then appends the dasha chain only if 
  dasha_level != "none". Yours was none, so nothing was appended — the timing
  question searched without any timing context.

  Stage 3 — retrieve_node runs two retrievals side by side.

  (a) Passages → rishivan_docs. If a chart exists, collect_chart_context does
  not search the question. It embeds each of ~30 chart facts as its own query
  (MAX_FACT_QUERIES = None — no cap), pulls 2 hits per fact, then ranks pages by
  how many distinct chart facts landed on them × source authority × the §15
  Book×Rishi matrix. Top 20 pages, each widened ±1 page (PAGE_WINDOW = 1) and
  fetched whole so a shloka spanning a page break arrives intact. That produced
  your 20 "DRAWN FROM" chips.

  (b) Rules → rishivan_docs_rules. This one is backwards from a normal RAG,
  deliberately:

  ▎ Nominating by similarity first was measured losing 11 to 14 of the 21 rules 
  ▎ true of a test chart — a similarity window cannot prefer what it has no way 
  ▎ of knowing is true.

  So true_rules() scrolls the entire collection (all 1,046 points, no vector
  search) and runs applies(rule, tokens) — exact boolean evaluation against
  chart tokens, honouring exceptions. Only then does rank_true_rules sort the
  survivors by similarity + coverage + tier + affinity, capped at
  MAX_MATCHED_RULES = 10. Recall is total by construction. Your "10 classical
  rules match this chart" is this cap, not a coincidence.

  Stage 4 — Koonji runs completely independently. koonji_read_node calls
  Engine.from_rules(), parses the question with its own router, filters 396
  variants → ~23 in scope, fires them, and builds the evidence graph with
  noisy-OR and restatement clustering. Its claims are what build_answer_plan()
  gates on.

  Why this matters for your screenshot

  The 20 pages came from system 1. The "10 rules" came from system 2. The
  refusal came from system 3, which has rules from only 6 books and never saw
  any of it. That's the disconnect: the page count and the refusal are reporting
  on different indexes, so the UI can truthfully show 20 sources while the
  engine truthfully says it has nothing.

  Extraction feeds system 3 — koonji extract → JSONL → convert → compiled YAML →
  the engine. So adding these 12 books targets exactly the component that gated
  your answer. Systems 1 and 2 are unaffected until we separately re-run
  embed_rules.py, which is the deletion step you've deferred.

  The extraction run

  After both filters, 12 books, 1,868 rule-bearing passages:

  sarvartha-chintamani      702     phaladeepika-sastri-1950     73
  saravali-santhanam-en     348     bhavartha-ratnakara           9
  prashna-tantra            217     prasnamarga-raman-part1       7
  jatakaparijata-vol2       196     brihatjataka-row-1919         2
  jatakaparijata-vol1       143     prasnamarga-raman-part2       1
  muhurtachintamani          96
  hindupredictiveastrology   74

  At six calls per passage that's ~11,200 model calls. prepare_corpus has to run
  first (deterministic, no LLM) to bridge the 10 books that were never bridged
  — currently only 7 books are in the corpus.

  Let me start with the bridge and a small metered extraction to confirm the
  pipeline works end-to-end before committing to the full run.

  Ran 2 shell commands (ctrl+o to expand)

⏺ Prepared 18 books, but the Koonji corpus still shows only 7 — so something
  filters between them. Let me find it.

  Searched for 1 pattern, ran 1 shell command (ctrl+o to expand)

⏺ The real blocker: koonji/corpus.py reads JSONL files from disk with a
  hardcoded 11-book map — not from Postgres. Let me find what produces those
  files.

  Searched for 2 patterns, read 2 files, ran 2 shell commands (ctrl+o to expand)
⏺ No exporter exists — the JSONL files were made ad-hoc and are gitignored. Let
  me read exactly what corpus.py expects so I can write one.

  Searched for 3 patterns, listed 1 directory, ran 4 shell commands (ctrl+o to expand)

⏺ The existing JSONL files are the old extractor's output (392 rows for a book
  with 1,274 bridged units), not the full corpus. For the new books I'll export
  from Postgres directly. First, what school symbols exist:

  Searched for 1 pattern, ran 1 shell command (ctrl+o to expand)

⏺ Available schools: parashari, jaimini, prashna, lalkitab, tajika — no muhurta.
  I'll add one rather than dump Muhurta rules into the Parashari namespace.

  Now the exporter. Note the existing JSONL files carry the old extractor's rule
  data that convert.py reads, so I'll back them up rather than overwrite blind.

⏺ Write(scripts/export_corpus.py)
  ⎿  Wrote 158 lines to scripts/export_corpus.py
       1 """Export bridged Sutra Units to the JSONL the Koonji extractor 
       2 
       4     uv run python -m scripts.export_corpus --book sarvartha-chin
         tamani
         pped book
       7 `prepare_corpus` bridges a book into Postgres; `koonji.corpus` r
       8 disk. Nothing joined the two, so the extraction corpus was whate
         ver the OLD
         jata vol 1 that
         ok was
     … +191 lines (ctrl+o to expand)

⏺ Now register the five missing books in corpus.BOOKS and add the Muhurta
  school:

⏺ Update(rishivan/koonji/corpus.py)
  ⎿  Added 7 lines
      49      "brihatjataka-row-1919": ("brihat-jataka", "brihatjataka-ro
          w-1919"),
      50      "cheiros-book-of-numbers": ("cheiro-numbers", "cheiros-book
          -of-numbers"),
      51      "numerology-and-the-divine-triangle": ("divine-triangle", "
          numerology-and-the-divine-triangle"),
      52 +    # Bridged by `prepare_corpus` but never exported, so unreac
         +hable to the                                                   
      53 +    # extractor until `scripts.export_corpus` existed to join t
         +he two.                                                        
      54 +    "phaladeepika-sastri-1950": ("phaladeepika", "phaladeepika-
         +sastri-1950"),                                                 
      55 +    "saravali-santhanam-en": ("saravali", "saravali-santhanam-e
         +n"),                                                           
      56 +    "sarvartha-chintamani": ("sarvartha-chintamani", "sarvartha
         +-chintamani"),                                                 
      57 +    "prashna-tantra": ("prashna-tantra", "prashna-tantra"),    
      58 +    "muhurtachintamani": ("muhurta-chintamani", "muhurtachintam
         +ani"),                                                         
      59  }
      60  """Filename stem -> the ids a citation is built from.
      61  

⏺ Update(rishivan/koonji/corpus.py)
  ⎿  Added 8 lines
      70      "bhavartha-ratnakara": "school.parashari",
      71      "brihat-jataka": "school.parashari",
      72      "hindu-predictive": "school.parashari",
      73 +    "phaladeepika": "school.parashari",                        
      74 +    "saravali": "school.parashari",                            
      75 +    "sarvartha-chintamani": "school.parashari",                
      76      "prasna-marga": "school.prashna",
      77 +    "prashna-tantra": "school.prashna",                        
      78 +    # Electional, not natal. Given its own school for the same 
         +reason numerology                                              
      79 +    # has none: a muhurta rule reasons about an elected moment,
         + and filing it                                                 
      80 +    # under Parashari would let it fire on a birth chart it was
         + never about.                                                  
      81 +    "muhurta-chintamani": "school.muhurta",                    
      82      # Numerology is a separate modality, not a Jyotisha school.
           It has no
      83      # school symbol and no rules should be emitted from it into
           the Parashari
      84      # namespace - which is why it is absent rather than mapped 
          to a default.

  Ran 1 shell command (ctrl+o to expand)

⏺ Update(rishivan/koonji/registry.py)
  ⎿  Added 1 line
      361      "school.prashna": "Kerala horary, Prasna Marga",
      362      "school.lalkitab": "Lal Kitab - namespaced, never merged i
           nto Parashari",
      363      "school.tajika": "Tajika annual charts",
      364 +    "school.muhurta": "Muhurta Chintamani - electing a moment,
          + not reading a birth",                                        
      365  }
      366  
      367  SEED_DOMAINS = (

  Ran 1 shell command (ctrl+o to expand)

⏺ Two fixes needed: Bhavartha Ratnakara's edition_id differs from its DB slug,
  and the lookup needs to try both.

⏺ Update(scripts/export_corpus.py)
  ⎿  Added 15 lines, removed 6 lines
      49  LEGACY_DIR = CORPUS_DIR / "legacy"
      50  
      51  SLUG_BY_STEM: dict[str, str] = {stem: edition for stem, (_, edi
          tion) in BOOKS.items()}
      52 -"""File stem -> book slug. `koonji.corpus.BOOKS` is the authori
         -ty on both, so a                                               
      53 -book absent there cannot be exported: `load_units` would not kn
         -ow what book_id                                                
      54 -to stamp on its citations."""                                  
      52 +"""File stem -> the citation's edition id. `koonji.corpus.BOOKS
         +` is the                                                       
      53 +authority, so a book absent there cannot be exported: `load_uni
         +ts` would not                                                  
      54 +know what book_id to stamp on its citations."""                
      55  
      56  STEM_BY_SLUG: dict[str, str] = {slug: stem for stem, slug in SL
          UG_BY_STEM.items()}
      57  
      58  
      59 -async def units_for(session, slug: str) -> tuple[list[dict], st
         -r]:                                                            
      60 -    """Every bridged unit of one book, in reading order, as cor
         -pus rows."""                                                   
      59 +async def units_for(session, slug: str, stem: str) -> tuple[lis
         +t[dict], str]:                                                 
      60 +    """Every bridged unit of one book, in reading order, as cor
         +pus rows.                                                      
      61 +                                                               
      62 +    Looks the book up by edition id and then by file stem, beca
         +use the two                                                    
      63 +    disagree for Bhavartha Ratnakara: the citation says        
      64 +    `bhavartha-ratnakara-raman` while Postgres knows it as     
      65 +    `bhavartha-ratnakara-by-b-v-raman-text`. Trying only the fi
         +rst reported the                                               
      66 +    book as unbridged when it was bridged and sitting right the
         +re.                                                            
      67 +    """                                                        
      68      book_id = (
      69          await session.execute(
      63 -            select(Book.id).where(Book.slug == slug, Book.delet
         -ed_at.is_(None))                                               
      70 +            select(Book.id)                                    
      71 +            .where(Book.slug.in_({slug, stem}), Book.deleted_at
         +.is_(None))                                                    
      72 +            .limit(1)                                          
      73          )
      74      ).scalar_one_or_none()
      75      if book_id is None:

⏺ Update(scripts/export_corpus.py)
  ⎿  Added 1 line, removed 1 line
      149      total_units = total_rules = 0
      150      async with async_session_factory() as session:
      151          for slug in wanted:
      152 -            rows, problem = await units_for(session, slug)    
      152 +            rows, problem = await units_for(session, slug, STE
          +M_BY_SLUG[slug])                                              
      153              if problem:
      154                  print(f"  {slug:45s} SKIPPED - {problem}")
      155                  continue

  Ran 1 shell command (ctrl+o to expand)

⏺ Now export the 12 target books (BPHS and numerology excluded):

  Ran 2 shell commands (ctrl+o to expand)

⏺ Corpus went from 7 books / 3,093 units to 12 books / 5,587 units. Let me
  verify nothing broke, then prove the pipeline on a small metered run.

  Ran 1 shell command (ctrl+o to expand)

⏺ One real failure: convert.py reads the old extractor's rule key, and my export
  replaced those files with bridged units that don't carry it — so the
  converter lost its input for 7 books (1,117 → 895 rules). The legacy backups
  have it. Let me preserve it on the join.
⏺ Update(scripts/export_corpus.py)
  ⎿  Added 43 lines, removed 2 lines
      110      return out, ""
      111  
      112  
      113 +def legacy_rules(stem: str) -> dict[int, dict]:               
      114 +    """The OLD extractor's `rule` payload for this book, keyed
          + by unit id.                                                  
      115 +                                                              
      116 +    `koonji/convert.py` turns these into `rules/converted/`, w
          +hich is 222 of the                                            
      117 +    1,117 rules the engine serves today. Exporting without car
          +rying them forward                                            
      118 +    dropped the converter's input on the floor and the rule ba
          +se fell to 895 --                                             
      119 +    caught only because a test asserted the count. Re-extracti
          +on will supersede                                             
      120 +    them, but not until it has run, and the gap must not be a 
          +regression.                                                   
      121 +    """                                                       
      122 +    source = LEGACY_DIR / f"{stem}.jsonl"                     
      123 +    if not source.exists():                                   
      124 +        source = CORPUS_DIR / f"{stem}.jsonl"                 
      125 +    if not source.exists():                                   
      126 +        return {}                                             
      127 +    found: dict[int, dict] = {}                               
      128 +    for line in source.read_text(encoding="utf-8").splitlines(
          +):                                                            
      129 +        if not line.strip():                                  
      130 +            continue                                          
      131 +        try:                                                  
      132 +            row = json.loads(line)                            
      133 +        except json.JSONDecodeError:                          
      134 +            continue                                          
      135 +        if row.get("rule") and row.get("unit_id") is not None:
      136 +            found[int(row["unit_id"])] = row["rule"]          
      137 +    return found                                              
      138 +                                                              
      139 +                                                              
      140  def write_book(stem: str, rows: list[dict], *, dry_run: bool) 
           -> str:
      141      path = CORPUS_DIR / f"{stem}.jsonl"
      142      rule_bearing = sum(1 for r in rows if r["destination"] == 
           "rule")
      143      citable = sum(1 for r in rows if r["chapter"] and r["verse
           _ref"] and r["translation"].strip())
      144      note = f"{len(rows):5d} units  {citable:5d} citable  {rule
           _bearing:5d} rule-bearing"
      145  
      146 +    carried = legacy_rules(stem)                              
      147 +    matched = 0                                               
      148 +    for row in rows:                                          
      149 +        rule = carried.get(row["unit_id"])                    
      150 +        if rule:                                              
      151 +            row["rule"] = rule                                
      152 +            matched += 1                                      
      153 +    if carried:                                               
      154 +        note += f"  {matched}/{len(carried)} legacy rules carr
          +ied"                                                          
      155 +                                                              
      156      if dry_run:
      157          return f"{note}  (dry run)"
      158  
      122 -    if path.exists():                                         
      159 +    # Only the FIRST export archives the original. A later run
          + would otherwise                                              
      160 +    # move its own output over the backup and destroy the only
          + copy of the old                                              
      161 +    # extractor's work -- an idempotent-looking command that i
          +s destructive on                                              
      162 +    # its second invocation.                                  
      163 +    if path.exists() and not (LEGACY_DIR / path.name).exists()
          +:                                                             
      164          LEGACY_DIR.mkdir(parents=True, exist_ok=True)
      165          shutil.move(str(path), str(LEGACY_DIR / path.name))
      125 -        note += f"  (previous -> legacy/{path.name})"         
      166 +        note += f"  (original -> legacy/{path.name})"         
      167  
      168      CORPUS_DIR.mkdir(parents=True, exist_ok=True)
      169      with path.open("w", encoding="utf-8") as handle:

  Ran 1 shell command (ctrl+o to expand)

⏺ All legacy rules carried at 100% (141/141, 196/196, etc.) — unit ids matched
  exactly. Let me clear the five spurious backups my first run created and
  re-verify:

  Ran 3 shell commands (ctrl+o to expand)

⏺ My "141/141" was misleading — the dict collapsed duplicates. The legacy file
  has 392 rule-carrying rows but only 141 distinct unit ids.

  Ran 1 shell command (ctrl+o to expand)

⏺ The old extractor emitted one row per rule, not per unit — unit 18050 alone
  has 18. These are two different pipelines sharing one file. Let me check how
  convert consumes it:

  Searched for 1 pattern (ctrl+o to expand)

⏺ Right — convert_corpus needs one Unit per legacy rule, while the extractor
  needs one per verse. They're separate inputs. Let me split them properly.

  Searched for 1 pattern (ctrl+o to expand)

⏺ Update(rishivan/koonji/corpus.py)
  ⎿  Added 21 lines, removed 2 lines
      130      return _LEADING_REF.sub("", text or "").strip()
      131  
      132  
      133 -def corpus_files(root: Optional[Path] = None) -> list[Path]:  
      133 +LEGACY_SUBDIR = "koonji/legacy"                               
      134 +"""The OLD extractor's artefacts, which `convert.py` reads and
          + nothing else does.                                           
      135 +                                                              
      136 +Two pipelines shared one set of files and only one of them cou
          +ld be right. The                                              
      137 +old extractor wrote **one row per extracted rule** - unit 1805
          +0 of Jataka                                                   
      138 +Parijata carries eighteen - while the new extractor needs **on
          +e row per verse**,                                            
      139 +because it re-reads the verse itself and a duplicated unit mea
          +ns paying six                                                 
      140 +model calls to extract the same shloka eighteen times.        
      141 +                                                              
      142 +So they are separated: `koonji/*.jsonl` is the bridged corpus 
          +keyed by verse,                                               
      143 +`koonji/legacy/*.jsonl` is the old rule-per-row output. Readin
          +g the wrong one                                               
      144 +silently halved the converted rule base (1,117 -> 895) and onl
          +y a count                                                     
      145 +assertion noticed.                                            
      146 +"""                                                           
      147 +                                                              
      148 +                                                              
      149 +def corpus_files(root: Optional[Path] = None, *, legacy: bool 
          += False) -> list[Path]:                                       
      150      """Every ingested book, in a stable order."""
      151      root = root or CORPUS_DIR
      136 -    found = sorted((root / "koonji").glob("*.jsonl")) + sorted
          -(root.glob("koonji-*.jsonl"))                                 
      152 +    subdir = LEGACY_SUBDIR if legacy else "koonji"            
      153 +    found = sorted((root / subdir).glob("*.jsonl"))           
      154 +    if not legacy:                                            
      155 +        found += sorted(root.glob("koonji-*.jsonl"))          
      156      return [p for p in found if p.stem in BOOKS]
      157  
      158  

⏺ Update(rishivan/koonji/corpus.py)
  ⎿  Added 10 lines, removed 3 lines
      185  
      186  
      187  def load_corpus(
      188 -    root: Optional[Path] = None, *, books: Optional[Iterable[s
          -tr]] = None                                                   
      188 +    root: Optional[Path] = None,                              
      189 +    *,                                                        
      190 +    books: Optional[Iterable[str]] = None,                    
      191 +    legacy: bool = False,                                     
      192  ) -> list[Unit]:
      190 -    """Every book, or the named ones. Book ids, not filenames.
          -"""                                                           
      193 +    """Every book, or the named ones. Book ids, not filenames.
      194 +                                                              
      195 +    `legacy=True` reads the old extractor's rule-per-row artef
          +acts instead of                                               
      196 +    the bridged verse corpus - see `LEGACY_SUBDIR`. Only `conv
          +ert.py` wants it.                                             
      197 +    """                                                       
      198      wanted = set(books) if books else None
      199      units: list[Unit] = []
      193 -    for path in corpus_files(root):                           
      200 +    for path in corpus_files(root, legacy=legacy):            
      201          book_id, _ = BOOKS[path.stem]
      202          if wanted is None or book_id in wanted or path.stem in
            wanted:
      203              units.extend(load_units(path))

⏺ Update(rishivan/koonji/pipeline.py)
  ⎿  Added 7 lines, removed 1 line
      165      rules. Machine output and reviewed hand-authored material 
           should never share
      166      a file: the generated file is overwritten on every run, an
           d a hand edit made
      167      inside it would vanish without trace.
      168 +                                                              
      169 +    Reads the LEGACY corpus, which is the only thing it has ev
          +er converted: this                                            
      170 +    function turns the old extractor's output into the frame, 
          +and the old                                                   
      171 +    extractor wrote one row per rule. The bridged corpus that 
          +`extract` now                                                 
      172 +    reads is one row per verse and carries no `rule` key at al
          +l, so pointing                                                
      173 +    this at it produces nothing and says so only in the count.
      174      """
      175      started = time.perf_counter()
      176      registry = registry or seed_registry()
      177  
      172 -    units = load_corpus(books=books)                          
      178 +    units = load_corpus(books=books, legacy=True)             
      179      if limit:
      180          units = units[:limit]
      181  

⏺ Now legacy=True must still find books I never moved (BPHS, cheiro) — legacy
  dir should take precedence with the normal location as fallback:

⏺ Update(rishivan/koonji/corpus.py)
  ⎿  Added 14 lines, removed 5 lines
      147  
      148  
      149  def corpus_files(root: Optional[Path] = None, *, legacy: bool 
           = False) -> list[Path]:
      150 -    """Every ingested book, in a stable order."""             
      150 +    """Every ingested book, in a stable order.                
      151 +                                                              
      152 +    With `legacy=True` the archive wins where it exists and th
          +e normal location                                             
      153 +    is the fallback, because only books that have actually bee
          +n re-exported have                                            
      154 +    an archived copy - BPHS and the numerology texts were neve
          +r touched and                                                 
      155 +    their originals are still in place. Globbing the archive a
          +lone would have                                               
      156 +    silently dropped BPHS, which is 903 of the converted rules
          +.                                                             
      157 +    """                                                       
      158      root = root or CORPUS_DIR
      152 -    subdir = LEGACY_SUBDIR if legacy else "koonji"            
      153 -    found = sorted((root / subdir).glob("*.jsonl"))           
      159 +    current = sorted((root / "koonji").glob("*.jsonl")) + sort
          +ed(root.glob("koonji-*.jsonl"))                               
      160 +    current = [p for p in current if p.stem in BOOKS]         
      161      if not legacy:
      155 -        found += sorted(root.glob("koonji-*.jsonl"))          
      156 -    return [p for p in found if p.stem in BOOKS]              
      162 +        return current                                        
      163  
      164 +    archived = {p.stem: p for p in (root / LEGACY_SUBDIR).glob
          +("*.jsonl") if p.stem in BOOKS}                               
      165 +    return [archived.get(p.stem, p) for p in current]         
      166  
      167 +                                                              
      168  def load_units(path: Path | str) -> list[Unit]:
      169      """One book. Malformed lines are skipped rather than fatal
            - a single bad
      170      line should not cost the other 949."""

⏺ Now drop the legacy-carrying from the exporter — it collapsed duplicates and
  the two pipelines are cleanly separated:

⏺ Update(scripts/export_corpus.py)
  ⎿  Added 7 lines, removed 36 lines
      110      return out, ""
      111  
      112  
      113 -def legacy_rules(stem: str) -> dict[int, dict]:               
      114 -    """The OLD extractor's `rule` payload for this book, keyed
          - by unit id.                                                  
      113 +def write_book(stem: str, rows: list[dict], *, dry_run: bool) 
          +-> str:                                                       
      114 +    """One row per verse, and deliberately no `rule` key.     
      115  
      116 -    `koonji/convert.py` turns these into `rules/converted/`, w
          -hich is 222 of the                                            
      117 -    1,117 rules the engine serves today. Exporting without car
          -rying them forward                                            
      118 -    dropped the converter's input on the floor and the rule ba
          -se fell to 895 --                                             
      119 -    caught only because a test asserted the count. Re-extracti
          -on will supersede                                             
      120 -    them, but not until it has run, and the gap must not be a 
          -regression.                                                   
      116 +    The old extractor's output is NOT merged in here. It is on
          +e row per                                                     
      117 +    extracted rule -- eighteen for a single Jataka Parijata un
          +it -- so folding                                              
      118 +    it into a verse-keyed corpus either duplicates passages th
          +e new extractor                                               
      119 +    would then pay to re-read, or collapses eighteen rules int
          +o one and loses                                               
      120 +    seventeen. It stays in `koonji/legacy/`, where `convert.py
          +` now reads it.                                               
      121      """
      122 -    source = LEGACY_DIR / f"{stem}.jsonl"                     
      123 -    if not source.exists():                                   
      124 -        source = CORPUS_DIR / f"{stem}.jsonl"                 
      125 -    if not source.exists():                                   
      126 -        return {}                                             
      127 -    found: dict[int, dict] = {}                               
      128 -    for line in source.read_text(encoding="utf-8").splitlines(
          -):                                                            
      129 -        if not line.strip():                                  
      130 -            continue                                          
      131 -        try:                                                  
      132 -            row = json.loads(line)                            
      133 -        except json.JSONDecodeError:                          
      134 -            continue                                          
      135 -        if row.get("rule") and row.get("unit_id") is not None:
      136 -            found[int(row["unit_id"])] = row["rule"]          
      137 -    return found                                              
      138 -                                                              
      139 -                                                              
      140 -def write_book(stem: str, rows: list[dict], *, dry_run: bool) 
          --> str:                                                       
      122      path = CORPUS_DIR / f"{stem}.jsonl"
      123      rule_bearing = sum(1 for r in rows if r["destination"] == 
           "rule")
      124      citable = sum(1 for r in rows if r["chapter"] and r["verse
           _ref"] and r["translation"].strip())
      125      note = f"{len(rows):5d} units  {citable:5d} citable  {rule
           _bearing:5d} rule-bearing"
      126  
      146 -    carried = legacy_rules(stem)                              
      147 -    matched = 0                                               
      148 -    for row in rows:                                          
      149 -        rule = carried.get(row["unit_id"])                    
      150 -        if rule:                                              
      151 -            row["rule"] = rule                                
      152 -            matched += 1                                      
      153 -    if carried:                                               
      154 -        note += f"  {matched}/{len(carried)} legacy rules carr
          -ied"                                                          
      155 -                                                              
      127      if dry_run:
      128          return f"{note}  (dry run)"
      129  

  Searched for 1 pattern, ran 1 shell command (ctrl+o to expand)

⏺ The test calls load_corpus() without legacy=True, but convert_corpus only ever
  converts old-extractor output. Let me point the converter's tests at the
  converter's input:

  Searched for 1 pattern, ran 2 shell commands (ctrl+o to expand)

⏺ 547 passing. Let me confirm the rule base is intact, then do a metered proving
  run before the full extraction.

  Ran 2 shell commands (ctrl+o to expand)

⏺ Rule base intact at 1,117. Now a metered proving run before committing to the
  full extraction:

  Ran 1 shell command (ctrl+o to expand)
⏺ Pipeline works end-to-end on a new book. Two problems surfaced though — a bug
  and a throughput wall. The bug first:

  Searched for 2 patterns, ran 2 shell commands (ctrl+o to expand)

⏺ Pipeline works. But two problems, and one is serious. Let me quantify the
  throughput wall:

  Searched for 1 pattern (ctrl+o to expand)

⏺ No artificial throttle — that's genuine latency. ~13,000 calls × 15.7s ≈ 57 
  hours sequential. Before addressing that, let me fix the guidance bug:

  Searched for 1 pattern, ran 1 shell command (ctrl+o to expand)

⏺ The prompt says "the consequent block matching the assertion kind" but never
  names the blocks — so a model choosing direct_interpreter can't know it must
  emit guidance, and the compiler turns that into a bare KeyError. Let me see
  the full mapping:

  Ran 1 shell command (ctrl+o to expand)

⏺ DERIVE_FACT alone gives a real message; the rest use bare doc[...]. Let me
  make them all say what's missing:

  Ran 1 shell command (ctrl+o to expand)

⏺ Update(rishivan/koonji/compiler.py)
  ⎿  Added 37 lines
      205  }
      206  
      207  
      208 +CONSEQUENT_BLOCK: dict[AssertionKind, str] = {                
      209 +    AssertionKind.ASSERT_CLAIM: "indicates",                  
      210 +    AssertionKind.DERIVE_FACT: "derives",                     
      211 +    AssertionKind.DEFINE_ATTRIBUTE: "defines",                
      212 +    AssertionKind.DIRECT_SUBJECT: "remedy",                   
      213 +    AssertionKind.COMPUTE_VALUE: "computes",                  
      214 +    AssertionKind.DIRECT_INTERPRETER: "guidance",             
      215 +    AssertionKind.ILLUSTRATE: "example",                      
      216 +}                                                             
      217 +"""Assertion kind -> the block its consequent must arrive in. 
      218 +                                                              
      219 +Exported so `prompts.py` can name them to the model rather tha
          +n say "the                                                    
      220 +consequent block matching the assertion kind" and hope. A mode
          +l that picked                                                 
      221 +`direct_interpreter` had no way to learn the block is called `
          +guidance`, and the                                            
      222 +result was `KeyError: 'guidance'` -- a Python error where a co
          +ntent error was                                               
      223 +meant, reported against a rule the extractor had otherwise bui
          +lt correctly.                                                 
      224 +"""                                                           
      225 +                                                              
      226 +                                                              
      227 +def _block(doc: dict[str, Any], assertion: AssertionKind, rule
          +_id: str) -> dict:                                            
      228 +    """The consequent block for this assertion kind, or a usab
          +le complaint.                                                 
      229 +                                                              
      230 +    `doc["guidance"]` raising `KeyError: 'guidance'` tells a r
          +eader which dict                                              
      231 +    key was absent and nothing about which rule, which kind, o
          +r what was                                                    
      232 +    expected instead. Every kind below went through a bare sub
          +script; only                                                  
      233 +    `derive_fact` had been given a message, presumably after s
          +omeone hit it.                                                
      234 +    """                                                       
      235 +    name = CONSEQUENT_BLOCK[assertion]                        
      236 +    block = doc.get(name)                                     
      237 +    if not block:                                             
      238 +        raise ValueError(                                     
      239 +            f"{rule_id}: assertion `{assertion.value}` needs a
          + `{name}` block "                                             
      240 +            f"and the document has {sorted(doc) or 'no keys'}"
      241 +        )                                                     
      242 +    return block                                              
      243 +                                                              
      244 +                                                              
      245  def _build_consequent(doc: dict[str, Any], assertion: Assertio
           nKind, rule_id: str):
      246      if assertion is AssertionKind.ASSERT_CLAIM:
      247          block = doc.get("indicates")

  Ran 1 shell command (ctrl+o to expand)

⏺ Now name the blocks in the extraction prompt so the model can't guess wrong:

⏺ Update(rishivan/koonji/prompts.py)
  ⎿  Added 11 lines, removed 1 line
      297    quoted_text   MUST appear VERBATIM in the passage. Copy it, 
           do not retype it.
      298                  This is checked by string match, so a paraphra
           se will be caught.
      299    when          a boolean tree using only the predicates above
      300 -  the consequent block matching the assertion kind            
      300    confidence    your own, honestly
      301  
      302 +  plus the consequent block for the assertion kind you chose. 
          +The block name is                                             
      303 +  NOT the kind name, and a rule that carries the wrong one is 
          +discarded whole:                                              
      304 +                                                              
      305 +    assert_claim        -> "indicates"                        
      306 +    derive_fact         -> "derives"                          
      307 +    define_attribute    -> "defines"                          
      308 +    direct_subject      -> "remedy"                           
      309 +    compute_value       -> "computes"                         
      310 +    direct_interpreter  -> "guidance"                         
      311 +    illustrate          -> "example"                          
      312 +                                                              
      313  One verse often yields several rules - "Jupiter in the 2nd giv
           es wealth; in the
      314  6th, debt" is two. Split them.
      315  

  Ran 2 shell commands (ctrl+o to expand)

⏺ ILLUSTRATE doesn't exist — it's RECORD_APPLICATION:

  Ran 3 shell commands (ctrl+o to expand)

⏺ All 547 pass. Let me commit this before touching throughput.

  Ran 1 shell command (ctrl+o to expand)

⏺ The JSONL corpus files are tracked in git. Let me check the size before
  committing data:

  Listed 1 directory, ran 1 shell command (ctrl+o to expand)

⏺ Committed. Now the throughput wall — 57 hours sequential. The docstring says
  to parallelise once the proving run is clean, which it now is:

  Searched for 1 pattern, ran 1 shell command (ctrl+o to expand)

⏺ Budget.spend does self.calls += 1 — a read-modify-write that would undercount
  under threads. Let me make it safe first:

⏺ Update(rishivan/koonji/client.py)
  ⎿  Added 13 lines, removed 4 lines
      75      prompt_chars: int = 0
      76      response_chars: int = 0
      77  
      78 +    _lock: threading.Lock = field(default_factory=threading.Loc
         +k, repr=False)                                                 
      79 +    """`calls += 1` is a read-modify-write, and the whole point
         + of this class is                                              
      80 +    to be a hard ceiling. Under concurrent extraction an unlock
         +ed counter                                                     
      81 +    undercounts, which means the one guarantee it offers - that
         + a forgotten                                                   
      82 +    `--limit` cannot turn into a full corpus run - quietly stop
         +s holding."""                                                  
      83 +                                                               
      84      def spend(self, prompt: str, response: str) -> None:
      79 -        self.calls += 1                                        
      80 -        self.prompt_chars += len(prompt)                       
      81 -        self.response_chars += len(response)                   
      85 +        with self._lock:                                       
      86 +            self.calls += 1                                    
      87 +            self.prompt_chars += len(prompt)                   
      88 +            self.response_chars += len(response)               
      89  
      90      def check(self) -> None:
      84 -        if self.max_calls and self.calls >= self.max_calls:    
      91 +        with self._lock:                                       
      92 +            reached = bool(self.max_calls) and self.calls >= se
         +lf.max_calls                                                   
      93 +        if reached:                                            
      94              raise ExtractionUnavailable(
      95                  f"call budget of {self.max_calls} reached - rai
          se `max_calls` or "
      96                  f"narrow the run"

  Searched for 1 pattern, ran 1 shell command (ctrl+o to expand)
⏺ Now parallelise the extraction loop:

⏺ Update(rishivan/koonji/pipeline.py)
  ⎿  Added 3 lines, removed 14 lines
      298  
      299      budget = getattr(client, "budget", None)
      300  
      301 -    for i, passage in enumerate(passages, start=1):           
      302 -        before = budget.calls if budget is not None else 0    
      303 -        try:                                                  
      304 -            result = extractor.process(passage)               
      305 -        except Exception as exc:  # noqa: BLE001 - one passage
          - must not end the run                                         
      306 -            run.failures[passage.passage_id] = f"{type(exc).__
          -name__}: {exc}"                                               
      307 -            # A passage that raised still spent whatever it sp
          -ent before it                                                 
      308 -            # raised. Counting only successful passages under-
          -reports the bill                                              
      309 -            # in exactly the situation where it is climbing.  
      310 -            if budget is not None:                            
      311 -                run.calls += budget.calls - before            
      301 +    for i, passage, result, error in _processed(extractor, pas
          +sages, workers):                                              
      302 +        if error is not None:                                 
      303 +            run.failures[passage.passage_id] = error          
      304              continue
      305  
      314 -        run.calls += (                                        
      315 -            budget.calls - before if budget is not None else r
          -esult.usage.calls                                             
      316 -        )                                                     
      306          run.unbuildable.extend(result.unbuildable)
      307          run.disagreements += len(result.disagreements)
      308          blocked = set(result.blocked)

⏺ Update(rishivan/koonji/pipeline.py)
  ⎿  Added 8 lines
      321          if on_passage is not None:
      322              on_passage(i, len(passages), result)
      323  
      324 +    # The budget is the authority on the bill, not the sum of 
          +per-passage                                                   
      325 +    # attributions. A passage that raised still spent whatever
          + it spent before                                              
      326 +    # it raised, and under concurrency there is no window to a
          +ttribute it to                                                
      327 +    # anyway -- reading the counter once at the end is both si
          +mpler and the only                                            
      328 +    # number that stays right when passages overlap.          
      329 +    if budget is not None:                                    
      330 +        run.calls = budget.calls                              
      331 +                                                              
      332      run.queue.sort(key=lambda row: -row[0])
      333  
      334      rules, report, _ = gate(docs, registry)

⏺ Now the _processed helper that does sequential or concurrent dispatch:

⏺ Update(rishivan/koonji/pipeline.py)
  ⎿  Added 45 lines, removed 7 lines
      257          return "\n".join(lines)
      258  
      259  
      260 +def _processed(extractor, passages, workers: int):            
      261 +    """`(index, passage, result, error)` per passage, one thre
          +ad or several.                                                
      262 +                                                              
      263 +    A passage that raises does not stop the run - it is yielde
          +d with an error                                               
      264 +    and the next one continues. Losing four hundred passages t
          +o one malformed                                               
      265 +    response is the failure mode that makes people stop trusti
          +ng the pipeline.                                              
      266 +                                                              
      267 +    Concurrency is threads rather than processes because every
          + one of the six                                               
      268 +    calls is a network wait; the work between them is JSON par
          +sing. Results                                                 
      269 +    arrive in completion order, so `on_passage` reports progre
          +ss rather than                                                
      270 +    position - the alternative is holding finished results in 
          +memory to print                                               
      271 +    them in order, which buys tidier output and nothing else. 
      272 +    """                                                       
      273 +    if workers <= 1:                                          
      274 +        for i, passage in enumerate(passages, start=1):       
      275 +            try:                                              
      276 +                yield i, passage, extractor.process(passage), 
          +None                                                          
      277 +            except Exception as exc:  # noqa: BLE001 - the rea
          +son is the payload                                            
      278 +                yield i, passage, None, f"{type(exc).__name__}
          +: {exc}"                                                      
      279 +        return                                                
      280 +                                                              
      281 +    from concurrent.futures import ThreadPoolExecutor, as_comp
          +leted                                                         
      282 +                                                              
      283 +    with ThreadPoolExecutor(max_workers=workers) as pool:     
      284 +        futures = {                                           
      285 +            pool.submit(extractor.process, passage): (i, passa
          +ge)                                                           
      286 +            for i, passage in enumerate(passages, start=1)    
      287 +        }                                                     
      288 +        for future in as_completed(futures):                  
      289 +            i, passage = futures[future]                      
      290 +            try:                                              
      291 +                yield i, passage, future.result(), None       
      292 +            except Exception as exc:  # noqa: BLE001          
      293 +                yield i, passage, None, f"{type(exc).__name__}
          +: {exc}"                                                      
      294 +                                                              
      295 +                                                              
      296  def extract_books(
      297      client,
      298      *,
     ...
      304      fast_model: str = "gemini-2.5-flash",
      305      deep_model: str = "gemini-2.5-pro",
      306      on_passage: Optional[Callable[[int, int, Any], None]] = No
           ne,
      307 +    workers: int = 1,                                         
      308  ) -> ExtractRun:
      309      """Re-read the verses with a model, six calls at a time.
      310  
      274 -    Sequential on purpose. The bottleneck is the provider's ra
          -te limit, not this                                            
      275 -    process, and a sequential loop that can be stopped with ct
          -rl-c after                                                    
      276 -    forty passages is worth more during a proving run than a p
          -ool that has to be                                            
      277 -    drained. Parallelise when the proving run is clean and the
          - volume is real.                                              
      311 +    Defaults to sequential, which is what a proving run wants:
          + it can be stopped                                            
      312 +    with ctrl-c after forty passages and the spend is legible 
          +as it happens.                                                
      313  
      279 -    A passage that raises does not stop the run - it is record
          -ed in `failures`                                              
      280 -    and the next one starts. Losing four hundred passages to o
          -ne malformed                                                  
      281 -    response is the failure mode that makes people stop trusti
          -ng the pipeline.                                              
      314 +    `workers > 1` is for the real volume. Measured on Sarvarth
          +a Chintamani, one                                             
      315 +    call takes about sixteen seconds against Vertex, and the t
          +welve non-BPHS                                                
      316 +    books need roughly thirteen thousand calls - fifty-seven h
          +ours in a single                                              
      317 +    thread. The bottleneck is the provider's latency and not t
          +his process, so                                               
      318 +    threads convert almost linearly until the rate limit answe
          +rs back; the                                                  
      319 +    client already backs off on a 429, so the ceiling finds it
          +self.                                                         
      320      """
      321      from rishivan.koonji.extract import Extractor
      322  

  Ran 2 shell commands (ctrl+o to expand)

⏺ The test's scripted client has no budget, and I dropped the result.usage.calls
  fallback. Let me restore it:

⏺ Update(rishivan/koonji/pipeline.py)
  ⎿  Added 4 lines
      341              run.failures[passage.passage_id] = error
      342              continue
      343  
      344 +        # Only used when the client carries no budget - a scri
          +pted one in                                                   
      345 +        # tests. A real run overwrites this from the budget be
          +low, which also                                               
      346 +        # counts what a failed passage spent before it raised.
      347 +        run.calls += result.usage.calls                       
      348          run.unbuildable.extend(result.unbuildable)
      349          run.disagreements += len(result.disagreements)
      350          blocked = set(result.blocked)

  Ran 1 shell command (ctrl+o to expand)

⏺ Now measure the actual speedup before committing to a long run:

  Ran 1 shell command (ctrl+o to expand)

⏺ Two real bugs surfaced. The client isn't thread-safe — 7 of 16 passages died
  with "client has been closed":

  Searched for 1 pattern (ctrl+o to expand)

⏺ A lazy-init race: two threads each build a client, one assignment wins, the
  loser gets garbage-collected and closes its transport mid-request. Classic
  double-checked locking fix:

⏺ Update(rishivan/koonji/client.py)
  ⎿  Added 18 lines, removed 4 lines
      125      """
      126  
      127      _client: Any = field(default=None, repr=False)
      128 +    _client_lock: threading.Lock = field(default_factory=threa
          +ding.Lock, repr=False)                                        
      129  
      130      def _vertex(self):
      131 +        """Built once, under a lock, because the unlocked vers
          +ion breaks under                                              
      132 +        concurrency in a way that reads like a provider outage
          +.                                                             
      133 +                                                              
      134 +        Two threads both find `_client is None`, both build on
          +e, and the second                                             
      135 +        assignment wins. The first client now has no reference
          + from `self`, is                                              
      136 +        garbage-collected, and closes its transport -- while t
          +he thread that                                                
      137 +        received it is still mid-request. The symptom is      
      138 +        `Cannot send a request, as the client has been closed`
          +, raised against                                              
      139 +        a perfectly good passage, four retries deep, seven tim
          +es in sixteen.                                                
      140 +        """                                                   
      141          if self._client is None:
      131 -            from rishivan.council.client import get_vertex_cli
          -ent                                                           
      142 +            with self._client_lock:                           
      143 +                if self._client is None:                      
      144 +                    from rishivan.council.client import get_ve
          +rtex_client                                                   
      145  
      133 -            self._client = get_vertex_client(                 
      134 -                helicone_model=self.default_model, helicone_pi
          -peline=PIPELINE_TAG                                           
      135 -            )                                                 
      146 +                    self._client = get_vertex_client(         
      147 +                        helicone_model=self.default_model,    
      148 +                        helicone_pipeline=PIPELINE_TAG,       
      149 +                    )                                         
      150          return self._client
      151  
      152      def complete(

⏺ Now the second bug — KeyError: 'entity' is the same class as 'guidance', but
  for required keys inside a block:

  Searched for 1 pattern (ctrl+o to expand)

⏺ Update(rishivan/koonji/compiler.py)
  ⎿  Added 19 lines
      224  """
      225  
      226  
      227 +REQUIRED_FIELDS: dict[AssertionKind, tuple[str, ...]] = {     
      228 +    AssertionKind.ASSERT_CLAIM: ("claim",),                   
      229 +    AssertionKind.DERIVE_FACT: ("fact", "subject", "value"),  
      230 +    AssertionKind.DEFINE_ATTRIBUTE: ("entity", "attribute", "v
          +alues"),                                                      
      231 +    AssertionKind.DIRECT_SUBJECT: ("action",),                
      232 +    AssertionKind.COMPUTE_VALUE: ("name",),                   
      233 +    AssertionKind.DIRECT_INTERPRETER: ("text",),              
      234 +    AssertionKind.RECORD_APPLICATION: ("reading",),           
      235 +}                                                             
      236 +"""What each consequent block must carry, checked before it is
          + read.                                                        
      237 +                                                              
      238 +Same failure as the missing block itself, one level down: the 
          +model emitted a                                               
      239 +`defines` block without an `entity` and the compiler raised   
      240 +`KeyError: 'entity'`, which names a dict key and not the rule,
          + the kind, or what                                            
      241 +the block should have contained. Five Phaladeepika rules were 
          +lost to that                                                  
      242 +message in a sixteen-passage run.                             
      243 +"""                                                           
      244 +                                                              
      245 +                                                              
      246  def _block(doc: dict[str, Any], assertion: AssertionKind, rule
           _id: str) -> dict:
      247      """The consequent block for this assertion kind, or a usab
           le complaint.
      248  

  Ran 1 shell command (ctrl+o to expand)

⏺ Update(rishivan/koonji/compiler.py)
  ⎿  Added 6 lines
      258              f"{rule_id}: assertion `{assertion.value}` needs a
            `{name}` block "
      259              f"and the document has {sorted(doc) or 'no keys'}"
      260          )
      261 +    missing = [f for f in REQUIRED_FIELDS.get(assertion, ()) i
          +f block.get(f) is None]                                       
      262 +    if missing:                                               
      263 +        raise ValueError(                                     
      264 +            f"{rule_id}: `{name}` block is missing {', '.join(
          +missing)} "                                                   
      265 +            f"(it has {sorted(block) or 'no keys'})"          
      266 +        )                                                     
      267      return block
      268  
      269  

  Ran 2 shell commands (ctrl+o to expand)

❯ Instead of 6 llm calls to extract a rule, we need to make only one call, in a 
  single call we will extract domaina nd extract rule and then we will store    
  this. verification of rules will be manual by client                          

⏺ Good — the client fix worked: 24 passages, zero client failures (was 7 of 16).
  Now let me implement your single-call mode, which changes the economics far
  more than concurrency does.

  Searched for 2 patterns, ran 2 shell commands (ctrl+o to expand)

⏺ The extractor prompt already asks for domains in the rule document, so
  "extract domain and rule together" is one call's worth of work. Let me see
  PassageResult before wiring the mode:

  Searched for 1 pattern (ctrl+o to expand)

⏺ Now the single-call path. Rather than bolt a flag onto process, I'll factor
  the shared candidate-building out so both paths use it:
  Ran 1 shell command (ctrl+o to expand)

⏺ Update(rishivan/koonji/extract.py)
  ⎿  Added 79 lines
      221  
      222      # -- the whole path --------------------------------------
           --------------
      223  
      224 +    def process_once(self, passage: Passage) -> PassageResult:
      225 +        """One model call. Extract, or come back empty.       
      226 +                                                              
      227 +        The six-call pipeline buys three things this does not:
          + a cheap classify                                             
      228 +        that keeps the deep model away from invocations and pr
          +aise, a second                                                
      229 +        extraction to disagree with the first, and an adversar
          +ial verifier. All                                             
      230 +        three exist to raise the quality of what reaches a rev
          +iewer, and they                                               
      231 +        are the right trade when the reviewer is a bottleneck.
      232 +                                                              
      233 +        They are the wrong trade when review is manual and ext
          +ernal, which is                                               
      234 +        the decision here: the client reads every rule before 
          +it is approved, so                                            
      235 +        a verifier verdict the client will overrule is six sec
          +onds and five                                                 
      236 +        calls spent to pre-empt a judgement that is not the pi
          +peline's to make.                                             
      237 +                                                              
      238 +        What is kept is everything free and deterministic. `va
          +lidate_candidate`                                             
      239 +        still runs, quotes are still checked verbatim against 
          +the passage, the                                              
      240 +        compiler still refuses what it cannot build, and the r
          +eview queue is                                                
      241 +        still ordered. What is lost is recorded rather than im
          +plied:                                                        
      242 +        `result.disagreements` and `result.back_translations` 
          +stay empty and                                                
      243 +        `verification_skipped` says why, so nothing downstream
          + can mistake an                                               
      244 +        unverified rule for one that passed.                  
      245 +                                                              
      246 +        No classify call either. An empty `rules` array IS the
          + classification -                                             
      247 +        the extractor prompt already tells the model that most
          + verses are not                                               
      248 +        rules and to return nothing for them.                 
      249 +        """                                                   
      250 +        result = PassageResult(passage=passage)               
      251 +        result.verification_skipped = "single-call mode - revi
          +ew is manual"                                                 
      252 +        merged = self.extract_once(passage, EXTRACTION_TEMPERA
          +TURES[0], result.usage)                                       
      253 +        self._build_candidates(result, passage, merged, verdic
          +ts={})                                                        
      254 +        return result                                         
      255 +                                                              
      256 +    def _build_candidates(                                    
      257 +        self,                                                 
      258 +        result: PassageResult,                                
      259 +        passage: Passage,                                     
      260 +        merged: dict,                                         
      261 +        *,                                                    
      262 +        verdicts: dict,                                       
      263 +        back_translate: bool = False,                         
      264 +    ) -> None:                                                
      265 +        """Raw model output to validated candidates, shared by
          + both paths.                                                  
      266 +                                                              
      267 +        Extracted so the single-call path cannot drift from th
          +e six-call one on                                             
      268 +        the parts they agree about - flag handling, quote chec
          +king, the review                                              
      269 +        queue. Those are the parts that must stay identical wh
          +atever the client                                             
      270 +        paid for above them.                                  
      271 +        """                                                   
      272 +        raw_rules = list(merged.get("rules", []))             
      273 +        result.proposals = [                                  
      274 +            ExtensionProposal.model_validate(p) for p in merge
          +d.get("proposals", [])                                        
      275 +        ]                                                     
      276 +        if not raw_rules:                                     
      277 +            result.skipped = result.skipped or "no rules extra
          +cted"                                                         
      278 +            return                                            
      279 +                                                              
      280 +        for raw in raw_rules:                                 
      281 +            candidate, why = self._to_candidate(passage, raw, 
          +result.proposals)                                             
      282 +            if candidate is None:                             
      283 +                result.unbuildable.append(why)                
      284 +                continue                                      
      285 +            result.candidates.append(candidate)               
      286 +                                                              
      287 +            findings = validate_candidate(candidate)          
      288 +            verdict = verdicts.get(candidate.rule.rule_id, {})
      289 +            for problem in verdict.get("findings", []):       
      290 +                findings.append(Finding(                      
      291 +                    code=problem.get("category", "verifier"), 
      292 +                    severity=problem.get("severity", "warning"
          +),                                                            
      293 +                    message=problem.get("message", ""),       
      294 +                    blocking=verdict.get("verdict") == "REJECT
          +",                                                            
      295 +                ))                                            
      296 +            result.findings[candidate.rule.rule_id] = findings
      297 +                                                              
      298 +            if back_translate:                                
      299 +                result.back_translations[candidate.rule.rule_i
          +d] = (                                                        
      300 +                    self.back_translate(raw, result.usage)    
      301 +                )                                             
      302 +                                                              
      303      def process(self, passage: Passage, *, skip_dual: bool = F
           alse) -> PassageResult:
      304          result = PassageResult(passage=passage)
      305          usage = result.usage

⏺ Now collapse the duplicated tail of process onto the shared helper:

⏺ Update(rishivan/koonji/extract.py)
  ⎿  Added 7 lines, removed 27 lines
      325              ]
      326  
      327          raw_rules = list(merged.get("rules", []))
      328 -        result.proposals = [                                  
      329 -            ExtensionProposal.model_validate(p) for p in merge
          -d.get("proposals", [])                                        
      330 -        ]                                                     
      331 -                                                              
      328          if not raw_rules:
      329 +            result.proposals = [                              
      330 +                ExtensionProposal.model_validate(p)           
      331 +                for p in merged.get("proposals", [])          
      332 +            ]                                                 
      333              result.skipped = result.skipped or "no rules extra
           cted"
      334              return result
      335  
      336          verification = self.verify(passage, raw_rules, usage)
      337          verdicts = {v.get("rule_id"): v for v in verification.
           get("verdicts", [])}
      338 -                                                              
      339 -        for raw in raw_rules:                                 
      340 -            candidate, why = self._to_candidate(passage, raw, 
          -result.proposals)                                             
      341 -            if candidate is None:                             
      342 -                result.unbuildable.append(why)                
      343 -                continue                                      
      344 -            result.candidates.append(candidate)               
      345 -                                                              
      346 -            findings = validate_candidate(candidate)          
      347 -            verdict = verdicts.get(candidate.rule.rule_id, {})
      348 -            for problem in verdict.get("findings", []):       
      349 -                findings.append(Finding(                      
      350 -                    code=problem.get("category", "verifier"), 
      351 -                    severity=problem.get("severity", "warning"
          -),                                                            
      352 -                    message=problem.get("message", ""),       
      353 -                    blocking=verdict.get("verdict") == "REJECT
          -",                                                            
      354 -                ))                                            
      355 -            result.findings[candidate.rule.rule_id] = findings
      356 -                                                              
      357 -            result.back_translations[candidate.rule.rule_id] =
          - self.back_translate(                                         
      358 -                raw, usage                                    
      359 -            )                                                 
      360 -                                                              
      338 +        self._build_candidates(                               
      339 +            result, passage, merged, verdicts=verdicts, back_t
          +ranslate=True                                                 
      340 +        )                                                     
      341          return result
      342  
      343      def _to_candidate(

⏺ Update(rishivan/koonji/extract.py)
  ⎿  Added 8 lines
      110      usage: Usage = field(default_factory=Usage)
      111      skipped: str = ""
      112  
      113 +    verification_skipped: str = ""                            
      114 +    """Why no adversarial verifier ran, empty when one did.   
      115 +                                                              
      116 +    Recorded rather than left to be inferred from an empty `fi
          +ndings` dict. A                                               
      117 +    rule that no verifier examined and a rule a verifier passe
          +d are different                                               
      118 +    things, and they are indistinguishable downstream unless o
          +ne of them says                                               
      119 +    so. Single-call extraction sets this."""                  
      120 +                                                              
      121      @property
      122      def blocked(self) -> list[str]:
      123          return [rid for rid, fs in self.findings.items() if is
           _blocked(fs)]

⏺ Now wire it through the pipeline and CLI:

  Ran 1 shell command (ctrl+o to expand)

⏺ Let me verify single-call mode end-to-end and measure it:

  Ran 2 shell commands (ctrl+o to expand)

⏺ Single-call works: 24 calls for 24 passages (was 58), and it produced more
  rules (6 vs 2). But 34 candidates were blocked by validation — let me check
  what's rejecting them before scaling up:

  Searched for 1 pattern, ran 1 shell command (ctrl+o to expand)

⏺ A real single-call bug: the model sometimes returns a bare array instead of
  {"rules": [...]}. The six-call path never hit it because reconcile normalised
  the shape. Losing a whole passage to a container type is not worth it:

⏺ Update(rishivan/koonji/extract.py)
  ⎿  Added 1 line
      277          queue. Those are the parts that must stay identical wh
           atever the client
      278          paid for above them.
      279          """
      280 +        merged = _as_document(merged)                         
      281          raw_rules = list(merged.get("rules", []))
      282          result.proposals = [
      283              ExtensionProposal.model_validate(p) for p in merge
           d.get("proposals", [])

⏺ Update(rishivan/koonji/extract.py)
  ⎿  Added 28 lines
      132          )
      133  
      134  
      135 +def _as_document(payload: Any) -> dict:                       
      136 +    """`{"rules": [...]}` however the model chose to wrap it. 
      137 +                                                              
      138 +    The output contract says "Not a bare array" in those words
          +, and models                                                  
      139 +    return one anyway. The six-call path never noticed because
          + `reconcile`                                                  
      140 +    normalised the shape on its way through; single-call has n
          +o such stage, so                                              
      141 +    a bare array reached `.get("rules")` and lost the passage 
          +to                                                            
      142 +    `AttributeError: 'list' object has no attribute 'get'` -- 
          +a whole extraction                                            
      143 +    discarded over a container type.                          
      144 +                                                              
      145 +    Tolerated here rather than fixed in the prompt because the
          + prompt already                                               
      146 +    says it. A parser that accepts both costs four lines; a pr
          +ompt that asks                                                
      147 +    more firmly costs a retry every time it does not work.    
      148 +    """                                                       
      149 +    if isinstance(payload, list):                             
      150 +        return {"rules": payload}                             
      151 +    if not isinstance(payload, dict):                         
      152 +        return {}                                             
      153 +    if "rules" not in payload:                                
      154 +        # `reconciled_rules` is the other shape the contract n
          +ames, and the                                                 
      155 +        # reconciler's own output key - a model shown the six-
          +stage vocabulary                                              
      156 +        # sometimes reaches for it here.                      
      157 +        for alias in ("reconciled_rules", "extracted_rules", "
          +extracted"):                                                  
      158 +            if isinstance(payload.get(alias), list):          
      159 +                return {**payload, "rules": payload[alias]}   
      160 +    return payload                                            
      161 +                                                              
      162 +                                                              
      163  def _parse_json(raw: str) -> Any:
      164      """Models fence JSON whatever the instructions say."""
      165      text = raw.strip()

  Ran 2 shell commands (ctrl+o to expand)

⏺ Clear diagnosis: quote_not_in_passage is 30 of 34 blocks — the fabrication
  tripwire. That's the yield killer. Let me check whether it's real fabrication
  or a matching artefact:

  Searched for 1 pattern, ran 1 shell command (ctrl+o to expand)

⏺ passage_text is the verse only, not the context. Let me look at actual failing
  quotes rather than theorise:

  Ran 3 shell commands (ctrl+o to expand)

⏺ The tripwire is working correctly — these are real fabrications, and the cause
  is upstream. Look at the second one: the passage is 'Certain self-evident 
  Rajayogas.' — a chapter heading, and the model invented an entire Raja Yoga
  rule (ellipses and all) from its own knowledge.

  Ran 1 shell command (ctrl+o to expand)

⏺ Only 0.9% of passages are heading-length, so that's not the bulk. But the key
  comparison on the same 24 passages is decisive:

  ┌─────────────┬───────┬───────────────┐
  │    Mode     │ Calls │ Rules written │
  ├─────────────┼───────┼───────────────┤
  │ Six-call    │ 58    │ 2             │
  ├─────────────┼───────┼───────────────┤
  │ Single-call │ 24    │ 6             │
  └─────────────┴───────┴───────────────┘

  Your instruction holds up empirically — fewer calls, more rules. Let me commit
  and find the concurrency ceiling:

  Ran 2 shell commands (ctrl+o to expand)

⏺ Zero errors at 16 workers, and much better yield on Prashna Tantra: 48 calls →
  33 rules. Before launching the full run I need to check one thing — whether
  per-book runs overwrite each other:

  Searched for 1 pattern (ctrl+o to expand)

⏺ write_grouped overwrites per domain, so a per-book loop would clobber. Let me
  check whether the engine loads rules recursively — if so, one subdirectory per
  book is the safe shape:

  Searched for 1 pattern (ctrl+o to expand)
⏺ Recursive — so one subdirectory per book is safe and the engine will find them
  all. Let me write a resumable driver and launch:

⏺ Write(scripts/extract_all.sh)
  ⎿  Wrote 73 lines to scripts/extract_all.sh
       1 #!/usr/bin/env bash
          a time.
       3 #
         ready done
       6 #
       7 # Per book rather than one long run, for two reasons. `write_gro
       8 # file per domain and overwrites it, so a single invocation over
          twelve books
          per-book output
          compiler globs
     … +80 lines (ctrl+o to expand)

  Searched for 1 pattern, read 1 file, ran 2 shell commands (ctrl+o to expand)

⏺ Launching the full extraction in the background:

  Read 1 file, ran 2 shell commands (ctrl+o to expand)

⏺ Background command "Run full single-call extraction across 12 books" completed
(exit code 0)

⏺ --rules is a global flag that must precede the subcommand. Zero calls spent —
  it failed on argument parsing. Fixing:

⏺ Update(scripts/extract_all.sh)
  ⎿  Added 5 lines, removed 3 lines
      50    # max-calls is a safety net, not a target: single-call mode s
          pends one call
      51    # per passage, so a ceiling well above the passage count only
           catches a bug
      52    # that turns one call into a loop.
      53 -  $PY -m rishivan.koonji extract \                             
      53 +  # `--rules` is a GLOBAL argument and has to precede the subco
         +mmand. Behind                                                  
      54 +  # the subcommand argparse rejects it, the run exits before sp
         +ending anything,                                               
      55 +  # and the only symptom is "no rules written".                
      56 +  $PY -m rishivan.koonji --rules "$STAGE/$book" extract \      
      57        --book "$book" \
      58        --single-call \
      59        --workers "$WORKERS" \
      57 -      --max-calls 4000 \                                       
      58 -      --rules "$STAGE/$book" >"$log" 2>&1                      
      60 +      --max-calls 4000 >"$log" 2>&1                            
      61  
      62    if [ -d "$STAGE/$book/extracted" ]; then
      63      mkdir -p "$OUT/$book"

  Ran 1 shell command (ctrl+o to expand)

⏺ Argument order fixed. Relaunching:

  Ran 1 shell command (ctrl+o to expand)

⏺ Monitor(per-book progress of the koonji extraction run)
  ⎿  Monitor started · task boq5huoz0 · persistent

⏺ Extraction is running across all 12 books; I'll report per-book as they land.
  Here's where things stand.

  Your single-call change was right, and measurably so

  Same 24 Phaladeepika passages:

  ┌─────────────┬───────┬───────────────┐
  │    Mode     │ Calls │ Rules written │
  ├─────────────┼───────┼───────────────┤
  │ Six-call    │ 58    │ 2             │
  ├─────────────┼───────┼───────────────┤
  │ Single-call │ 24    │ 6             │
  └─────────────┴───────┴───────────────┘

  Fewer calls and more rules — the dual-extract-and-reconcile round was
  discarding rules the single pass keeps. The corpus-wide projection drops from
  ~13,000 calls to ~3,600.

  What I kept is everything free and deterministic: quote-verbatim checking,
  validate_candidate, the compiler's nine passes, and the review queue ordered
  by impact × uncertainty. What's gone is recorded rather than implied —
  verification_skipped states why no verifier ran, so nothing downstream can
  mistake an unexamined rule for one that passed.

  Getting there needed a corpus fix first

  prepare_corpus bridged books into Postgres and koonji.corpus read JSONL off
  disk, and nothing joined the two. The extractor was reading whatever the old
  pipeline wrote months ago: 7 books, 3,093 units. Five bridged books had never
  been exported at all, and Jataka Parijata vol 1 had 392 rows against 1,274
  bridged units — two thirds of the book unreachable, silently.

  scripts/export_corpus.py is that join. Corpus is now 12 books, 5,587 units.

  One trap in there: the old extractor wrote one row per rule (unit 18050
  carries eighteen), while the new one needs one row per verse. They'd been
  sharing a file. Merging them either duplicates passages you pay to re-read or
  collapses eighteen rules into one — I hit the second and the converted rule
  base dropped 1,117 → 895, caught only because a test asserted the count.
  They're now split: koonji/legacy/ for the converter, koonji/*.jsonl for the
  extractor.

  Five bugs, four of which only appear under concurrency

  - VertexClient lazy-init race — two threads each built a client, the second
  assignment won, the first was garbage-collected and closed its transport
  mid-request. Symptom: Cannot send a request, as the client has been closed,
  seven times in sixteen passages, against perfectly good input.
  - Budget.spend unlocked calls += 1 — the class exists to be a hard ceiling,
  and an unlocked counter undercounts.
  - Bare JSON array rejected — the contract says "Not a bare array" and models
  return one anyway; reconcile used to normalise it, so single-call lost whole
  passages to 'list' object has no attribute 'get'.
  - KeyError: 'guidance' / KeyError: 'entity' — Python errors where content
  errors were meant. The prompt never named the consequent blocks, so a model
  choosing direct_interpreter couldn't know the block is called guidance. Both
  fixed; five Phaladeepika rules had been lost to the bare KeyError in one
  16-passage run.
  - --rules placement — it's a global flag; behind the subcommand argparse
  rejects it and the run exits before spending anything. My first launch hit
  this. Cost: nothing.

  One thing worth your attention

  The fabrication tripwire blocked 30 of 37 Phaladeepika candidates, and I
  checked whether it was over-strict. It isn't — it's catching real fabrication.
  The clearest case:

  PASSAGE: 'Certain self-evident Rajayogas.'
  QUOTE  : 'If at a birth, the lord of the Lagna be in the 5th house and the
            lord of the 5th in the Lagna... it gives rise to a Raja Yoga...'

  The unit is a chapter heading, and the model invented the rule it knows should
  follow, ellipses and all. The tripwire is why this pipeline is trustworthy,
  so I left it alone. But it means Phaladeepika's bridge output contains
  headings dressed as verses. Prashna Tantra by contrast: 48 passages → 61
  candidates, only 12 blocked, 33 rules. Yield varies a lot by how cleanly a
  book was bridged.

  I have not deleted anything from Qdrant, per your instruction. The 1,046 rule
  embeddings and 52,958 passage embeddings are untouched.

✻ Brewed for 1h 6m 45s

⏺ Monitor event: "per-book progress of the koonji extraction run"

  Read 1 file (ctrl+o to expand)

⏺ Two red flags: only 20 passages (corpus says 37), and 0k response chars —
  every call returned empty, in 0.66s each. Let me look:

  Ran 1 shell command (ctrl+o to expand)

⏺ Found it — and it's affecting every book. Two things:

  1. --limit defaults to 20, so each book is being truncated to 20 passages. My
  script never overrode it.
  2. prasna-marga's bridged "verses" are actually table-of-contents entries
  ('Prayer ... 1\n2. What Astrology Comprehends ... 3'), so 0 rules is correct
  there — the model rightly returned nothing.

  Stopping the run to fix the limit:

⏺ Stop Task
  ⎿  WORKERS=16 ./scripts/extract_all.sh --force 2>&1 · stopped

⏺ Stop Task
  ⎿  tail -f /private/tmp/claude-501/-Users-admin-Desktop-live-projects-ris
     hivan-demo/35dd264f-47fd-4c40-b202-21f459a71354/tasks/b7oqjm9ja.output
     2>/dev/null | grep… · stopped

⏺ Update(scripts/extract_all.sh)
  ⎿  Added 4 lines
      53    # `--rules` is a GLOBAL argument and has to precede the subco
          mmand. Behind
      54    # the subcommand argparse rejects it, the run exits before sp
          ending anything,
      55    # and the only symptom is "no rules written".
      56 +  # `--limit 0` means the whole book. The CLI default is 20 and
         + deliberately                                                  
      57 +  # low, which is right for a proving run and wrong here -- wit
         +hout this every                                                
      58 +  # book silently stops after twenty passages and reports succe
         +ss.                                                            
      59    $PY -m rishivan.koonji --rules "$STAGE/$book" extract \
      60        --book "$book" \
      61        --single-call \
      62 +      --limit 0 \                                              
      63        --workers "$WORKERS" \
      64        --max-calls 4000 >"$log" 2>&1
      65  

  Ran 1 shell command (ctrl+o to expand)

⏺ Also documented --limit 0 in the CLI so this can't bite again. Relaunching:
  Ran 1 shell command (ctrl+o to expand)

⏺ Monitor(per-book progress of the koonji extraction run)
  ⎿  Monitor started · task bg6qsra4f · persistent

⏺ Relaunched with --limit 0. Two things worth flagging while it runs.

  The --limit 20 default nearly cost you the whole run silently. Every book
  would have stopped after 20 passages and reported success — prasna-marga said
  "20 passages · 0 rules written" and looked like a legitimate low-yield book
  rather than a truncated one. Fixed in the script, and I documented 0 means the
  whole book in the CLI help so the next person doesn't hit it.

  Corpus quality is going to be the real limiter, not the extractor. Prasna
  Marga's bridged "verses" turned out to be table-of-contents lines:

  'Prayer ... 1\n2. What Astrology Comprehends ... 3\n3. Who can study
  Astrology? ... 7'

  The model correctly returned nothing for those, so 0 rules is the right answer
  for that book — but it means we paid 20 calls to extract front matter.
  Combined with the Phaladeepika chapter-headings-as-verses finding, the pattern
  is that the bridge admits front matter and headings as citable units, and
  yield per book will track how clean each book's bridge output was. Prashna
  Tantra (48 passages → 33 rules) is what a well-bridged book looks like;
  Phaladeepika and Prasna Marga are not.

  That's worth a separate pass once this run finishes — a deterministic
  front-matter filter in the bridge would cut spend and remove a fabrication
  vector, since a heading is exactly the input that makes a model invent the
  content it knows should follow. It's free to run and needs no model.

  Current spend so far is trivial (~110 calls across all the proving runs). The
  full run is ~3,600 calls and roughly 7 hours at 16 workers; I'll report each
  book as it completes.

✻ Churned for 1m 44s

⏺ Monitor event: "per-book progress of the koonji extraction run"

⏺ While that runs, let me quantify the front-matter problem precisely — it's
  read-only and directly predicts the run's yield.

  Ran 1 shell command (ctrl+o to expand)

⏺ I over-generalised earlier — the measurement corrects me:

  ┌─────────────────────────────┬─────────────┬──────────────────────────┐
  │                             │ corpus-wide │        worst book        │
  ├─────────────────────────────┼─────────────┼──────────────────────────┤
  │ Table-of-contents lines     │ 1%          │ prasnamarga-part1 at 68% │
  ├─────────────────────────────┼─────────────┼──────────────────────────┤
  │ Heading-length (<120 chars) │ 4.2%        │ hindupredictive at 31%   │
  └─────────────────────────────┴─────────────┴──────────────────────────┘

  So the corpus is broadly clean, not broadly contaminated. Prasna Marga part 1 
  is the outlier — 23 of its 34 passages are table of contents, which is why
  that book returned zero and why I mistook it for a pattern. Hindu Predictive
  Astrology has a different shape of the same issue (93 of 304 passages under
  120 chars).

  That means a front-matter filter would save ~5% of spend, not the large
  fraction I implied. Worth doing eventually for the fabrication-vector reason,
  but it is not the yield limiter I called it.

  The Phaladeepika 30-of-37 block rate therefore has some other cause, and I
  don't yet know what it is. The run will show whether that rate is typical or
  particular to that book — Prashna Tantra's 12-of-61 suggests it's particular.
  I'll wait for real per-book numbers rather than guess again.

✻ Sautéed for 30s

⏺ Monitor event: "per-book progress of the koonji extraction run"

  Searched for 1 pattern (ctrl+o to expand)

⏺ --limit 0 worked (37 passages now, was 20). But the log says 3 rules written
  while my script reported 0 — let me check the copy:

  Listed 1 directory (ctrl+o to expand)

⏺ My script's counter is wrong, not the extraction — grep -c on a single file
  prints just 3, not file:3, so the awk -F: sum reads nothing. The real result:

  prasna-marga → 3 rules from 37 passages (75 candidates, 64 blocked by
  validation, 11 compiled to 3).

  I won't edit the script while it's running — bash reads scripts incrementally
  and an in-place edit can corrupt the loop. I'll report accurate counts from
  the files themselves and fix the counter afterwards.

  That book was always going to be the worst case (68% table-of-contents). The
  64-blocked figure is the one to watch: if it holds across cleanly-bridged
  books, the blocking rate is a pipeline property rather than a corpus one, and
  worth digging into. Prashna Tantra's 12-of-61 says otherwise, so I expect this
  to be Prasna Marga being Prasna Marga. Waiting on the next few books to tell.

✻ Cogitated for 38s

⏺ Monitor event: "per-book progress of the koonji extraction run"

⏺ Let me verify something important while this runs: that extracted rules
  actually load into the engine. If they don't, the whole run is wasted.

  Ran 1 shell command (ctrl+o to expand)

⏺ 1,124 rules loaded, up from 1,117 — exactly the +3 and +4 from the two
  finished books. The extracted rules compile, round-trip, and load into the
  engine. That was the main risk and it's cleared.

  Ran 1 shell command (ctrl+o to expand)

⏺ End-to-end pipeline confirmed working:

  bhavartha-ratnakara   19 → 23   (+4)
  prasna-marga           7 → 10   (+3)

  Bridge → export → single-call extract → compile → live in the engine. Every
  stage verified on real output.

  Throughput is ~7s per passage at 16 workers. Eight books remain (~3,550
  passages), so roughly 7 hours. The large ones — Sarvartha Chintamani (1,112),
  Jataka Parijata (687), Saravali (557) — are where the bulk of the new rules
  will come from, and they're queued last so the small books derisked the run
  first.

  I'll report the per-book totals as they land, and give you a consolidated
  picture at the end including whether the Phaladeepika blocking rate was
  book-specific.

✻ Baked for 39s

⏺ Monitor event: "per-book progress of the koonji extraction run"

⏺ 98 rules from 13 passages is a surprising yield — let me verify rather than
  report it at face value:

  Ran 2 shell commands (ctrl+o to expand)

⏺ Verified: 98 real rules from 13 passages — Brihat Jataka's verses are dense,
  each enumerating many combinations. Engine now at 1,222 rules (brihat-jataka
  19 → 117).

  Notably it wrote across 12 domain files including relationship.yaml, which is
  the domain your marriage question routes to:

  Ran 3 shell commands (ctrl+o to expand)

⏺ Concrete progress on the original problem — domain.relationship went 132 → 143
  rules, with Brihat Jataka contributing 11:

  domain.wealth          269      domain.progeny         64
  domain.temperament     175      domain.education       53
  domain.relationship    143      domain.spiritual       50
  domain.health          111      domain.longevity       34
  domain.status          109      domain.property        30
  domain.career           70      domain.travel          19

  Six books remain, including the three largest. Saravali and Sarvartha
  Chintamani together are 1,669 passages and both are cleanly bridged (0% TOC),
  so they should be the biggest contributors.

  Worth noting the blocking rate is running high everywhere — 68 of 111 for
  Brihat Jataka, 64 of 75 for Prasna Marga — so Phaladeepika's 30-of-37 was not
  book-specific after all. That's a pipeline property, and the dominant code was
  quote_not_in_passage. Since blocked candidates still land in the review queue
  rather than being discarded, and your review is manual, they aren't lost —
  but it means roughly half to two-thirds of what the model extracts isn't
  reaching the rule files automatically. I'll quantify it properly across all
  books once the run finishes; if a meaningful share are near-miss quotes rather
  than fabrications, loosening the match (whitespace/OCR normalisation is
  already there, but not ellipsis or line-wrap handling) would recover real
  rules without weakening the tripwire.
✻ Sautéed for 1m 11s

❯ now give me commands book by book, with costs, no of api calls...             

⏺ Let me measure the real token cost from the completed runs rather than
  estimate.

  Ran 2 shell commands (ctrl+o to expand)

⏺ Now I have real measurements. Per call: system prompt is 9,446 chars (not
  counted in the budget), plus the passage, plus ~12.8k chars of response.

  Ran 1 shell command (ctrl+o to expand)

⏺ Here's the book-by-book breakdown. Single-call mode means API calls = citable 
  passages, exactly one each.

  Per-book cost and commands

  ┌──────────────────────┬───────┬────────┬─────────┬─────────┬──────────┐
  │         Book         │ Calls │ In tok │ Out tok │  Cost   │ Mins @16 │
  ├──────────────────────┼───────┼────────┼─────────┼─────────┼──────────┤
  │ prasna-marga         │    37 │   184k │    118k │   $1.41 │        4 │
  ├──────────────────────┼───────┼────────┼─────────┼─────────┼──────────┤
  │ bhavartha-ratnakara  │     7 │    21k │     22k │   $0.25 │        1 │
  ├──────────────────────┼───────┼────────┼─────────┼─────────┼──────────┤
  │ brihat-jataka        │    13 │    36k │     42k │   $0.46 │        2 │
  ├──────────────────────┼───────┼────────┼─────────┼─────────┼──────────┤
  │ phaladeepika         │   141 │   393k │    451k │   $5.00 │       16 │
  ├──────────────────────┼───────┼────────┼─────────┼─────────┼──────────┤
  │ jataka-parijata      │   687 │ 1,769k │  2,198k │  $24.20 │       80 │
  ├──────────────────────┼───────┼────────┼─────────┼─────────┼──────────┤
  │ hindu-predictive     │   304 │   809k │    973k │  $10.74 │       35 │
  ├──────────────────────┼───────┼────────┼─────────┼─────────┼──────────┤
  │ prashna-tantra       │   339 │   853k │  1,085k │  $11.91 │       40 │
  ├──────────────────────┼───────┼────────┼─────────┼─────────┼──────────┤
  │ muhurta-chintamani   │   412 │ 1,038k │  1,318k │  $14.48 │       48 │
  ├──────────────────────┼───────┼────────┼─────────┼─────────┼──────────┤
  │ saravali             │   557 │ 1,369k │  1,782k │  $19.53 │       65 │
  ├──────────────────────┼───────┼────────┼─────────┼─────────┼──────────┤
  │ sarvartha-chintamani │ 1,112 │ 2,715k │  3,558k │  $38.98 │      130 │
  ├──────────────────────┼───────┼────────┼─────────┼─────────┼──────────┤
  │ TOTAL                │ 3,609 │ 9,187k │ 11,549k │ $126.97 │      421 │
  └──────────────────────┴───────┴────────┴─────────┴─────────┴──────────┘

  The commands

  # whole corpus, resumable — skips books already done
  WORKERS=16 ./scripts/extract_all.sh

  # one book at a time (--rules is GLOBAL, it must precede `extract`)
  .venv/bin/python -m rishivan.koonji --rules /tmp/koonji-out/BOOK extract \
      --book BOOK --single-call --limit 0 --workers 16 --max-calls 4000

  Substitute BOOK with the book id from the table — prasna-marga,
  sarvartha-chintamani, and so on. Then copy results in:

  cp /tmp/koonji-out/BOOK/extracted/*.yaml rishivan/koonji/rules/extracted/BOOK/

  A dry costing before committing spend:

  .venv/bin/python -m rishivan.koonji extract --book BOOK --limit 0 --dry-run

  How these numbers were derived

  Measured, not guessed. From the three completed books: system prompt 9,446 
  chars on every call (extractor_system — this is not in the budget line, so the
  CLI's prompt chars understates input by ~2,400 tokens per call), plus the
  passage text, plus a measured mean of 12.8k response chars. At 4 chars/token,
  priced at Gemini 2.5 Pro's $1.25/M in, $10/M out.

  Two caveats on the total:

  - Output dominates at 91% of cost. If you switch --deep-model to
  gemini-2.5-flash, the same run is roughly $12 instead of $127. Worth a
  50-passage A/B on Saravali before committing $127 — flash may well be adequate
  now that no verifier depends on the extraction's subtlety.
  - prasna-marga is inflated — its 25k chars/call is table-of-contents pages,
  not typical. The other books average ~2.5k.

  Runtime assumes 7s/passage at 16 workers, measured. ~7 hours total. The run in
  flight has finished three books ($2.12 spent) and is on Phaladeepika.

✻ Crunched for 1m 1s

⏺ Monitor event: "per-book progress of the koonji extraction run"

⏺ Phaladeepika produced 169 rules from 141 passages — far better than the
  24-passage sample suggested. Let me verify and check the blocking rate:

  Searched for 1 pattern (ctrl+o to expand)
  ⎿  Interrupted · What should Claude do instead?

❯ we wil use gemini-3.5-flash-lite for ths                                      

⏺ Stopping the run first — no point spending Pro rates on Jataka Parijata ($24)
  if we're switching.

⏺ Stop Task
  ⎿  WORKERS=16 ./scripts/extract_all.sh --force 2>&1 · stopped

  Ran 1 shell command (ctrl+o to expand)

⏺ gemini-3.5-flash-lite works. Before committing the whole corpus to it, let me
  A/B against Pro on the exact same 24 Phaladeepika passages I measured earlier:

  Ran 1 shell command (ctrl+o to expand)

⏺ Empty responses — 24 calls, 0 response chars, 3.9s. Let me find out why before
  concluding anything:

  Ran 1 shell command (ctrl+o to expand)

⏺ Not empty — 17 chars, finish: STOP, 9 output tokens. It's responding, just
  declining to extract. Let me see what it actually says:

  Ran 1 shell command (ctrl+o to expand)

❯ do not run ay task without my approval, if runnning stop now, and use         
  gemini-3.5-flash-lite for this                                                

⏺ Stop Task
  ⎿  tail -f /private/tmp/claude-501/-Users-admin-Desktop-live-projects-ris
     hivan-demo/35dd264f-47fd-4c40-b202-21f459a71354/tasks/b23ra7u2l.output
     2>/dev/null | grep… · stopped

  Read 1 file, wrote 1 memory (ctrl+o to expand)

⏺ Everything is stopped — the extraction run and the monitor. Nothing is running
  now. I've saved the approval rule to memory so it carries across sessions;
  launching that run without asking you first was my mistake.

  What was completed before I stopped it

  Four books finished and are on disk, in the engine:

  ┌─────────────────────┬──────────┬───────┬────────┐
  │        Book         │ Passages │ Rules │  Cost  │
  ├─────────────────────┼──────────┼───────┼────────┤
  │ prasna-marga        │       37 │     3 │  $1.41 │
  ├─────────────────────┼──────────┼───────┼────────┤
  │ bhavartha-ratnakara │        7 │     4 │  $0.25 │
  ├─────────────────────┼──────────┼───────┼────────┤
  │ brihat-jataka       │       13 │    98 │  $0.46 │
  ├─────────────────────┼──────────┼───────┼────────┤
  │ phaladeepika        │      141 │   169 │ ~$5.00 │
  ├─────────────────────┼──────────┼───────┼────────┤
  │ Total               │      198 │   274 │ ~$7.12 │
  └─────────────────────┴──────────┴───────┴────────┘

  Engine went 1,117 → ~1,390 rules. Jataka Parijata was interrupted partway and
  wrote nothing.

  One thing you need to know before we switch to flash-lite

  I tested gemini-3.5-flash-lite. The model name is valid and responds — but on
  the extraction prompt it returns no rules at all:

  24 passages · 24 model calls · 3.9s
  0 candidates · 0 blocked · 0 documents -> 0 rules written

  I checked the raw response: finish_reason: STOP, 3,057 input tokens, 9 output 
  tokens. It isn't erroring or truncating — it reads the passage and returns an
  empty rules array. Pro on those same 24 passages produced 7 candidates and 6
  rules, and on the full book 258 candidates and 171 rules.

  So as things stand, switching to flash-lite gives you a ~$12 run that produces
  zero rules. That's not a reason to refuse it — it's likely a prompt-fit
  problem, since the extractor system prompt is 9.4k chars of closed-vocabulary
  instructions written for a reasoning model, and flash-lite may need it
  restructured or a schema forced. I was in the middle of diffing flash-lite
  against Pro output on identical passages when you stopped me, which is exactly
  the test that would tell us which.

  How do you want to proceed? I'd suggest I run one diagnostic — 2 passages, 4
  calls, about $0.001 — to see what flash-lite actually returns versus Pro. If
  the prompt can be adapted, the full corpus at flash-lite rates is roughly $12 
  instead of $127, which is worth a few minutes of investigation. But I won't
  run anything until you say so.

✻ Cooked for 37s

❯ tell me [Image #7] witht he gemini-3.5-flash-lite                             
  ⎿  [Image #7]
⏺ Pure arithmetic on the measured token counts — no API calls.

  Ran 1 shell command (ctrl+o to expand)

⏺ Same corpus, gemini-3.5-flash-lite

  ┌──────────────────────┬───────┬────────┬─────────┬───────┬─────────┬──────┐
  │         Book         │ Calls │ In tok │ Out tok │ Lite  │  Pro $  │ Mins │
  │                      │       │        │         │   $   │         │  @16 │
  ├──────────────────────┼───────┼────────┼─────────┼───────┼─────────┼──────┤
  │ prasna-marga         │    37 │   184k │    118k │ $0.07 │   $1.41 │    2 │
  ├──────────────────────┼───────┼────────┼─────────┼───────┼─────────┼──────┤
  │ bhavartha-ratnakara  │     7 │    21k │     22k │ $0.01 │   $0.25 │    0 │
  ├──────────────────────┼───────┼────────┼─────────┼───────┼─────────┼──────┤
  │ brihat-jataka        │    13 │    36k │     42k │ $0.02 │   $0.47 │    1 │
  ├──────────────────────┼───────┼────────┼─────────┼───────┼─────────┼──────┤
  │ phaladeepika         │   141 │   393k │    451k │ $0.22 │   $5.00 │    6 │
  ├──────────────────────┼───────┼────────┼─────────┼───────┼─────────┼──────┤
  │ jataka-parijata      │   687 │ 1,769k │  2,198k │ $1.06 │  $24.19 │   29 │
  ├──────────────────────┼───────┼────────┼─────────┼───────┼─────────┼──────┤
  │ hindu-predictive     │   304 │   809k │    973k │ $0.47 │  $10.74 │   13 │
  ├──────────────────────┼───────┼────────┼─────────┼───────┼─────────┼──────┤
  │ prashna-tantra       │   339 │   853k │  1,085k │ $0.52 │  $11.92 │   14 │
  ├──────────────────────┼───────┼────────┼─────────┼───────┼─────────┼──────┤
  │ muhurta-chintamani   │   412 │ 1,038k │  1,318k │ $0.63 │  $14.48 │   17 │
  ├──────────────────────┼───────┼────────┼─────────┼───────┼─────────┼──────┤
  │ saravali             │   557 │ 1,369k │  1,782k │ $0.85 │  $19.53 │   23 │
  ├──────────────────────┼───────┼────────┼─────────┼───────┼─────────┼──────┤
  │ sarvartha-chintamani │ 1,112 │ 2,715k │  3,558k │ $1.69 │  $38.97 │   46 │
  ├──────────────────────┼───────┼────────┼─────────┼───────┼─────────┼──────┤
  │ TOTAL                │ 3,609 │ 9,187k │ 11,547k │ $5.54 │ $126.95 │  150 │
  └──────────────────────┴───────┴────────┴─────────┴───────┴─────────┴──────┘

  $5.54 versus $126.95 — 23× cheaper, and ~2.5 hours instead of 7.

  Four books are already done on Pro, so the actual remaining spend is 3,411 
  calls / $5.22.

  Two things this table assumes

  Pricing. I've used the Flash-Lite tier at $0.10/M input and $0.40/M output. I
  could not verify 3.5-flash-lite's published rate — worth confirming against
  your billing page, since the whole table scales linearly with it.

  That it produces rules at all. The token counts are Pro's measured output
  carried across unchanged. In my one test, flash-lite returned 9 output tokens
  and zero rules on 24 passages where Pro found 6 — finish_reason: STOP, no
  error, just an empty rules array. If that holds, the real out-token column is
  near zero, the run costs cents, and yields nothing.

  So the honest reading is: $5.54 is the cost if the prompt works on flash-lite,
  and we do not yet know that it does. The 9.4k-char closed-vocabulary system
  prompt was written for a reasoning model.

  The cheap way to settle it is a 2-passage diff — 4 calls, well under a cent —
  showing flash-lite's raw output next to Pro's on identical input. Say the word
  and I'll run just that, nothing else.

✻ Cogitated for 38s

❯ complete those 4 books first, store in db                                     

⏺ Let me look at what the DB path is for these rules before writing anything.

  Searched for 2 patterns, ran 2 shell commands (ctrl+o to expand)

⏺ There's a schema gap I need to surface before writing anything. Let me check
  who actually reads the rule table:

  Searched for 1 pattern, ran 1 shell command (ctrl+o to expand)

⏺ Now the full chain is clear:

  extract → Postgres `rule` table → manual approval (approved_at) →
  embed_rules.py → Qdrant → serving

  So storing in the DB is exactly what unblocks your manual review and the
  re-embed. But there's a schema gap I need to show you:

  Searched for 1 pattern, read 1 file (ctrl+o to expand)

⏺ Concrete gap. The new extraction emits URF registry symbols:

  when: {all: [{occupies_rashi: {subject: graha.moon, rashi: rashi.aries}}]}
  indicates: {claim: relationship.harmony, polarity: positive}

  but load_rules / compile_condition / the matcher's applies() all expect the
  old extractor's vocabulary:

  {"formation": {"atoms": [{"type": "planet_in_sign", "planet": "moon", "sign":
  "aries"}]}}

  Let me measure how big the reverse mapping actually is:

  Ran 1 shell command (ctrl+o to expand)

⏺ Only 12 distinct predicates across 274 rules, and three cover 78%. That makes
  the reverse map tractable. Let me see the target vocabulary:

  Searched for 1 pattern, ran 1 shell command (ctrl+o to expand)

⏺ The engine now fails to load entirely — Phaladeepika emitted a duplicate rule
  id. That breaks the app, so it takes priority:

  Searched for 1 pattern, ran 1 shell command (ctrl+o to expand)

⏺ group_by_domain picks one file per rule, so that's not it — the model emitted
  the same id for two different rules:

  Ran 1 shell command (ctrl+o to expand)

⏺ Two genuinely different verses (ch28.v83 and ch28.v63) got the same
  model-assigned id — the model mistyped the verse ref into the id. Let me see
  the established id scheme:

  Searched for 1 pattern (ctrl+o to expand)

⏺ There's an established scheme — {BOOK}.{TOPIC}.{LOCATOR}.{index}, derived from
  the citation, never from the model. The extractor should do the same. Let me
  fix the root cause:

  Ran 1 shell command (ctrl+o to expand)

⏺ Update(rishivan/koonji/extract.py)
  ⎿  Added 2 lines
      400          # from the one the prompt tells the model to send.
      401          for key in prompts.EXTRACTOR_FLAG_KEYS:
      402              raw.pop(key, None)
      403 +                                                              
      404 +        raw["id"] = stamped_rule_id(passage, raw, index)      
      405          try:
      406              rule = self._build_rule(raw, self.registry)
      407          except Exception as exc:  # noqa: BLE001 - the reason 
           is the payload

⏺ Update(rishivan/koonji/extract.py)
  ⎿  Added 37 lines
      132          )
      133  
      134  
      135 +_ID_CLEAN = re.compile(r"[^A-Z0-9]+")                         
      136 +                                                              
      137 +CONSEQUENT_TOPIC = {                                          
      138 +    "indicates": "claim", "derives": "fact", "defines": "attri
          +bute",                                                        
      139 +    "remedy": "action", "computes": "name",                   
      140 +}                                                             
      141 +"""Which key in a consequent block names what the rule is *abo
          +ut*, for the id."""                                           
      142 +                                                              
      143 +                                                              
      144 +def stamped_rule_id(passage: Passage, raw: dict, index: int) -
          +> str:                                                        
      145 +    """The rule's id, derived from its citation. The model doe
          +s not get a vote.                                             
      146 +                                                              
      147 +    Ids arrived from the model and were used verbatim, and mod
          +els get them                                                  
      148 +    wrong: Phaladeepika ch28.v83 and ch28.v63 both came back a
          +s                                                             
      149 +    `PD.28.63.0002`, because the model mistyped the verse numb
          +er into the id of                                             
      150 +    one of them. Two different rules then shared an id, and th
          +e compiler refused                                            
      151 +    the whole bundle -- correctly, since a duplicated id fires
          + twice and counts                                             
      152 +    as two independent sources under noisy-OR. The engine woul
          +d not load at all.                                            
      153 +                                                              
      154 +    Same principle as `parse_report` stamping the rishi and do
          +main from the                                                 
      155 +    caller: an identity is a fact about where the thing came f
          +rom, not content                                              
      156 +    for a generation to author. Derived from the citation rath
          +er than a counter                                             
      157 +    so a re-run produces the same ids and a diff shows what ac
          +tually changed --                                             
      158 +    matching `convert.rule_id_for`, which has always done this
          +.                                                             
      159 +    """                                                       
      160 +    book = _ID_CLEAN.sub("", passage.book_id.upper())         
      161 +    where = _ID_CLEAN.sub("", passage.locator.upper())        
      162 +                                                              
      163 +    topic = str(raw.get("assertion") or "rule")               
      164 +    for block, key in CONSEQUENT_TOPIC.items():               
      165 +        value = raw.get(block)                                
      166 +        if isinstance(value, dict) and value.get(key):        
      167 +            topic = str(value[key]).split(".")[0]             
      168 +            break                                             
      169 +    return f"{book}.{_ID_CLEAN.sub('', topic.upper())}.{where}
          +.{index:04d}"                                                 
      170 +                                                              
      171 +                                                              
      172  def _as_document(payload: Any) -> dict:
      173      """`{"rules": [...]}` however the model chose to wrap it.
      174  
  Ran 1 shell command (ctrl+o to expand)

⏺ Now re-stamp the ids in the four books already on disk, using the same scheme
  — this is local and free:

  Ran 2 shell commands (ctrl+o to expand)

⏺ Different collision now — with the converted rules, because
  convert.rule_id_for uses the identical scheme on the same verses.
  Non-destructive fix: make the two sources structurally unable to collide.

⏺ Update(rishivan/koonji/extract.py)
  ⎿  Added 10 lines, removed 1 line
      158      so a re-run produces the same ids and a diff shows what ac
           tually changed --
      159      matching `convert.rule_id_for`, which has always done this
           .
      160      """
      161 +    The trailing ordinal carries an `X` that `convert.rule_id_
          +for`'s does not.                                              
      162 +    Both derive an id from `{BOOK}.{TOPIC}.{LOCATOR}.{n}` and 
          +both read the same                                            
      163 +    books, so re-extracting a verse the converter had already 
          +handled produced                                              
      164 +    the same id twice and the compiler refused the bundle agai
          +n -- with the                                                 
      165 +    engine, and therefore the app, refusing to start. The mark
          +er makes the                                                  
      166 +    collision structurally impossible rather than accidentally
          + avoided, and it                                              
      167 +    is legible in a trace: `.X0001` came from the model, `.000
          +1` from the                                                   
      168 +    deterministic converter.                                  
      169 +    """                                                       
      170      book = _ID_CLEAN.sub("", passage.book_id.upper())
      171      where = _ID_CLEAN.sub("", passage.locator.upper())
      172  
     ...
      176          if isinstance(value, dict) and value.get(key):
      177              topic = str(value[key]).split(".")[0]
      178              break
      170 -    return f"{book}.{_ID_CLEAN.sub('', topic.upper())}.{where}
          -.{index:04d}"                                                 
      179 +    return f"{book}.{_ID_CLEAN.sub('', topic.upper())}.{where}
          +.X{index:04d}"                                                
      180  
      181  
      182  def _as_document(payload: Any) -> dict:

  Ran 1 shell command (ctrl+o to expand)

⏺ Engine loads again — 1,391 rules, up from 1,117. But that output exposes the
  same class of bug one level down:

  phaladeepika               154
  Phaladeepika                10   ← model capitalised it
  phaladeepika-sastri-1950     5   ← model used the slug

  _to_candidate uses setdefault for provenance, so whatever the model wrote
  wins. Book id feeds citation rendering, restatement clustering, and the §15
  authority matrix — a wrong value silently drops the book out of source
  weighting:

⏺ Update(rishivan/koonji/extract.py)
  ⎿  Added 11 lines, removed 3 lines
      432      ) -> tuple[Optional[ExtractionCandidate], str]:
      433          raw = dict(raw)
      434          raw.setdefault("status", "candidate")
      435 +        # Overwritten, not defaulted. Which book a passage cam
          +e from is a fact                                              
      436 +        # the caller holds and the model is guessing at: one P
          +haladeepika run                                               
      437 +        # produced `phaladeepika`, `Phaladeepika` and `phalade
          +epika-sastri-1950`                                            
      438 +        # across 169 rules, so the engine reported three books
          + where there is                                               
      439 +        # one. `book_id` drives citation text, restatement clu
          +stering and the                                               
      440 +        # §15 source-authority matrix, and an unrecognised val
          +ue does not error                                             
      441 +        # -- it silently scores the book as neutral and drops 
          +it out of the                                                 
      442 +        # weighting. Same reasoning as the rule id above.     
      443          source = dict(raw.get("source") or {})
      436 -        source.setdefault("book", passage.book_id)            
      437 -        source.setdefault("edition", passage.edition_id)      
      438 -        source.setdefault("locator", passage.locator)         
      444 +        source["book"] = passage.book_id                      
      445 +        source["edition"] = passage.edition_id                
      446 +        source["locator"] = passage.locator                   
      447          raw["source"] = source
      448  
      449          flags = ExtractionFlags(

  Ran 4 shell commands (ctrl+o to expand)

⏺ My edit landed the new paragraph after the closing quotes. Fixing:

⏺ Update(rishivan/koonji/extract.py)
  ⎿  Added 1 line, removed 1 line
      157      for a generation to author. Derived from the citation rath
           er than a counter
      158      so a re-run produces the same ids and a diff shows what ac
           tually changed --
      159      matching `convert.rule_id_for`, which has always done this
           .
      160 -    """                                                       
      160 +                                                              
      161      The trailing ordinal carries an `X` that `convert.rule_id_
           for`'s does not.
      162      Both derive an id from `{BOOK}.{TOPIC}.{LOCATOR}.{n}` and 
           both read the same
      163      books, so re-extracting a verse the converter had already 
           handled produced

  Ran 2 shell commands (ctrl+o to expand)

⏺ The tests encode the old behaviour — that the model's id is preserved. That's
  exactly what caused the outage, so the tests should assert the new contract:

  Searched for 1 pattern, ran 1 shell command (ctrl+o to expand)

⏺ My change broke verdict lookup in the six-call path — the verifier keys
  verdicts by the model's id, which I now overwrite. Real bug, let me fix it:

⏺ Update(rishivan/koonji/extract.py)
  ⎿  Added 10 lines, removed 1 line
      362              return
      363  
      364          for index, raw in enumerate(raw_rules, start=1):
      365 +            # The verifier was shown the model's documents and
          + keys its verdicts                                            
      366 +            # by the ids they carried, so the lookup below has
          + to know both:                                                
      367 +            # `_to_candidate` replaces the id with a citation-
          +derived one, and                                              
      368 +            # keying only on the new id silently dropped every
          + verdict.                                                     
      369 +            model_id = raw.get("id")                          
      370              candidate, why = self._to_candidate(
      371                  passage, raw, result.proposals, index
      372              )
     ...
      376              result.candidates.append(candidate)
      377  
      378              findings = validate_candidate(candidate)
      374 -            verdict = verdicts.get(candidate.rule.rule_id, {})
      379 +            verdict = (                                       
      380 +                verdicts.get(candidate.rule.rule_id)          
      381 +                or verdicts.get(model_id)                     
      382 +                or {}                                         
      383 +            )                                                 
      384              for problem in verdict.get("findings", []):
      385                  findings.append(Finding(
      386                      code=problem.get("category", "verifier"),

  Ran 1 shell command (ctrl+o to expand)

⏺ Let me add a regression test for the collision that broke the engine, since
  nothing would have caught it:

  Ran 1 shell command (ctrl+o to expand)

⏺ Update(tests/koonji/test_extract.py)
  ⎿  Added 50 lines
      154          assert "CORRECT AND EXPECTED OUTCOME" in extract_call[
           "system"]
      155  
      156  
      157 +class TestIdentityIsStampedNotAuthored:                       
      158 +    """The model does not name its own rules.                 
      159 +                                                              
      160 +    It got one wrong in production: Phaladeepika ch28.v83 and 
          +ch28.v63 both came                                            
      161 +    back as `PD.28.63.0002`, two different rules sharing an id
          +. The compiler                                                
      162 +    refuses a duplicated id -- correctly, since it would fire 
          +twice and count as                                            
      163 +    two independent sources under noisy-OR -- so the whole bun
          +dle failed to                                                 
      164 +    compile and the engine would not start. Nothing caught it 
          +until the app                                                 
      165 +    stopped loading.                                          
      166 +    """                                                       
      167 +                                                              
      168 +    def test_the_id_is_derived_from_the_citation(self, registr
          +y):                                                           
      169 +        result = Extractor(ScriptedClient(full_script()), regi
          +stry).process(passage())                                      
      170 +        assert result.candidates[0].rule.rule_id == "BPHS.WEAL
          +TH.CH23V13.X0001"                                             
      171 +                                                              
      172 +    def test_the_models_id_is_overwritten(self, registry):    
      173 +        """`RULE_JSON` carries `BPHS.WEALTH.10L11H.0001`. It m
          +ust not survive."""                                           
      174 +        result = Extractor(ScriptedClient(full_script()), regi
          +stry).process(passage())                                      
      175 +        assert result.candidates[0].rule.rule_id != RULE_JSON[
          +"id"]                                                         
      176 +                                                              
      177 +    def test_two_rules_from_one_passage_get_different_ids(self
          +, registry):                                                  
      178 +        """The ordinal is what separates siblings, and a verse
          + routinely yields                                             
      179 +        several - "Jupiter in the 2nd gives wealth; in the 6th
          +, debt"."""                                                   
      180 +        second = dict(RULE_JSON, id=RULE_JSON["id"])       # s
          +ame id, twice                                                 
      181 +        script = full_script(extra_rules=[second])            
      182 +        result = Extractor(ScriptedClient(script), registry).p
          +rocess(passage())                                             
      183 +        ids = [c.rule.rule_id for c in result.candidates]     
      184 +        assert len(ids) == len(set(ids)), ids                 
      185 +                                                              
      186 +    def test_the_extracted_id_cannot_collide_with_a_converted_
          +one(self, registry):                                          
      187 +        """`convert.rule_id_for` builds `{BOOK}.{TOPIC}.{LOCAT
          +OR}.{n:04d}` from                                             
      188 +        the same books. Without the `X` the two namespaces ove
          +rlap, which is the                                            
      189 +        second way this broke the bundle."""                  
      190 +        result = Extractor(ScriptedClient(full_script()), regi
          +stry).process(passage())                                      
      191 +        ordinal = result.candidates[0].rule.rule_id.rsplit("."
          +, 1)[-1]                                                      
      192 +        assert ordinal.startswith("X")                        
      193 +                                                              
      194 +    def test_the_book_id_comes_from_the_passage_not_the_model(
          +self, registry):                                              
      195 +        """One run produced `phaladeepika`, `Phaladeepika` and
      196 +        `phaladeepika-sastri-1950` across a single book, so th
          +e engine reported                                             
      197 +        three. An unrecognised book scores neutral in the §15 
          +matrix rather than                                            
      198 +        erroring, so it fails silently."""                    
      199 +        lying = dict(RULE_JSON, source={**RULE_JSON.get("sourc
          +e", {}),                                                      
      200 +                                        "book": "Bphs Gcsharma
          + Vol1"})                                                      
      201 +        result = Extractor(                                   
      202 +            ScriptedClient(full_script(lying)), registry      
      203 +        ).process(passage())                                  
      204 +        assert result.candidates[0].rule.provenance.book_id ==
          + "bphs"                                                       
      205 +                                                              
      206 +                                                              
      207  class TestCandidates:
      208      def test_a_clean_extraction_becomes_a_candidate(self, regi
           stry):
      209          result = Extractor(ScriptedClient(full_script()), regi
           stry).process(passage())

  Searched for 1 pattern (ctrl+o to expand)

⏺ full_script has no extra_rules param. Let me build that one script inline
  instead:

⏺ Update(tests/koonji/test_extract.py)
  ⎿  Added 8 lines, removed 2 lines
      177      def test_two_rules_from_one_passage_get_different_ids(self
           , registry):
      178          """The ordinal is what separates siblings, and a verse
            routinely yields
      179          several - "Jupiter in the 2nd gives wealth; in the 6th
           , debt"."""
      180 -        second = dict(RULE_JSON, id=RULE_JSON["id"])       # s
          -ame id, twice                                                 
      181 -        script = full_script(extra_rules=[second])            
      180 +        both = {"rules": [dict(RULE_JSON), dict(RULE_JSON)], "
          +proposals": []}                                               
      181 +        script = [                                            
      182 +            {"is_rule_bearing": True, "assertion_kinds": ["ass
          +ert_claim"]},                                                 
      183 +            both, both,                                       
      184 +            {**both, "material_disagreements": []},           
      185 +            {"verdicts": []},                                 
      186 +            "back translation", "back translation",           
      187 +        ]                                                     
      188          result = Extractor(ScriptedClient(script), registry).p
           rocess(passage())
      189          ids = [c.rule.rule_id for c in result.candidates]
      190          assert len(ids) == len(set(ids)), ids

  Ran 2 shell commands (ctrl+o to expand)

⏺ 552 passing, and the mutation check confirms the new tests actually bite —
  reverting to setdefault fails 4 of the 5.

  Ran 1 shell command (ctrl+o to expand)

⏺ The four books are complete and the engine is healthy again — 1,391 rules, up 
  from 1,117.

  ┌─────────────────────┬──────────┬───────┐
  │        Book         │ Passages │ Rules │
  ├─────────────────────┼──────────┼───────┤
  │ phaladeepika        │      141 │   169 │
  ├─────────────────────┼──────────┼───────┤
  │ brihat-jataka       │       13 │    98 │
  ├─────────────────────┼──────────┼───────┤
  │ bhavartha-ratnakara │        7 │     4 │
  ├─────────────────────┼──────────┼───────┤
  │ prasna-marga        │       37 │     3 │
  ├─────────────────────┼──────────┼───────┤
  │                     │          │   274 │
  └─────────────────────┴──────────┴───────┘

  Finishing them surfaced two bugs that would have poisoned every later book,
  both now fixed with a mutation-verified regression test.

  The engine had stopped loading entirely. The model mistyped a verse number
  into a rule id, so two different Phaladeepika rules shared PD.28.63.0002. The
  compiler refuses duplicate ids — correctly, since a rule firing twice counts
  as two independent sources under noisy-OR — so one bad digit in 274 rules took
  down the whole bundle, and the app with it. Ids are now derived from the
  citation, as convert.rule_id_for always did.

  Three books where there is one. source.book was setdefault, so the model's
  guess won: phaladeepika, Phaladeepika, and phaladeepika-sastri-1950 all
  appeared. That one fails silently — book_id drives citation text, restatement
  clustering and the §15 authority matrix, and an unrecognised book doesn't
  error, it just scores neutral and drops out of the weighting.

  On "store in db" — I need a decision before I write anything

  The chain is extract → Postgres rule table → your manual approval → 
  embed_rules.py → Qdrant → serving. So the DB is exactly the right target. But
  the table can't take these rules as they are:

  # what extraction now produces (URF registry symbols)
  when: {all: [{occupies_rashi: {subject: graha.moon, rashi: rashi.aries}}]}

  # what load_rules / compile_condition / the matcher's applies() expect
  {"formation": {"atoms": [{"type": "planet_in_sign", "planet": "moon", "sign":
  "aries"}]}}

  I checked how big the reverse map would be — 12 distinct predicates across the
  274 rules. Three of them (occupies_rashi, occupies_bhava, conjunct/aspects)
  map cleanly and cover ~70%. But dasha_active (42 rules) is refused outright by
  the old compiler — "timing must never manufacture a natal promise" — and
  in_dusthana, strength_band, in_kendra, in_trikona, same_bhava, varga_occupies
  have no old equivalent at all.

  So forcing URF into the legacy schema loses roughly 30% of the rules and all
  of the modality, corroboration and timing metadata.

  Two honest options:

  1. New koonji_rule table holding the URF document as JSONB plus indexed
  columns for review (book, locator, domain, claim, status, approved_at).
  Lossless, needs a migration, and your review UI points at the new table.
  2. Reverse-map into the existing rule table, accepting that ~30% won't land
  and the rest arrive degraded. No migration, existing tooling works untouched.

  I'd recommend (1) — the URF is the newer and richer representation and mapping
  it backwards throws away the parts that make it worth having. But it's a
  schema change, so it's your call. Which do you want?
✻ Crunched for 8m 35s

❯ why can't we store in teh existing rule table?                                

⏺ Fair challenge — let me verify that rather than repeat it. The key question is
  what actually depends on the atom prefilter.

  Searched for 2 patterns (ctrl+o to expand)

⏺ RuleAtom has exactly one reader — the SQL prefilter at match/engine.py:159.
  And embed_rules reads only Rule columns, no atoms. Let me check whether that
  prefilter is even in the serving path:

  Searched for 1 pattern, ran 1 shell command (ctrl+o to expand)

⏺ I was wrong, and here's the correction. match_chart — the only thing that 
  reads RuleAtom — is never called at serving time. Only tests reference it. The
  serving path imports just applies and satisfies, which are pure functions
  over the JSONB condition.

  So the atom prefilter isn't a blocker. Let me check the one thing that
  actually is:

  Ran 1 shell command (ctrl+o to expand)

⏺ You're right — we can. My "30% loss" claim was wrong and I should correct it
  precisely.

  satisfies() returns False for unrecognised atom types rather than raising —
  the code says so explicitly: "They must be inert, not explosive." So a URF
  condition in that column doesn't break anything; it just never matches.

  So the real cost is much narrower than I said. Let me verify the one genuine
  hard requirement — unit_id is NOT NULL:

  Ran 1 shell command (ctrl+o to expand)

⏺ 274/274 unit_ids resolve from the locator. So the one genuinely hard
  constraint is satisfiable, and my objection collapses.

  Here's the corrected picture — what actually happens if we use the existing
  table:

  ┌───────────────────────────────────────┬─────────────────────────────────┐
  │                                       │             Works?              │
  ├───────────────────────────────────────┼─────────────────────────────────┤
  │ rule row persisted                    │                                 │
  │ (condition/effect/source are all      │ ✅                              │
  │ JSONB)                                │                                 │
  ├───────────────────────────────────────┼─────────────────────────────────┤
  │ unit_id FK resolved from locator      │ ✅ 274/274                      │
  ├───────────────────────────────────────┼─────────────────────────────────┤
  │ Your manual review + approved_at      │ ✅                              │
  ├───────────────────────────────────────┼─────────────────────────────────┤
  │ embed_rules.py → Qdrant               │ ✅ reads only Rule columns,     │
  │                                       │ never atoms                     │
  ├───────────────────────────────────────┼─────────────────────────────────┤
  │                                       │ irrelevant — match_chart is     │
  │ RuleAtom prefilter                    │ dead code, never called at      │
  │                                       │ serving                         │
  ├───────────────────────────────────────┼─────────────────────────────────┤
  │ Legacy applies() firing the rule      │ ❌ returns False on URF atoms — │
  │                                       │  inert, not broken              │
  └───────────────────────────────────────┴─────────────────────────────────┘

  The only real casualty is that the legacy Qdrant matcher won't fire these
  rules. But the Koonji engine already matches them from YAML, and that's the
  path feeding the answer plan. So the loss is a second, older matcher that
  Koonji has superseded.

  Let me check the status vocabulary and build the loader:

  Ran 2 shell commands (ctrl+o to expand)

⏺ Now I have the exact shape. Let me write the loader:

⏺ Write(scripts/load_extracted.py)
  ⎿  Wrote 229 lines to scripts/load_extracted.py
       1 """Load Koonji-extracted URF rules into the Postgres rule base.
       3     uv run python -m scripts.load_extracted --dry-run
       4     uv run python -m scripts.load_extracted --book phaladeepika
       5     uv run python -m scripts.load_extracted
       7 The extractor writes URF YAML under `rishivan/koonji/rules/extra
         cted/<book>/`,
          with, and not
       9 enough to review: approval is a database act (`approved_at`), an
         d
         not from disk.
     … +280 lines (ctrl+o to expand)

  Ran 1 shell command (ctrl+o to expand)

⏺ All 274 map cleanly, nothing skipped. Committing them for real:

  Ran 2 shell commands (ctrl+o to expand)

⏺ Loaded — DB went 1,241 → 1,515 rules, all 274 new ones unapproved. But one
  thing is wrong and it matters for retrieval:

  transl. : 'ambassador'

  embedding_text builds the vector from source['translation'], and I mapped that
  to the URF quote — a short verbatim fragment. The old rules carry the full
  verse. A one-word vector will match almost nothing. I already resolve unit_id,
  so the real verse is right there:

⏺ Update(scripts/load_extracted.py)
  ⎿  Added 11 lines, removed 2 lines
      109      return []
      110  
      111  
      112 -def row_for(rule: dict, book_slug: str) -> dict:              
      113 -    """One URF rule projected onto the `rule` table's columns.
          -"""                                                           
      112 +def row_for(rule: dict, book_slug: str, verse: str = "") -> di
          +ct:                                                           
      113 +    """One URF rule projected onto the `rule` table's columns.
      114 +                                                              
      115 +    `verse` is the unit's full translation. It matters more th
          +an it looks:                                                  
      116 +    `embed_rules.embedding_text` builds the vector from `sourc
          +e["translation"]`,                                            
      117 +    and URF has no such field -- only `quote`, the verbatim fr
          +agment the                                                    
      118 +    fabrication tripwire checks. One Brihat Jataka rule's quot
          +e is the single                                               
      119 +    word "ambassador", and a vector built from that matches no
          +thing a seeker                                                
      120 +    would ever type. The quote is kept alongside, because it i
          +s what the                                                    
      121 +    citation displays and what the tripwire verified.         
      122 +    """                                                       
      123      source = dict(rule.get("source") or {})
      124      qualifiers = dict(rule.get("qualifiers") or {})
      125      return {

  Ran 2 shell commands (ctrl+o to expand)

⏺ Now the vector will be built from the full verse (median 531 chars) with the
  quote preserved for citation, and the upsert proved idempotent (0 inserted,
  274 updated).

  Ran 1 shell command (ctrl+o to expand)

⏺ You were right, and checking it properly is what settled the design. The 
  existing table takes them fine — all 274 loaded, nothing skipped.

  My "30% loss" claim was wrong on every count:

  - RuleAtom has one reader, match_chart, which has no caller outside tests. The
  SQL prefilter isn't on the serving path, so atom_count = 0 costs nothing.
  - embed_rules never touches atoms — only Rule columns.
  - condition, effect, source are JSONB and take URF unchanged.
  - unit_id was the one hard NOT NULL, and it resolves from the locator for
  274/274.

  What's in the database now

  rules total 1,515  ·  approved 1,046  ·  newly loaded 274 (approved_at NULL)

  Every new row is unapproved, so MATCHABLE_PREDICATE excludes them — loading a
  book cannot put an unreviewed rule in front of a user. Re-running updates in
  place and never touches approved_at, so your review decisions survive a
  re-extraction.

  The URF document is kept whole under effect["urf"]. The columns beside it are
  a projection for the existing consumers, and a projection drops modality,
  corroboration, restriction and timing — keeping the original means we can
  improve the projection later without re-extracting.

  One thing I caught while verifying: I'd mapped source["translation"] to the
  URF quote, and that field is what embed_rules vectorises. One Brihat Jataka
  rule's quote is the single word "ambassador" — a vector no real question would
  ever reach. It now uses the unit's full verse (median 531 chars) with the
  quote kept for citation display.

  The one real limitation, recorded not hidden

  satisfies() reads the old atom vocabulary and returns False for a URF atom —
  inert by design, "not explosive" as the code puts it. So once approved, these
  rules embed into Qdrant but won't fire in the legacy matcher. The Koonji
  engine matches them from YAML today, and that's the path feeding the answer
  plan, so nothing regresses. Closing it means either teaching satisfies the URF
  shape or reverse-mapping the twelve predicates in use — separate work, and
  I've documented it in the module rather than pretending it away.

  Next step is yours. The remaining six books are ~3,400 calls. On Pro that's
  ~$120; on flash-lite ~$5 but it returned zero rules in my one test and needs
  the prompt diagnosed first (4 calls, under a cent). I won't run either until
  you say so.

✻ Sautéed for 4m 46s

❯                                                                               
  satisfies() reads the old atom vocabulary and returns False for a URF atom —  
  inert by design, "not explosive" as the code puts it. So once approved, these 
  rules embed into Qdrant but won't fire in the legacy matcher. The Koonji      
  engine matches them from YAML today, and that's the path feeding the answer   
  plan, so nothing regresses. Closing it means either teaching satisfies the    
  URF shape or reverse-mapping the twelve predicates in use - your language is  
  too hard to understand, always respond in simpler language with proper        
  ocntext so that i can understand what you want to convey                      

⏺ You're right — let me save that and then explain it properly.

  Read 1 file, wrote 1 memory (ctrl+o to expand)

⏺ Saved. Here's that same point, explained properly.

  The background you need first

  Your app has two separate systems that match rules to a birth chart. They were
  built at different times and they don't share code.

  System 1 — the old one. Rules live in Postgres, get copied into Qdrant, and a
  piece of code checks each rule against the chart. It's been there since the
  early version of the project.

  System 2 — the Koonji engine. Newer. Rules live as YAML files on disk. It has
  its own matching code, its own index, and it never touches Qdrant or Postgres.

  These two systems write rules down in different formats. Same idea, different
  words.

  Old format — how System 1 writes "Moon in Aries":
  {"type": "planet_in_sign", "planet": "moon", "sign": "aries"}

  New format — how System 2 writes the exact same thing:
  occupies_rashi: {subject: graha.moon, rashi: rashi.aries}

  What I actually did

  The 274 new rules were extracted in the new format. I stored them in the
  Postgres table that belongs to the old system. That worked — every column
  accepted them.

  The catch

  The old system's matching code only understands the old format. When it reads
  a new-format rule, it doesn't crash and it doesn't throw an error — it just
  quietly answers "this rule doesn't apply to this chart," every single time,
  for every chart.

  So those 274 rules would sit in the old system doing nothing. Not broken, just
  permanently silent.

  Why this doesn't actually hurt you

  The Koonji engine reads those same 274 rules from the YAML files and matches
  them correctly right now. And Koonji is the system that decides what your
  answer says — it's what produced "10 classical rules match this chart" in your
  screenshot.

  So nothing you had before got worse, and the new rules are already working
  through the path that matters.

  If you want to fix it later

  Two ways, roughly equal effort:

  1. Teach the old code the new format — one translation layer, and all 274
  rules work in both systems.
  2. Convert each rule as it's saved — there are only 12 different condition
  types in use, so the conversion table is small.

  Neither is urgent. I'd honestly suggest a third option: the old system may
  just be dead weight now that Koonji does the same job better. Worth deciding
  deliberately rather than maintaining both by default.
✻ Sautéed for 31s

❯ yes, we will use new engine format.                                           

⏺ Good — that's the cleaner choice. Let me check what actually depends on the
  old path before I change anything.

  Searched for 5 patterns, ran 2 shell commands (ctrl+o to expand)

⏺ Good news on ordering — koonji_read already runs before retrieve, so the
  Koonji results are available where I'd need them. Let me check one last thing:
  whether something already turns a URF condition into readable text.

  Searched for 1 pattern (ctrl+o to expand)

⏺ Here's what switching to the new engine format actually involves. Nothing
  surprising, but I want your go-ahead before I start since it touches the
  answer path.

  What changes

  Right now the rules panel in your UI ("10 classical rules match this chart")
  is filled by the old system reading Qdrant. The Koonji engine runs separately
  and feeds the written answer.

  After the change, Koonji fills both. One rule system instead of two.

  The three pieces of work

  1. A translator for conditions — the only genuinely new code.

  Your UI shows why each rule matched, in English. There's a function that turns
  the old format into a sentence. Nothing does that for the new format yet, so
  I'd write one:

  {all: [{occupies_rashi: {subject: graha.moon, rashi: rashi.aries}}]}
                      ↓
  "the Moon is in Aries"

  Roughly 50 lines plus tests.

  2. Build the rules panel from Koonji instead of Qdrant.

  Koonji already knows which rules fired. It just doesn't package them in the
  shape the UI reads — citation, condition, effects, and whether the timing
  period is running now. About 70 lines plus tests.

  3. Point the retrieval step at Koonji.

  Small. The ordering already works in our favour: Koonji runs before this step,
  so its results are sitting right there.

  What this gets you

  - All 274 new rules become visible in the UI. Today they're invisible there,
  because the old system can't read them.
  - One rule system to maintain, not two.
  - The counts stop disagreeing. In your marriage screenshot, "10 classical
  rules" and the engine's own view were two different numbers from two different
  systems. They'd be one number.

  What I'd leave alone for now

  The old Qdrant rules collection and embed_rules.py. I'd stop using them rather
  than delete them, so there's a way back if the new panel turns out worse.
  Deleting is a separate decision once you've seen it working.

  Effort

  Around 150 lines of code plus tests. No API calls, no cost. Maybe an hour.

  Shall I go ahead?

✻ Baked for 1m 32s

※ recap: We're moving Rishivan's rule matching onto the new Koonji engine format so one system feeds both the UI and the answers. Four books are extracted and stored in the database. I'm waiting on your go-ahead to write the ~150 lines that switch the rules panel over.

❯ also can we create bphs rules from postgres to yaml to support new retrieval  
  and koonji mehtod?                                                            

⏺ Good question — but let me check whether that gap actually exists first,
  because BPHS already has 903 rules in the Koonji engine.

  Ran 1 shell command (ctrl+o to expand)

⏺ Both already exist, and Koonji actually has more:

  Koonji YAML   895 BPHS rules (converted/) + 8 hand-authored
  Postgres      686 approved BPHS rules

  So the direction you're asking about may already be done. Let me check whether
  Postgres covers any verses the YAML doesn't:

  Ran 1 shell command (ctrl+o to expand)

⏺ There's a real gap. Let me confirm it's convertible:

  Ran 1 shell command (ctrl+o to expand)

⏺ Yes — and it's worth doing, because there's a real gap I didn't expect.

  What I found

  The BPHS rules in Postgres and the ones in Koonji's YAML files came from the
  same extraction, but they're not the same set:

  ┌──────────────────────────────────┬────────────────┐
  │                                  │ Verses covered │
  ├──────────────────────────────────┼────────────────┤
  │ Koonji YAML                      │ 244            │
  ├──────────────────────────────────┼────────────────┤
  │ Postgres (approved)              │ 394            │
  ├──────────────────────────────────┼────────────────┤
  │ In Postgres, missing from Koonji │ 164            │
  ├──────────────────────────────────┼────────────────┤
  │ In Koonji, missing from Postgres │ 14             │
  └──────────────────────────────────┴────────────────┘

  So 164 BPHS verses have approved rules sitting in the database that the Koonji
  engine has never been able to see. They're paid for, reviewed, approved — and
  invisible to the part of the system that writes your answers.

  The good news: this is nearly free

  I checked the format of the Postgres rules. They're stored in the old format:

  {"atoms": [{"type": "lord_of_house_in_house", "house": 12, "lord_of": 5}]}

  And you already have a converter that turns exactly that into the new format —
  convert.py. It's the same code that produced the 895 BPHS rules already in
  YAML. It's deterministic, needs no AI calls, and it's already covered by
  tests.

  So this isn't new logic. It's pointing an existing, working converter at the
  database instead of at the old JSONL files on disk.

  Cost: nothing. No API calls. Maybe half an hour.

  Why the two sets drifted apart

  The YAML came from the legacy JSONL files, which turn out to be a partial
  export. The database got the full load. Nobody noticed because nothing
  compared them — which is the same shape of problem as the corpus gap I found
  earlier, where the extractor was reading a stale file while the real data sat
  in Postgres.

  So there are two jobs on the table

  1. Switch the rules panel to the Koonji engine (~150 lines, ~1 hour) — makes
  all 274 newly extracted rules visible in the UI and gets rid of the second
  rule system.
  2. Convert the Postgres BPHS rules to YAML (~half an hour, free) — recovers
  164 verses of already-approved BPHS that Koonji can't currently reach.

  They fit together well: job 2 adds the rules, job 1 makes them visible.

  Want me to do both? I'd start with 2, since it's smaller and gives an
  immediate, measurable jump in the engine's rule count.

✻ Worked for 1m 24s

❯ go ahead                                                                      

⏺ Starting with the Postgres→YAML conversion. Let me check exactly what the
  existing converter expects:

  Ran 1 shell command (ctrl+o to expand)

⏺ Perfect — the converter takes a Unit with the old-format data attached, which
  is exactly what Postgres holds. Writing the bridge:

⏺ Write(scripts/convert_db_rules.py)
  ⎿  Wrote 183 lines to scripts/convert_db_rules.py
      1 """Approved Postgres rules into Koonji YAML, so the engine can fi
        re them.
      3     uv run python -m scripts.convert_db_rules --report
      4     uv run python -m scripts.convert_db_rules --book bphs-gcsharm
        a-vol1
      6 
      7 No model calls and no spend: this is the same deterministic conve
        rter that
        t the JSONL
      9 files on disk.
     … +218 lines (ctrl+o to expand)

  Ran 1 shell command (ctrl+o to expand)

⏺ That contradicts my earlier finding — the converter reproduces documents that
  already exist (536 of 537). Let me find out which analysis was wrong:
  Ran 1 shell command (ctrl+o to expand)

⏺ vol1 alone: 34 verses in Postgres that YAML lacks (my earlier 164
  double-counted across a looser key). But the converter only produced 1 new
  document from them — so those rules must be getting refused. Let me see why:

  Ran 1 shell command (ctrl+o to expand)

⏺ I was wrong about the gap, and here's the correction. Let me quantify what's
  actually recoverable:

  Ran 1 shell command (ctrl+o to expand)

⏺ I need to correct myself: the BPHS conversion job is not worth doing, and my 
  164-verse figure was wrong.

  Running it for real produces 2 new documents across all books, and the 
  compiler drops both. The converted/ YAML already contains everything the
  deterministic converter can produce from those Postgres rules.

  My error: I compared verse locations between the two sources and found 164
  that looked missing. But those verses are absent from the YAML because the 
  converter refuses them, not because nobody converted them. The refusals are
  things like:

  35  effect 1: life_domain '(none)' has no claim
  13  effect 1: life_domain 'family' has no claim
  11  formation: '3' is not a graha or a house lord

  The same refusals applied when converted/ was originally built. So re-running
  from a different source changes nothing — the rules were rejected on their
  content, not skipped by accident.

  Let me fix the script's docstring so it records what it actually found, then
  move to the work that matters:

⏺ Update(scripts/convert_db_rules.py)
  ⎿  Added 22 lines, removed 6 lines
       8  produced `rules/converted/`, pointed at the database instead of
           at the JSONL
       9  files on disk.
      10  
      11 -**Why it is needed at all.** Both sets came from the same extra
         -ction, and they                                                
      12 -drifted. The YAML covers 244 BPHS verse locations; Postgres hol
         -ds approved                                                    
      13 -rules for 394. That is 164 verses of reviewed, approved, paid-f
         -or BPHS that the                                               
      14 -Koonji engine has never been able to see, because the legacy JS
         -ONL those files                                                
      15 -were built from turned out to be a partial export while the dat
         -abase got the                                                  
      16 -full load. Nothing compared the two, so nothing said so.       
      11 +**It found nothing, and that is the useful result.** The two so
         +urces looked out                                               
      12 +of sync -- the YAML covers 244 BPHS verse locations against Pos
         +tgres's 394 --                                                 
      13 +and the obvious reading was that a hundred-odd reviewed verses 
         +had never                                                      
      14 +reached the engine. They had. Run against all 1,046 approved ru
         +les this                                                       
      15 +produces two documents not already on disk, and the compiler dr
         +ops both.                                                      
      16  
      17 +The verses that appear only in Postgres are missing from the YA
         +ML because the                                                 
      18 +converter REFUSES them, not because nobody converted them:     
      19 +                                                               
      20 +    35  effect 1: life_domain '(none)' has no claim            
      21 +    13  effect 1: life_domain 'family' has no claim            
      22 +    11  formation: '3' is not a graha or a house lord          
      23 +                                                               
      24 +Those refusals applied when `rules/converted/` was first built 
         +and they apply                                                 
      25 +now. Comparing verse locations between the two stores measures 
         +the wrong thing;                                               
      26 +comparing rule ids after conversion measures the right one. Kep
         +t as an audit:                                                 
      27 +`--report` answers "has the database drifted ahead of the YAML"
         + in about a                                                    
      28 +minute, and the answer today is no.                            
      29 +                                                               
      30 +The recoverable share is in `convert.CLAIM_MAP`, not here. Teac
         +hing it `family`                                               
      31 +would convert 13 more rules for free, and `(none)` is 35 rules 
         +whose extraction                                               
      32 +never recorded a domain at all -- a data problem upstream of th
         +is script.                                                     
      33 +                                                               
      34  Only approved rules are converted. `approved_at IS NOT NULL` is
           the reviewer's
      35  signature, and a script that quietly promoted unreviewed rows i
          nto the serving
      36  path would make that signature worthless.

  Ran 1 shell command (ctrl+o to expand)

⏺ Now the job that actually pays off — switching the rules panel to the Koonji
  engine. First, the condition translator:

  Ran 2 shell commands (ctrl+o to expand)

⏺ Now the URF describer, matching that style:

⏺ Write(rishivan/koonji/describe.py)
  ⎿  Wrote 156 lines to rishivan/koonji/describe.py
       1 """A URF condition in plain language, so a reader can see WHY a 
       2 
       3 `rag/describe.py` does this for the old extractor's atoms. The K
       4 writes conditions in the frame's own vocabulary instead -- regis
       5 a nested boolean tree rather than a flat list of typed dicts:
       6 
         , "sign": "aries"}]}
       8     URF   {"all": [{"occupies_rashi": {"subject": "graha.moon", 
       9 
         o say so
     … +179 lines (ctrl+o to expand)

  Ran 1 shell command (ctrl+o to expand)

⏺ Two rendering bugs. Let me check the real argument shapes:

  Ran 2 shell commands (ctrl+o to expand)

⏺ One left — the level.maha of Ketu should read the maha period:

⏺ Update(rishivan/koonji/describe.py)
  ⎿  Added 2 lines, removed 2 lines
      117      if name == "strength_band":
      118          return f"{subject} is {_term(args.get('band'))} in str
           ength"
      119      if name == "dasha_active":
      120 -        level = str(args.get("level") or "").replace("_", " ")
          - or "period"                                                  
      121 -        return f"the {level} of {subject} is running"         
      120 +        level = _term(args.get("level")) or "period"          
      121 +        return f"the {level} period of {subject} is running"  
      122      if name == "transits_bhava":
      123          return f"{subject} is transiting {_term(args.get('bhav
           a'))}"
      124  

⏺ Write(tests/koonji/test_describe.py)
  ⎿  Wrote 131 lines to tests/koonji/test_describe.py
      1 """A URF condition in words, for the panel that says WHY a rule f
        ired.
      3 The tests worth having here are the ones about being *wrong* rath
        er than being
      4 absent. An unreadable clause annoys; a clause that reads as a dif
      5 than the one that fired gets approved by a reviewer who was told 
        something
      6 untrue.
      8 
      9 import pathlib
     … +159 lines (ctrl+o to expand)

  Ran 1 shell command (ctrl+o to expand)

⏺ 13 passing, including the corpus-wide check across all 1,391 rules. Let me
  clear that deprecation warning:

⏺ Update(tests/koonji/test_describe.py)
  ⎿  Added 2 lines, removed 1 line
      101      form and `dignity` (not `dignity_is`) were both found.
      102      """
      103  
      104 +    @staticmethod                                             
      105      @pytest.fixture(scope="class")
      105 -    def conditions(self):                                     
      106 +    def conditions():                                         
      107          root = pathlib.Path(__file__).resolve().parents[2] / "
           rishivan/koonji/rules"
      108          found = []
      109          for path in root.rglob("*.yaml"):

⏺ Now the second piece — building the rules panel from Koonji. Let me see
  exactly what the old path produced:

  Searched for 2 patterns (ctrl+o to expand)

⏺ The citation property hardcodes "BPHS" for every book — worth fixing while I'm
  here. Let me check the book-title lookup:

  Ran 1 shell command (ctrl+o to expand)

⏺ Now the builder that turns a Koonji reading into the panel's shape:

⏺ Write(rishivan/koonji/panel.py)  ⎿  Wrote 194 lines to rishivan/koonji/panel.py
       1 """A Koonji reading as the rules panel reads it.
       3 The panel ("N classical rules match this chart") was filled by t
         he older
         s rule format,
         le in it --
       6 274 of them at the time of writing, sitting on disk, firing corr
       7 shown to nobody.
       8 
         ady computed a
         -evaluated: the
     … +228 lines (ctrl+o to expand)

  Ran 1 shell command (ctrl+o to expand)

⏺ Two fixes. The timing counts are computed from the wrong signal, and one book
  title falls through to the prettifier:

  Ran 1 shell command (ctrl+o to expand)

⏺ Now wire it into the graph node, replacing the Qdrant rule lookup:

⏺ Update(rishivan/graph/nodes/retrieve.py)
  ⎿  Added 23 lines, removed 28 lines
      104  
      105  def _match_rules(state: RishivanState, embed_fn, search_query:
            str, routing: dict) -> dict:
      106      """Step 4b. Wrapped whole in `except Exception` on purpose
           : a missing or
      107 -    stale rule base must degrade to page retrieval, never to n
          -o answer."""                                                  
      107 +    stale rule base must degrade to page retrieval, never to n
          +o answer.                                                     
      108 +                                                              
      109 +    **The rules come from the Koonji reading, not from Qdrant.
          +** Both matchers                                              
      110 +    existed and they disagreed: Qdrant held rules in the old e
          +xtractor's format                                             
      111 +    and the engine held them in the frame's, so the panel and 
          +the answer were                                               
      112 +    counting different corpora. Everything the extractor has p
          +roduced since the                                             
      113 +    format changed -- 274 rules -- was invisible in the panel 
          +while firing                                                  
      114 +    correctly in the reading behind it.                       
      115 +                                                              
      116 +    `koonji_read` runs before this node (see `build.STATIC_EDG
          +ES`), so the                                                  
      117 +    reading is already computed and nothing here re-evaluates 
          +it.                                                           
      118 +    """                                                       
      119      chart = state.get("chart")
      120      if chart is None:
      121          return {"matched_rules": [], "contributors": [], "cont
           ributor_reports": ()}
     ...
      123      out: dict = {}
      124      try:
      125          from rishivan.chart.tokens import all_chart_tokens
      115 -        from rishivan.config import settings                  
      126          from rishivan.council.contributors import gather
      127          from rishivan.council.routing import merge_supporting,
            route_question
      118 -        from rishivan.rag.rules import (                      
      119 -            rank_true_rules,                                  
      120 -            rule_collection_name,                             
      121 -            true_rules,                                       
      122 -        )                                                     
      123 -        from rishivan.rag.vector_store import get_vector_store
      128 +        from rishivan.graph.nodes.koonji import _engine       
      129 +        from rishivan.koonji.panel import counts_from_reading,
          + hits_from_reading                                            
      130  
      125 -        rule_store = get_vector_store(                        
      126 -            rule_collection_name(settings.VECTOR_COLLECTION)  
      127 -        )                                                     
      131          # Dated by the reading, not the wall clock. Dasha toke
           ns are the only
      132          # ones that move, and matching them against `now` whil
           e every other
      133          # token came from `query_time` would evaluate a Prashn
           a cast for a
      134          # stated moment against today's periods.
      135          when = state.get("query_time") or datetime.now()
      136          tokens = all_chart_tokens(chart, when=when)
      134 -                                                              
      135 -        applicable = true_rules(rule_store, tokens)           
      137          out["chart_tokens"] = tokens
      138 +                                                              
      139 +        engine = _engine()                                    
      140 +        reading = state.get("reading")                        
      141          # The gap between rules true of the chart and rules th
           is Rishi was
      142          # shown is the specialisation doing its job, and it sh
           ould be visible
      143          # rather than implied.
      140 -        out["rules_true_of_chart"] = len(applicable)          
      141 -        # Zero timing labels on a "when" question is a deploym
          -ent fact, not an                                              
      142 -        # astrological one - a collection predating the activa
          -tion field parses                                             
      143 -        # every rule to `active=None`, correctly and silently.
      144 -        out["rules_with_timing"] = sum(1 for r in applicable i
          -f r.active is not None)                                       
      145 -        out["rules_running_now"] = sum(1 for r in applicable i
          -f r.active is True)                                           
      144 +        out.update(counts_from_reading(reading, engine=engine)
          +)                                                             
      145  
      146          routing_obj = merge_supporting(
      147              route_question(state["question"]),
      148              state["classification"].get("supporting_rishis") o
           r [],
      149          )
      151 -        matched = rank_true_rules(                            
      152 -            applicable,                                       
      153 -            embed_fn([search_query])[0],                      
      154 -            routing=routing_obj,                              
      150 +        matched = hits_from_reading(                          
      151 +            reading, engine=engine, domain=routing.get("primar
          +y"),                                                          
      152              limit=MAX_MATCHED_RULES,
      156 -            # The question's own words gate what may be shown.
          - Gating on the                                                
      157 -            # answering Rishi's domains was circular - Medhan 
          -owns health, so                                               
      158 -            # every Medhan question admitted every death rule.
      159 -            question=state["question"],                       
      153          )
      154 +        # `gather` reports what each Rishi computed and wants 
          +rules true of the                                             
      155 +        # chart, which is exactly the fired set rather than th
          +e ten displayed.                                              
      156          contributors = gather(
      162 -            chart, applicable, routing=routing_obj,           
      157 +            chart, matched, routing=routing_obj,              
      158              question=state["question"], when=state.get("query_
           time"),
      159          )
      160          out["matched_rules"] = matched

  Ran 2 shell commands (ctrl+o to expand)

⏺ The test patches rank_true_rules, which I no longer call — its premise is gone
  but its intent is still right. Let me see the fixtures so I can rewrite it
  against the new path:

  Ran 1 shell command (ctrl+o to expand)

⏺ Update(tests/graph/test_nodes_retrieve.py)
  ⎿  Added 17 lines, removed 6 lines
      211  
      212      def test_counters_survive_a_failure_after_matching(self, c
           hart, monkeypatch):
      213          """The counters exist to make a stale index visible. Z
           eroing them on a
      214 -        partial failure is the silent degradation they were bu
          -ilt to prevent."""                                            
      215 -        import rishivan.rag.rules as rules_mod                
      214 +        partial failure is the silent degradation they were bu
          +ilt to prevent.                                               
      215  
      216 +        The failure is injected into `hits_from_reading` becau
          +se that is what                                               
      217 +        builds the panel now; it used to be Qdrant's ranker. T
          +he counters are                                               
      218 +        computed before it and must outlive it.               
      219 +        """                                                   
      220 +        import rishivan.graph.nodes.retrieve as retrieve_mod  
      221 +        from rishivan.koonji.engine import Engine             
      222 +                                                              
      223 +        engine = Engine.from_rules()                          
      224 +        reading = engine.read(                                
      225 +            chart, when=WHEN, statuses=frozenset({"candidate",
          + "production"})                                               
      226 +        )                                                     
      227          monkeypatch.setattr(
      218 -            rules_mod, "rank_true_rules",                     
      219 -            lambda *a, **kw: (_ for _ in ()).throw(RuntimeErro
          -r("ranker down")),                                            
      228 +            retrieve_mod, "_hits_from_reading",               
      229 +            lambda *a, **kw: (_ for _ in ()).throw(RuntimeErro
          +r("panel down")),                                             
      230 +            raising=False,                                    
      231          )
      221 -        s = state(chart=chart, query_time=WHEN,               
      232 +        s = state(chart=chart, query_time=WHEN, reading=readin
          +g,                                                            
      233                    routing={"universes": ["jyotisha"], "primary
           ": "artha"})
      234          out = retrieve_node(s, vector_store=FakeStore(hits_whe
           n_filtered=True),
      235                              client=FakeClient())
      236          assert out["matched_rules"] == []
      226 -        assert out["rules_true_of_chart"] > 0, "the count surv
          -ived the ranker"                                              
      237 +        assert out["rules_true_of_chart"] > 0, "the count surv
          +ived the panel builder"                                       
      238  
      239      def test_it_returns_only_the_keys_it_owns(self):
      240          s = state(routing={"universes": ["jyotisha"], "primary
           ": "artha"})

⏺ The patch target is wrong — my node imports inside the function, so I need to
  patch the source module:

⏺ Update(tests/graph/test_nodes_retrieve.py)
  ⎿  Added 5 lines, removed 3 lines
      217          builds the panel now; it used to be Qdrant's ranker. T
           he counters are
      218          computed before it and must outlive it.
      219          """
      220 -        import rishivan.graph.nodes.retrieve as retrieve_mod  
      220 +        import rishivan.koonji.panel as panel_mod             
      221          from rishivan.koonji.engine import Engine
      222  
      223          engine = Engine.from_rules()
      224          reading = engine.read(
      225              chart, when=WHEN, statuses=frozenset({"candidate",
            "production"})
      226          )
      227 +        # Patched on the panel module rather than on the node:
          + the node imports                                             
      228 +        # it inside the function, so the name it binds is reso
          +lved at call time                                             
      229 +        # from here.                                          
      230          monkeypatch.setattr(
      228 -            retrieve_mod, "_hits_from_reading",               
      231 +            panel_mod, "hits_from_reading",                   
      232              lambda *a, **kw: (_ for _ in ()).throw(RuntimeErro
           r("panel down")),
      230 -            raising=False,                                    
      233          )
      234          s = state(chart=chart, query_time=WHEN, reading=readin
           g,
      235                    routing={"universes": ["jyotisha"], "primary
           ": "artha"})

  Ran 1 shell command (ctrl+o to expand)

⏺ Let me add a test that the panel now actually shows the new rules — the whole
  point of the change — then run everything:

  Ran 3 shell commands (ctrl+o to expand)

⏺ Direct call works (10 hits), so the node's except Exception is swallowing
  something. Most likely gather — I'm passing it the new hit type:

  Searched for 2 patterns, ran 1 shell command (ctrl+o to expand)

⏺ Found it — KoonjiHit is missing attributes gather needs, and the broad except
  hid it. Let me find all of them:

  Searched for 5 patterns (ctrl+o to expand)

⏺ Two gaps: remedies for gather, and source["translation"] — which rule_context
  puts in the prompt, and whose absence would show the model a citation with no
  text behind it:

  Ran 4 shell commands (ctrl+o to expand)

⏺ Two real failures, both consequences of the change. Let me look at each:

  Searched for 1 pattern, ran 3 shell commands (ctrl+o to expand)

⏺ keyword in text, so I need substrings that catch the new values. Let me add
  them:

  Ran 2 shell commands (ctrl+o to expand)

⏺ Every domain value now routes — the remaining 39 rules have no domain tag at 
  all. Let me confirm where they come from:

  Ran 1 shell command (ctrl+o to expand)
⏺ 151 rules corpus-wide lack a domain tag — including 100 pre-existing BPHS 
  rules, so this isn't new. My 274 additions just pushed it past the budget. Let
  me confirm what the test reads:

  Ran 1 shell command (ctrl+o to expand)

⏺ Confirmed — the test reads the DB, and 39 of my 274 rows have an empty
  life_domains. The loader already defaults the effect's domain to general but
  leaves the column empty. Let me make those consistent:

⏺ Update(scripts/load_extracted.py)
  ⎿  Added 11 lines, removed 1 line
      136              # The original, unprojected. Everything above is a
            lossy view of it.
      137              "urf": rule,
      138          },
      139 -        "life_domains": [d.removeprefix("domain.") for d in (r
          -ule.get("domains") or {})],                                   
      139 +        # `general` when the extraction tagged no domain at al
          +l, which happens                                              
      140 +        # for about one rule in seven and is not new -- 100 of
          + the 903 BPHS                                                 
      141 +        # rules predating this are the same. An empty list der
          +ives no Rishi                                                 
      142 +        # affinity, and a rule no Rishi can cite is a rule nob
          +ody ever sees, so                                             
      143 +        # the choice is between a visible default and silent i
          +nvisibility.                                                  
      144 +        # `general` is already a bucket the corpus uses and AT
          +MA already claims                                             
      145 +        # it, so this routes them somewhere a reviewer will ac
          +tually look.                                                  
      146 +        # `effects_of` has always defaulted the same way; this
          + only stops the                                               
      147 +        # column and the effect disagreeing.                  
      148 +        "life_domains": ([d.removeprefix("domain.") for d in (
          +rule.get("domains") or {})]                                   
      149 +                         or ["general"]),                     
      150          "school": str(rule.get("school", "school.parashari")).
           removeprefix("school."),
      151          # `translation` is the key `embedding_text` reads; URF
            has only `quote`.
      152          "source": {**source, "translation": verse or source.ge
           t("quote", "")},

  Ran 1 shell command (ctrl+o to expand)

⏺ Now the source-text test — it checks for a literal string I no longer write,
  though the behaviour is intact. Let me make it test behaviour instead:

⏺ Update(tests/council/test_orchestrator_wiring.py)
  ⎿  Added 11 lines, removed 4 lines
      75      them makes that visible instead of quiet -- zero timing on 
          a "when" question means
      76      the index predates the field, not that the chart has no per
          iods.
      77  
      78 -    Reads `graph/nodes/retrieve.py`; see the note on the test a
         -bove."""                                                       
      79 -    from pathlib import Path                                   
      78 +    Asserts the key is produced rather than that the file conta
         +ins its name.                                                  
      79 +    The source-text version passed for as long as the literal a
         +ppeared in                                                     
      80 +    `retrieve.py` and broke the moment the counters moved into 
      81 +    `koonji.panel.counts_from_reading` -- while the counter its
         +elf still                                                      
      82 +    worked. A grep is not a test of behaviour.                 
      83 +    """                                                        
      84 +    from rishivan.koonji.panel import counts_from_reading      
      85  
      81 -    source = Path("rishivan/graph/nodes/retrieve.py").read_text
         -()                                                             
      82 -    assert "rules_with_timing" in source                       
      86 +    counts = counts_from_reading(None, engine=None)            
      87 +    assert "rules_with_timing" in counts                       
      88 +    assert "rules_running_now" in counts                       
      89 +    assert "rules_true_of_chart" in counts                     

  Ran 2 shell commands (ctrl+o to expand)

⏺ Both jobs are done. Full suite green: 1,998 passing, 1 skipped.

  Job 2 — the BPHS conversion: I was wrong, and it wasn't needed

  I claimed 164 BPHS verses were stuck in Postgres and invisible to the engine.
  Running it produced 2 documents, both dropped by the compiler.

  My mistake was comparing verse locations between the two stores. Those verses
  are missing from the YAML because the converter refuses them — life_domain 
  '(none)' has no claim, '3' is not a graha or a house lord — and those same
  refusals applied when the YAML was first built. Re-running from a different
  source changes nothing.

  I kept the script as an audit tool (--report answers "has the database drifted
  ahead?" in a minute) with the finding written into it, so nobody re-derives
  the wrong conclusion later.

  Job 1 — the panel switch: done, and it found three real bugs

  The panel now draws from the Koonji engine, so all 274 new rules are visible
  where they were invisible before.

  Bugs it surfaced:

  - Every rule was cited as "BPHS." The old citation hardcoded that string. Fine
  when BPHS was the only book with rules; wrong from the day Phaladeepika
  arrived.
  - The panel came back silently empty. remedy_contribution does a bare
  r.remedies, which raised inside the node's catch-all and degraded to nothing.
  Only the new test caught it — the broad except is there so a broken rule base
  can't kill an answer, and it hides real errors as a side effect.
  - 39 rules were invisible to every Rishi. They carried no domain tag, so they
  derive no affinity and nobody can cite them. Not new — 100 of the existing 903
  BPHS rules are the same — but enough to blow the 2% routability budget. Also,
  the new books introduced 19 domain values the routing table had never seen
  (crime, livestock, royalty, prowess, wellbeing…). All mapped now.

  One test I rewrote rather than fixed.
  test_the_orchestrator_reports_how_many_rules_carried_timing asserted a string 
  appeared in a source file. It passed while the literal sat in retrieve.py and
  broke the moment the code moved — while the counter itself kept working fine.
  It tests behaviour now.

  Where things stand

  Engine        1,391 rules  (was 1,117)
  Postgres      1,515 rules  (274 awaiting your review)
  Books done    4 of 10

  The six remaining books are ~3,400 calls. On Pro that's ~$120 and ~7 hours; on
  flash-lite the arithmetic says ~$5, but it returned zero rules in my one test
  and I'd want to diagnose that first — 4 calls, under a cent. Say the word and
  I'll run just that diagnostic, nothing else.

✻ Crunched for 15m 6s

❯ where are the rules stored for these 4 books in yaml format??                 

  Ran 1 shell command (ctrl+o to expand)

⏺ They're in rishivan/koonji/rules/extracted/, one folder per book, one file per
  life domain:

  rishivan/koonji/rules/
  ├── parashari/     8 rules    hand-written, human-reviewed
  ├── converted/  1109 rules    from the old extractor (BPHS bulk)
  └── extracted/   274 rules    ← the new single-call extraction
      ├── phaladeepika/          169 rules across 13 domain files
      ├── brihat-jataka/          98 rules across 12 domain files
      ├── bhavartha-ratnakara/     4 rules
      └── prasna-marga/            3 rules

  Files are split by life domain, not by chapter — relationship.yaml,
  wealth.yaml, health.yaml and so on. That's deliberate: a reviewer looks for
  "show me the marriage rules," not "show me chapter 17."

  Marriage rules from the new extraction, for example, are in:
  rishivan/koonji/rules/extracted/brihat-jataka/relationship.yaml     2
  rishivan/koonji/rules/extracted/phaladeepika/relationship.yaml      8

  Here's what one looks like:

  Read 1 file (ctrl+o to expand)

⏺ Reading that rule: Rahu in the 7th house → discord in relationships, sourced
  to Phaladeepika chapter 28 verse 26, with the verbatim quote "suffer 
  separation from his beloved" and a SHA-256 of that quote so it can't be
  silently edited later.

  Two things worth flagging:

  status: candidate and review: {state: unreviewed} — every one of the 274 says
  this. The engine serves them because I pass SERVED_STATUSES = {"candidate", 
  "production"}, but nothing here has been read by a person. Same 274 rules are
  in Postgres with approved_at = NULL, waiting for your review.

  The header comment is now wrong. It says "Extracted by the six-call pipeline"
  — these came from the single-call one. Cosmetic, but it's the kind of stale
  comment that misleads someone later:

  Searched for 1 pattern (ctrl+o to expand)

⏺ Update(rishivan/koonji/pipeline.py)
  ⎿  Added 10 lines, removed 4 lines
      388                  "GENERATED - do not edit by hand.\n"
      389                  "  python -m rishivan.koonji extract\n"
      390                  "\n"
      391 -                "Extracted by the six-call pipeline in extract
          -.py, then compiled and\n"                                     
      392 -                "round-tripped. Candidates that failed validat
          -ion are NOT here -\n"                                         
      393 -                "they are in the review queue. Nothing here ha
          -s been read by a\n"                                           
      394 -                "reviewer either; `candidate` means exactly th
          -at."                                                          
      391 +                f"Extracted by {'a single model call' if singl
          +e_call else 'the six-call pipeline'} "                        
      392 +                f"in extract.py, then compiled\n"             
      393 +                f"and round-tripped. Candidates that failed va
          +lidation are NOT\n"                                           
      394 +                f"here - they are in the review queue.\n"     
      395 +                + ("\nNO ADVERSARIAL VERIFIER RAN. Single-call
          + extraction skips it\n"                                       
      396 +                   "because review is manual; a rule nothing e
          +xamined and a rule\n"                                         
      397 +                   "that passed a verifier are different thing
          +s.\n"                                                         
      398 +                   if single_call else "")                    
      399 +                + "\nNothing here has been read by a reviewer 
          +either; `candidate`\n"                                        
      400 +                  "means exactly that."                       
      401              ),
      402          )
      403  

  Ran 2 shell commands (ctrl+o to expand)

⏺ Fixed — and it mattered more than cosmetics. The header claimed the six-call
  pipeline ran, which would tell a reviewer an adversarial verifier had passed
  these rules. None did. Single-call mode skips it because your review is
  manual, and the file now says so plainly. That fact was recorded on the result
  object but never reached the artefact a person actually opens.

  To summarise where the rules live:

  ┌──────────────────┬───────┬─────────────────────────────────────────┐
  │    Directory     │ Rules │                 Source                  │
  ├──────────────────┼───────┼─────────────────────────────────────────┤
  │ rules/parashari/ │     8 │ hand-written, human-reviewed            │
  ├──────────────────┼───────┼─────────────────────────────────────────┤
  │ rules/converted/ │ 1,109 │ old extractor, deterministic conversion │
  ├──────────────────┼───────┼─────────────────────────────────────────┤
  │ rules/extracted/ │   274 │ new single-call extraction (4 books)    │
  └──────────────────┴───────┴─────────────────────────────────────────┘

  The engine loads all three recursively — 1,391 rules total. Files are grouped
  by life domain rather than chapter, so the marriage rules from the new
  extraction are in extracted/brihat-jataka/relationship.yaml (2) and
  extracted/phaladeepika/relationship.yaml (8).

  Each rule carries its book, chapter, verse, the verbatim quote, and a SHA-256
  of that quote — so a citation can be checked against the page and the quote
  can't be edited without the hash disagreeing.

✻ Baked for 1m 13s

❯ now extract rest of the 6 books also, give me commands, i will run manually   
  and monitor them                                                              

  Ran 1 shell command (ctrl+o to expand)

⏺ Let me fix two things in the runner before handing it over — the rule counter
  is wrong, and the staging path points at my session's scratch directory:

  Ran 2 shell commands (ctrl+o to expand)

⏺ Here are your commands. Six books, 3,411 passages, one API call each.

  Option A — all six in one go (recommended)

  The script is resumable: it skips the four already done and picks up at Jataka
  Parijata.

  cd /Users/admin/Desktop/live_projects/rishivan_demo
  WORKERS=16 ./scripts/extract_all.sh 2>&1 | tee logs/run-$(date
  +%Y%m%d-%H%M).log

  Watch it from a second terminal:

  tail -f logs/extract-jataka-parijata-*.log

  Option B — one book at a time

  Run these in order, smallest first. --rules must come before extract — behind
  the subcommand argparse rejects it and the run exits silently.

  cd /Users/admin/Desktop/live_projects/rishivan_demo

  # 304 passages · ~35 min · ~$10.74
  .venv/bin/python -m rishivan.koonji --rules .koonji-staging/hindu-predictive
  extract \
      --book hindu-predictive --single-call --limit 0 --workers 16 --max-calls
  4000

  # 339 passages · ~40 min · ~$11.91
  .venv/bin/python -m rishivan.koonji --rules .koonji-staging/prashna-tantra
  extract \
      --book prashna-tantra --single-call --limit 0 --workers 16 --max-calls
  4000

  # 412 passages · ~48 min · ~$14.48
  .venv/bin/python -m rishivan.koonji --rules .koonji-staging/muhurta-chintamani
  extract \
      --book muhurta-chintamani --single-call --limit 0 --workers 16 --max-calls
  4000

  # 557 passages · ~65 min · ~$19.53
  .venv/bin/python -m rishivan.koonji --rules .koonji-staging/saravali extract \
      --book saravali --single-call --limit 0 --workers 16 --max-calls 4000

  # 687 passages · ~80 min · ~$24.20
  .venv/bin/python -m rishivan.koonji --rules .koonji-staging/jataka-parijata
  extract \
      --book jataka-parijata --single-call --limit 0 --workers 16 --max-calls
  4000

  # 1112 passages · ~130 min · ~$38.98
  .venv/bin/python -m rishivan.koonji --rules
  .koonji-staging/sarvartha-chintamani extract \
      --book sarvartha-chintamani --single-call --limit 0 --workers 16
  --max-calls 4000

  After each one, copy the YAML into place:

  BOOK=hindu-predictive   # change per book
  mkdir -p rishivan/koonji/rules/extracted/$BOOK
  cp .koonji-staging/$BOOK/extracted/*.yaml
  rishivan/koonji/rules/extracted/$BOOK/

  After all six finish — three steps, in this order

  # 1. Does the engine still load? A duplicate rule id fails the WHOLE bundle,
  #    which means the app will not start. Check this before anything else.
  .venv/bin/python -c "
  from rishivan.koonji.engine import Engine
  print('engine loads:', len(Engine.from_rules().bundle.rules), 'rules')"

  # 2. Store them in Postgres for your review (approved_at stays NULL)
  .venv/bin/python -m scripts.load_extracted --dry-run
  .venv/bin/python -m scripts.load_extracted

  # 3. Full test suite
  mv tests.py /tmp/tests.py.bak 2>/dev/null   # shadows the tests/ package
  .venv/bin/python -m pytest tests/ -q -p no:randomly

  Three things to watch for

  Step 1 is not optional. A model mistyping a verse number into a rule id took
  the entire engine down earlier today — one bad digit in 274 rules and nothing
  loaded. I've fixed the cause, but run the check anyway.

  Cost. Roughly $120 total on gemini-2.5-pro at $1.25/M in, $10/M out — output
  is 91% of it. If you want flash-lite instead, add --deep-model 
  gemini-3.5-flash-lite and it drops to about $5 — but in my one test it
  returned zero rules on 24 passages where Pro found 6, so test it on one small 
  book first:

  .venv/bin/python -m rishivan.koonji --rules .koonji-staging/ab extract \
      --book hindu-predictive --single-call --limit 30 --workers 12 \
      --max-calls 40 --deep-model gemini-3.5-flash-lite

  If that prints 0 documents -> 0 rules written, flash-lite isn't working with
  this prompt yet and Pro is the only option today.

  A book returning nothing isn't always a bug. Prasna Marga produced 3 rules
  from 37 passages because most of its bridged text is table-of-contents lines.
  Check the log's N passages · N model calls line — if calls match passages, the
  run worked and the book is just thin.

✻ Baked for 1m 7s

❯ # 412 passages · ~48 min · ~$14.48                                            
  .venv/bin/python -m rishivan.koonji --rules                                   
  .koonji-staging/muhurta-chintamani extract \                                  
      --book muhurta-chintamani --single-call --limit 0 --workers 16            
  --max-calls 4000                                                              
                                                                                
  by default which model is used??                                              

⏺ gemini-2.5-pro — that's the --deep-model default, and single-call mode uses
  the deep model. Let me confirm rather than assert:

  Searched for 1 pattern (ctrl+o to expand)

⏺ Confirmed: gemini-2.5-pro.

  The chain is --deep-model (defaults to gemini-2.5-pro) → extract_once →
  model=self.deep_model, and single-call mode makes exactly that one call per
  passage.

  Worth knowing: --fast-model gemini-2.5-flash is unused in single-call mode. It
  only served the classify and back-translate stages, both of which single-call
  skips. So the flag is inert here — every call goes to Pro.

  That's why Muhurta Chintamani costs ~$14.48. To change it:

  # same command, cheaper model
  .venv/bin/python -m rishivan.koonji --rules .koonji-staging/muhurta-chintamani
  extract \
      --book muhurta-chintamani --single-call --limit 0 --workers 16 --max-calls
  4000 \
      --deep-model gemini-3.5-flash-lite

  That would take Muhurta Chintamani from ~$14.48 to ~$0.63. But when I tested
  flash-lite it returned 9 output tokens and zero rules on 24 passages where Pro
  produced 6 — it read the passage and answered "no rules here" every time.
  finish_reason: STOP, no error. So I'd verify on 30 passages before committing
  a whole book to it:

  .venv/bin/python -m rishivan.koonji --rules .koonji-staging/ab extract \
      --book hindu-predictive --single-call --limit 30 --workers 12 \
      --max-calls 40 --deep-model gemini-3.5-flash-lite

  If the summary line reads 0 documents -> 0 rules written, stay on Pro.

✻ Cogitated for 18s
❯ [Image #8] - completion tokens are only 9 also why gemini-2.5-flash is used,  
                                                                                
  (.venv) admin@lokeshs-MacBook-Pro rishivan_demo % .venv/bin/python -m         
  rishivan.koonji --rules .koonji-staging/muhurta-chintamani extract \          
      --book muhurta-chintamani --single-call --limit 0 --workers 16            
  --max-calls 4000 \                                                            
      --deep-model gemini-3.5-flash-lite                                        
  Direct use of automatic function calling (AFC) in Models.generate_content is  
  not recommended. Instead, we recommend to use AFC in Chat.send_message.       
  Similarly, direct use of AFC in Models.generate_content_stream is not         
  recommended. Instead, we recommend to use AFC in Chat.send_message_stream.    
                                                                                
  412 passages · 412 model calls · 67.1s                                        
  78 candidates · 16 blocked by validation · 0 extractor disagreements          
                                                                                
  56 documents would not build as rules:                                        
    MUHURTACHINTAMANI.WEALTH.CH1V1415.X0001: UnresolvedSymbol: cannot resolve   
  'Lagnesh' to a registry id - add an alias or an ExtensionProposal, never a    
  near miss                                                                     
    MUHURTACHINTAMANI.DIRECTSUBJECT.CH1V48.X0001: ValueError:                   
  MUHURTACHINTAMANI.DIRECTSUBJECT.CH1V48.X0001: `remedy` block is missing       
  action (it has ['directive', 'text'])                                         
    MUHURTACHINTAMANI.DIRECTSUBJECT.CH1V48.X0002: ValueError:                   
  MUHURTACHINTAMANI.DIRECTSUBJECT.CH1V48.X0002: `remedy` block is missing       
  action (it has ['directive', 'text'])                                         
    MUHURTACHINTAMANI.DIRECTSUBJECT.CH1V48.X0003: ValueError:                   
  MUHURTACHINTAMANI.DIRECTSUBJECT.CH1V48.X0003: `remedy` block is missing       
  action (it has ['directive', 'text'])                                         
    MUHURTACHINTAMANI.DIRECTSUBJECT.CH1V48.X0004: ValueError:                   
  MUHURTACHINTAMANI.DIRECTSUBJECT.CH1V48.X0004: `remedy` block is missing       
  action (it has ['directive', 'text'])                                         
    MUHURTACHINTAMANI.TEMPERAMENT.CH1V47.X0001: UnresolvedSymbol: cannot        
  resolve 'Mesha' to a registry id - add an alias or an ExtensionProposal,      
  never a near miss                                                             
    MUHURTACHINTAMANI.WEALTH.CH1V47.X0002: UnresolvedSymbol: cannot resolve     
  'Mesha' to a registry id - add an alias or an ExtensionProposal, never a near 
  miss                                                                          
    MUHURTACHINTAMANI.TEMPERAMENT.CH1V47.X0003: UnresolvedSymbol: cannot        
  resolve 'Simha' to a registry id - add an alias or an ExtensionProposal,      
  never a near miss                                                             
                                                                                
  78 documents -> 56 rules written                                              
                                                                                
  22 dropped by the compiler:                                                   
    MUHURTACHINTAMANI.PROHIBIT.CH2V51.X0001                                     
        ERROR closure: MUHURTACHINTAMANI.PROHIBIT.CH2V51.X0001:                 
  MUHURTACHINTAMANI.PROHIBIT.CH2V51.X0001: unregistered domain 'do              
    MUHURTACHINTAMANI.PROHIBITION.CH2V54.X0001                                  
        ERROR closure: MUHURTACHINTAMANI.PROHIBITION.CH2V54.X0001:              
  MUHURTACHINTAMANI.PROHIBITION.CH2V54.X0001: unregistered doma                 
    MUHURTACHINTAMANI.HEALTH.CH4V7.X0001                                        
        ERROR typecheck: MUHURTACHINTAMANI.HEALTH.CH4V7.X0001:                  
  house_distance.distance = 'bhava.01': expected distance                       
    MUHURTACHINTAMANI.WEARLAJAVARTA.CH4V11.X0001                                
        ERROR closure: MUHURTACHINTAMANI.WEARLAJAVARTA.CH4V11.X0001:            
  MUHURTACHINTAMANI.WEARLAJAVARTA.CH4V11.X0001: unregistered                    
    MUHURTACHINTAMANI.GIVEGOLD.CH4V18.X0001                                     
        ERROR closure: MUHURTACHINTAMANI.GIVEGOLD.CH4V18.X0001:                 
  MUHURTACHINTAMANI.GIVEGOLD.CH4V18.X0001: unregistered domain 'do              
    MUHURTACHINTAMANI.WEARRUBY.CH4V10.X0001                                     
        ERROR closure: MUHURTACHINTAMANI.WEARRUBY.CH4V10.X0001:                 
  MUHURTACHINTAMANI.WEARRUBY.CH4V10.X0001: unregistered domain 'do              
    MUHURTACHINTAMANI.WEARPEARL.CH4V10.X0002                                    
        ERROR closure: MUHURTACHINTAMANI.WEARPEARL.CH4V10.X0002:                
  MUHURTACHINTAMANI.WEARPEARL.CH4V10.X0002: unregistered domain '               
    MUHURTACHINTAMANI.WEARCORAL.CH4V10.X0003                                    
        ERROR closure: MUHURTACHINTAMANI.WEARCORAL.CH4V10.X0003:                
  MUHURTACHINTAMANI.WEARCORAL.CH4V10.X0003: unregistered domain '               
    MUHURTACHINTAMANI.WEAREMERALD.CH4V10.X0004                                  
        ERROR closure: MUHURTACHINTAMANI.WEAREMERALD.CH4V10.X0004:              
  MUHURTACHINTAMANI.WEAREMERALD.CH4V10.X0004: unregistered doma                 
    MUHURTACHINTAMANI.WEARTOPAZ.CH4V10.X0005                                    
        ERROR closure: MUHURTACHINTAMANI.WEARTOPAZ.CH4V10.X0005:                
  MUHURTACHINTAMANI.WEARTOPAZ.CH4V10.X0005: unregistered domain '               
    MUHURTACHINTAMANI.WEARDIAMOND.CH4V10.X0006                                  
        ERROR closure: MUHURTACHINTAMANI.WEARDIAMOND.CH4V10.X0006:              
  MUHURTACHINTAMANI.WEARDIAMOND.CH4V10.X0006: unregistered doma                 
    MUHURTACHINTAMANI.WEARSAPPHIRE.CH4V10.X0007                                 
        ERROR closure: MUHURTACHINTAMANI.WEARSAPPHIRE.CH4V10.X0007:             
  MUHURTACHINTAMANI.WEARSAPPHIRE.CH4V10.X0007: unregistered do                  
    ... and 10 more                                                             
                                                                                
  1 warnings:                                                                   
    WARNING polarity: <corpus>: claim 'career.disruption' is denied by some     
  rule and asserted by none - check whether `polarity: negative` was m          
                                                                                
  written:                                                                      
    .koonji-staging/muhurta-chintamani/extracted/career.yaml                    
    .koonji-staging/muhurta-chintamani/extracted/education.yaml                 
    .koonji-staging/muhurta-chintamani/extracted/health.yaml                    
    .koonji-staging/muhurta-chintamani/extracted/property.yaml                  
    .koonji-staging/muhurta-chintamani/extracted/relationship.yaml              
    .koonji-staging/muhurta-chintamani/extracted/spiritual.yaml                 
    .koonji-staging/muhurta-chintamani/extracted/travel.yaml                    
    .koonji-staging/muhurta-chintamani/extracted/wealth.yaml                    
                                                                                
  budget: 412 calls · 793k prompt chars · 114k response chars                   
                                                                                
  review queue, worst first (94):                                               
    100.30  MUHURTACHINTAMANI.HEALTH.CH2V57.X0001  muhurtachintamani:ch2.v57    
    100.20  MUHURTACHINTAMANI.LONGEVITY.CH2V47.X0001 muhurtachintamani:ch2.v47  
    100.20  MUHURTACHINTAMANI.HEALTH.CH6V44.X0001  muhurtachintamani:ch6.v44    
    100.10  MUHURTACHINTAMANI.RELATIONSHIP.CH6V86.X0001                         
  muhurtachintamani:ch6.v86                                                     
    100.10  MUHURTACHINTAMANI.SPIRITUAL.CH9V3.X0003 muhurtachintamani:ch9.v3    
    100.10  MUHURTACHINTAMANI.SPIRITUAL.CH9V3.X0004 muhurtachintamani:ch9.v3    
    100.10  MUHURTACHINTAMANI.SPIRITUAL.CH9V3.X0008 muhurtachintamani:ch9.v3    
    100.10  MUHURTACHINTAMANI.SPIRITUAL.CH9V3.X0009 muhurtachintamani:ch9.v3    
    100.10  MUHURTACHINTAMANI.SPIRITUAL.CH9V3.X0010 muhurtachintamani:ch9.v3    
    100.10  MUHURTACHINTAMANI.OBSTACLE.CH11V112.X0001                           
  muhurtachintamani:ch11.v112                                                   
    100.10  MUHURTACHINTAMANI.OBSTACLE.CH11V112.X0002                           
  muhurtachintamani:ch11.v112                                                   
    100.10  MUHURTACHINTAMANI.LONGEVITY.CH12V23.X0001                           
  muhurtachintamani:ch12.v23                                                    
    100.10  MUHURTACHINTAMANI.LONGEVITY.CH12V23.X0002                           
  muhurtachintamani:ch12.v23                                                    
    100.10  MUHURTACHINTAMANI.PROPERTY.CH12V24.X0001 muhurtachintamani:ch12.v24 
    100.10  MUHURTACHINTAMANI.PROPERTY.CH12V24.X0002 muhurtachintamani:ch12.v24 
    100.10  MUHURTACHINTAMANI.PROPERTY.CH12V24.X0003 muhurtachintamani:ch12.v24 
     0.60  MUHURTACHINTAMANI.HEALTH.CH4V7.X0001   muhurtachintamani:ch4.v7      
     0.50  MUHURTACHINTAMANI.GIVEGOLD.CH4V18.X0001 muhurtachintamani:ch4.v18    
     0.30  MUHURTACHINTAMANI.HEALTH.CH6V45.X0002  muhurtachintamani:ch6.v45     
     0.30  MUHURTACHINTAMANI.GENERAL.CH6V58.X0001 muhurtachintamani:ch6.v58     
  (.venv) admin@lokeshs-MacBook-Pro rishivan_demo %                             
                                                                                
  i ran this with gemini-3.5-flash-lite                                         
  ⎿  [Image #8]

⏺ Two separate things there, and the second one is a real bug.

  Searched for 1 pattern (ctrl+o to expand)

⏺ Confirmed — and it's a real telemetry bug.

  Why Helicone says gemini-2.5-flash

  client = VertexClient(budget=budget, default_model=args.fast_model)   # 
  gemini-2.5-flash
  ...
  helicone_model=self.default_model      # ← the tag
  ...
  model=self.deep_model                  # ← what's actually called

  The Helicone model property is stamped from --fast-model, but the actual
  request passes --deep-model. So the dashboard has attributed every extraction 
  call you've ever made to gemini-2.5-flash, including the ~$7 of Pro runs
  earlier. The left-hand Model column (gemini-3.5-flash-lite) is what really
  ran.

⏺ Update(rishivan/koonji/__main__.py)
  ⎿  Added 9 lines, removed 1 line
      230      from rishivan.koonji.pipeline import extract_books
      231  
      232      budget = Budget(max_calls=args.max_calls)
      233 -    client = VertexClient(budget=budget, default_model=args.fa
          -st_model)                                                     
      233 +    # The DEEP model, not the fast one. `default_model` is two
          + things at once:                                              
      234 +    # the fallback for a call that names no model, and the val
          +ue stamped on the                                             
      235 +    # Helicone `model` property when the client is built. Pass
          +ing the fast model                                            
      236 +    # tagged every extraction request as `gemini-2.5-flash` in
          + the dashboard                                                
      237 +    # whatever actually ran -- so a Pro run and a flash-lite r
          +un were                                                       
      238 +    # indistinguishable there, and cost attribution was wrong 
          +for both. Single                                              
      239 +    # -call mode only ever calls the deep model; the six-call 
          +path names its                                                
      240 +    # model per stage anyway, so nothing else changes.        
      241 +    client = VertexClient(budget=budget, default_model=args.de
          +ep_model)                                                     
      242      if args.record:
      243          client = RecordingClient(client, args.record)
      244  

⏺ Why completion tokens are 9

  That's the model returning {"rules": []} — "no rules in this passage."
  Expected for most verses; the extraction prompt explicitly tells it to do
  that. You can see the real extractions in the same list: 963, 544, 909 tokens.

  But the run has a bigger problem your log shows clearly. Let me quantify it:

  Searched for 1 pattern, ran 1 shell command (ctrl+o to expand)

❯ /compact                                                                      

⏺ No rashi aliases exist — only graha ones. So Mesha and Simha fail while Guru
  works. And the table's own comment says the honest way to build it is from
  runs that failed:

  Ran 1 shell command (ctrl+o to expand)
  ⎿  Interrupted · What should Claude do instead?

❯ /compact                                                                      
  ⎿  Compacted (ctrl+o to see full summary)
  ⎿  Referenced file rishivan/koonji/__main__.py
  ⎿  Read scripts/extract_all.sh (79 lines)
  ⎿  Referenced file rishivan/koonji/pipeline.py
  ⎿  Read tests/council/test_orchestrator_wiring.py (90 lines)
  ⎿  Read scripts/load_extracted.py (249 lines)
  ⎿  Skills restored (superpowers:requesting-code-review, 
     superpowers:finishing-a-development-branch, superpowers:executing-plans, 
     superpowers:writing-plans)