"""Radius: the Streamlit app.

One purpose: name an album, see the records most deeply connected to it, and
every statistic behind the verdict. Three views:

* Find     - seed picker (with a MusicBrainz search to disambiguate), the
             seed card(s), result cards with reasons, filters that narrow the
             current result without re-running, a table with every column
* Compare  - a dialog laying the seed and one match side by side, every stat
             in one table plus a per-axis breakdown
* Library  - saved and rated albums, seedable, with the old ratings and
             bookmarks imported once

The engine runs synchronously in the script thread; its worker threads never
touch Streamlit, and progress arrives on this thread through the callback.
"""

import html
import json
import os
import sys

# pandas pulls in OpenBLAS, which allocates one big buffer per CPU thread at
# import time and dies on machines short of commit memory. One is plenty.
os.environ.setdefault('OPENBLAS_NUM_THREADS', '1')

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from radius import config as radius_config  # noqa: E402
from radius.cache import Cache  # noqa: E402
from radius.clients import ApiError  # noqa: E402
from radius.engine import MODES, SeedNotFound, Services, find_similar, search_albums  # noqa: E402
from radius.library import Library  # noqa: E402
from radius.similarity import AXIS_GROUPS, AXIS_LABELS, SimilarityWeights  # noqa: E402

st.set_page_config(page_title='Radius', page_icon='🧭', layout='wide',
                   initial_sidebar_state='expanded')

MAX_SEEDS = 4

MODE_LABELS = {
    'closest': ('🎯 Closest', 'The most connected records, whatever they are.'),
    'sideways': ('🧭 Sideways', 'Same broad genre, corners of it the seed is not in.'),
    'deep_cuts': ('💎 Deep cuts', 'Only records less heard than the seed.'),
}

STAGE_LABELS = {
    'seed': 'Reading the seed',
    'candidates': 'Finding the neighbourhood',
    'fingerprint': 'Fingerprinting the pool',
    'enrich': 'Listener kinship and crowd tags',
    'score': 'Scoring',
    'connections': 'Tracing the connections: people, credits, editions',
    'stats': 'Gathering the statistics',
}

CSS = """
<style>
  .rad-hero { padding: .2rem 0 1rem; }
  .rad-hero h1 { font-size: 2.3rem; font-weight: 700; letter-spacing: -.02em; margin: 0 0 .2rem; }
  .rad-hero p { opacity: .62; margin: 0; }
  .rad-seed { display: flex; gap: 1rem; align-items: center; padding: 1rem 1.1rem; border-radius: 14px;
              background: rgba(255,255,255,.04); border: 1px solid rgba(255,255,255,.09); margin: .3rem 0 .8rem; }
  .rad-seed img, .rad-seed .ph { width: 96px; height: 96px; border-radius: 10px; object-fit: cover; flex: none;
                                  box-shadow: 0 6px 20px rgba(0,0,0,.45); }
  .rad-seed .t { font-size: 1.25rem; font-weight: 650; line-height: 1.2; }
  .rad-seed .a { opacity: .7; margin-bottom: .45rem; }
  .rad-chips { display: flex; flex-wrap: wrap; gap: .35rem .4rem; }
  .rad-chip { font-size: .74rem; padding: .18rem .55rem; border-radius: 999px; background: rgba(255,255,255,.07);
              border: 1px solid rgba(255,255,255,.1); white-space: nowrap; }
  .rad-chip.hot { background: rgba(139,92,246,.22); border-color: rgba(139,92,246,.5); }
  .rad-card { display: flex; gap: .9rem; padding: .75rem; border-radius: 14px; border: 1px solid rgba(255,255,255,.08);
              background: rgba(255,255,255,.025); min-height: 158px; }
  .rad-card img, .rad-card .ph { width: 84px; height: 84px; border-radius: 8px; object-fit: cover; flex: none;
                                  box-shadow: 0 4px 14px rgba(0,0,0,.4); }
  .ph { background: linear-gradient(135deg,#2a2a33,#15151a); display: flex; align-items: center;
        justify-content: center; font-size: 1.6rem; opacity: .35; }
  .rad-body { min-width: 0; flex: 1; }
  .rad-title { font-weight: 640; font-size: .97rem; line-height: 1.25; overflow: hidden; text-overflow: ellipsis;
               white-space: nowrap; }
  .rad-artist { opacity: .68; font-size: .85rem; margin-bottom: .3rem; overflow: hidden; text-overflow: ellipsis;
                white-space: nowrap; }
  .rad-meter { height: 5px; border-radius: 99px; background: rgba(255,255,255,.08); overflow: hidden; margin: .15rem 0 .1rem; }
  .rad-meter span { display: block; height: 100%; border-radius: 99px; background: linear-gradient(90deg,#8b5cf6,#d946a6); }
  .rad-pct { font-size: .72rem; opacity: .6; letter-spacing: .02em; }
  .rad-pct b { color: #c4b5fd; font-weight: 600; }
  .rad-why { font-size: .76rem; opacity: .8; margin-top: .35rem; line-height: 1.4; }
  .rad-why div::before { content: '• '; opacity: .5; }
  .rad-stats { font-size: .72rem; opacity: .5; margin-top: .3rem; }
  .rad-axis { display: flex; align-items: center; gap: .6rem; font-size: .8rem; margin: .12rem 0; }
  .rad-axis .l { width: 165px; opacity: .8; flex: none; }
  .rad-axis .bar { flex: 1; height: 7px; border-radius: 99px; background: rgba(255,255,255,.08); overflow: hidden; }
  .rad-axis .bar span { display: block; height: 100%; background: linear-gradient(90deg,#8b5cf6,#d946a6); }
  .rad-axis .bar span.ev { background: linear-gradient(90deg,#10b981,#34d399); }
  .rad-axis .v { width: 64px; text-align: right; opacity: .7; flex: none; font-variant-numeric: tabular-nums; }
  .rad-muted { opacity: .55; font-size: .85rem; }
</style>
"""


