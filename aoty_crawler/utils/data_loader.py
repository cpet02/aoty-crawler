#!/usr/bin/env python3
"""
Simple data loader for AOTY Crawler
Loads album data from JSON/CSV files in data/output/
"""

import json
import csv
import os
import glob
from datetime import datetime


def load_albums_from_json(json_file_path):
    """Load albums from a single JSON file"""
    try:
        with open(json_file_path, 'r', encoding='utf-8') as f:
            albums = json.load(f)
        
        # Ensure we have a list
        if isinstance(albums, dict):
            albums = [albums]
        
        # Clean and convert types for each album
        for album in albums:
            # Convert numeric fields from strings to appropriate types
            for field in ['critic_score', 'user_score']:
                value = album.get(field)
                if value is not None and value != '' and value != 'null' and value != 'None':
                    try:
                        album[field] = float(value)
                    except (ValueError, TypeError):
                        album[field] = None
                else:
                    album[field] = None
            
            for field in ['critic_review_count', 'user_review_count', 'scrape_year']:
                value = album.get(field)
                if value is not None and value != '' and value != 'null' and value != 'None':
                    try:
                        album[field] = int(float(value))  # Handle float strings like 2.0
                    except (ValueError, TypeError):
                        album[field] = 0
                else:
                    album[field] = 0 if field != 'scrape_year' else None
        
        print(f"✅ Loaded {len(albums)} albums from {json_file_path}")
        return albums
        
    except Exception as e:
        print(f"❌ Error loading JSON file {json_file_path}: {e}")
        return []


def load_albums_from_csv(csv_file_path):
    """Load albums from a single CSV file"""
    try:
        albums = []
        with open(csv_file_path, 'r', encoding='utf-8', newline='') as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Convert numeric fields
                album = dict(row)
                
                # Clean and convert numeric fields
                for field in ['critic_score', 'user_score']:
                    value = album.get(field)
                    if value is not None and value != '' and value != 'null' and value != 'None':
                        try:
                            album[field] = float(value)
                        except (ValueError, TypeError):
                            album[field] = None
                    else:
                        album[field] = None
                
                for field in ['critic_review_count', 'user_review_count', 'scrape_year']:
                    value = album.get(field)
                    if value is not None and value != '' and value != 'null' and value != 'None':
                        try:
                            album[field] = int(float(value))
                        except (ValueError, TypeError):
                            album[field] = 0 if field != 'scrape_year' else None
                    else:
                        album[field] = 0 if field != 'scrape_year' else None
                
                # Parse genres from JSON string if needed
                for field in ['genres', 'genre_tags']:
                    if field in album and album[field]:
                        try:
                            album[field] = json.loads(album[field])
                        except json.JSONDecodeError:
                            album[field] = [album[field]] if album[field] else []
                
                albums.append(album)
        
        print(f"✅ Loaded {len(albums)} albums from {csv_file_path}")
        return albums
        
    except Exception as e:
        print(f"❌ Error loading CSV file {csv_file_path}: {e}")
        return []


def load_all_albums(output_dir='data/output', deduplicate=True):
    """Load all albums from all JSON/CSV files in the output directory"""
    all_albums = []
    
    # Ensure directory exists
    if not os.path.exists(output_dir):
        print(f"❌ Output directory not found: {output_dir}")
        return []
    
    # Find all JSON files
    json_files = glob.glob(os.path.join(output_dir, 'albums_*.json'))
    
    # Find all CSV files
    csv_files = glob.glob(os.path.join(output_dir, 'albums_*.csv'))
    
    print(f"🔍 Found {len(json_files)} JSON files and {len(csv_files)} CSV files in {output_dir}")
    
    # Load from JSON files
    for json_file in sorted(json_files):
        albums = load_albums_from_json(json_file)
        all_albums.extend(albums)
    
    # Load from CSV files (if any)
    for csv_file in sorted(csv_files):
        albums = load_albums_from_csv(csv_file)
        all_albums.extend(albums)
    
    # Remove duplicates based on aoty_id (if enabled)
    if deduplicate:
        unique_albums = {}
        for album in all_albums:
            aoty_id = album.get('aoty_id')
            # Only add if we have a valid aoty_id and title
            if aoty_id and aoty_id != 'album' and album.get('title'):
                unique_albums[aoty_id] = album
        
        unique_albums_list = list(unique_albums.values())
        duplicates_removed = len(all_albums) - len(unique_albums_list)
        
        if duplicates_removed > 0:
            print(f"🗑️  Removed {duplicates_removed} duplicate/invalid entries")
    else:
        unique_albums_list = all_albums
    
    # Filter out invalid/placeholder albums
    valid_albums = filter_invalid_albums(unique_albums_list)
    
    print(f"📊 Total valid albums loaded: {len(valid_albums)}")
    return valid_albums


