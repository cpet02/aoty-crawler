#!/usr/bin/env python3
"""
Simple test to verify AOTY Crawler setup
"""

import sys


def test_imports():
    """Test that all required modules can be imported"""
    print("Testing imports...")

    try:
        from aoty_crawler.spiders import ComprehensiveAlbumSpider, ProductionSpider
        print("✅ Spiders imported successfully")

        from aoty_crawler.utils.data_loader import load_all_albums, filter_albums
        print("✅ Data loader imported successfully")

        return True

    except ImportError as e:
        print(f"❌ Import error: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False


def test_spider_structure():
    """Test spider structure"""
    print("\nTesting spider structure...")

    try:
        from aoty_crawler.spiders import ProductionSpider

        spider = ProductionSpider()

        assert spider.name == "production"
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

    results = [
        ("Imports", test_imports()),
        ("Spider Structure", test_spider_structure()),
        ("Settings", test_settings()),
    ]

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