# ---------------------------------------------------------------------------
# Shared resources and state
# ---------------------------------------------------------------------------

@st.cache_resource
def services():
    """One set of clients per process, so every browser tab shares the rate
    limiters and the cache counters."""
    return Services.create()


def library():
    return Library()


DEFAULTS = {
    # The nav radio is driven by its own session-state key, never by index=:
    # Streamlit honours index= only when the widget is first registered, so a
    # programmatic view change (Seed from the Library, say) would be undone
    # by the widget's remembered value on the very next rerun.
    'nav_view': 'Find',
    'view': 'find',
    'seeds': [],           # [{'mbid','artist','album','year','image_url'}]
    'result': None,
    'result_id': 0,
    'history': [],
    'search_hits': [],
    'run_requested': False,
    'legacy_imported': False,
    'last_error': None,
}
for _key, _value in DEFAULTS.items():
    if _key not in st.session_state:
        st.session_state[_key] = _value


def seed_spec(mbid, artist, album, year=None, image_url=''):
    return {'mbid': mbid, 'artist': artist, 'album': album, 'year': year, 'image_url': image_url}


def spec_from_features(features):
    return seed_spec(features.mbid, features.artist, features.title, features.year, features.image_url)


def set_seeds(specs, run=True):
    st.session_state.seeds = [s for s in specs if s and s.get('mbid')][:MAX_SEEDS]
    st.session_state.run_requested = bool(run and st.session_state.seeds)
    st.session_state.view = 'find'
    st.session_state.nav_view = 'Find'


def add_seed(spec, run=True):
    seeds = [s for s in st.session_state.seeds if s['mbid'] != spec['mbid']]
    set_seeds(seeds + [spec], run=run)


def remember(specs):
    history = [h for h in st.session_state.history if h['mbid'] not in {s['mbid'] for s in specs}]
    st.session_state.history = (list(specs) + history)[:12]


def art(url, cls=''):
    if url:
        return f'<img src="{html.escape(url)}" alt="" class="{cls}">'
    return f'<div class="ph {cls}">♪</div>'


def fmt_int(value):
    return f'{int(value):,}' if value else '–'


def fmt_minutes(seconds):
    return f'{int(seconds) // 60} min' if seconds else '–'


def chips(items, hot=()):
    parts = []
    for item in items:
        if item in (None, ''):
            continue
        cls = 'rad-chip hot' if item in hot else 'rad-chip'
        parts.append(f'<span class="{cls}">{html.escape(str(item))}</span>')
    return '<div class="rad-chips">' + ''.join(parts) + '</div>'


# ---------------------------------------------------------------------------
# Sidebar: navigation, seeds, mode, filters, fine-tuning, history, about
# ---------------------------------------------------------------------------

def render_sidebar():
    with st.sidebar:
        st.markdown('### 🧭 Radius')
        view = st.radio('View', ['Find', 'Library'], horizontal=True,
                        label_visibility='collapsed', key='nav_view')
        st.session_state.view = 'find' if view == 'Find' else 'library'

        st.markdown('**Seeds**')
        if not st.session_state.seeds:
            st.caption('No seed yet. Search for an album, or pick one from the Library.')
        for index, seed in enumerate(list(st.session_state.seeds)):
            col_text, col_x = st.columns([5, 1])
            year = f' ({seed["year"]})' if seed.get('year') else ''
            col_text.markdown(f'{seed["artist"]} — *{seed["album"]}*{year}')
            if col_x.button('✕', key=f'seed_rm_{seed["mbid"]}', help='Remove this seed'):
                remaining = [s for s in st.session_state.seeds if s['mbid'] != seed['mbid']]
                set_seeds(remaining, run=False)
                st.rerun()
        if len(st.session_state.seeds) > 1:
            st.caption('Several seeds are blended into one fingerprint.')

        mode_keys = list(MODE_LABELS)
        mode = st.radio('Mode', mode_keys, format_func=lambda k: MODE_LABELS[k][0],
                        key='mode', horizontal=False)
        st.caption(MODE_LABELS[mode][1])

        settings = render_fine_tuning()
        filters = render_filters()
        render_history()
        render_about()
    return settings, filters