def load_latest_albums(output_dir='data/output', limit=1, deduplicate=True):
    """Load albums from the most recent JSON/CSV files"""
    all_albums = []
    
    # Ensure directory exists
    if not os.path.exists(output_dir):
        print(f"❌ Output directory not found: {output_dir}")
        return []
    
    # Find all JSON files and sort by modification time
    json_files = sorted(glob.glob(os.path.join(output_dir, 'albums_*.json')), 
                       key=lambda x: os.path.getmtime(x), reverse=True)
    
    # Find all CSV files and sort by modification time
    csv_files = sorted(glob.glob(os.path.join(output_dir, 'albums_*.csv')), 
                      key=lambda x: os.path.getmtime(x), reverse=True)
    
    # Load from latest files (up to limit of each type)
    for json_file in json_files[:limit]:
        albums = load_albums_from_json(json_file)
        all_albums.extend(albums)
    
    for csv_file in csv_files[:limit]:
        albums = load_albums_from_csv(csv_file)
        all_albums.extend(albums)
    
    # Remove duplicates based on aoty_id (if enabled)
    if deduplicate:
        unique_albums = {}
        for album in all_albums:
            aoty_id = album.get('aoty_id')
            # Only add if we have a valid aoty_id and title
            if aoty_id and aoty_id != 'album' and album.get('title'):
                unique_albums[aoty_id] = album
        
        unique_albums_list = list(unique_albums.values())
        duplicates_removed = len(all_albums) - len(unique_albums_list)
        
        if duplicates_removed > 0:
            print(f"🗑️  Removed {duplicates_removed} duplicate/invalid entries")
    else:
        unique_albums_list = all_albums
    
    print(f"📊 Loaded {len(unique_albums_list)} unique albums from latest files")
    return unique_albums_list


def filter_albums(albums, **kwargs):
    """
    Filter albums based on criteria
    
    Args:
        albums: List of album dictionaries
        **kwargs: Filter criteria
            - genres: List of genres to match (any match)
            - genres_all: List of genres to match (all must match)
            - min_score: Minimum critic score (0-100)
            - max_score: Maximum critic score (0-100)
            - min_user_score: Minimum user score (0-100)
            - max_user_score: Maximum user score (0-100)
            - min_reviews: Minimum review count
            - min_user_reviews: Minimum user review count
            - min_critic_reviews: Minimum critic review count
            - year: Exact release year
            - year_min: Minimum release year
            - year_max: Maximum release year
            - search: Search string (matches title, artist, description)
    
    Returns:
        Filtered list of albums
    """
    if not albums:
        return []
    
    filtered = albums[:]
    
    # Filter by genres (any match)
    if 'genres' in kwargs and kwargs['genres']:
        # Convert album genres to lowercase set for comparison
        filtered = [a for a in filtered if any(
            g.lower() in [ag.lower() for ag in a.get('genres', [])]
            for g in kwargs['genres']
        )]
        print(f"🔍 Filtered by genres: {kwargs['genres']} → {len(filtered)} albums")
    
    # Filter by genres (all must match)
    if 'genres_all' in kwargs and kwargs['genres_all']:
        # Check if ALL filter genres are in the album's genres
        filtered = [a for a in filtered if all(
            g.lower() in [ag.lower() for ag in a.get('genres', [])]
            for g in kwargs['genres_all']
        )]
        print(f"🔍 Filtered by all genres: {kwargs['genres_all']} → {len(filtered)} albums")
    
    # Filter by critic score
    if 'min_score' in kwargs and kwargs['min_score'] is not None:
        filtered = [a for a in filtered if a.get('critic_score') is not None and a.get('critic_score') >= kwargs['min_score']]
        print(f"🔍 Filtered by min critic score ≥ {kwargs['min_score']} → {len(filtered)} albums")
    
    if 'max_score' in kwargs and kwargs['max_score'] is not None:
        filtered = [a for a in filtered if a.get('critic_score') is not None and a.get('critic_score') <= kwargs['max_score']]
        print(f"🔍 Filtered by max critic score ≤ {kwargs['max_score']} → {len(filtered)} albums")
    
    # Filter by user score
    if 'min_user_score' in kwargs and kwargs['min_user_score'] is not None:
        filtered = [a for a in filtered if a.get('user_score') is not None and a.get('user_score') >= kwargs['min_user_score']]
        print(f"🔍 Filtered by min user score ≥ {kwargs['min_user_score']} → {len(filtered)} albums")
    
    if 'max_user_score' in kwargs and kwargs['max_user_score'] is not None:
        filtered = [a for a in filtered if a.get('user_score') is not None and a.get('user_score') <= kwargs['max_user_score']]
        print(f"🔍 Filtered by max user score ≤ {kwargs['max_user_score']} → {len(filtered)} albums")
    
    # Filter by review count
    if 'min_reviews' in kwargs and kwargs['min_reviews'] is not None:
        filtered = [a for a in filtered if (a.get('critic_review_count') or 0) + (a.get('user_review_count') or 0) >= kwargs['min_reviews']]
        print(f"🔍 Filtered by min reviews ≥ {kwargs['min_reviews']} → {len(filtered)} albums")
    
    if 'min_user_reviews' in kwargs and kwargs['min_user_reviews'] is not None:
        filtered = [a for a in filtered if (a.get('user_review_count') or 0) >= kwargs['min_user_reviews']]
        print(f"🔍 Filtered by min user reviews ≥ {kwargs['min_user_reviews']} → {len(filtered)} albums")
    
    if 'min_critic_reviews' in kwargs and kwargs['min_critic_reviews'] is not None:
        filtered = [a for a in filtered if (a.get('critic_review_count') or 0) >= kwargs['min_critic_reviews']]
        print(f"🔍 Filtered by min critic reviews ≥ {kwargs['min_critic_reviews']} → {len(filtered)} albums")
    
    # Filter by year
    if 'year' in kwargs and kwargs['year'] is not None:
        filtered = [a for a in filtered if a.get('scrape_year') == kwargs['year']]
        print(f"🔍 Filtered by year {kwargs['year']} → {len(filtered)} albums")
    
    if 'year_min' in kwargs and kwargs['year_min'] is not None:
        filtered = [a for a in filtered if a.get('scrape_year', 0) >= kwargs['year_min']]
        print(f"🔍 Filtered by year ≥ {kwargs['year_min']} → {len(filtered)} albums")
    
    if 'year_max' in kwargs and kwargs['year_max'] is not None:
        filtered = [a for a in filtered if a.get('scrape_year', 9999) <= kwargs['year_max']]
        print(f"🔍 Filtered by year ≤ {kwargs['year_max']} → {len(filtered)} albums")
    
    # Filter by search string
    if 'search' in kwargs and kwargs['search']:
        search_term = kwargs['search'].lower()
        filtered = [a for a in filtered if 
                   search_term in (a.get('title') or '').lower() or
                   search_term in (a.get('artist_name') or '').lower() or
                   search_term in (a.get('description') or '').lower()]
        print(f"🔍 Filtered by search '{kwargs['search']}' → {len(filtered)} albums")
    
    return filtered


