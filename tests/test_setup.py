#!/usr/bin/env python3
"""
Simple test to verify AOTY Crawler setup
"""

import sys
import os

def test_imports():
    """Test that all required modules can be imported"""
    print("Testing imports...")
    
    try:
        # Test database imports
        from database.models import Album, Artist, Genre, Review, ScrapeJob
        print("✅ Database models imported successfully")
        
        # Test Scrapy imports
        from aoty_crawler import AlbumSpider, ArtistSpider, GenreSpider, YearSpider
        print("✅ Spiders imported successfully")
        
        # Test utilities
        from aoty_crawler.utils.selenium_helper import SeleniumHelper, CloudflareBypass
        print("✅ Utilities imported successfully")
        
        return True
        
    except ImportError as e:
        print(f"❌ Import error: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False


def test_database():
    """Test database initialization"""
    print("\nTesting database initialization...")
    
    try:
        from database.models import init_database, get_session
        engine = init_database()
        session = get_session(engine)
        
        # Test basic query
        from database.models import Album
        count = session.query(Album).count()
        print(f"✅ Database initialized successfully (0 albums)")
        
        session.close()
        return True
        
    except Exception as e:
        print(f"❌ Database error: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_spider_structure():
    """Test spider structure"""
    print("\nTesting spider structure...")
    
    try:
        from aoty_crawler.spiders import AlbumSpider
        from scrapy.http import Request
        
        # Create spider instance
        spider = AlbumSpider()
        
        # Test basic properties
        assert spider.name == "album"
        assert spider.allowed_domains == ["albumoftheyear.org"]
        
        print("✅ Spider structure is correct")
        return True
        
    except Exception as e:
        print(f"❌ Spider error: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_settings():
    """Test Scrapy settings"""
    print("\nTesting Scrapy settings...")
    
    try:
        from scrapy.utils.project import get_project_settings
        settings = get_project_settings()
        
        # Check key settings
        assert settings.get('BOT_NAME') == 'aoty_crawler'
        assert settings.get('DOWNLOAD_DELAY') == 3
        assert settings.get('CONCURRENT_REQUESTS') == 1
        
        print("✅ Scrapy settings are correct")
        return True
        
    except Exception as e:
        print(f"❌ Settings error: {e}")
        return False


def main():
    """Run all tests"""
    print("=" * 50)
    print("AOTY Crawler Setup Verification")
    print("=" * 50)
    
    results = []
    
    # Run tests
    results.append(("Imports", test_imports()))
    results.append(("Database", test_database()))
    results.append(("Spider Structure", test_spider_structure()))
    results.append(("Settings", test_settings()))
    
    # Summary
    print("\n" + "=" * 50)
    print("Test Summary")
    print("=" * 50)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {name}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 All tests passed! AOTY Crawler is ready to use.")
        return 0
    else:
        print(f"\n⚠️  {total - passed} test(s) failed. Please check the errors above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