def render_fine_tuning():
    with st.expander('Fine-tuning'):
        st.caption('Each axis is one part of the fingerprint; zero switches it off. '
                   'Evidence axes (people, circle, co-listening) only pull when there is an overlap.')
        weights = {}
        defaults = SimilarityWeights()
        for group, axes in AXIS_GROUPS.items():
            st.markdown(f'**{group}**')
            for axis in axes:
                weights[axis] = st.slider(AXIS_LABELS[axis], 0.0, 2.0, float(getattr(defaults, axis)),
                                          0.05, key=f'w_{axis}')
        st.divider()
        top_n = st.slider('Results', 6, 60, 24, 3, key='top_n')
        pool_size = st.slider('Candidates to fingerprint', 40, 400, 150, 10, key='pool_size')
        shortlist = st.slider('Deep-checked shortlist', 10, 120, max(int(1.5 * top_n), 30), 5, key='shortlist',
                              help='How many get the MusicBrainz credit and personnel lookups '
                                   '(one request per second, so this sets the cold-run time).')
        per_artist = st.slider('Max albums per artist', 1, 6, 1, 1, key='per_artist')
        studio_only = st.checkbox('Studio albums only', True, key='studio_only')
        exclude_same = st.checkbox("Exclude the seed's artist", True, key='exclude_same')
        deep = st.checkbox('Deep lookups (credits, personnel, statistics)', True, key='deep')
        with_deezer = st.checkbox('Deezer: fans, BPM, loudness', True, key='with_deezer')
        with_wikidata = st.checkbox('Wikidata: critic scores, producers, ids', True, key='with_wikidata')
        with_discogs = st.checkbox('Discogs: styles, want/have, rating', services().discogs_enabled,
                                   key='with_discogs',
                                   help='25 requests a minute without a token, so this is the slow one.')
        crowd = st.checkbox('Last.fm crowd tags and listeners', True, key='crowd',
                            help='Needs LASTFM_API_KEY; ignored without one.')
    return {
        'weights': weights, 'top_n': int(top_n), 'pool_size': int(pool_size), 'shortlist': int(shortlist),
        'per_artist': int(per_artist), 'studio_only': studio_only, 'exclude_same': exclude_same,
        'deep': deep, 'with_deezer': with_deezer, 'with_wikidata': with_wikidata,
        'with_discogs': with_discogs, 'crowd': crowd,
    }


def render_filters():
    result = st.session_state.result
    with st.expander('Filter the results', expanded=False):
        if result is None or not result.matches:
            st.caption('Run a search first.')
            return None
        rid = st.session_state.result_id
        matches = result.matches
        years = [m.features.year for m in matches if m.features.year]
        runtimes = [m.features.runtime_seconds / 60.0 for m in matches if m.features.runtime_seconds]
        countries = sorted({m.features.artist_area for m in matches if m.features.artist_area})
        filters = {'connected': st.checkbox('Only connected records', False, key=f'f_conn_{rid}',
                                            help='At least one of: people in common, shared circle, co-listening.')}
        filters['text'] = st.text_input('Contains', '', key=f'f_text_{rid}',
                                        placeholder='artist, title or tag')
        if years and min(years) < max(years):
            filters['years'] = st.slider('Year', min(years), max(years), (min(years), max(years)), key=f'f_year_{rid}')
        if runtimes and int(min(runtimes)) < int(max(runtimes)) + 1:
            lo, hi = int(min(runtimes)), int(max(runtimes)) + 1
            filters['runtime'] = st.slider('Runtime (min)', lo, hi, (lo, hi), key=f'f_run_{rid}')
        if countries:
            filters['countries'] = st.multiselect('Country', countries, key=f'f_country_{rid}')
        filters['act'] = st.selectbox('Act', ['Any', 'Group', 'Person'], key=f'f_act_{rid}')
        listeners = [m.features.listeners for m in matches if m.features.listeners]
        if listeners:
            filters['min_listeners'] = st.select_slider(
                'Min listeners', options=[0, 100, 500, 1000, 5000, 20000, 100000],
                value=0, key=f'f_lis_{rid}')
        return filters


def apply_filters(matches, filters):
    if not filters:
        return list(matches)
    kept = []
    text = (filters.get('text') or '').strip().lower()
    for match in matches:
        x = match.features
        if filters.get('connected') and not match.connected:
            continue
        years = filters.get('years')
        if years and x.year and not (years[0] <= x.year <= years[1]):
            continue
        runtime = filters.get('runtime')
        if runtime and x.runtime_seconds and not (runtime[0] <= x.runtime_seconds / 60.0 <= runtime[1]):
            continue
        if filters.get('countries') and x.artist_area not in filters['countries']:
            continue
        act = filters.get('act', 'Any')
        if act != 'Any' and (x.artist_type or '').lower() != act.lower():
            continue
        if filters.get('min_listeners') and x.listeners < filters['min_listeners']:
            continue
        if text:
            haystack = ' '.join([x.artist, x.title, x.label, ' '.join(x.top_tags),
                                 ' '.join(match.reasons)]).lower()
            if text not in haystack:
                continue
        kept.append(match)
    return kept


def render_history():
    if not st.session_state.history:
        return
    with st.expander('Recent seeds'):
        for seed in st.session_state.history:
            if st.button(f'{seed["artist"]} — {seed["album"]}', key=f'hist_{seed["mbid"]}', width='stretch'):
                set_seeds([seed])
                st.rerun()


