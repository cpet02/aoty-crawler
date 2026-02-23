#!/usr/bin/env python3
"""
Streamlit UI for AOTY Crawler
Simple, clean, data-heavy dashboard
"""

# Add parent directory to path for imports
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
import pandas as pd
from aoty_crawler.utils.data_loader import load_all_albums, filter_albums

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

# Load data
@st.cache_data
def load_data():
    """Load all albums with caching"""
    try:
        albums = load_all_albums(output_dir=DATA_DIR)
        return albums
    except Exception as e:
        st.error(f"Error loading data: {e}")
        return []

# Initialize session state
if 'albums' not in st.session_state:
    with st.spinner("Loading album data..."):
        st.session_state.albums = load_data()

albums = st.session_state.albums

if not albums:
    st.warning("No albums found. Run 'python -m cli scrape' to scrape data first.")
    st.stop()

# Sidebar filters
st.sidebar.header("🔍 Search Filters")

# Genre filter
all_genres = sorted(set(genre for album in albums for genre in album.get('genres', [])))
selected_genres = st.sidebar.multiselect(
    "Genres",
    all_genres,
    default=[]
)

# Score filters
col1, col2 = st.sidebar.columns(2)
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

# Year filter
min_year = min((album.get('scrape_year') or 2026) for album in albums)
max_year = max((album.get('scrape_year') or 2026) for album in albums)
selected_year = st.sidebar.selectbox(
    "Year",
    options=["All"] + list(range(max_year, min_year - 1, -1)),
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

# Album grid
st.header("💿 Album Grid")

# Filter controls
cols_per_row = 4
albums_per_page = 20

# Pagination
page = st.number_input("Page", min_value=1, max_value=max(1, len(filtered_albums) // albums_per_page + 1), value=1)
start_idx = (page - 1) * albums_per_page
end_idx = min(start_idx + albums_per_page, len(filtered_albums))

page_albums = filtered_albums[start_idx:end_idx]

# Album cards grid
cols = st.columns(cols_per_row)
for i, album in enumerate(page_albums):
    with cols[i % cols_per_row]:
        cover_url = album.get('cover_image_url')
        title = album.get('title', 'Unknown')
        artist = album.get('artist_name', 'Unknown')
        critic_score = album.get('critic_score')
        user_score = album.get('user_score')
        genres = album.get('genres', [])
        
        # Album card
        st.markdown("---")
        # Skip images due to hotlinking restrictions
        
        st.markdown(f"**{title}**")
        st.caption(artist)
        
        scores = []
        if critic_score:
            scores.append(f"⭐ {critic_score}")
        if user_score:
            scores.append(f"👥 {user_score}")
        if scores:
            st.write(" | ".join(scores))
        
        if genres:
            genre_str = ", ".join(genres[:2])
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
