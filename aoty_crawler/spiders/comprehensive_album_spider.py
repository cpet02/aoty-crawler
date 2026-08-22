#!/usr/bin/env python3
"""
Comprehensive Album Spider - Extract ALL data from a fixed set of album pages.
Intended for manual/debug verification of the extraction logic in album_extraction.py,
not for production scraping (see ProductionSpider for that).
"""

import scrapy
from datetime import datetime
from aoty_crawler.items import AlbumItem
from aoty_crawler.spiders.album_extraction import AlbumExtractionMixin


class ComprehensiveAlbumSpider(AlbumExtractionMixin, scrapy.Spider):
    name = "comprehensive_album"
    allowed_domains = ["albumoftheyear.org"]

    # Sample albums used to sanity-check extraction against real pages
    start_urls = [
        "https://www.albumoftheyear.org/album/183-sunn-o-monoliths-and-dimensions.php",
        "https://www.albumoftheyear.org/album/1608723-sarah-kinsley-fleeting.php",
        "https://www.albumoftheyear.org/album/123456-tom-petty-an-american-treasure.php",
    ]

    custom_settings = {
        'DOWNLOAD_DELAY': 3,
        'USER_AGENT': 'AOTY-Comprehensive-Spider/1.0 (Data Collection)',
        'ROBOTSTXT_OBEY': True,
    }

    def parse(self, response):
        """Parse album page and extract ALL data"""
        if '/album/' not in response.url:
            self.logger.warning(f"Not an album page: {response.url}")
            return

        self.logger.info(f"Parsing album page: {response.url}")

        album = AlbumItem()
        album['url'] = response.url
        album['scraped_at'] = datetime.utcnow()
        self._extract_album_fields(response, album)

        self._log_extraction_results(album)

        yield album

    def _log_extraction_results(self, album):
        """Log what data was extracted"""
        self.logger.info(f"\n{'='*60}")
        self.logger.info(f"EXTRACTION RESULTS for: {album.get('title', 'Unknown')}")
        self.logger.info(f"{'='*60}")

        fields = [
            ('AOTY ID', 'aoty_id'),
            ('Title', 'title'),
            ('Artist', 'artist_name'),
            ('Release Date', 'release_date'),
            ('Critic Score', 'critic_score'),
            ('User Score', 'user_score'),
            ('Critic Reviews', 'critic_review_count'),
            ('User Reviews', 'user_review_count'),
            ('Genres', 'genres'),
            ('Genre Tags', 'genre_tags'),
            ('Cover Image', 'cover_image_url'),
        ]

        for label, key in fields:
            value = album.get(key)
            if value is not None:
                self.logger.info(f"{label:20}: {value}")
            else:
                self.logger.warning(f"{label:20}: MISSING")

        self.logger.info(f"{'='*60}\n")