def render_about():
    with st.expander('About & cache'):
        svc = services()
        st.caption('Keyless: MusicBrainz, ListenBrainz, Wikidata, Deezer, Discogs. '
                   + ('Last.fm key: set. ' if svc.tag_enrichment else 'Last.fm key: not set. ')
                   + ('Discogs token: set.' if svc.discogs_enabled else 'Discogs token: not set (25 req/min).'))
        try:
            stats = Cache(radius_config.CACHE_PATH).stats()
            st.caption(f'Cache: {stats["entries"]:,} responses, {stats["size_bytes"] / 1e6:.1f} MB. '
                       f'This session: {svc.requests_made} requests, {svc.cache_hits} cache hits.')
        except Exception:  # noqa: BLE001 - purely informational
            pass
        if st.button('Clear the response cache', key='clear_cache'):
            deleted = Cache(radius_config.CACHE_PATH).clear()
            st.toast(f'Cleared {deleted:,} cached responses.')


# ---------------------------------------------------------------------------
# Find view
# ---------------------------------------------------------------------------

def render_search():
    col_input, col_button = st.columns([5, 1])
    query = col_input.text_input('Album', label_visibility='collapsed',
                                 placeholder='Artist - Album   (e.g. Slint - Spiderland)', key='search_text')
    go = col_button.button('Search', type='primary', width='stretch', key='search_go')
    if go and query.strip():
        artist, album, free = None, None, None
        if ' - ' in query:
            artist, _, album = (part.strip() for part in query.partition(' - '))
        else:
            free = query.strip()
        hits = search_albums(services(), artist=artist, album=album, query=free, limit=8)
        if not hits:
            st.session_state.search_hits = []
            st.session_state.last_error = 'MusicBrainz has no album matching that. Try "Artist - Album".'
        else:
            st.session_state.last_error = None
            exact = [h for h in hits if artist and album and h['artist'].casefold() == artist.casefold()
                     and h['album'].casefold() == album.casefold() and h['type'].lower() == 'album'
                     and not h['secondary_types']]
            if exact:
                st.session_state.search_hits = []
                set_seeds([seed_spec(exact[0]['mbid'], exact[0]['artist'], exact[0]['album'], exact[0]['year'])])
                st.rerun()
            st.session_state.search_hits = hits
    if st.session_state.last_error:
        st.warning(st.session_state.last_error)
    hits = st.session_state.search_hits
    if hits:
        st.caption('Pick the record you meant:')
        for hit in hits[:8]:
            col_label, col_seed, col_blend = st.columns([6, 1, 1])
            kind = hit['type'] or 'release'
            if hit['secondary_types']:
                kind += ' · ' + ', '.join(hit['secondary_types'])
            extra = f' — {hit["disambiguation"]}' if hit['disambiguation'] else ''
            col_label.markdown(f'**{hit["artist"]}** — {hit["album"]} '
                               f'<span class="rad-muted">({hit["year"] or "?"}, {kind}{extra})</span>',
                               unsafe_allow_html=True)
            if col_seed.button('Seed', key=f'hit_seed_{hit["mbid"]}', width='stretch'):
                st.session_state.search_hits = []
                set_seeds([seed_spec(hit['mbid'], hit['artist'], hit['album'], hit['year'])])
                st.rerun()
            if col_blend.button('+ Blend', key=f'hit_blend_{hit["mbid"]}', width='stretch',
                                disabled=len(st.session_state.seeds) >= MAX_SEEDS):
                st.session_state.search_hits = []
                add_seed(seed_spec(hit['mbid'], hit['artist'], hit['album'], hit['year']))
                st.rerun()


def run_engine(settings):
    seeds = st.session_state.seeds
    mode = st.session_state.get('mode', 'closest')
    status = st.status('Working…', expanded=False)
    bar = st.progress(0.0)

    def on_progress(stage, done, total, label):
        status.update(label=f'{STAGE_LABELS.get(stage, stage)} — {label}')
        bar.progress(min(max((done / total) if total else 0.0, 0.0), 1.0))

    try:
        result = find_similar(
            seeds=[{'mbid': s['mbid']} for s in seeds],
            weights=SimilarityWeights(**settings['weights']),
            mode=mode, top_n=settings['top_n'], pool_size=settings['pool_size'],
            shortlist_size=settings['shortlist'], max_per_artist=settings['per_artist'],
            studio_only=settings['studio_only'], exclude_same_artist=settings['exclude_same'],
            deep=settings['deep'], with_deezer=settings['with_deezer'],
            with_wikidata=settings['with_wikidata'], with_discogs=settings['with_discogs'],
            enrich_tags_with_lastfm=settings['crowd'],
            services=services(), progress=on_progress,
        )
    except SeedNotFound as exc:
        status.update(label="Couldn't find that album", state='error')
        st.error(str(exc))
        return False
    except ApiError as exc:
        status.update(label='A lookup failed', state='error')
        st.error(str(exc))
        return False
    except Exception as exc:  # noqa: BLE001 - shown to the person, not swallowed
        status.update(label='Something broke', state='error')
        st.exception(exc)
        return False
    bar.empty()
    status.update(label=f'Found {len(result.matches)} connected records', state='complete')
    st.session_state.result = result
    st.session_state.result_id += 1
    remember([spec_from_features(f) for f in result.seeds if f.mbid])
    return True


