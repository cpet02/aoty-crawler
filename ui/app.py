#!/usr/bin/env python3
"""
Streamlit UI for Radius — seed one album, find its neighbours by fingerprint.

The whole app is this one view. See radius/README.md for how matching works,
and radius/engine.py for the pipeline this screen drives.
"""

import sys
import os
import html

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
import pandas as pd

from radius import clients as radius_clients
from radius import engine as radius_engine
from radius import similarity as radius_similarity

st.set_page_config(
    page_title="Radius",
    page_icon="🧭",
    layout="wide",
    initial_sidebar_state="collapsed",
)

RADIUS_CSS = """
<style>
  /* The engine has sixteen tunable axes; almost nobody wants to meet all
     sixteen on arrival, so the surface here is one search box and three
     plain-English choices, with the full control panel folded away. */
  .rad-hero { text-align:center; padding: 0.5rem 0 1.25rem; }
  .rad-hero h1 { font-size: 2.6rem; font-weight: 700; letter-spacing:-0.02em;
                 margin:0 0 .35rem; line-height:1.1; }
  .rad-hero p  { opacity:.62; font-size:1.02rem; margin:0; }

  .rad-seed { display:flex; gap:1.1rem; align-items:center;
              padding:1.1rem 1.25rem; border-radius:16px;
              background:rgba(255,255,255,.035);
              border:1px solid rgba(255,255,255,.09); margin:.5rem 0 1.5rem; }
  .rad-seed img { width:104px; height:104px; border-radius:10px;
                  object-fit:cover; flex:none;
                  box-shadow:0 6px 20px rgba(0,0,0,.45); }
  .rad-seed .t  { font-size:1.3rem; font-weight:650; line-height:1.25; }
  .rad-seed .a  { opacity:.7; font-size:1rem; margin-bottom:.5rem; }
  .rad-stats    { display:flex; flex-wrap:wrap; gap:.4rem .45rem; }
  .rad-chip { font-size:.76rem; padding:.2rem .6rem; border-radius:999px;
              background:rgba(255,255,255,.07);
              border:1px solid rgba(255,255,255,.1); opacity:.9;
              white-space:nowrap; }

  .rad-card { display:flex; gap:.95rem; padding:.8rem;
              border-radius:14px; border:1px solid rgba(255,255,255,.07);
              background:rgba(255,255,255,.022); height:100%;
              transition:border-color .15s ease, background .15s ease; }
  .rad-card:hover { border-color:rgba(255,255,255,.2);
                    background:rgba(255,255,255,.05); }
  .rad-card img { width:84px; height:84px; border-radius:8px;
                  object-fit:cover; flex:none;
                  box-shadow:0 4px 14px rgba(0,0,0,.4); }
  .rad-card .ph { width:84px; height:84px; border-radius:8px; flex:none;
                  background:linear-gradient(135deg,#2a2a33,#15151a);
                  display:flex; align-items:center; justify-content:center;
                  font-size:1.6rem; opacity:.35; }
  .rad-body { min-width:0; flex:1; }
  .rad-title { font-weight:640; font-size:.98rem; line-height:1.25;
               overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .rad-artist { opacity:.68; font-size:.86rem; margin-bottom:.35rem;
                overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .rad-tags { font-size:.74rem; opacity:.5; margin-top:.3rem; line-height:1.35;
              overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }

  /* The match bar is the one number that matters, so it gets the only colour
     on the card and reads left-to-right like a fill gauge. */
  .rad-meter { height:5px; border-radius:99px; background:rgba(255,255,255,.08);
               overflow:hidden; margin:.15rem 0 .1rem; }
  .rad-meter span { display:block; height:100%; border-radius:99px;
                    background:linear-gradient(90deg,#8b5cf6,#d946a6); }
  .rad-pct { font-size:.73rem; opacity:.55; letter-spacing:.02em; }
  .rad-why { font-size:.74rem; opacity:.45; margin-top:.3rem; line-height:1.35; }

  /* Fine-tuning: every slider row is the same shape regardless of how many
     axes share its group, and the group label reads like a section header
     rather than another line of body text. */
  .rad-group-label { font-weight:640; font-size:.92rem; margin:1rem 0 .1rem;
                      opacity:.85; text-transform:uppercase; letter-spacing:.03em; }
  .rad-group-label:first-child { margin-top:0; }
</style>
"""