def filter_invalid_albums(albums):
    """
    Filter out placeholder/invalid albums (e.g., artist='Submit Correction', no scores, no genres)
    
    Args:
        albums: List of album dictionaries
    
    Returns:
        Filtered list of valid albums
    """
    if not albums:
        return []
    
    valid_albums = []
    for album in albums:
        # Skip placeholder entries
        artist = (album.get('artist_name') or '').strip()
        title = (album.get('title') or '').strip()
        
        # Skip if artist is placeholder
        if artist.lower() in ['submit correction', 'album', 'artist', 'unknown', '']:
            continue
        
        # Skip if title is placeholder
        if title.lower() in ['discography', 'album', 'artist', 'unknown', '']:
            continue
        
        # Skip if no scores and no reviews
        critic_score = album.get('critic_score')
        user_score = album.get('user_score')
        critic_reviews = album.get('critic_review_count')
        user_reviews = album.get('user_review_count')
        
        has_score = critic_score is not None or user_score is not None
        has_reviews = (critic_reviews or 0) > 0 or (user_reviews or 0) > 0
        
        if not has_score and not has_reviews:
            continue
        
        # Skip if genres is empty or None
        genres = album.get('genres')
        if not genres or (isinstance(genres, list) and len(genres) == 0):
            continue
        
        valid_albums.append(album)
    
    removed_count = len(albums) - len(valid_albums)
    if removed_count > 0:
        print(f"🗑️  Removed {removed_count} invalid/placeholder albums")
    
    return valid_albums


# Test function for manual testing
if __name__ == '__main__':
    print("=" * 60)
    print("Testing Data Loader")
    print("=" * 60)
    
    # Test loading from default directory
    albums = load_all_albums()
    
    if albums:
        print(f"\n✅ Successfully loaded {len(albums)} albums!")
        print("\nFirst album sample:")
        if albums[0]:
            for key, value in list(albums[0].items())[:5]:
                print(f"  {key}: {value}")
        
        # Test filtering
        print("\n" + "=" * 60)
        print("Testing Filter Function")
        print("=" * 60)
        
        # Test 1: Filter by genre
        rock_albums = filter_albums(albums, genres=['Rock'])
        print(f"Rock albums: {len(rock_albums)}")
        
        # Test 2: Filter by score
        high_score_albums = filter_albums(albums, min_score=80)
        print(f"Albums with score ≥ 80: {len(high_score_albums)}")
        
        # Test 3: Filter by user reviews
        popular_albums = filter_albums(albums, min_user_reviews=1000)
        print(f"Albums with ≥ 1000 user reviews: {len(popular_albums)}")
        
        # Test 4: Combined filters
        filtered = filter_albums(albums, genres=['Rock'], min_user_reviews=100, min_score=70)
        print(f"Rock albums with ≥ 100 user reviews and score ≥ 70: {len(filtered)}")
        
        if filtered:
            print("\nSample filtered results:")
            for album in filtered[:3]:
                print(f"  - {album.get('title')} by {album.get('artist_name')} (Score: {album.get('user_score')}, Reviews: {album.get('user_review_count')})")
    else:
        print("\n❌ No albums loaded. Check if data/output/ directory exists and contains JSON/CSV files.")