def seed_card_html(features, blend=False):
    year = f' · {features.year}' if features.year else ''
    stats = []
    if features.listeners:
        stats.append(f'{features.listeners:,} listeners')
        stats.append(f'{features.devotion:.0f} listens each')
    if features.fans:
        stats.append(f'{features.fans:,} Deezer fans')
    if features.runtime_seconds:
        stats.append(f'{features.track_count} tracks · {fmt_minutes(features.runtime_seconds)}')
    if features.bpm_mean:
        stats.append(f'{features.bpm_mean:.0f} bpm')
    if features.artist_area:
        stats.append(features.artist_area)
    if features.career_stage is not None:
        stats.append(f'{features.career_stage} yrs into career')
    if features.label:
        stats.append(f'on {features.label}')
    for name in features.producer_names[:2]:
        stats.append(f'prod. {name}')
    people = [n for m, n in features.personnel.items() if m != features.artist_mbid]
    if people:
        stats.append(f'{len(people)} connected people')
    if features.critic_scores:
        stats.append('critics ' + ', '.join(f'{k} {v:.2f}' for k, v in list(features.critic_scores.items())[:2]))
    if features.want:
        stats.append(f'{features.want:,} want / {features.have:,} have')
    hot = set(stats[:2])
    title = features.title if not blend else f'Blend: {features.title}'
    return f"""
    <div class="rad-seed">
      {art(features.image_url)}
      <div style="min-width:0;">
        <div class="t">{html.escape(title)}</div>
        <div class="a">{html.escape(features.artist)}{year}</div>
        {chips(stats, hot)}
        <div style="height:.35rem"></div>
        {chips(features.top_tags[:8])}
      </div>
    </div>"""


def card_html(match):
    x = match.features
    pct = int(round(match.similarity * 100))
    year = f' · {x.year}' if x.year else ''
    reasons = ''.join(f'<div>{html.escape(r)}</div>' for r in match.reasons[:3])
    stats = [fmt_int(x.listeners) + ' listeners']
    if x.runtime_seconds:
        stats.append(fmt_minutes(x.runtime_seconds))
    if x.artist_area:
        stats.append(x.artist_area)
    if x.label:
        stats.append(x.label)
    badge = ' <b>connected</b>' if match.connected else ''
    return f"""
    <div class="rad-card">
      {art(x.image_url)}
      <div class="rad-body">
        <div class="rad-title">{html.escape(x.title)}</div>
        <div class="rad-artist">{html.escape(x.artist)}{year}</div>
        <div class="rad-meter"><span style="width:{pct}%"></span></div>
        <div class="rad-pct">{pct}% match{badge}</div>
        <div class="rad-why">{reasons}</div>
        <div class="rad-stats">{html.escape(' · '.join(stats))}</div>
      </div>
    </div>"""


def render_card(match, seed):
    x = match.features
    st.markdown(card_html(match), unsafe_allow_html=True)
    b1, b2, b3, b4 = st.columns(4)
    if b1.button('Compare', key=f'cmp_{x.mbid}', width='stretch'):
        compare_dialog(seed, match)
    if b2.button('Seed', key=f'seed_{x.mbid}', width='stretch', help='Start again from this record'):
        set_seeds([spec_from_features(x)])
        st.rerun()
    if b3.button('+ Blend', key=f'blend_{x.mbid}', width='stretch',
                 disabled=len(st.session_state.seeds) >= MAX_SEEDS,
                 help='Add it to the seeds and search for what connects them all'):
        add_seed(spec_from_features(x))
        st.rerun()
    lib = library()
    saved = lib.is_saved(x.mbid)
    if b4.button('Saved ✓' if saved else 'Save', key=f'save_{x.mbid}', width='stretch'):
        if saved:
            lib.unsave(x.mbid)
            st.toast(f'Removed {x.title} from the library.')
        else:
            lib.save_album(x.as_row(), from_seed=f'{seed.artist} - {seed.title}')
            st.toast(f'Saved {x.title}.')
        st.rerun()