# The three modes are the whole options surface for most runs. Each is a
# plain-English intention mapped onto engine arguments the user never sees.
RADIUS_MODES = {
    "🎯 Closest": {
        "help": "Nearest fingerprints, whatever they are.",
        "kwargs": {"lateral": False, "obscurity": "any"},
    },
    "🧭 Sideways": {
        "help": "Same broad genre, but corners of it your album isn't in.",
        "kwargs": {"lateral": True, "obscurity": "any"},
    },
    "💎 Deep cuts": {
        "help": "Only records less heard than your album.",
        "kwargs": {"lateral": False, "obscurity": "more_obscure"},
    },
}

# Consistent slider width regardless of how many axes are in a group — the
# original layout put one column per axis, so a two-axis group ("Provenance")
# rendered much wider sliders than a six-axis one ("Sound & association").
FINE_TUNE_COLS = 2


def radius_services():
    """One set of clients per session, so the rate limiters and cache counters
    survive Streamlit's reruns."""
    if 'radius_services' not in st.session_state:
        st.session_state.radius_services = radius_engine.Services.create()
    return st.session_state.radius_services


def _rad_art(url):
    if url:
        return f'<img src="{url}" alt="">'
    return '<div class="ph">♪</div>'


def _rad_card(match):
    features = match.features
    pct = int(round(match.similarity * 100))
    year = f' · {features.year}' if features.year else ''
    tags = ', '.join(features.top_tags[:4])
    why = radius_similarity.describe_axes(match, limit=3)
    link = features.url or '#'
    return f"""
    <a href="{link}" target="_blank" style="text-decoration:none;color:inherit;">
      <div class="rad-card">
        {_rad_art(features.image_url)}
        <div class="rad-body">
          <div class="rad-title">{html.escape(features.title)}</div>
          <div class="rad-artist">{html.escape(features.artist)}{year}</div>
          <div class="rad-meter"><span style="width:{pct}%"></span></div>
          <div class="rad-pct">{pct}% match</div>
          <div class="rad-tags">{html.escape(tags)}</div>
          <div class="rad-why">{html.escape(why)}</div>
        </div>
      </div>
    </a>
    """


def _rad_seed_card(seed):
    chips = []
    if seed.listeners:
        chips.append(f'{seed.listeners:,} listeners')
        chips.append(f'{seed.devotion:.0f} listens each')
    if seed.runtime_seconds:
        chips.append(f'{seed.runtime_seconds // 60} min')
    if seed.artist_area:
        chips.append(seed.artist_area)
    if seed.career_stage is not None:
        chips.append(f'{seed.career_stage} yrs into career')
    chips += seed.top_tags[:5]
    chip_html = ''.join(f'<span class="rad-chip">{html.escape(str(c))}</span>'
                        for c in chips)
    year = f' · {seed.year}' if seed.year else ''
    return f"""
    <div class="rad-seed">
      {_rad_art(seed.image_url)}
      <div style="min-width:0;">
        <div class="t">{html.escape(seed.title)}</div>
        <div class="a">{html.escape(seed.artist)}{year}</div>
        <div class="rad-stats">{chip_html}</div>
      </div>
    </div>
    """


def resolve_seed_candidates(services, artist, album, query, limit=5):
    """Up to `limit` fingerprinted matches for what the user typed, best
    guess first — the pool the user picks their real seed from."""
    results = radius_engine.search_albums(services, artist=artist, album=album,
                                          query=query, limit=limit)
    if not results:
        return []
    results.sort(key=lambda r: 0 if (r.get('type') or '').lower() == 'album' else 1)
    built = radius_engine.fingerprint_many(services, [r['mbid'] for r in results[:limit]])
    return [built[r['mbid']] for r in results[:limit] if built.get(r['mbid']) is not None]


