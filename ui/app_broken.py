#!/usr/bin/env python3
"""
Streamlit UI for AOTY Crawler
Simple, clean, data-heavy dashboard with hierarchical genre support
"""

# Add parent directory to path for imports
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

# Use absolute path for data directory
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(PROJECT_ROOT, 'data', 'output')

# Page config
st.set_page_config(
    page_title="AOTY Explorer",
    page_icon="🎵",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Title
st.title("🎵 AOTY Explorer")
st.markdown("Album of the Year Data Dashboard")

# Load data (no caching for initial load to detect file changes)
def load_data():
    """Load all albums - no caching to detect file changes"""
    try:
        if not os.path.exists(DATA_DIR):
            return []
        albums = load_all_albums(output_dir=DATA_DIR)
        
        # Discover new genres from loaded albums
        if albums:
            discovery_result = discover_from_albums(albums)
            if discovery_result["new_genres"]:
                st.toast(f"🆕 Discovered {len(discovery_result['new_genres'])} new genre(s)!")
        
        return albums
    except Exception as e:
        st.error(f"Error loading data: {e}")
        return []

# Initialize session state
if 'albums' not in st.session_state:
    with st.spinner("Loading album data..."):
        st.session_state.albums = load_data()

# Track scrape status in session state
if 'scrape_running' not in st.session_state:
    st.session_state.scrape_running = False

# Show scrape-in-progress banner
if st.session_state.scrape_running:
    st.warning("⚠️ A scrape is currently running in the background. Please do not close the app or refresh the page.")

albums = st.session_state.albums

# Sidebar content (always show, even with no albums)
with st.sidebar:
    # Sidebar filters
    st.header("🔍 Search Filters")

    # Genre filter
    all_genres = sorted(set(genre for album in albums for genre in album.get('genres', [])))
    selected_genres = st.multiselect(
        "Genres",
        all_genres,
        default=[]
    )

    # Score filters
    col1, col2 = st.columns(2)
    with col1:
        min_critic_score = st.number_input(
            "Min Critic Score",
            min_value=0.0,
            max_value=100.0,
            value=0.0,
            step=1.0
        )
    with col2:
        min_user_score = st.number_input(
            "Min User Score",
            min_value=0.0,
            max_value=100.0,
            value=0.0,
            step=1.0
        )

    # Year filter (safe for empty albums)
    if albums:
        min_year = min((album.get('scrape_year') or 2026) for album in albums)
        max_year = max((album.get('scrape_year') or 2026) for album in albums)
        year_options = ["All"] + list(range(max_year, min_year - 1, -1))
    else:
        year_options = ["All"]
    selected_year = st.selectbox(
        "Year",
        options=year_options,
        index=0
    )

    # Apply filters
    filtered_albums = filter_albums(
        albums,
        genres=selected_genres if selected_genres else None,
        min_score=min_critic_score if min_critic_score > 0 else None,
        min_user_score=min_user_score if min_user_score > 0 else None,
        year=int(selected_year) if selected_year != "All" else None
    )

    # --- NEW: Start New Scrape Section ---
    st.markdown("---")
    st.header("🚀 Start New Scrape")

    all_genres_list = get_all_genres()
    parent_genres_list = get_parent_genres()
    
    st.caption(f"🎵 {len(all_genres_list)} total genres available (including subgenres)")
    
    # Tab-based genre selection
    tab1, tab2 = st.tabs(["🔍 Search", "📂 Browse Hierarchy"])
    
    with tab1:
        # Search interface
        genre_search = st.text_input(
            "Search genres",
            placeholder="Type to filter (e.g., 'pop', 'wave', 'rock', 'ethereal')...",
            help="Find genres by typing keywords"
        )
        
        if genre_search:
            filtered_genre_list = sorted([g for g in all_genres_list if genre_search.lower() in g.lower()])
            st.caption(f"📍 Found {len(filtered_genre_list)} of {len(all_genres_list)} genres")
        else:
            filtered_genre_list = sorted(all_genres_list)
        
        genre = st.selectbox(
            "Select Genre",
            filtered_genre_list,
            index=0,
            help="Choose a specific genre or subgenre to scrape",
            key="genre_search_select"
        )
    
    with tab2:
        # Hierarchical browsing
        st.caption("Browse parent genres and their subgenres:")
        
        selected_parent = st.selectbox(
            "Select Parent Genre",
            parent_genres_list,
            help="Choose a parent genre to see its subgenres",
            key="parent_select"
        )
        
        genre_info = get_genre_with_children(selected_parent)
        
        if genre_info["has_children"]:
            st.markdown(f"**Subgenres of {selected_parent}:** ({len(genre_info['children'])} available)")
            
            # Show subgenres as buttons in columns
            cols = st.columns(3)
            selected_subgenre = None
            for idx, subgenre in enumerate(genre_info['children']):
                with cols[idx % 3]:
                    if st.button(subgenre, use_container_width=True, key=f"subgenre_btn_{subgenre}"):
                        selected_subgenre = subgenre
            
            # Dropdown for subgenres
            genre = st.selectbox(
                "Or select from dropdown",
                genre_info['children'],
                index=0 if not selected_subgenre else (genre_info['children'].index(selected_subgenre) if selected_subgenre in genre_info['children'] else 0),
                key="subgenre_dropdown"
            )
            
            if selected_subgenre:
                genre = selected_subgenre
        else:
            st.info(f"ℹ️ {selected_parent} has no subgenres")
            genre = selected_parent

    scrape_start_year = st.number_input(
        "Start Year", min_value=1800, max_value=2030, value=2026
    )
    scrape_years_back = st.number_input(
        "Years Back", min_value=1, max_value=10, value=1
    )
    scrape_albums_per_year = st.number_input(
        "Albums per Year", min_value=1, max_value=500, value=250
    )
    scrape_test_mode = st.checkbox("Test Mode", value=False)
    scrape_limit = st.number_input(
        "Limit (test mode)", min_value=1, max_value=100, value=10
    )

    # Separator before scrape config
    st.markdown("---")

    if st.button("🚀 Start Scrape", type="primary"):
        import subprocess
        
        # Build CLI command
        cmd = ["python", "-m", "cli", "scrape"]
        
        cmd.extend(["--genre", genre])
        cmd.extend(["--start-year", str(scrape_start_year)])
        cmd.extend(["--years-back", str(scrape_years_back)])
        cmd.extend(["--albums-per-year", str(scrape_albums_per_year)])
        
        if scrape_test_mode:
            cmd.append("--test-mode")
            cmd.extend(["--limit", str(scrape_limit)])
        
        # Change working directory to project root
        cwd = PROJECT_ROOT
        
        # Start process WITHOUT piping (let it output to console/log file naturally)
        st.session_state.scrape_process = subprocess.Popen(
            cmd,
            cwd=cwd,
            # Don't pipe - let the CLI handle its own logging
        )
        
        # Set scrape running flag
        st.session_state.scrape_running = True
        st.session_state.scrape_start_time = pd.Timestamp.now()
        
        # Trigger immediate rerun to start polling
        st.rerun()

    # --- Handle scrape process polling (inside sidebar context) ---
    if st.session_state.scrape_running and hasattr(st.session_state, 'scrape_process'):
        proc = st.session_state.scrape_process
        
        # Check if process is still running
        if proc.poll() is None:
            # Still running - show spinner with elapsed time
            elapsed = (pd.Timestamp.now() - st.session_state.scrape_start_time).total_seconds()
            st.sidebar.info(f"🔄 Scrape is running... ({int(elapsed)}s elapsed)")
            
            # Use time.sleep to avoid hammering the UI
            import time
            time.sleep(2)  # Check every 2 seconds
            st.rerun()
        else:
            # Process finished
            # Clean up process reference
            del st.session_state.scrape_process
            if hasattr(st.session_state, 'scrape_start_time'):
                del st.session_state.scrape_start_time
            
            # Check return code
            if proc.returncode == 0:
                st.sidebar.success("✅ Scrape completed! Check logs/aoty_crawler.log for details.")
                # Reload data
                with st.spinner("Loading new data..."):
                    st.session_state.albums = load_data()
            else:
                st.sidebar.error(f"❌ Scrape failed with return code {proc.returncode}. Check logs/aoty_crawler.log for details.")
            
            # Reset scrape running flag
            st.session_state.scrape_running = False
            # Trigger final rerun to update UI
            st.rerun()

# --- End Scrape Section ---

if not albums:
    st.info("📊 No albums loaded yet. Use the sidebar to start a new scrape.")
    st.stop()

# Stats overview
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

# Top albums by user score (minimum 100 ratings)
st.subheader("🏆 Top Albums by User Score (≥100 Ratings)")

# Filter albums with at least 100 user reviews
popular_albums = [a for a in filtered_albums if (a.get('user_review_count') or 0) >= 100]

if popular_albums:
    top_albums = sorted(popular_albums, key=lambda x: x.get('user_score') or 0, reverse=True)[:5]
    
    for i, album in enumerate(top_albums, 1):
        title = album.get('title', 'Unknown')
        artist = album.get('artist_name', 'Unknown')
        critic_score = album.get('critic_score')
        user_score = album.get('user_score')
        user_reviews = album.get('user_review_count')
        genres = album.get('genres', [])
        
        col1, col2, col3 = st.columns([3, 1, 1])
        with col1:
            st.write(f"**{i}. {title}**")
            st.write(f"*by {artist}*")
        with col2:
            if user_score:
                st.write(f"👥 {user_score}/100")
            if user_reviews:
                st.caption(f"({user_reviews} reviews)")
        with col3:
            if genres:
                st.write(f"🎵 {', '.join(genres[:2])}")
else:
    st.info("No albums with ≥100 user reviews found.")

# Album list view
st.header("💿 Album List")

# Filter controls
albums_per_page_options = [10, 25, 50]
albums_per_page = st.sidebar.selectbox(
    "Albums per page",
    options=albums_per_page_options,
    index=0  # Default to 10
)

# Pagination
page = st.number_input("Page", min_value=1, max_value=max(1, len(filtered_albums) // albums_per_page + 1), value=1)
start_idx = (page - 1) * albums_per_page
end_idx = min(start_idx + albums_per_page, len(filtered_albums))

page_albums = filtered_albums[start_idx:end_idx]

# Display as list with reduced spacing
for i, album in enumerate(page_albums, start=start_idx + 1):
    title = album.get('title', 'Unknown')
    artist = album.get('artist_name', 'Unknown')
    critic_score = album.get('critic_score')
    user_score = album.get('user_score')
    critic_reviews = album.get('critic_review_count')
    user_reviews = album.get('user_review_count')
    genres = album.get('genres', [])
    year = album.get('scrape_year')

    # Cast scores to int for display
    critic_score_int = int(critic_score) if critic_score is not None else None
    user_score_int = int(user_score) if user_score is not None else None

    # Build year string (only if present)
    year_str = f"📅 {year}" if year is not None else ""
    
    # Build genre string with collapse logic
    if genres:
        if len(genres) <= 3:
            genre_str = ", ".join(genres)
        else:
            genre_str = ", ".join(genres[:3]) + f" (+{len(genres) - 3} more)"
    else:
        genre_str = "No genres"

    # Display row with reduced spacing (25% more compact)
    st.markdown(f"---")
    col1, col2, col3, col4 = st.columns([3, 2, 2, 2])
    
    with col1:
        st.write(f"**{i}. {title}**")
        if year_str or artist:
            st.caption(f"*by {artist} • {year_str}*")
    
    with col2:
        scores = []
        if critic_score_int is not None:
            scores.append(f"⭐ {critic_score_int}")
        if user_score_int is not None:
            scores.append(f"👥 {user_score_int}")
        st.write(" | ".join(scores) if scores else "No scores")
    
    with col3:
        reviews = []
        if critic_reviews:
            reviews.append(f"Critics: {critic_reviews}")
        if user_reviews:
            reviews.append(f"Users: {user_reviews}")
        st.caption(" | ".join(reviews) if reviews else "No reviews")
    
    with col4:
        st.caption(f"🎵 {genre_str}")

st.write(f"Showing {len(page_albums)} of {len(filtered_albums)} albums")

# Genre distribution (simple text)
st.header("🎵 Genre Distribution")
genre_counts = {}
for album in filtered_albums:
    for genre in album.get('genres', []):
        genre_counts[genre] = genre_counts.get(genre, 0) + 1

if genre_counts:
    sorted_genres = sorted(genre_counts.items(), key=lambda x: x[1], reverse=True)
    for genre, count in sorted_genres[:10]:
        st.progress(count / len(filtered_albums), text=f"{genre}: {count}")
