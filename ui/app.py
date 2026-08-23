#!/usr/bin/env python3
"""
Streamlit UI for AOTY Crawler

Three views, switched via a top nav: Home, New Scrape, Past Scrapes.
Progress is completion-based (albums scraped / target albums), computed from
each job's own parameters rather than elapsed time, and read from small JSON
status files the spider writes as it works (see aoty_crawler/utils/job_tracker.py).
"""

import sys
import os
import subprocess
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
import pandas as pd

from aoty_crawler.utils.data_loader import (
    load_all_albums, load_albums_from_json, filter_albums, filter_invalid_albums
)
from aoty_crawler.utils import job_tracker
from aoty_crawler.utils.genres_manager import (
    get_all_genres, get_parent_genres, get_genre_with_children, discover_from_albums
)

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(PROJECT_ROOT, 'data', 'output')
JOBS_DIR = job_tracker.jobs_dir_for(DATA_DIR)

st.set_page_config(
    page_title="AOTY Explorer",
    page_icon="🎵",
    layout="wide",
    initial_sidebar_state="expanded"
)

DEFAULTS = {
    'view': 'home',
    'active_job_id': None,
    'scrape_process': None,
    'scrape_job_id': None,
    'scrape_start_time': None,
}
for key, value in DEFAULTS.items():
    if key not in st.session_state:
        st.session_state[key] = value


def goto(view, job_id=None):
    st.session_state.view = view
    if job_id is not None:
        st.session_state.active_job_id = job_id


def get_jobs():
    return job_tracker.list_jobs(JOBS_DIR)


def running_process_job():
    """The job_id tied to a subprocess this session actually launched, if it's still running."""
    proc = st.session_state.scrape_process
    if proc is not None and proc.poll() is None:
        return st.session_state.scrape_job_id
    return None


def fmt_duration(start_iso, end_iso=None):
    try:
        start = datetime.fromisoformat(start_iso)
    except (TypeError, ValueError):
        return "?"
    end = datetime.fromisoformat(end_iso) if end_iso else datetime.utcnow()
    secs = int((end - start).total_seconds())
    if secs < 60:
        return f"{secs}s"
    mins, secs = divmod(secs, 60)
    if mins < 60:
        return f"{mins}m {secs}s"
    hours, mins = divmod(mins, 60)
    return f"{hours}h {mins}m"


def job_progress_fraction(job):
    target = job.get('target_total')
    completed = job.get('completed', 0)
    if not target:
        return None
    return max(0.0, min(1.0, completed / target))


# ---------------------------------------------------------------------------
# Top navigation
# ---------------------------------------------------------------------------

st.title("🎵 AOTY Explorer")

jobs = get_jobs()
live_job_id = running_process_job()

# Plain buttons (not segmented_control/radio) are used deliberately: those
# widgets persist their selection across every future rerun, which fights
# with the programmatic view transitions below (e.g. jumping into the
# progress view right after starting a scrape). A button is only True on
# the exact rerun it was clicked, so it can't clobber state afterwards.
current_view = st.session_state.view
nav_col1, nav_col2, nav_col3 = st.columns(3)
with nav_col1:
    if st.button("🏠 Home", use_container_width=True, key="nav_home",
                 type="primary" if current_view == 'home' else "secondary"):
        goto('home')
        st.rerun()
with nav_col2:
    if st.button("🚀 New Scrape", use_container_width=True, key="nav_new_scrape",
                 type="primary" if current_view == 'new_scrape' else "secondary"):
        goto('new_scrape')
        st.rerun()
with nav_col3:
    if st.button("📁 Past Scrapes", use_container_width=True, key="nav_past_scrapes",
                 type="primary" if current_view == 'past_scrapes' else "secondary"):
        goto('past_scrapes')
        st.rerun()

if live_job_id and st.session_state.view not in ('progress', 'past_scrapes', 'results'):
    # Only steer into progress automatically right after a launch; once the
    # user has navigated elsewhere, let them stay there (Past Scrapes always
    # offers a "View progress" button for any running job).
    goto('progress', live_job_id)


# ---------------------------------------------------------------------------
# New Scrape form
# ---------------------------------------------------------------------------

