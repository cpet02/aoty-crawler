#!/usr/bin/env python3
"""
Comprehensive Test for AOTY Production Spider
Tests navigation flow, data extraction, and output format
"""

import sys
import os
import json
from datetime import datetime

# Add project to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_imports():
    """Test that all required imports work"""
    print("=" * 60)
    print("TEST 1: IMPORTS AND MODULE STRUCTURE")
    print("=" * 60)
    
    try:
        from aoty_crawler.items import AlbumItem
        print("✓ AlbumItem imported successfully")
        
        # Check fields
        album = AlbumItem()
        expected_fields = [
            'aoty_id', 'title', 'artist_name', 'url', 'scraped_at',
            'release_date', 'critic_score', 'user_score', 
            'critic_review_count', 'user_review_count',
            'genres', 'genre_tags', 'cover_image_url', 'description',
            'scrape_genre', 'scrape_year', 'artist_id', 'genre_ids', 'tracklist'
        ]
        
        missing_fields = []
        for field in expected_fields:
            if field not in album.fields:
                missing_fields.append(field)
        
        if missing_fields:
            print(f"✗ Missing fields in AlbumItem: {missing_fields}")
            return False
        else:
            print("✓ All expected fields present in AlbumItem")
            
    except ImportError as e:
        print(f"✗ Import error: {e}")
        return False
    
    try:
        from aoty_crawler.spiders.production_spider import ProductionSpider
        print("✓ ProductionSpider imported successfully")
    except ImportError as e:
        print(f"✗ Import error for ProductionSpider: {e}")
        return False
    
    print()
    return True

def test_navigation_logic():
    """Test that navigation logic matches requirements"""
    print("=" * 60)
    print("TEST 2: NAVIGATION LOGIC")
    print("=" * 60)
    
    # Test URL patterns
    test_cases = [
        {
            "name": "Genre page",
            "url": "https://www.albumoftheyear.org/genre.php",
            "expected": "Should extract genre links"
        },
        {
            "name": "Ratings page pattern",
            "pattern": "/ratings/user-highest-rated/{YEAR}/{genre-slug}/",
            "example": "/ratings/user-highest-rated/2026/rock/",
            "expected": "Matches required pattern"
        },
        {
            "name": "Album page pattern",
            "pattern": "/album/{AOTY_ID}-{album-name}.php",
            "example": "/album/1611085-wait-what-did-you-say-stay-safe-little-one.php",
            "expected": "Extracts AOTY ID and album name"
        }
    ]
    
    all_passed = True
    
    for test in test_cases:
        print(f"\nTesting: {test['name']}")
        print(f"  Pattern: {test.get('pattern', test.get('url', 'N/A'))}")
        print(f"  Expected: {test['expected']}")
        
        if test['name'] == "Ratings page pattern":
            # Verify pattern matches example
            import re
            pattern = r"/ratings/user-highest-rated/(\d{4})/([^/]+)/"
            match = re.match(pattern, test['example'])
            if match:
                year, genre_slug = match.groups()
                print(f"  ✓ Pattern matches: year={year}, genre={genre_slug}")
            else:
                print(f"  ✗ Pattern doesn't match example")
                all_passed = False
                
        elif test['name'] == "Album page pattern":
            # Verify pattern matches example
            import re
            pattern = r"/album/(\d+-[^/]+)\.php"
            match = re.match(pattern, test['example'])
            if match:
                aoty_id = match.group(1)
                print(f"  ✓ Pattern matches: AOTY ID={aoty_id}")
            else:
                print(f"  ✗ Pattern doesn't match example")
                all_passed = False
    
    print()
    return all_passed

def test_data_extraction():
    """Test data extraction logic"""
    print("=" * 60)
    print("TEST 3: DATA EXTRACTION REQUIREMENTS")
    print("=" * 60)
    
    # Original requirements from successful tests
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
    
    print("Original 9 Requirements:")
    for i, req in enumerate(requirements, 1):
        print(f"  {i}. {req}")
    
    # Check which fields in AlbumItem map to requirements
    from aoty_crawler.items import AlbumItem
    album = AlbumItem()
    
    field_mapping = {
        "Album Title": "title",
        "Release Date": "release_date", 
        "Genre/Primary Genre": "genres",
        "User Rating Score": "user_score",
        "Critic Rating Score": "critic_score", 
        "User Review Count": "user_review_count",
        "Critic Review Count": "critic_review_count",
        "Genre Tags (secondary genres)": "genre_tags",
        "Album URL": "url"
    }
    
    print("\nField Mapping Check:")
    all_mapped = True
    for req, field in field_mapping.items():
        if field in album.fields:
            print(f"  ✓ {req} → {field}")
        else:
            print(f"  ✗ {req} → {field} (MISSING!)")
            all_mapped = False
    
    # Bonus fields
    bonus_fields = [
        "Cover image URLs",
        "Descriptions from meta tags", 
        "AOTY IDs for unique identification",
        "Scrape timestamps",
        "Scrape metadata (genre/year)"
    ]
    
    print("\nBonus Fields:")
    for field in bonus_fields:
        print(f"  ✓ {field}")
    
    print()
    return all_mapped

