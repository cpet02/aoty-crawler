#!/usr/bin/env python3
"""
Streamlit UI for AOTY Crawler - FIXED GENRE SELECTION
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
import pandas as pd
from aoty_crawler.utils.data_loader import load_all_albums, filter_albums
from genres_manager import (
    get_all_genres, get_parent_genres, get_genre_with_children,
    discover_from_albums, get_stats
)

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(PROJECT_ROOT, 'data', 'output')

st.set_page_config(
    page_title="AOTY Explorer",
    page_icon="🎵",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.title("🎵 AOTY Explorer")
st.markdown("Album of the Year Data Dashboard")

def load_data():
    try:
        if not os.path.exists(DATA_DIR):
            return []
        albums = load_all_albums(output_dir=DATA_DIR)
        if albums:
            discovery_result = discover_from_albums(albums)
            if discovery_result["new_genres"]:
                st.toast(f"🆕 Discovered {len(discovery_result['new_genres'])} new genre(s)!")
        return albums
    except Exception as e:
        st.error(f"Error loading data: {e}")
        return []

if 'albums' not in st.session_state:
    with st.spinner("Loading album data..."):
        st.session_state.albums = load_data()

if 'scrape_running' not in st.session_state:
    st.session_state.scrape_running = False

if st.session_state.scrape_running:
    st.warning("⚠️ A scrape is currently running in the background.")

albums = st.session_state.albums

with st.sidebar:
    st.header("🔍 Search Filters")
    
    all_genres = sorted(set(genre for album in albums for genre in album.get('genres', [])))
    selected_genres = st.multiselect("Genres", all_genres, default=[])
    
    col1, col2 = st.columns(2)
    with col1:
        min_critic_score = st.number_input("Min Critic Score", min_value=0.0, max_value=100.0, value=0.0, step=1.0)
    with col2:
        min_user_score = st.number_input("Min User Score", min_value=0.0, max_value=100.0, value=0.0, step=1.0)
    
    if albums:
        min_year = min((album.get('scrape_year') or 2026) for album in albums)
        max_year = max((album.get('scrape_year') or 2026) for album in albums)
        year_options = ["All"] + list(range(max_year, min_year - 1, -1))
    else:
        year_options = ["All"]
    selected_year = st.selectbox("Year", options=year_options, index=0)
    
    filtered_albums = filter_albums(
        albums,
        genres=selected_genres if selected_genres else None,
        min_score=min_critic_score if min_critic_score > 0 else None,
        min_user_score=min_user_score if min_user_score > 0 else None,
        year=int(selected_year) if selected_year != "All" else None
    )
    
    st.markdown("---")
    st.header("🚀 Start New Scrape")
    
    all_genres_list = get_all_genres()
    parent_genres_list = get_parent_genres()
    st.caption(f"🎵 {len(all_genres_list)} total genres available")
    
    # FIXED: Use session state to track which tab and what genre is selected
    if 'scrape_genre_tab' not in st.session_state:
        st.session_state.scrape_genre_tab = 'search'
    if 'scrape_genre_search' not in st.session_state:
        st.session_state.scrape_genre_search = all_genres_list[0] if all_genres_list else ""
    if 'scrape_genre_hierarchy' not in st.session_state:
        st.session_state.scrape_genre_hierarchy = parent_genres_list[0] if parent_genres_list else ""
    
    tab1, tab2 = st.tabs(["🔍 Search", "📂 Browse"])
    
    with tab1:
        st.session_state.scrape_genre_tab = 'search'
        genre_search_text = st.text_input(
            "Search genres",
            placeholder="Type to filter (e.g., 'ethereal', 'wave', 'rock')...",
            help="Find genres by typing keywords"
        )
        
        if genre_search_text:
            filtered_list = sorted([g for g in all_genres_list if genre_search_text.lower() in g.lower()])
            st.caption(f"📍 Found {len(filtered_list)} of {len(all_genres_list)} genres")
        else:
            filtered_list = sorted(all_genres_list)
        
        st.session_state.scrape_genre_search = st.selectbox(
            "Select Genre",
            filtered_list,
            index=0,
            key="scrape_genre_search_select"
        )
    
    with tab2:
        st.session_state.scrape_genre_tab = 'hierarchy'
        selected_parent = st.selectbox(
            "Select Parent Genre",
            parent_genres_list,
            key="scrape_parent_select"
        )
        
        genre_info = get_genre_with_children(selected_parent)
        
        if genre_info["has_children"]:
            st.markdown(f"**Subgenres:** ({len(genre_info['children'])} available)")
            cols = st.columns(3)
            for idx, subgenre in enumerate(genre_info['children']):
                with cols[idx % 3]:
                    if st.button(subgenre, use_container_width=True, key=f"scrape_subgenre_btn_{subgenre}"):
                        st.session_state.scrape_genre_hierarchy = subgenre
            
            st.session_state.scrape_genre_hierarchy = st.selectbox(
                "Or select from dropdown",
                genre_info['children'],
                index=0 if st.session_state.scrape_genre_hierarchy not in genre_info['children'] else genre_info['children'].index(st.session_state.scrape_genre_hierarchy),
                key="scrape_subgenre_dropdown"
            )
        else:
            st.info(f"ℹ️ {selected_parent} has no subgenres")
            st.session_state.scrape_genre_hierarchy = selected_parent
    
    # CRITICAL: Get the genre from the ACTIVE tab only
    if st.session_state.scrape_genre_tab == 'search':
        selected_scrape_genre = st.session_state.scrape_genre_search
    else:
        selected_scrape_genre = st.session_state.scrape_genre_hierarchy
    
    st.info(f"📌 Selected Genre: **{selected_scrape_genre}**")
    
    scrape_start_year = st.number_input("Start Year", min_value=1800, max_value=2030, value=2026)
    scrape_years_back = st.number_input("Years Back", min_value=1, max_value=10, value=1)
    scrape_albums_per_year = st.number_input("Albums per Year", min_value=1, max_value=500, value=250)
    scrape_test_mode = st.checkbox("Test Mode", value=False)
    scrape_limit = st.number_input("Limit (test mode)", min_value=1, max_value=100, value=10)
    
    st.markdown("---")
    
    if st.button("🚀 Start Scrape", type="primary"):
        import subprocess
        
        cmd = ["python", "-m", "cli", "scrape"]
        cmd.extend(["--genre", selected_scrape_genre])
        cmd.extend(["--start-year", str(scrape_start_year)])
        cmd.extend(["--years-back", str(scrape_years_back)])
        cmd.extend(["--albums-per-year", str(scrape_albums_per_year)])
        
        if scrape_test_mode:
            cmd.append("--test-mode")
            cmd.extend(["--limit", str(scrape_limit)])
        
        st.session_state.scrape_process = subprocess.Popen(cmd, cwd=PROJECT_ROOT)
        st.session_state.scrape_running = True
        st.session_state.scrape_start_time = pd.Timestamp.now()
        st.rerun()
    
    if st.session_state.scrape_running and hasattr(st.session_state, 'scrape_process'):
        proc = st.session_state.scrape_process
        if proc.poll() is None:
            elapsed = (pd.Timestamp.now() - st.session_state.scrape_start_time).total_seconds()
            st.sidebar.info(f"🔄 Scrape running... ({int(elapsed)}s elapsed)")
            import time
            time.sleep(2)
            st.rerun()
        else:
            del st.session_state.scrape_process
            if proc.returncode == 0:
                st.sidebar.success("✅ Scrape completed!")
                with st.spinner("Loading new data..."):
                    st.session_state.albums = load_data()
            else:
                st.sidebar.error(f"❌ Scrape failed (code {proc.returncode})")
            st.session_state.scrape_running = False
            st.rerun()

if not albums:
    st.info("📊 No albums loaded yet. Use the sidebar to start a new scrape.")
    st.stop()

st.header("📊 Statistics Overview")
col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("Total Albums", len(filtered_albums))
with col2:
    unique_genres = len(set(genre for album in filtered_albums for genre in album.get('genres', [])))
    st.metric("Unique Genres", unique_genres)
with col3:
    albums_with_scores = sum(1 for a in filtered_albums if a.get('critic_score') or a.get('user_score'))
    st.metric("Albums with Scores", albums_with_scores)
with col4:
    total_reviews = sum((a.get('critic_review_count') or 0) + (a.get('user_review_count') or 0) for a in filtered_albums)
    st.metric("Total Reviews", total_reviews)

st.subheader("🏆 Top Albums by User Score (≥100 Ratings)")
popular_albums = [a for a in filtered_albums if (a.get('user_review_count') or 0) >= 100]
if popular_albums:
    top_albums = sorted(popular_albums, key=lambda x: x.get('user_score') or 0, reverse=True)[:5]
    for i, album in enumerate(top_albums, 1):
        col1, col2, col3 = st.columns([3, 1, 1])
        with col1:
            st.write(f"**{i}. {album.get('title', 'Unknown')}**")
            st.write(f"*by {album.get('artist_name', 'Unknown')}*")
        with col2:
            if album.get('user_score'):
                st.write(f"👥 {album.get('user_score')}/100")
            if album.get('user_review_count'):
                st.caption(f"({album.get('user_review_count')} reviews)")
        with col3:
            genres = album.get('genres', [])
            if genres:
                st.write(f"🎵 {', '.join(genres[:2])}")
else:
    st.info("No albums with ≥100 user reviews found.")

st.header("💿 Album List")
albums_per_page = st.sidebar.selectbox("Albums per page", options=[10, 25, 50], index=0)
page = st.number_input("Page", min_value=1, max_value=max(1, len(filtered_albums) // albums_per_page + 1), value=1)
start_idx = (page - 1) * albums_per_page
end_idx = min(start_idx + albums_per_page, len(filtered_albums))
page_albums = filtered_albums[start_idx:end_idx]

for i, album in enumerate(page_albums, start=start_idx + 1):
    st.markdown("---")
    col1, col2, col3, col4 = st.columns([3, 2, 2, 2])
    
    with col1:
        st.write(f"**{i}. {album.get('title', 'Unknown')}**")
        year_str = f"📅 {album.get('scrape_year')}" if album.get('scrape_year') else ""
        st.caption(f"*by {album.get('artist_name', 'Unknown')} • {year_str}*")
    
    with col2:
        scores = []
        if album.get('critic_score'):
            scores.append(f"⭐ {int(album.get('critic_score'))}")
        if album.get('user_score'):
            scores.append(f"👥 {int(album.get('user_score'))}")
        st.write(" | ".join(scores) if scores else "No scores")
    
    with col3:
        reviews = []
        if album.get('critic_review_count'):
            reviews.append(f"Critics: {album.get('critic_review_count')}")
        if album.get('user_review_count'):
            reviews.append(f"Users: {album.get('user_review_count')}")
        st.caption(" | ".join(reviews) if reviews else "No reviews")
    
    with col4:
        genres = album.get('genres', [])
        if genres:
            genre_str = ", ".join(genres[:3]) if len(genres) <= 3 else ", ".join(genres[:3]) + f" (+{len(genres)-3})"
        else:
            genre_str = "No genres"
        st.caption(f"🎵 {genre_str}")

st.write(f"Showing {len(page_albums)} of {len(filtered_albums)} albums")

st.header("🎵 Genre Distribution")
genre_counts = {}
for album in filtered_albums:
    for genre in album.get('genres', []):
        genre_counts[genre] = genre_counts.get(genre, 0) + 1

if genre_counts:
    sorted_genres = sorted(genre_counts.items(), key=lambda x: x[1], reverse=True)
    for genre, count in sorted_genres[:10]:
        st.progress(count / len(filtered_albums), text=f"{genre}: {count}")
