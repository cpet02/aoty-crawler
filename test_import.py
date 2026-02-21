#!/usr/bin/env python3
"""Test script to check imports and field definitions"""

import sys
sys.path.insert(0, '.')

try:
    from aoty_crawler.items import AlbumItem
    print("✓ Successfully imported AlbumItem")
    
    # Check if fields exist
    album = AlbumItem()
    
    # Try to set the fields mentioned in the handoff
    try:
        album['scrape_genre'] = 'Test Genre'
        album['scrape_year'] = 2026
        print("✓ Successfully set scrape_genre and scrape_year fields")
    except KeyError as e:
        print(f"✗ KeyError when setting fields: {e}")
        print(f"  Available fields: {list(album.fields.keys())}")
        
except ImportError as e:
    print(f"✗ Import error: {e}")
except Exception as e:
    print(f"✗ Unexpected error: {e}")

# Also test spider import
print("\nTesting spider imports...")
try:
    from aoty_crawler.spiders.production_spider import ProductionSpider
    print("✓ Successfully imported ProductionSpider")
except ImportError as e:
    print(f"✗ Import error for ProductionSpider: {e}")
except Exception as e:
    print(f"✗ Unexpected error: {e}")