def render_new_scrape():
    st.header("🚀 Start a New Scrape")

    all_genres_list = sorted(get_all_genres())

    # A selectbox already lets you type to filter its own options, so a
    # separate search box next to it would just do the same thing twice.
    selected_genre = st.selectbox(
        f"Genre ({len(all_genres_list)} available — type to search)",
        all_genres_list,
        index=None,
        placeholder="e.g. 'rock', 'ethereal', 'hop'...",
    )

    with st.expander("📂 Browse genres by category instead"):
        parent_genres_list = get_parent_genres()
        selected_parent = st.selectbox("Category", parent_genres_list, key="browse_parent")
        genre_info = get_genre_with_children(selected_parent)
        if genre_info["has_children"]:
            browse_choice = st.selectbox("Subgenre", genre_info["children"], key="browse_child")
        else:
            browse_choice = selected_parent
        if st.button("Use this genre", key="use_browsed_genre"):
            selected_genre = browse_choice
            st.session_state["_pending_genre"] = browse_choice

    if st.session_state.get("_pending_genre"):
        selected_genre = st.session_state["_pending_genre"]

    st.markdown("---")

    current_year = datetime.utcnow().year
    year_range = st.slider(
        "Years to cover",
        min_value=1970, max_value=current_year,
        value=(current_year - 1, current_year),
    )
    start_year = year_range[1]
    years_back = year_range[1] - year_range[0] + 1

    albums_per_year = st.select_slider(
        "Albums per year",
        options=[10, 25, 50, 100, 150, 250, 500],
        value=100,
        help="How many top-rated albums to pull for each year in the range above.",
    )

    est_total = albums_per_year * years_back
    st.caption(
        f"📊 This will scrape up to **{est_total} albums** "
        f"({albums_per_year}/year × {years_back} year{'s' if years_back != 1 else ''})."
    )

    with st.expander("⚙️ Advanced options"):
        test_mode = st.checkbox(
            "Test mode", value=False,
            help="Faster and lighter: fewer albums, shorter delays between requests."
        )
        resume = st.checkbox(
            "Resume", value=False,
            help="Skip albums already present in a previous scrape's output before re-running."
        )
        custom_output_dir = st.text_input("Custom output directory", value="")

    st.markdown("---")

    disabled = not selected_genre or live_job_id is not None
    if live_job_id:
        st.info("A scrape is already running — wait for it to finish before starting another.")

    if st.button("🚀 Start Scrape", type="primary", disabled=disabled, key="start_scrape_submit"):
        job_id = job_tracker.new_job_id()
        cmd = [sys.executable, "-m", "cli", "scrape",
               "--genre", selected_genre,
               "--start-year", str(start_year),
               "--years-back", str(years_back),
               "--albums-per-year", str(albums_per_year),
               "--job-id", job_id]
        if test_mode:
            cmd.append("--test-mode")
        if resume:
            cmd.append("--resume")
        if custom_output_dir.strip():
            cmd.extend(["--output-dir", custom_output_dir.strip()])

        st.session_state.scrape_process = subprocess.Popen(cmd, cwd=PROJECT_ROOT)
        st.session_state.scrape_job_id = job_id
        st.session_state.scrape_start_time = time.time()
        st.session_state["_pending_genre"] = None
        goto('progress', job_id)
        st.rerun()


# ---------------------------------------------------------------------------
# Progress view (completion-based, not time-based)
# ---------------------------------------------------------------------------