def render_results(result, filters):
    seed = result.seed
    if len(result.seeds) > 1:
        cols = st.columns(len(result.seeds))
        for col, features in zip(cols, result.seeds):
            col.markdown(seed_card_html(features), unsafe_allow_html=True)
        st.caption(f'Blended fingerprint: {seed.artist}')
    else:
        st.markdown(seed_card_html(seed), unsafe_allow_html=True)

    for note in result.notes:
        st.info(note)
    if not result.matches:
        return

    shown = apply_filters(result.matches, filters)
    sources = ' · '.join(f'{kind} {count}' for kind, count in result.sources.items())
    st.caption(f'{len(shown)} of {len(result.matches)} shown · {result.fingerprinted} fingerprinted from '
               f'{result.considered} candidates, {result.shortlisted} deep-checked · '
               f'{result.requests_made} requests, {result.cache_hits} from cache'
               + (f' · sources: {sources}' if sources else ''))

    columns = st.columns(3)
    for index, match in enumerate(shown):
        with columns[index % 3]:
            render_card(match, seed)
            st.write('')

    st.divider()
    tab_table, tab_axes = st.tabs(['Every statistic', 'How the axes behaved'])
    with tab_table:
        rows = [m.as_row() for m in shown]
        frame = pd.DataFrame(rows)
        front = ['artist', 'album', 'year', 'similarity', 'connected', 'reasons', 'listeners', 'listens_each',
                 'fans', 'runtime_min', 'tracks', 'bpm_mean', 'gain_mean', 'from', 'label', 'producers',
                 'engineers', 'studios', 'shared_personnel', 'shared_producers', 'shared_engineers',
                 'shared_studios', 'shared_labels', 'shared_similar_artists', 'genre_tags', 'mood_tags',
                 'critic_scores', 'mb_rating', 'discogs_rating', 'have', 'want', 'editions']
        ordered = [c for c in front if c in frame.columns] + [c for c in frame.columns if c not in front]
        frame = frame[ordered]
        st.dataframe(frame, hide_index=True, width='stretch',
                     column_config={
                         'similarity': st.column_config.ProgressColumn('match', min_value=0.0, max_value=1.0,
                                                                       format='%.3f'),
                         'url': st.column_config.LinkColumn('MusicBrainz', display_text='open'),
                         'image_url': None, 'recording_mbids': None,
                     })
        d1, d2 = st.columns(2)
        stem = f'radius_{seed.artist}_{seed.title}'.replace(' ', '_').replace('/', '_')
        d1.download_button('⬇️ CSV', frame.to_csv(index=False).encode('utf-8'), f'{stem}.csv',
                           'text/csv', key='dl_csv', width='stretch')
        payload = json.dumps({'seed': seed.as_row(), 'seeds': [f.as_row() for f in result.seeds],
                              'results': rows, 'notes': result.notes, 'timings': result.timings,
                              'sources': result.sources}, indent=2)
        d2.download_button('⬇️ JSON', payload.encode('utf-8'), f'{stem}.json', 'application/json',
                           key='dl_json', width='stretch')
    with tab_axes:
        render_axis_summary(shown, result)


def render_axis_summary(matches, result):
    if not matches:
        return
    st.caption('Mean closeness per axis across the shown results (1 = identical), and how often each '
               'evidence axis fired. An axis measured for few records is a thin signal.')
    rows = []
    for group, axes in AXIS_GROUPS.items():
        for axis in axes:
            distances = [m.axes[axis] for m in matches if axis in m.axes]
            fired = sum(1 for m in matches if axis in m.strengths)
            if not distances:
                continue
            rows.append({'group': group, 'axis': AXIS_LABELS[axis],
                         'closeness': round(1.0 - sum(distances) / len(distances), 3),
                         'measured': f'{len(distances)}/{len(matches)}',
                         'fired': f'{fired}/{len(matches)}' if fired else ''})
    st.dataframe(pd.DataFrame(rows), hide_index=True, width='stretch',
                 column_config={'closeness': st.column_config.ProgressColumn('closeness', min_value=0.0,
                                                                              max_value=1.0, format='%.2f')})
    timings = ' · '.join(f'{stage} {seconds}s' for stage, seconds in result.timings.items())
    if timings:
        st.caption(f'Timings: {timings}')


# ---------------------------------------------------------------------------
# Compare dialog
# ---------------------------------------------------------------------------

STAT_ROWS = [
    ('Year', lambda f: f.year),
    ('Country', lambda f: f.artist_area),
    ('Act', lambda f: f.artist_type),
    ('Years into career', lambda f: f.career_stage),
    ('Label', lambda f: ', '.join(sorted(f.labels.values())) or f.deezer_label),
    ('Producers', lambda f: ', '.join(f.producer_names)),
    ('Engineers', lambda f: ', '.join(sorted(f.engineers.values()))),
    ('Studios', lambda f: ', '.join(f.studio_names)),
    ('Guests', lambda f: ', '.join(sorted(f.performers.values()))),
    ('People around the artist', lambda f: ', '.join(n for m, n in f.personnel.items() if m != f.artist_mbid)),
    ('Listeners (ListenBrainz)', lambda f: fmt_int(f.listeners)),
    ('Listens per listener', lambda f: f'{f.devotion:.1f}' if f.listeners else ''),
    ('Deezer fans', lambda f: fmt_int(f.fans)),
    ('Last.fm listeners', lambda f: fmt_int(f.lastfm_listeners)),
    ('Standing in discography', lambda f: f'{f.canonicity:.0%}' if f.canonicity is not None else ''),
    ('Editions', lambda f: f.editions or ''),
    ('Released in', lambda f: ', '.join(sorted(f.release_countries))),
    ('Tracks', lambda f: f.track_count or ''),
    ('Runtime', lambda f: fmt_minutes(f.runtime_seconds)),
    ('Mean track', lambda f: f'{f.mean_track_seconds / 60:.1f} min' if f.mean_track_seconds else ''),
    ('Track length spread', lambda f: f'{f.track_length_spread:.2f}' if f.mean_track_seconds else ''),
    ('BPM', lambda f: f'{f.bpm_mean:.0f} (±{f.bpm_spread:.0f})' if f.bpm_mean else ''),
    ('Loudness gain', lambda f: f'{f.gain_mean:.1f} dB' if f.gain_mean is not None else ''),
    ('Explicit', lambda f: {True: 'yes', False: 'no'}.get(f.explicit, '')),
    ('MusicBrainz genres', lambda f: ', '.join(f.mb_genres)),
    ('Genre tags', lambda f: ', '.join(t for t in f.top_tags if t in f.genre_profile)[:160]),
    ('Mood tags', lambda f: ', '.join(t for t in f.top_tags if t in f.mood_profile)[:160]),
    ('Artist lineage', lambda f: ', '.join(sorted(f.artist_profile, key=f.artist_profile.get, reverse=True)[:6])),
    ('Discogs styles', lambda f: ', '.join(f.styles)),
    ('Critic scores', lambda f: ', '.join(f'{k} {v:.2f}' for k, v in f.critic_scores.items())),
    ('MusicBrainz rating', lambda f: f'{f.mb_rating:.2f} ({f.mb_rating_votes} votes)' if f.mb_rating else ''),
    ('Discogs rating', lambda f: f'{f.discogs_rating:.2f} ({f.discogs_votes} votes)' if f.discogs_rating else ''),
    ('Discogs have / want', lambda f: f'{f.have:,} / {f.want:,}' if f.have or f.want else ''),
    ('Tag definition', lambda f: f'{f.definition:.2f}' if f.profile else ''),
    ('Formats', lambda f: ', '.join(f.formats)),
    ('Catalogue numbers', lambda f: ', '.join(f.catalog_numbers)),
]