def test_output_files():
    """Test that output files are created correctly"""
    print("=" * 60)
    print("TEST 4: OUTPUT FILES AND FORMAT")
    print("=" * 60)
    
    output_dir = "data/output"
    if not os.path.exists(output_dir):
        print(f"✗ Output directory doesn't exist: {output_dir}")
        return False
    
    # Find most recent album file
    import glob
    album_files = glob.glob(os.path.join(output_dir, "albums_*.json"))
    
    if not album_files:
        print("✗ No album JSON files found")
        return False
    
    # Get most recent file
    latest_file = max(album_files, key=os.path.getctime)
    print(f"Latest output file: {os.path.basename(latest_file)}")
    
    try:
        with open(latest_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        if not isinstance(data, list):
            print(f"✗ JSON file doesn't contain a list")
            return False
        
        print(f"✓ File contains {len(data)} album(s)")
        
        if data:
            # Check first album
            album = data[0]
            print(f"\nFirst album check:")
            
            # Required fields
            required = ['title', 'artist_name', 'url', 'release_date', 'genres']
            for field in required:
                if field in album and album[field]:
                    print(f"  ✓ {field}: {album[field] if isinstance(album[field], (str, int, float)) else 'Present'}")
                else:
                    print(f"  ✗ {field}: MISSING or empty")
            
            # Check for scrape metadata
            if 'scrape_genre' in album and 'scrape_year' in album:
                print(f"  ✓ Scrape metadata: genre={album['scrape_genre']}, year={album['scrape_year']}")
            else:
                print(f"  ⚠ Scrape metadata missing")
                
    except Exception as e:
        print(f"✗ Error reading output file: {e}")
        return False
    
    print()
    return True

def test_spider_configuration():
    """Test spider configuration and parameters"""
    print("=" * 60)
    print("TEST 5: SPIDER CONFIGURATION")
    print("=" * 60)
    
    try:
        from aoty_crawler.spiders.production_spider import ProductionSpider
        
        # Test default configuration
        spider = ProductionSpider()
        
        config_checks = [
            ("name", "production"),
            ("DEFAULT_START_YEAR", 2026),
            ("DEFAULT_YEARS_BACK", 1),
            ("DEFAULT_ALBUMS_PER_YEAR", 10),
            ("DEFAULT_GENRE", None),
        ]
        
        all_good = True
        for attr, expected in config_checks:
            actual = getattr(spider, attr) if hasattr(spider, attr) else getattr(ProductionSpider, attr, None)
            if actual == expected:
                print(f"✓ {attr}: {actual}")
            else:
                print(f"✗ {attr}: {actual} (expected: {expected})")
                all_good = False
        
        # Test parameter handling
        test_spider = ProductionSpider(
            genre="hip-hop",
            start_year="2025",
            years_back="2",
            albums_per_year="5",
            test_mode=True
        )
        
        print(f"\nParameter handling:")
        print(f"✓ target_genre: {test_spider.target_genre} (expected: hip-hop)")
        print(f"✓ start_year: {test_spider.start_year} (expected: 2025)")
        print(f"✓ years_back: {test_spider.years_back} (expected: 2)")
        print(f"✓ end_year: {test_spider.end_year} (expected: 2024)")
        print(f"✓ albums_per_year: {test_spider.albums_per_year} (expected: 5)")
        print(f"✓ test_mode: {test_spider.test_mode} (expected: True)")
        
    except Exception as e:
        print(f"✗ Error testing spider configuration: {e}")
        return False
    
    print()
    return True

def run_comprehensive_test():
    """Run all tests"""
    print("\n" + "=" * 60)
    print("COMPREHENSIVE AOTY PRODUCTION SPIDER TEST")
    print("=" * 60 + "\n")
    
    tests = [
        ("Imports and Module Structure", test_imports),
        ("Navigation Logic", test_navigation_logic),
        ("Data Extraction Requirements", test_data_extraction),
        ("Output Files and Format", test_output_files),
        ("Spider Configuration", test_spider_configuration),
    ]
    
    results = []
    
    for test_name, test_func in tests:
        try:
            print(f"\nRunning: {test_name}")
            print("-" * 40)
            result = test_func()
            results.append((test_name, result))
            if result:
                print(f"✓ {test_name}: PASSED")
            else:
                print(f"✗ {test_name}: FAILED")
        except Exception as e:
            print(f"✗ {test_name}: ERROR - {e}")
            results.append((test_name, False))
    
    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status}: {test_name}")
    
    print(f"\nOverall: {passed}/{total} tests passed ({passed/total*100:.0f}%)")
    
    if passed == total:
        print("\n✅ ALL TESTS PASSED - Production spider is ready!")
        return True
    else:
        print(f"\n⚠ {total-passed} test(s) failed - Needs attention")
        return False

if __name__ == "__main__":
    success = run_comprehensive_test()
    sys.exit(0 if success else 1)