def render_progress():
    job_id = st.session_state.active_job_id
    job = job_tracker.load_job(job_id, JOBS_DIR)

    if not job:
        st.info("No progress to show yet — waiting for the scrape to start writing status...")
        time.sleep(1)
        st.rerun()
        return

    params = job.get('params', {})
    st.header(f"🔄 Scraping: {params.get('genre', 'unknown genre')}")
    st.caption(
        f"Years {params.get('end_year')}–{params.get('start_year')} · "
        f"{params.get('albums_per_year')} albums/year"
        + (" · test mode" if params.get('test_mode') else "")
    )

    status = job.get('status', 'running')
    completed = job.get('completed', 0)
    target = job.get('target_total')
    frac = job_progress_fraction(job)

    if frac is not None:
        st.progress(frac, text=f"{completed} / {target} albums scraped ({frac*100:.0f}%)")
    else:
        st.progress(0.0, text=f"{completed} albums scraped (total unknown for all-genre runs)")

    where = []
    if job.get('current_genre'):
        where.append(job['current_genre'])
    if job.get('current_year'):
        where.append(str(job['current_year']))
    if where:
        st.caption(f"📍 Currently on: {' · '.join(where)}")

    st.caption(f"⏱️ Elapsed: {fmt_duration(job.get('started_at'), job.get('ended_at'))}")

    col1, col2 = st.columns(2)
    with col1:
        if status == 'running' and st.session_state.scrape_process is not None:
            if st.button("⛔ Cancel scrape", key="cancel_scrape"):
                proc = st.session_state.scrape_process
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                # The killed process never gets to write its own final status,
                # so record the cancellation here or the UI would show
                # "running" forever.
                job_tracker.update_job(
                    job_id, JOBS_DIR,
                    status='cancelled',
                    ended_at=datetime.utcnow().isoformat(),
                    finish_reason='cancelled_by_user',
                )
                st.session_state.scrape_process = None
                st.rerun()
    with col2:
        if status in ('completed', 'failed', 'cancelled'):
            if st.button("📊 View Results", type="primary", key="progress_view_results"):
                goto('results', job_id)
                st.rerun()

    if status == 'running':
        time.sleep(2)
        st.rerun()
    elif status == 'completed':
        st.success(f"✅ Done — {completed} albums scraped.")
    elif status == 'failed':
        st.error(f"❌ Scrape stopped early ({job.get('finish_reason', 'unknown reason')}).")
    elif status == 'cancelled':
        st.warning(f"⛔ Cancelled — {completed} albums scraped before stopping.")


# ---------------------------------------------------------------------------
# Past scrapes list
# ---------------------------------------------------------------------------

def render_past_scrapes():
    st.header("📁 Past Scrapes")

    if not jobs:
        st.info("No scrapes yet.")
        if st.button("🚀 Start your first scrape", type="primary", key="past_scrapes_start_first"):
            goto('new_scrape')
            st.rerun()
        return

    if st.button("🗂️ Browse ALL scraped data combined", use_container_width=True, key="browse_all_data"):
        goto('results', None)
        st.rerun()

    st.markdown("---")

    status_icon = {'running': '🔄', 'completed': '✅', 'failed': '❌', 'cancelled': '⛔'}

    for job in jobs:
        params = job.get('params', {})
        icon = status_icon.get(job.get('status'), '❓')
        with st.container(border=True):
            c1, c2, c3, c4 = st.columns([3, 2, 2, 2])
            with c1:
                st.write(f"**{icon} {params.get('genre', 'Unknown genre')}**")
                st.caption(f"Years {params.get('end_year')}–{params.get('start_year')}")
            with c2:
                st.caption(f"{job.get('completed', 0)} albums scraped")
                if job.get('target_total'):
                    st.caption(f"target: {job['target_total']}")
            with c3:
                started = job.get('started_at', '')[:19].replace('T', ' ')
                st.caption(f"🕒 {started}")
                st.caption(f"⏱️ {fmt_duration(job.get('started_at'), job.get('ended_at'))}")
            with c4:
                if job.get('status') == 'running':
                    if st.button("View progress", key=f"prog_{job['job_id']}"):
                        goto('progress', job['job_id'])
                        st.rerun()
                else:
                    if job.get('output_files'):
                        if st.button("View results", key=f"res_{job['job_id']}"):
                            goto('results', job['job_id'])
                            st.rerun()
                    else:
                        st.caption("No data saved")

                    confirm_key = f"confirm_delete_{job['job_id']}"
                    if st.session_state.get(confirm_key):
                        st.caption("Delete this scrape permanently?")
                        dc1, dc2 = st.columns(2)
                        with dc1:
                            if st.button("✅ Yes, delete", key=f"confirm_yes_{job['job_id']}"):
                                job_tracker.delete_job(job['job_id'], JOBS_DIR)
                                st.session_state[confirm_key] = False
                                st.rerun()
                        with dc2:
                            if st.button("Cancel", key=f"confirm_no_{job['job_id']}"):
                                st.session_state[confirm_key] = False
                                st.rerun()
                    else:
                        if st.button("🗑️ Delete", key=f"del_{job['job_id']}"):
                            st.session_state[confirm_key] = True
                            st.rerun()