def axis_rows_html(match):
    parts = []
    for group, axes in AXIS_GROUPS.items():
        for axis in axes:
            if axis not in match.axes:
                continue
            if axis in match.strengths:
                strength = match.strengths[axis]
                bar = f'<span class="ev" style="width:{int(strength * 100)}%"></span>'
                value = f'shared {strength:.2f}'
            else:
                closeness = 1.0 - match.axes[axis]
                bar = f'<span style="width:{int(closeness * 100)}%"></span>'
                value = f'{closeness:.2f}'
            parts.append(f'<div class="rad-axis"><div class="l">{html.escape(AXIS_LABELS[axis])}</div>'
                         f'<div class="bar">{bar}</div><div class="v">{value}</div></div>')
    return ''.join(parts)


@st.dialog('Compare', width='large')
def compare_dialog(seed, match):
    st.markdown(CSS, unsafe_allow_html=True)
    other = match.features
    left, right = st.columns(2)
    left.markdown(seed_card_html(seed), unsafe_allow_html=True)
    right.markdown(seed_card_html(other), unsafe_allow_html=True)
    st.markdown(f'**{int(round(match.similarity * 100))}% match** over {len(match.axes)} axes'
                + (' · connected' if match.connected else ''))
    for reason in match.reasons:
        st.markdown(f'- {reason}')
    if match.shared_neighbours:
        st.caption('Similar artists in common: ' + ', '.join(match.shared_neighbours))
    st.markdown('**Axes**')
    st.markdown(axis_rows_html(match), unsafe_allow_html=True)
    st.markdown('**Every statistic, side by side**')
    # Fixed column names: two records can share the first 40 characters of a
    # title, and a repeated key would collapse the two columns into one.
    seed_column, match_column = 'seed', 'match'
    rows = []
    for label, getter in STAT_ROWS:
        a, b = getter(seed), getter(other)
        a = '' if a in (None, '') else str(a)
        b = '' if b in (None, '') else str(b)
        if a or b:
            rows.append({'statistic': label, seed_column: a, match_column: b})
    st.dataframe(pd.DataFrame(rows), hide_index=True, width='stretch',
                 height=min(38 * len(rows) + 40, 640),
                 column_config={
                     seed_column: st.column_config.TextColumn(f'{seed.artist} — {seed.title}'),
                     match_column: st.column_config.TextColumn(f'{other.artist} — {other.title}'),
                 })
    links = {k: v for k, v in other.links.items() if v}
    if other.url:
        links.setdefault('musicbrainz', other.url)
    if links:
        st.caption(' · '.join(f'[{k}]({v})' for k, v in sorted(links.items())))


# ---------------------------------------------------------------------------
# Library view
# ---------------------------------------------------------------------------

def on_note_change(key):
    library().set_note(key, st.session_state.get(f'note_{key}') or '')


def on_rating_change(key):
    rating = st.session_state.get(f'rate_{key}')
    if rating is None:
        library().unrate(key)
    else:
        library().rate(key, rating)


