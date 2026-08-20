"""Rishivan — Council of Rishis · Streamlit POC UI."""

from __future__ import annotations

import datetime as dt

import streamlit as st
from markdown_it import MarkdownIt

from rishivan.config import settings
from rishivan.council.conversation import Conversation
from rishivan.council.personas import get_persona

_MD = MarkdownIt("commonmark", {"breaks": True, "html": False})
_MD.enable("table")


def _md(text: str) -> str:
    return _MD.render(text or "")


# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Rishivan · Council of Rishis",
    page_icon="🪐",
    layout="wide",
)

# ── CSS ──────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Cinzel:wght@400;500;600;700&family=Noto+Serif:ital,wght@0,400;1,400&display=swap');

/* Never style html/body: Streamlit sets overflow on them to drive scrolling,
   and background-attachment:fixed on the scroll container silently killed
   scrolling on newer Streamlit builds. The gradient goes on a fixed
   pseudo-element behind the app instead, which stays put without touching
   any scroll mechanics. */
[data-testid="stAppViewContainer"] {
    font-family: 'Inter', sans-serif;
    color: #ddd8f0;
}
[data-testid="stAppViewContainer"]::before {
    content: '';
    position: fixed;
    inset: 0;
    background: radial-gradient(circle at 50% 0%, #1b1035 0%, #060612 70%);
    pointer-events: none;
    z-index: -1;
}
/* Belt and braces: keep the main column scrollable whatever the version calls it. */
[data-testid="stAppViewContainer"], [data-testid="stMain"], section.main {
    overflow-y: auto !important;
    max-height: none !important;
}
[data-testid="stHeader"]  { background: transparent; }
[data-testid="stSidebarCollapsedControl"] { display: none; }
/* Streamlit's built-in RUNNING spinner / status widget */
[data-testid="stStatusWidget"] { display: none !important; }
.stSpinner { display: none !important; }
[data-testid="stSpinner"] { display: none !important; }

h1, h2, h3 { font-family:'Cinzel',serif !important; }
h1 { font-size:2.4rem !important; color:#e9d8fd; text-shadow: 0 0 20px rgba(196,162,248,0.3); }
h2 { font-size:1.1rem !important; color:#9fa6d2; font-weight:500; letter-spacing:3px; text-transform:uppercase; }
h3 { color:#c4b5fd; font-size:1.2rem !important; font-weight:600; }

/* Hero */
.hero { text-align:center; padding:50px 0 30px; position: relative; }
.hero-title { 
    font-family:'Cinzel',serif; font-size:3.5rem; font-weight:700;
    background:linear-gradient(135deg, #e9d5ff, #a78bfa, #818cf8); 
    -webkit-background-clip:text; -webkit-text-fill-color:transparent; 
    margin:0; letter-spacing: 2px;
    animation: titleGlow 4s ease-in-out infinite alternate;
}
@keyframes titleGlow {
    0% { filter: drop-shadow(0 0 10px rgba(167,139,250,0.2)); }
    100% { filter: drop-shadow(0 0 25px rgba(167,139,250,0.6)); }
}
.hero-sub { color:#8b8ba7; font-size:1rem; letter-spacing:4px; text-transform:uppercase; margin-top:8px; }
.hero-glow { 
    position:absolute; top:-50px; left:50%; transform:translateX(-50%);
    width:600px; height:300px;
    background:radial-gradient(circle, rgba(139,92,246,0.15) 0%, transparent 60%);
    pointer-events:none; z-index: -1;
}


/* Input Area (The Sanctum) */
.stTextArea textarea {
    background: rgba(10,10,25,0.6) !important; 
    border: 1px solid rgba(139,92,246,0.2) !important;
    color:#f3f0ff !important; border-radius:16px !important;
    font-size:1.1rem !important; font-family:'Noto Serif',serif !important;
    padding: 20px !important; transition:all .3s ease;
    box-shadow: inset 0 2px 10px rgba(0,0,0,0.5);
}
.stTextArea textarea:focus {
    border-color:#a78bfa !important;
    box-shadow: 0 0 30px rgba(139,92,246,0.2), inset 0 2px 10px rgba(0,0,0,0.5) !important;
}

/* Consult button */
.stButton > button {
    background:linear-gradient(135deg, #7c3aed, #4f46e5) !important;
    color:white !important; border:1px solid rgba(255,255,255,0.1) !important; 
    border-radius:14px !important; padding:14px 40px !important; 
    font-weight:600 !important; font-size:1.05rem !important; letter-spacing: 1px;
    transition:all .3s ease !important; 
    box-shadow:0 10px 30px rgba(124,58,237,.4), inset 0 1px 0 rgba(255,255,255,0.2) !important;
    text-transform: uppercase; font-family: 'Cinzel', serif !important;
}
.stButton > button:hover { 
    transform:translateY(-2px) scale(1.02) !important;
    box-shadow:0 15px 40px rgba(124,58,237,.6), inset 0 1px 0 rgba(255,255,255,0.3) !important; 
}

/* The Answer Card (Channelling) */
@keyframes etherealBreathe {
    0% { box-shadow: 0 10px 40px rgba(124,58,237,.1), inset 0 1px 0 rgba(255,255,255,.03); }
    50% { box-shadow: 0 15px 50px rgba(124,58,237,.25), inset 0 1px 0 rgba(255,255,255,.08); }
    100% { box-shadow: 0 10px 40px rgba(124,58,237,.1), inset 0 1px 0 rgba(255,255,255,.03); }
}
.answer-card {
    background:linear-gradient(160deg, rgba(20,20,45,0.8), rgba(10,10,25,0.95));
    backdrop-filter: blur(12px);
    border:1px solid rgba(124,58,237,.2); border-radius:24px;
    padding:40px 48px; margin:30px 0;
    position:relative; overflow:hidden;
    animation: etherealBreathe 6s infinite ease-in-out;
}
.answer-card::before {
    content:''; position:absolute; top:0;left:0;right:0; height:3px;
    background:linear-gradient(90deg, transparent, var(--ac,#a78bfa), transparent);
    opacity: 0.8;
}
.rishi-header { display:flex; align-items:center; gap:20px; margin-bottom:30px; border-bottom: 1px solid rgba(255,255,255,0.05); padding-bottom: 20px;}
.rishi-avatar { font-size:3rem; filter: drop-shadow(0 0 10px rgba(255,255,255,0.2)); }
.rishi-name-block .rn { font-family:'Cinzel',serif; font-size:1.6rem; color:#f5f3ff; font-weight: 600;}
.rishi-name-block .rt { font-size:.85rem; color:#a78bfa; letter-spacing:2px; text-transform:uppercase; margin-top: 4px;}
.answer-body { font-family:'Noto Serif',serif; font-size:1.1rem; line-height:2; color:#e2e0ed; }
.answer-body p { margin:0 0 18px; }
.answer-body h1,.answer-body h2,.answer-body h3 {
    font-family:'Cinzel',serif !important; color:#ddd6fe !important;
    font-size:1.2rem !important; margin:28px 0 12px !important;
}
.answer-body strong { color:#ffffff; font-weight: 600; }
.sign-off { margin-top:30px; padding-top:20px; border-top:1px solid rgba(255,255,255,0.05);
    font-family:'Cinzel',serif; font-size:.95rem; color:#8b8ba7; font-style:italic; text-align: right;}

/* Pipeline steps */
@keyframes pulseStep {
    0% { transform: scale(0.95); opacity: 0.7; box-shadow: 0 0 0 0 rgba(167,139,250, 0.4); }
    70% { transform: scale(1.05); opacity: 1; box-shadow: 0 0 0 10px rgba(167,139,250, 0); }
    100% { transform: scale(0.95); opacity: 0.7; box-shadow: 0 0 0 0 rgba(167,139,250, 0); }
}
.step { display:inline-flex; align-items:center; gap:8px;
    background:rgba(10,10,25,0.5); border:1px solid rgba(255,255,255,0.1); padding:8px 16px;
    border-radius:30px; font-size:.8rem; color:#6b7280; margin:0 8px 15px 0; 
    font-family: 'Cinzel', serif; letter-spacing: 1px;}
.step.active { border-color:#a78bfa; color:#ddd6fe; background: rgba(139,92,246,0.1); animation: pulseStep 2s infinite; }
.step.done   { border-color:#34d399; color:#6ee7b7; background: rgba(16,185,129,0.05);}

[data-testid="stExpander"] { background: rgba(20,20,35,0.4) !important; border:1px solid rgba(255,255,255,0.05) !important; border-radius:16px !important; }
[data-testid="stExpander"] summary { color:#a78bfa !important; font-size:.95rem; font-family: 'Cinzel', serif; }
</style>
""", unsafe_allow_html=True)


# ── Cached resources ─────────────────────────────────────────────────────────
@st.cache_resource(show_spinner=False)
def _get_vertex_client():
    from rishivan.council.client import get_vertex_client
    return get_vertex_client()


@st.cache_resource(show_spinner=False)
def _get_store():
    try:
        from rishivan.rag.vector_store import get_vector_store
        s = get_vector_store()
        return s if s.exists() else None
    except Exception:
        return None


# ── Configuration check ──────────────────────────────────────────────────────
# Fail loudly and legibly here rather than deep inside the pipeline: a missing
# secret is the most likely thing to go wrong on a fresh deployment.
_missing = settings.missing()
if _missing:
    st.error(
        "**Configuration incomplete.** Add the following to "
        "`.streamlit/secrets.toml` (locally) or to *Settings → Secrets* in "
        "Streamlit Cloud:\n\n" + "\n".join(f"- `{name}`" for name in _missing)
    )
    st.caption("See `.streamlit/secrets.toml.example` for the expected shape.")
    st.stop()


# ── Session state defaults ───────────────────────────────────────────────────
for k, v in [
    ("history", []),
    ("prefill", ""),
    ("conversation", Conversation()),
]:
    if k not in st.session_state:
        st.session_state[k] = v


# ── Hero ─────────────────────────────────────────────────────────────────────
st.markdown("""
<div class="hero" style="position:relative;">
  <div class="hero-glow"></div>
  <div class="hero-title">Council of Rishis</div>
  <div class="hero-sub">Rishivan · Ancient Wisdom · Modern Guidance</div>
</div>
""", unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

def _geocode_place_on_change():
    """Resolve the just-typed Place to lat/lon before the next rerun.

    Setting session_state here (in an on_change callback, which runs before
    Streamlit reruns the script) is what lets the Latitude/Longitude widgets
    below pick up the new value on their next render — they still read the
    key straight after, so the user can freely overwrite it by hand too.
    """
    place = st.session_state.get("bd_place", "").strip()
    if not place:
        return
    from rishivan.chart.geocode import geocode_place
    coords = geocode_place(place)
    if coords:
        st.session_state["bd_lat"], st.session_state["bd_lon"] = coords
        st.session_state["bd_geocode_status"] = (
            f"📍 Resolved \"{place}\" to {coords[0]:.4f}, {coords[1]:.4f}"
        )
    else:
        st.session_state["bd_geocode_status"] = (
            f"⚠️ Couldn't resolve \"{place}\" — enter latitude/longitude manually."
        )


# ── Birth Data Panel ──────────────────────────────────────────────────────────
def _build_birth_data():
    with st.expander("🌙 Birth Details (for personalised natal readings)", expanded=False):
        st.caption("Required for natal chart readings. Leave collapsed for muhurta / prashna / general questions.")
        use = st.checkbox("Use my birth chart", key="use_chart")
        c1, c2, c3 = st.columns(3)
        with c1:
            d = st.date_input("Date", value=dt.date(1990, 1, 1),
                              min_value=dt.date(1900, 1, 1),
                              max_value=dt.date.today(), key="bd_date")
            lat = st.number_input("Latitude", value=28.6139, format="%.4f", key="bd_lat")
        with c2:
            t = st.time_input("Time", key="bd_time", step=60)
            lon = st.number_input("Longitude", value=77.2090, format="%.4f", key="bd_lon")
        with c3:
            tz = st.number_input("TZ offset", value=5.5, step=0.5, format="%.1f", key="bd_tz")
            place = st.text_input("Place", value="New Delhi", key="bd_place",
                                   on_change=_geocode_place_on_change)
        if st.session_state.get("bd_geocode_status"):
            st.caption(st.session_state["bd_geocode_status"])
        if not use:
            return None
        try:
            from rishivan.chart.ephemeris import BirthData
            return BirthData(
                year=d.year, month=d.month, day=d.day,
                hour=t.hour, minute=t.minute,
                tz_offset_hours=tz, lat=lat, lon=lon, place=place,
            )
        except ImportError:
            st.error("pyswisseph not installed.")
            return None

birth_data = _build_birth_data()

# ── Query Input ───────────────────────────────────────────────────────────────
prefill_val = st.session_state.get("prefill", "")
question = st.text_area(
    "Enter the Sanctum:",
    value=prefill_val,
    placeholder="Present your life's query to the sacred fire... (e.g. What is my soul's true purpose?)",
    key="query_input",
    height=120,
    label_visibility="collapsed",
)
if prefill_val and question == prefill_val:
    st.session_state.prefill = ""

_convo = st.session_state.conversation
_c1, _c2 = st.columns([3, 1])
with _c1:
    ask_btn = st.button("Invoke the Council", key="ask_btn")
with _c2:
    if not _convo.is_empty and st.button("Start fresh", key="reset_convo",
                                         use_container_width=True):
        st.session_state.conversation = Conversation()
        st.session_state.history = []
        st.rerun()

if not _convo.is_empty:
    _p = get_persona(_convo.current_rishi)
    st.caption(
        f"{_p.emoji} Continuing with **{_p.display_name}** · "
        f"{len(_convo.turns)} exchange(s) remembered — reply naturally, or "
        "take up the thread they offered."
    )

# ── Pipeline Execution ────────────────────────────────────────────────────────
if ask_btn and question.strip():
    store = _get_store()
    if store is None:
        st.error(
            "Vector store unreachable. Check `QDRANT_URL` and "
            "`QDRANT_API_KEY`, and that the collection "
            f"`{settings.VECTOR_COLLECTION}` exists."
        )
        st.stop()

    try:
        client = _get_vertex_client()
    except Exception as exc:  # noqa: BLE001
        st.error(f"Could not reach Vertex AI: {exc}")
        st.stop()

    # No selector in the UI — the classifier always chooses the Rishi.
    rishi_override = None

    # Pipeline step indicator
    steps_ph = st.empty()
    def _steps(classify="", chart="", retrieve="", generate=""):
        cls = {"": "", "active": "active", "done": "done"}
        steps_ph.markdown(
            f"<div style='margin: 30px 0 20px; text-align: center;'>"
            f"<span class='step {cls[classify]}'>I. Aligning Stars</span>"
            f"<span class='step {cls[chart]}'>II. Casting Chart</span>"
            f"<span class='step {cls[retrieve]}'>III. Reading Shastras</span>"
            f"<span class='step {cls[generate]}'>IV. Channelling</span>"
            f"</div>",
            unsafe_allow_html=True,
        )

    _steps(classify="active")

    # No st.spinner — the step chips above already show progress.
    from rishivan.council.orchestrator import council_consult
    result = council_consult(
        client, store, question.strip(),
        rishi_override=rishi_override,
        birth_data=birth_data,
        query_time=dt.datetime.now(),
        conversation=st.session_state.conversation,
    )

    if result is None:
        st.warning("Consultation failed — please try again.")
        st.stop()

    rishi_name = result["primary_rishi"]
    persona = get_persona(rishi_name)

    classification = result.get("classification", {})
    domain = result.get("query_domain", "general")
    domain_str = domain.value if hasattr(domain, "value") else str(domain)

    _steps(classify="done", chart="done", retrieve="done", generate="active")

    # ── Rishi header ──
    is_warmth = bool(result.get("is_warmth"))
    conf = classification.get("confidence", 0)
    reasoning = classification.get("reasoning", "")
    supporting = classification.get("supporting_rishis", [])

    if is_warmth:
        # A greeting or gibberish never went through classification/routing —
        # no domain, no confidence, no reasoning to show, just a friendly
        # host at the door.
        st.markdown(
            f"""<div style="display:flex;align-items:center;gap:12px;margin:18px 0 6px;">
            <span style="font-size:2rem">{persona.emoji}</span>
            <div>
              <div style="font-family:'Cinzel',serif;color:{persona.color};font-size:1.4rem;font-weight:600">
                The Council welcomes you
              </div>
            </div>
            </div>""",
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f"""<div style="display:flex;align-items:center;gap:12px;margin:18px 0 6px;">
            <span style="font-size:2rem">{persona.emoji}</span>
            <div>
              <div style="font-family:'Cinzel',serif;color:{persona.color};font-size:1.4rem;font-weight:600">
                {persona.display_name} has entered the sanctum
              </div>
              <div style="color:#5a5a80;font-size:.78rem">
                {persona.title} · {domain_str.upper()} · {conf:.0%} confidence
              </div>
            </div>
            </div>""",
            unsafe_allow_html=True,
        )

        if reasoning:
            st.caption(f"*{reasoning}*")

    # ── Computed timings ──
    # Shown as data, not narration. These are Swiss Ephemeris values; the model
    # has been caught restating them wrongly, so the authoritative copy lives
    # here where it cannot be paraphrased.
    if result.get("panchang"):
        rows = [ln for ln in result["panchang"].splitlines() if ":" in ln]
        chips = ""
        for ln in rows:
            label, _, val = ln.partition(":")
            chips += (
                "<div style='display:inline-block;margin:0 18px 8px 0'>"
                f"<div style='color:#5a5a80;font-size:.68rem;letter-spacing:1px;"
                f"text-transform:uppercase'>{label.strip()}</div>"
                f"<div style='color:#f5f3ff;font-size:.95rem;"
                f"font-variant-numeric:tabular-nums'>{val.strip()}</div></div>"
            )
        st.markdown(
            "<div style='background:rgba(245,158,11,.07);"
            "border:1px solid rgba(245,158,11,.28);border-radius:14px;"
            "padding:14px 18px;margin:10px 0'>"
            "<div style='color:#f59e0b;font-size:.72rem;letter-spacing:1.5px;"
            "text-transform:uppercase;margin-bottom:10px'>"
            "Computed timings · Swiss Ephemeris</div>"
            f"{chips}</div>",
            unsafe_allow_html=True,
        )

    # ── Nakshatra & dasha ──
    # Ground truth, shown regardless of what the Rishi's prose says: an
    # instruction to "name the nakshatra plainly when asked" is not reliably
    # followed (it can get paraphrased into flavour text instead of the real
    # name), so the accurate names live here too, where they cannot be lost.
    if result.get("nakshatra_now"):
        nn = result["nakshatra_now"]
        rows = [
            ("Birth Nakshatra", f"{nn['birth']['nakshatra']} (pada {nn['birth']['pada']})"),
            ("Nakshatra Today", f"{nn['today']['nakshatra']} (pada {nn['today']['pada']})"),
        ]
        # Each level shown with its own lord and end date — a single chained
        # line ("Saturn → Mercury → Mercury, until <pratyantar's end date>")
        # hid the maha/antar end dates entirely, which is exactly the level
        # of detail asked for when someone names pratyantardasha specifically.
        _LEVEL_LABEL = {
            "maha": "Mahadasha", "antar": "Antardasha", "pratyantar": "Pratyantardasha",
        }
        for d in nn["dasha"]:
            rows.append((
                _LEVEL_LABEL.get(d["level"], d["level"]),
                f"{d['lord']} (until {d['ends']})",
            ))
        chips = ""
        for label, val in rows:
            chips += (
                "<div style='display:inline-block;margin:0 18px 8px 0'>"
                f"<div style='color:#5a5a80;font-size:.68rem;letter-spacing:1px;"
                f"text-transform:uppercase'>{label}</div>"
                f"<div style='color:#f5f3ff;font-size:.95rem;"
                f"font-variant-numeric:tabular-nums'>{val}</div></div>"
            )
        st.markdown(
            "<div style='background:rgba(245,158,11,.07);"
            "border:1px solid rgba(245,158,11,.28);border-radius:14px;"
            "padding:14px 18px;margin:10px 0'>"
            "<div style='color:#f59e0b;font-size:.72rem;letter-spacing:1.5px;"
            "text-transform:uppercase;margin-bottom:10px'>"
            "Computed Nakshatra &amp; Dasha · Swiss Ephemeris</div>"
            f"{chips}</div>",
            unsafe_allow_html=True,
        )

    # ── Chart summary ──
    # Always the D1 (Rashi) chart — the base placements every reading uses.
    if result.get("chart_summary"):
        with st.expander("📊 Computed Chart (D1 Rashi)", expanded=False):
            st.code(result["chart_summary"], language=None)
            if result.get("chart_facts"):
                st.caption(f"{len(result['chart_facts'])} ground-truth facts extracted via Swiss Ephemeris")

    # ── The facts this reading actually stood on ──
    # Blueprint §21: an important conclusion must be traceable from question -> calculation
    # -> rule -> source -> explanation. Everything below is that trail, shown to the reader
    # rather than only visible in a log.
    #
    # Two representations of the same chart, doing two different jobs, and it is worth
    # showing both: the sentences are what the language model reads and what page retrieval
    # searches on; the tokens are the only thing a rule can be tested against.
    chart_facts = result.get("chart_facts") or []
    chart_tokens = result.get("chart_tokens") or {}
    if chart_facts or chart_tokens:
        with st.expander(
            f"🔍 Facts used for this reading — {len(chart_facts)} statements, "
            f"{len(chart_tokens)} machine values",
            expanded=False,
        ):
            if chart_facts:
                st.markdown("**Chart facts** — ground truth given to the Rishi, and the "
                            "queries page retrieval searched on")
                st.caption(
                    "Computed locally by Swiss Ephemeris. The reading may interpret "
                    "these; it may not change them."
                )
                for fact in chart_facts:
                    st.markdown(f"- {fact}")
            if chart_tokens:
                st.markdown("**Machine values** — what classical rules were tested against")
                st.caption(
                    "A rule matches only if its condition holds exactly here. "
                    "`house.7.lord.house = 7` means the 7th lord sits in the 7th house."
                )
                st.code(
                    "\n".join(
                        f"{name} = {value}"
                        for name, value in sorted(chart_tokens.items())
                    ),
                    language=None,
                )

    # ── Matched Koonji rules ──
    # Blueprint §21's gold standard: "If Rishivan cannot show how an important
    # conclusion travels from user question -> calculation -> rule -> source ->
    # validation -> final explanation, the engine is not finished." This panel is the
    # rule -> source link, made visible to the person reading the answer rather than
    # only to whoever reads the logs.
    matched_rules = result.get("matched_rules") or []
    if matched_rules:
        with st.expander(
            f"📜 {len(matched_rules)} classical rules match this chart", expanded=False
        ):
            true_count = result.get("rules_true_of_chart") or len(matched_rules)
            routing = result.get("routing") or {}
            owners = [routing.get("primary"), *(routing.get("secondary") or [])]
            owners = [o.upper() for o in owners if o]
            st.caption(
                f"{true_count} approved rules apply to this chart; the "
                f"{len(matched_rules)} owned by "
                f"{' + '.join(owners) if owners else 'this question'} are shown. "
                f"Matched by exact condition test against the computed placements — "
                f"not by similarity. Relevance is the Rishi's stated astrological "
                f"coverage (Eight Rishis §4-11), so a rule about a house outside that "
                f"coverage is not shown however well it matches the chart."
            )
            from rishivan.rag.describe import describe_condition

            for hit in matched_rules:
                condition = describe_condition(hit.condition)
                owner = f" · {hit.domain.upper()}" if hit.domain else ""
                st.markdown(
                    f"**{hit.citation}**{owner} — because {condition}"
                    if condition
                    else f"**{hit.citation}**{owner}"
                )
                for effect in hit.effects or []:
                    st.markdown(
                        f"- _{effect.get('polarity')}_: {effect.get('statement')}"
                    )
                # The verse behind a collapsed toggle rather than inline. An enumeration
                # verse like BPHS 46.25-31 holds eight branches in one paragraph, and
                # printing it whole -- once per matched branch -- buried the clause that
                # actually fired under the six that did not.
                translation = (hit.source or {}).get("translation", "").strip()
                if translation:
                    with st.popover("source verse"):
                        st.caption(translation)
                if hit.sensitivities:
                    st.caption(
                        "⚠ traditional indication, not a prediction — "
                        + ", ".join(sorted(hit.sensitivities))
                    )
    elif result.get("chart_facts"):
        # Silence here would read as "the books say nothing", when the truth is that
        # only part of one book has been approved into the rule base so far.
        st.caption(
            "No classical rule in the approved rule base matched this chart — this "
            "reading comes from source passages only."
        )

    # ── Relevant divisional charts ──
    # Beyond D1, only the vargas this specific question actually needed were
    # computed (see orchestrator.py — the classifier decides relevance per
    # question, e.g. D9 for marriage, D7 for children). Shown here so the
    # reading can be checked against the exact chart it was grounded in,
    # not just the always-present D1.
    for code, table in result.get("relevant_chart_tables", {}).items():
        with st.expander(f"📊 Computed Chart ({code}) — used for this reading", expanded=False):
            st.markdown(_md(table), unsafe_allow_html=True)

    # ── Chart table — a display request, answered deterministically, no LLM ──
    if result.get("chart_table"):
        st.markdown(
            f"""<div class="answer-card" style="--ac:{persona.color};">
  <div class="rishi-header">
    <div class="rishi-avatar">{persona.emoji}</div>
    <div class="rishi-name-block">
      <div class="rn">{persona.display_name}</div>
      <div class="rt">{persona.title}</div>
    </div>
  </div>
  <div class="answer-body">{_md(result["chart_table"])}</div>
</div>""",
            unsafe_allow_html=True,
        )
        _steps(classify="done", chart="done", retrieve="done", generate="done")

    elif result.get("chart_table_error"):
        st.warning(result["chart_table_error"])
        _steps(classify="done", chart="done", retrieve="done", generate="done")

    else:
        # ── Stream answer ──
        answer_stream = result.get("answer_stream")
        if answer_stream is None:
            st.warning("No relevant context found in the classical texts for this query.")
        else:
            answer_ph = st.empty()
            answer = ""
            # A greeting doesn't need the Rishi's philosophical sign-off line.
            sign_off_html = "" if is_warmth else f'<div class="sign-off">— {persona.sign_off}</div>'

            for chunk in answer_stream:
                answer += chunk
                answer_ph.markdown(
                    f"""<div class="answer-card" style="--ac:{persona.color};">
  <div class="rishi-header">
    <div class="rishi-avatar">{persona.emoji}</div>
    <div class="rishi-name-block">
      <div class="rn">{persona.display_name}</div>
      <div class="rt">{persona.title}</div>
    </div>
  </div>
  <div class="answer-body">{_md(answer)}</div>
  {sign_off_html}
</div>""",
                    unsafe_allow_html=True,
                )

            _steps(classify="done", chart="done", retrieve="done", generate="done")

            # ── Who contributed ──
            # The supporting Rishis computed rather than spoke, so there is nothing
            # to generate here and nothing to wait for — every value below was
            # already established deterministically during the consultation.
            contributors = result.get("contributors") or []
            if contributors:
                with st.expander(
                    f"🔭 {len(contributors)} Rishis contributed to this reading",
                    expanded=False,
                ):
                    st.caption(
                        "Each contributor computes; only the primary Rishi speaks. "
                        "Values here are deterministic, not generated."
                    )
                    for entry in contributors:
                        persona = get_persona(entry["rishi"])
                        st.markdown(f"**{persona.display_name}** — {persona.title}")
                        for label, value in (entry.get("computed") or {}).items():
                            st.markdown(f"- {label}: `{value}`")
                        if entry.get("rules"):
                            st.markdown(f"- {entry['rules']} matched rules supplied")
                        if entry.get("note"):
                            st.caption(entry["note"])

            page_groups = result.get("sources", [])

            # Citation strip. The Rishi no longer speaks page numbers aloud (they
            # made the reading sound like a search engine), so the proof of
            # authority lives here instead — visible, but out of the voice.
            if page_groups:
                cites = sorted({
                    f"{g.get('book_title', 'Classical text')} · p. {g['page_number']}"
                    for g in page_groups
                })
                chips = " ".join(
                    f"<span style='display:inline-block;background:rgba(139,92,246,.10);"
                    f"border:1px solid rgba(139,92,246,.28);border-radius:20px;"
                    f"padding:4px 12px;margin:3px 4px 0 0;font-size:.75rem;"
                    f"color:#c4b5fd'>{c}</span>"
                    for c in cites
                )
                st.markdown(
                    "<div style='margin:-14px 0 6px'>"
                    "<span style='color:#5a5a80;font-size:.72rem;letter-spacing:1px;"
                    "text-transform:uppercase'>Drawn from</span><br>"
                    f"{chips}</div>",
                    unsafe_allow_html=True,
                )

                with st.expander(f"🔍 Read the source pages ({len(page_groups)})",
                                 expanded=False):
                    st.caption(f"**Search query used:** {result.get('search_query', '')}")
                    for g in page_groups:
                        flat = g["text"].replace("\n", " ")
                        preview = flat[:200] + ("…" if len(flat) > 200 else "")
                        st.markdown(
                            f"""<div class="src-chip" style="margin-bottom:8px;display:block;">
<span>{g.get('book_title', 'Classical text')} · Page {g['page_number']}</span>
· {g['n_elements']} elements<br>
<span style="color:#5a5a80;font-size:.76rem">{preview}</span></div>""",
                            unsafe_allow_html=True,
                        )

            # Remember the exchange so the Rishi's closing hook leads somewhere.
            st.session_state.conversation.add(question.strip(), answer, rishi_name)
            st.session_state.history.insert(0, {
                "q": question.strip(), "a": answer,
                "rishi": rishi_name, "domain": domain_str,
            })

            if not is_warmth:
                st.caption(
                    "Rishivan shares traditional Vedic interpretation for reflection "
                    "and guidance. It is not medical, legal, or financial advice — "
                    "please consult a qualified professional for those decisions."
                )

# ── History ───────────────────────────────────────────────────────────────────
if st.session_state.history:
    st.markdown("---")
    st.markdown("### 🕑 Previous Consultations")
    for item in st.session_state.history[1:5]:
        p = get_persona(item["rishi"])
        with st.expander(f"{p.emoji} {item['q'][:80]}", expanded=False):
            st.markdown(
                f"""<div class="answer-card" style="--ac:{p.color};">
<div class="answer-body">{_md(item['a'])}</div>
<div class="sign-off">— {p.sign_off}</div>
</div>""",
                unsafe_allow_html=True,
            )