# ---------------------------------------------------------------------------
# Results: searchable + sortable
# ---------------------------------------------------------------------------

def load_results_for_job(job_id):
    """Returns (albums, stats) where stats reports how many entries were
    dropped as duplicates or as invalid/incomplete, so the UI can tell the
    user something was hidden instead of the count just quietly being off."""
    if job_id is None:
        return load_all_albums(output_dir=DATA_DIR, return_stats=True)
    job = job_tracker.load_job(job_id, JOBS_DIR)
    json_path = (job or {}).get('output_files', {}).get('json')
    if json_path and not os.path.isabs(json_path):
        # Older job files (written before paths were stored absolute) hold a
        # path relative to whatever cwd the scraping process had. Resolve it
        # against the project root as a best-effort fallback rather than
        # just reporting "no albums found".
        json_path = os.path.join(PROJECT_ROOT, json_path)
    if json_path and os.path.exists(json_path):
        raw = load_albums_from_json(json_path)
        valid = filter_invalid_albums(raw)
        return valid, {'duplicates_removed': 0, 'invalid_removed': len(raw) - len(valid)}
    return [], {'duplicates_removed': 0, 'invalid_removed': 0}


def render_results():
    job_id = st.session_state.active_job_id
    albums, load_stats = load_results_for_job(job_id)

    if job_id:
        job = job_tracker.load_job(job_id, JOBS_DIR)
        params = (job or {}).get('params', {})
        st.header(f"📊 Results: {params.get('genre', 'scrape')}")
    else:
        st.header("📊 All Scraped Data")

    hidden_notes = []
    if load_stats.get('duplicates_removed'):
        hidden_notes.append(f"{load_stats['duplicates_removed']} duplicate re-scrapes (kept the newest)")
    if load_stats.get('invalid_removed'):
        hidden_notes.append(f"{load_stats['invalid_removed']} incomplete entries (no scores/reviews or genres)")
    if hidden_notes:
        st.caption(f"ℹ️ Hidden from results: {'; '.join(hidden_notes)}.")

    if not albums:
        st.info("No albums found for this scrape.")
        return

    discovery_result = discover_from_albums(albums)
    if discovery_result["new_genres"]:
        st.toast(f"🆕 Discovered {len(discovery_result['new_genres'])} new genre(s)!")

    with st.sidebar:
        st.header("🔍 Filter & Search")
        all_genres = sorted(set(g for a in albums for g in a.get('genres', [])))
        selected_genres = st.multiselect("Genres", all_genres, default=[])
        match_all_genres = st.checkbox(
            "Must match ALL selected genres", value=False,
            help="Off: album needs any one of the selected genres. On: album must have every one of them.",
        )

        min_critic_score, max_critic_score = st.slider("Critic score", 0, 100, (0, 100))
        min_user_score, max_user_score = st.slider("User score", 0, 100, (0, 100))

        max_critic_reviews_seen = max((a.get('critic_review_count') or 0) for a in albums) if albums else 0
        max_user_reviews_seen = max((a.get('user_review_count') or 0) for a in albums) if albums else 0

        st.caption("Critic reviews")
        min_critic_reviews, max_critic_reviews = st.slider(
            "Critic reviews", 0, max(max_critic_reviews_seen, 1), (0, max(max_critic_reviews_seen, 1)),
            label_visibility="collapsed",
        )
        st.caption("User reviews")
        min_user_reviews, max_user_reviews = st.slider(
            "User reviews", 0, max(max_user_reviews_seen, 1), (0, max(max_user_reviews_seen, 1)),
            label_visibility="collapsed",
        )

        years_seen = sorted({a.get('scrape_year') for a in albums if a.get('scrape_year')})
        selected_year = st.selectbox("Year", options=["All"] + years_seen[::-1])

        text_search = st.text_input("Search title / artist / description")

    filtered = filter_albums(
        albums,
        **({'genres_all': selected_genres} if match_all_genres and selected_genres else
           {'genres': selected_genres} if selected_genres else {}),
        min_score=min_critic_score if min_critic_score > 0 else None,
        max_score=max_critic_score if max_critic_score < 100 else None,
        min_user_score=min_user_score if min_user_score > 0 else None,
        max_user_score=max_user_score if max_user_score < 100 else None,
        min_critic_reviews=min_critic_reviews if min_critic_reviews > 0 else None,
        max_critic_reviews=max_critic_reviews if max_critic_reviews < max_critic_reviews_seen else None,
        min_user_reviews=min_user_reviews if min_user_reviews > 0 else None,
        max_user_reviews=max_user_reviews if max_user_reviews < max_user_reviews_seen else None,
        year=selected_year if selected_year != "All" else None,
        search=text_search if text_search else None,
    )

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Albums", len(filtered))
    with col2:
        st.metric("Unique Genres", len(set(g for a in filtered for g in a.get('genres', []))))
    with col3:
        st.metric("With Scores", sum(1 for a in filtered if a.get('critic_score') or a.get('user_score')))
    with col4:
        st.metric("Total Reviews", sum((a.get('critic_review_count') or 0) + (a.get('user_review_count') or 0) for a in filtered))

    if not filtered:
        st.warning("Nothing matches the current filters.")
        return

    df = pd.DataFrame(filtered)
    for col in ('genres', 'genre_tags'):
        if col in df.columns:
            df[col] = df[col].apply(lambda v: ', '.join(v) if isinstance(v, list) else v)

    display_cols = [c for c in [
        'cover_image_url', 'title', 'artist_name', 'scrape_year',
        'critic_score', 'user_score', 'critic_review_count', 'user_review_count',
        'genres', 'url'
    ] if c in df.columns]

    st.subheader("💿 Albums")
    st.caption("Click a column header to sort. Use the search icon in the table toolbar to filter across all columns.")
    st.dataframe(
        df[display_cols],
        use_container_width=True,
        height=600,
        hide_index=True,
        column_config={
            'cover_image_url': st.column_config.ImageColumn("Cover", width="small"),
            'title': st.column_config.TextColumn("Title"),
            'artist_name': st.column_config.TextColumn("Artist"),
            'scrape_year': st.column_config.NumberColumn("Year", format="%d"),
            'critic_score': st.column_config.ProgressColumn("Critic", min_value=0, max_value=100, format="%.0f"),
            'user_score': st.column_config.ProgressColumn("User", min_value=0, max_value=100, format="%.0f"),
            'critic_review_count': st.column_config.NumberColumn("Critic Reviews"),
            'user_review_count': st.column_config.NumberColumn("User Reviews"),
            'genres': st.column_config.TextColumn("Genres"),
            'url': st.column_config.LinkColumn("Link", display_text="Open"),
        },
    )


