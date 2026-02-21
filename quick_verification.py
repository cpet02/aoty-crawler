#!/usr/bin/env python3
"""Quick verification of current state"""

import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

print("=" * 60)
print("QUICK VERIFICATION OF AOTY PRODUCTION SPIDER")
print("=" * 60)

# 1. Check imports
print("\n1. Checking imports...")
try:
    from aoty_crawler.items import AlbumItem
    print("✓ AlbumItem imported")
    
    # Check for scrape_genre and scrape_year fields
    album = AlbumItem()
    if 'scrape_genre' in album.fields and 'scrape_year' in album.fields:
        print("✓ scrape_genre and scrape_year fields are defined")
    else:
        print("✗ scrape_genre and/or scrape_year fields are MISSING!")
        print(f"  Available fields: {list(album.fields.keys())}")
        
except ImportError as e:
    print(f"✗ Import error: {e}")

# 2. Check output files
print("\n2. Checking output files...")
output_dir = "data/output"
if os.path.exists(output_dir):
    import glob
    album_files = glob.glob(os.path.join(output_dir, "albums_*.json"))
    if album_files:
        latest = max(album_files, key=os.path.getctime)
        print(f"✓ Latest output file: {os.path.basename(latest)}")
        
        # Check content
        try:
            with open(latest, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            if data and len(data) > 0:
                album = data[0]
                print(f"✓ Contains {len(data)} album(s)")
                
                # Check for scrape metadata
                if 'scrape_genre' in album and 'scrape_year' in album:
                    print(f"✓ Has scrape metadata: genre={album['scrape_genre']}, year={album['scrape_year']}")
                else:
                    print("✗ Missing scrape metadata in output")
            else:
                print("✗ Output file is empty")
                
        except Exception as e:
            print(f"✗ Error reading output: {e}")
    else:
        print("✗ No album JSON files found")
else:
    print("✗ Output directory doesn't exist")

# 3. Check navigation requirements
print("\n3. Checking navigation requirements...")
print("Required navigation flow:")
print("  1. Start at /genre.php")
print("  2. Extract genre links (e.g., /genre/7-rock/)")
print("  3. Build ratings URLs: /ratings/user-highest-rated/{YEAR}/{genre-slug}/")
print("  4. Extract album links from ratings pages")
print("  5. Parse album pages for data")

# 4. Check data extraction requirements
print("\n4. Checking data extraction requirements...")
requirements = [
    "Album Title",
    "Release Date", 
    "Genre/Primary Genre",
    "User Rating Score",
    "Critic Rating Score", 
    "User Review Count",
    "Critic Review Count",
    "Genre Tags (secondary genres)",
    "Album URL"
]

print("Original 9 requirements:")
for i, req in enumerate(requirements, 1):
    print(f"  {i}. {req}")

print("\n" + "=" * 60)
print("VERIFICATION COMPLETE")
print("=" * 60)