def _weight_control(axis, default):
    """A slider paired with a click-to-type number field, kept in sync via
    session_state so either one can drive the value."""
    slider_key = f"radius_weight_{axis}"
    num_key = f"radius_weight_num_{axis}"
    if slider_key not in st.session_state:
        st.session_state[slider_key] = float(default)
    if num_key not in st.session_state:
        st.session_state[num_key] = st.session_state[slider_key]

    def sync_from_slider():
        st.session_state[num_key] = st.session_state[slider_key]

    def sync_from_num():
        st.session_state[slider_key] = st.session_state[num_key]

    slider_col, num_col = st.columns([4, 1.3])
    with slider_col:
        st.slider(
            radius_similarity.AXIS_LABELS[axis],
            min_value=0.0, max_value=2.0, step=0.05,
            key=slider_key, on_change=sync_from_slider,
            help=radius_similarity.AXIS_HELP.get(axis),
        )
    with num_col:
        st.number_input(
            radius_similarity.AXIS_LABELS[axis], min_value=0.0, max_value=2.0,
            step=0.05, key=num_key, on_change=sync_from_num,
            label_visibility="collapsed",
        )
    return st.session_state[slider_key]


def render_similar():
    st.markdown(RADIUS_CSS, unsafe_allow_html=True)
    services = radius_services()

    st.markdown(
        '<div class="rad-hero"><h1>What sounds like this?</h1>'
        '<p>Name one album you love. Get its neighbours.</p></div>',
        unsafe_allow_html=True,
    )

    search_col, button_col = st.columns([5, 1])
    with search_col:
        seed_text = st.text_input(
            "Seed album", label_visibility="collapsed",
            value=st.session_state.get('radius_seed_text', ''),
            placeholder="Radiohead - Kid A",
            key="radius_seed_input",
        )
    with button_col:
        submitted = st.button("Find", type="primary", use_container_width=True,
                              key="radius_go")

    mode_col, reach_col = st.columns([2, 3])
    with mode_col:
        mode = st.radio(
            "Mode", list(RADIUS_MODES), horizontal=True,
            label_visibility="collapsed", key="radius_mode",
        )
    with reach_col:
        radius_value = st.select_slider(
            "How far to roam", options=[0.3, 0.4, 0.5, 0.6, 0.7],
            value=st.session_state.get('radius_value', 0.5),
            format_func=lambda v: {0.3: "Very close", 0.4: "Close",
                                   0.5: "Balanced", 0.6: "Adventurous",
                                   0.7: "Far afield"}[v],
            label_visibility="collapsed", key="radius_reach",
        )
    st.caption(RADIUS_MODES[mode]["help"])

    # Everything below here is for people who want it; nobody has to look.
    with st.expander("Fine-tuning"):
        st.caption(
            "Each axis is one part of the fingerprint — hover the (?) on any "
            "of them for what it measures. Zero switches it off; type an "
            "exact value in the box, or drag the slider. An axis with no "
            "data for an album is skipped rather than guessed, so a missing "
            "value never counts as a perfect match."
        )
        weight_values = {}
        defaults = radius_similarity.SimilarityWeights()
        for group, axes in radius_similarity.AXIS_GROUPS.items():
            st.markdown(f'<div class="rad-group-label">{group}</div>',
                        unsafe_allow_html=True)
            for row_start in range(0, len(axes), FINE_TUNE_COLS):
                row_axes = axes[row_start:row_start + FINE_TUNE_COLS]
                columns = st.columns(FINE_TUNE_COLS)
                for column, axis in zip(columns, row_axes):
                    with column:
                        weight_values[axis] = _weight_control(axis, getattr(defaults, axis))
        st.divider()
        col1, col2, col3 = st.columns(3)
        with col1:
            top_n = st.number_input("Results", 5, 60, 24, 3, key="radius_topn")
            studio_only = st.checkbox("Studio albums only", True, key="radius_studio")
        with col2:
            pool_size = st.slider("Candidates to fingerprint", 40, 300, 120, 20,
                                  key="radius_pool")
            max_per_artist = st.slider(
                "Max albums per artist", 1, 6, 2, 1, key="radius_per_artist",
                help="Stops one close neighbour filling the list with its "
                     "whole discography.",
            )
            exclude_same_artist = st.checkbox("Exclude the seed's artist", True,
                                              key="radius_same_artist")
        with col3:
            enrich_results = st.checkbox(
                "Fetch tracklists", True, key="radius_enrich",
                help="Enables the runtime, pacing and titling axes. Adds about "
                     "a second per result.",
            )
            crowd_tags = st.checkbox(
                "Add Last.fm crowd tags", True, key="radius_crowd",
                help="Thickens tag vectors, especially mood. Needs "
                     "LASTFM_API_KEY; ignored without one.",
            )
            with_prose = st.checkbox(
                "Read Wikipedia", False, key="radius_prose",
                help="Prose axis. Off by default — album write-ups are mostly "
                     "boilerplate, so it measured worse than nothing.",
            )

    if submitted:
        if not seed_text.strip():
            st.warning("Type an album first — artist and title work best.")
            return
        st.session_state.radius_seed_text = seed_text
        st.session_state.radius_value = radius_value
        st.session_state.radius_result = None
        st.session_state.radius_result_signature = None
        st.session_state.radius_confirmed_seed = None

        artist_name, album_name, query = None, None, None
        if ' - ' in seed_text:
            artist_name, _, album_name = (p.strip() for p in seed_text.partition(' - '))
        else:
            query = seed_text.strip()

        with st.spinner("Looking that up…"):
            try:
                candidates = resolve_seed_candidates(services, artist_name, album_name, query)
            except radius_clients.ApiError as exc:
                st.error(str(exc))
                return
        if not candidates:
            st.error(
                "MusicBrainz has no album matching that. Check the spelling, "
                "or try \"Artist - Album\"."
            )
            st.session_state.radius_candidates = None
            return
        st.session_state.radius_candidates = candidates

    # --- Confirm step: nothing runs against the full pipeline until the user
    # has said yes, this is the right album. ---
    candidates = st.session_state.get('radius_candidates')
    confirmed = st.session_state.get('radius_confirmed_seed')
    if candidates and not confirmed:
        st.markdown("#### Is this the album?")
        options = [
            f"{c.artist} — {c.title}" + (f" ({c.year})" if c.year else "")
            for c in candidates
        ]
        picked_label = st.radio(
            "Which match is right", options, index=0,
            label_visibility="collapsed", key="radius_candidate_pick",
        )
        picked = candidates[options.index(picked_label)]
        st.markdown(_rad_seed_card(picked), unsafe_allow_html=True)

        confirm_col, cancel_col = st.columns([1, 1])
        with confirm_col:
            confirm_clicked = st.button(
                "✅ Yes, find similar albums", type="primary",
                use_container_width=True, key="radius_confirm",
            )
        with cancel_col:
            if st.button("✖ Not it — clear search", use_container_width=True,
                         key="radius_cancel"):
                st.session_state.radius_candidates = None
                st.rerun()

        if confirm_clicked:
            st.session_state.radius_confirmed_seed = picked
            st.session_state.radius_result_signature = None
            st.rerun()
        return

    confirmed = st.session_state.get('radius_confirmed_seed')
    if confirmed is None:
        st.caption("Try: `Slint - Spiderland` · `Bon Iver - For Emma, Forever Ago` "
                   "· `Portishead - Dummy`")
        return

    # Fine-tuning (or mode, or radius, or any other control above) changing
    # is itself a "run again" — otherwise moving a slider after a result is
    # already on screen just silently does nothing, which is what this
    # replaced. The signature is what a run actually depends on, so an
    # unrelated rerun (e.g. hovering a tooltip) reuses the stored result
    # rather than re-hitting the pipeline.
    run_signature = (
        confirmed.mbid, mode, radius_value, tuple(sorted(weight_values.items())),
        int(top_n), int(pool_size), studio_only, exclude_same_artist,
        int(max_per_artist), enrich_results, with_prose, crowd_tags,
    )

    if st.session_state.get('radius_result_signature') != run_signature:
        stage_labels = {
            'seed': 'Reading your album',
            'candidates': 'Finding its neighbourhood',
            'fingerprint': 'Fingerprinting candidates',
            'crowd tags': 'Adding crowd tags',
            'kinship': 'Mapping listener kinship',
            'prose': 'Reading Wikipedia',
            'shape': 'Measuring runtime and pacing',
        }
        status_box = st.status("Working…", expanded=False)
        progress_bar = st.progress(0.0)

        def on_progress(stage, done, total, label):
            status_box.update(label=f"{stage_labels.get(stage, stage)} — {label}")
            progress_bar.progress(min(max((done / total) if total else 0.0, 0.0), 1.0))

        try:
            result = radius_engine.find_similar(
                seed_features=confirmed,
                weights=radius_similarity.SimilarityWeights(**weight_values),
                radius=radius_value, top_n=int(top_n), pool_size=int(pool_size),
                studio_only=studio_only, exclude_same_artist=exclude_same_artist,
                max_per_artist=max_per_artist,
                enrich_results=enrich_results, with_prose=with_prose,
                enrich_tags_with_lastfm=crowd_tags,
                services=services, progress=on_progress,
                **RADIUS_MODES[mode]["kwargs"],
            )
        except radius_clients.ApiError as exc:
            status_box.update(label="A lookup failed", state="error")
            st.error(str(exc))
            return

        progress_bar.empty()
        status_box.update(label=f"Found {len(result.matches)}", state="complete")
        st.session_state.radius_result = result
        st.session_state.radius_result_signature = run_signature

    result = st.session_state.radius_result
    seed = result.seed
    seed_col, change_col = st.columns([5, 1])
    with seed_col:
        st.markdown(_rad_seed_card(seed), unsafe_allow_html=True)
    with change_col:
        if st.button("🔁 Change album", use_container_width=True, key="radius_change"):
            st.session_state.radius_candidates = None
            st.session_state.radius_confirmed_seed = None
            st.session_state.radius_result = None
            st.session_state.radius_result_signature = None
            st.rerun()

    for note in result.notes:
        st.info(note)
    if not result.matches:
        return

    # Three across reads well on a laptop and stays legible when Streamlit
    # stacks the columns on a narrow window.
    columns = st.columns(3)
    for index, match in enumerate(result.matches):
        with columns[index % 3]:
            st.markdown(_rad_card(match), unsafe_allow_html=True)
            st.write("")

    st.divider()
    detail_col, download_col = st.columns([3, 1])
    with detail_col:
        breakdown = ' · '.join(
            f'{name} {count}' for name, count in services.requests_by_service.items()
        )
        st.caption(
            f"{result.fingerprinted} of {result.considered} candidates "
            f"fingerprinted · {result.requests_made} requests this run "
            f"({breakdown}) · {result.cache_hits} more served from cache"
            + (" · tags enriched with Last.fm" if services.tag_enrichment else "")
        )
    with download_col:
        st.download_button(
            "⬇️ CSV", data=pd.DataFrame(result.rows()).to_csv(index=False).encode('utf-8'),
            file_name=f"similar_to_{seed.artist}_{seed.title}.csv".replace(' ', '_'),
            mime="text/csv", key="radius_csv", use_container_width=True,
        )

    with st.expander("Full table and per-album breakdown"):
        st.dataframe(
            pd.DataFrame(result.rows()), use_container_width=True, hide_index=True,
            column_config={
                'similarity': st.column_config.ProgressColumn(
                    'Match', min_value=0.0, max_value=1.0, format="%.3f"),
                'url': st.column_config.LinkColumn('MusicBrainz', display_text="open"),
                'image_url': None,
                'mbid': None,
            },
        )
        for rank, match in enumerate(result.matches, 1):
            st.markdown(f"**{rank}. {match.features.artist} — {match.features.title}** "
                        f"· {match.similarity:.3f} over {len(match.axes)} axes")
            st.caption(radius_similarity.describe_axes(match, limit=6))
            if match.shared_neighbours:
                st.caption(f"Artists both sit next to: {', '.join(match.shared_neighbours)}")


render_similar()