# ---------------------------------------------------------------------------
# Home
# ---------------------------------------------------------------------------

def render_home():
    if not jobs:
        st.subheader("👋 Welcome — let's find some albums.")
        st.write("You haven't run a scrape yet. Start one to begin building your local album database.")
        if st.button("🚀 Start a Scrape", type="primary", key="home_start_scrape"):
            goto('new_scrape')
            st.rerun()
        return

    completed_jobs = [j for j in jobs if j.get('status') == 'completed']
    running_jobs = [j for j in jobs if j.get('status') == 'running']

    total_albums = sum(j.get('albums_count', 0) for j in completed_jobs)
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total Scrapes", len(jobs))
    with col2:
        st.metric("Albums Collected", total_albums)
    with col3:
        st.metric("Currently Running", len(running_jobs))

    st.markdown("---")

    most_recent = jobs[0]
    params = most_recent.get('params', {})
    st.subheader("Most recent scrape")
    with st.container(border=True):
        st.write(f"**{params.get('genre', 'Unknown')}** — {most_recent.get('completed', 0)} albums")
        st.caption(f"Started {most_recent.get('started_at', '')[:19].replace('T', ' ')}")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("🚀 New Scrape", use_container_width=True, key="home_new_scrape"):
            goto('new_scrape')
            st.rerun()
    with col2:
        if st.button("📁 View Past Scrapes", use_container_width=True, key="home_view_past_scrapes"):
            goto('past_scrapes')
            st.rerun()


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

view = st.session_state.view
if view == 'home':
    render_home()
elif view == 'new_scrape':
    render_new_scrape()
elif view == 'progress':
    render_progress()
elif view == 'past_scrapes':
    render_past_scrapes()
elif view == 'results':
    render_results()
else:
    render_home()