def render_library():
    lib = library()
    if not st.session_state.legacy_imported:
        imported = lib.import_legacy()
        st.session_state.legacy_imported = True
        if imported:
            st.toast(f'Imported {imported} albums from the old ratings and bookmarks.')
    entries = lib.all()
    st.markdown('<div class="rad-hero"><h1>Library</h1><p>Saved and rated records. '
                'Any of them can seed a search, alone or blended.</p></div>', unsafe_allow_html=True)
    if not entries:
        st.caption('Nothing saved yet. Use Save on a result card.')
        return

    labels = {e['key']: f'{e["artist"]} — {e["title"]}' for e in entries if e.get('mbid')}
    picked = st.multiselect('Seed from the library', list(labels), format_func=labels.get,
                            max_selections=MAX_SEEDS, key='lib_pick')
    if st.button('Find what connects them', type='primary', disabled=not picked, key='lib_go'):
        by_key = {e['key']: e for e in entries}
        set_seeds([seed_spec(by_key[k]['mbid'], by_key[k]['artist'], by_key[k]['title'],
                             by_key[k].get('year'), by_key[k].get('image_url') or '') for k in picked])
        st.rerun()

    for entry in entries:
        with st.container(border=True):
            c_art, c_text = st.columns([1, 7])
            c_art.markdown(art(entry.get('image_url') or ''), unsafe_allow_html=True)
            year = f' ({entry["year"]})' if entry.get('year') else ''
            flags = []
            if entry.get('saved'):
                flags.append('saved')
            if not entry.get('mbid'):
                flags.append('not yet matched to MusicBrainz')
            if entry.get('from_seed'):
                flags.append(f'found via {entry["from_seed"]}')
            c_text.markdown(f'**{entry["artist"]}** — {entry["title"]}{year}  \n'
                            f'<span class="rad-muted">{" · ".join(flags)}</span>', unsafe_allow_html=True)
            # Note and rating are written on change, never by diffing the
            # widget against the file each rerun: a widget keeps the value it
            # was first drawn with, so a diff would write a stale value back
            # over anything that changed underneath (a resolved legacy entry
            # merging its rating in, say).
            c_note, c_rating, a1, a2, a3 = c_text.columns([4, 2, 1, 1, 1])
            c_note.text_input('Note', entry.get('note') or '', key=f'note_{entry["key"]}',
                              label_visibility='collapsed', placeholder='a note to yourself',
                              on_change=on_note_change, args=(entry['key'],))
            options = [None] + [x / 2 for x in range(0, 21)]
            current = entry.get('rating')
            c_rating.selectbox('Rating', options,
                               index=options.index(current) if current in options else 0,
                               format_func=lambda v: 'unrated' if v is None else f'{v:g} / 10',
                               key=f'rate_{entry["key"]}', label_visibility='collapsed',
                               on_change=on_rating_change, args=(entry['key'],))
            if entry.get('mbid'):
                if a1.button('Seed', key=f'lib_seed_{entry["key"]}', width='stretch'):
                    set_seeds([seed_spec(entry['mbid'], entry['artist'], entry['title'], entry.get('year'),
                                         entry.get('image_url') or '')])
                    st.rerun()
                if a2.button('+ Blend', key=f'lib_blend_{entry["key"]}', width='stretch',
                             disabled=len(st.session_state.seeds) >= MAX_SEEDS):
                    add_seed(seed_spec(entry['mbid'], entry['artist'], entry['title'], entry.get('year'),
                                       entry.get('image_url') or ''))
                    st.rerun()
            else:
                if a1.button('Match', key=f'lib_match_{entry["key"]}', width='stretch',
                             help='Look the record up on MusicBrainz so it can seed a search'):
                    hits = search_albums(services(), artist=entry['artist'], album=entry['title'], limit=5)
                    if hits:
                        lib.resolve(entry['key'], hits[0]['mbid'], year=hits[0]['year'] or None,
                                    url=f'https://musicbrainz.org/release-group/{hits[0]["mbid"]}')
                        st.toast(f'Matched {entry["title"]}.')
                    else:
                        st.toast(f'MusicBrainz has no match for {entry["title"]}.')
                    st.rerun()
            if a3.button('Remove', key=f'lib_rm_{entry["key"]}', width='stretch'):
                lib.remove(entry['key'])
                st.rerun()


# ---------------------------------------------------------------------------
# Find view and router
# ---------------------------------------------------------------------------

def render_find(settings, filters):
    st.markdown('<div class="rad-hero"><h1>What is this record connected to?</h1>'
                '<p>Name an album. Radius finds the records tied to it by the people who made it, '
                'the circle it was produced in, the listeners who pair them, and the sound.</p></div>',
                unsafe_allow_html=True)
    render_search()

    seeds = st.session_state.seeds
    if seeds:
        label = 'Find connections' if len(seeds) == 1 else f'Find what connects these {len(seeds)}'
        if st.button(label, type='primary', key='run_go'):
            st.session_state.run_requested = True
    if st.session_state.run_requested and seeds:
        st.session_state.run_requested = False
        # Only a successful run reruns the script (to draw the results with
        # fresh filter widgets); an error stays on screen.
        if run_engine(settings):
            st.rerun()

    result = st.session_state.result
    if result is None:
        st.caption('Try: `Slint - Spiderland` · `Bon Iver - For Emma, Forever Ago` · `Portishead - Dummy` · '
                   '`Talk Talk - Laughing Stock`')
        return
    render_results(result, filters)


st.markdown(CSS, unsafe_allow_html=True)
settings, filters = render_sidebar()
if st.session_state.view == 'library':
    render_library()
else:
    render_find(settings, filters)
