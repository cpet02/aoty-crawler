#!/usr/bin/env python3
"""
Production Test Spider - Small test version
Tests just 1 genre with 2 albums
"""

import scrapy
import re
from datetime import datetime
from aoty_crawler.items import AlbumItem


class ProductionTestSpider(scrapy.Spider):
    name = "production_test"
    allowed_domains = ["albumoftheyear.org"]
    
    custom_settings = {
        'DOWNLOAD_DELAY': 3,
        'USER_AGENT': 'AOTY-Production-Test/1.0 (Testing)',
        'ROBOTSTXT_OBEY': True,
        'CONCURRENT_REQUESTS': 1,
    }
    
    def start_requests(self):
        """Start at the genre page but only test one genre"""
        self.logger.info("Starting at genre page: https://www.albumoftheyear.org/genre.php")
        yield scrapy.Request(
            url="https://www.albumoftheyear.org/genre.php",
            callback=self.parse_genre_page,
            meta={'test_mode': True}
        )
    
    def parse_genre_page(self, response):
        """Parse genre page and extract just ONE genre for testing"""
        test_mode = response.meta.get('test_mode', False)
        
        self.logger.info(f"Parsing genre page: {response.url}")
        
        # Extract genre links
        genre_links = response.css('a[href*="/genre/"]')
        self.logger.info(f"Found {len(genre_links)} genre links")
        
        # For testing: just get the first REAL genre (skip "View More")
        test_genre = None
        for link in genre_links:
            href = link.css('::attr(href)').get()
            text = link.css('::text').get()
            
            if not href or not text:
                continue
            
            # Skip "View More" links
            if text.lower() in ['view more', 'similar artists', 'follow']:
                continue
            
            # Extract genre slug from URL: /genre/7-rock/ -> "rock"
            match = re.search(r'/genre/\d+-(.+)/', href)
            if match:
                genre_slug = match.group(1)
                genre_name = text.strip()
                
                self.logger.info(f"Found genre for testing: {genre_name} (slug: {genre_slug})")
                test_genre = {
                    'slug': genre_slug,
                    'name': genre_name,
                    'url': response.urljoin(href)
                }
                break
        
        if not test_genre:
            self.logger.error("No suitable genre found for testing!")
            return
        
        # Test with just 2026 and 2 albums
        test_year = 2026
        max_albums = 2
        
        ratings_url = f"/ratings/user-highest-rated/{test_year}/{test_genre['slug']}/"
        full_url = response.urljoin(ratings_url)
        
        self.logger.info(f"TESTING: {test_genre['name']} - {test_year} (max {max_albums} albums)")
        self.logger.info(f"URL: {full_url}")
        
        yield scrapy.Request(
            url=full_url,
            callback=self.parse_ratings_page,
            meta={
                'genre_name': test_genre['name'],
                'genre_slug': test_genre['slug'],
                'year': test_year,
                'max_albums': max_albums,
                'albums_scraped_this_page': 0,
                'test_mode': True
            }
        )
    
    def parse_ratings_page(self, response):
        """Parse ratings page and extract album links"""
        genre_name = response.meta['genre_name']
        year = response.meta['year']
        max_albums = response.meta['max_albums']
        albums_scraped_this_page = response.meta.get('albums_scraped_this_page', 0)
        
        self.logger.info(f"\nParsing ratings page: {genre_name} - {year}")
        self.logger.info(f"URL: {response.url}")
        
        # Extract album links
        album_links = response.css('.albumListRow .albumListTitle a::attr(href)').getall()
        self.logger.info(f"Found {len(album_links)} album links on this page")
        
        # Limit number of albums based on test configuration
        albums_to_scrape = min(
            len(album_links),
            max_albums - albums_scraped_this_page
        )
        
        if albums_to_scrape <= 0:
            self.logger.info(f"Reached album limit for {genre_name} {year}")
            return
        
        self.logger.info(f"Will scrape {albums_to_scrape} albums from this page")
        
        # Follow album links
        for i, album_link in enumerate(album_links[:albums_to_scrape]):
            full_album_url = response.urljoin(album_link)
            
            self.logger.info(f"  [{i+1}/{albums_to_scrape}] Album: {full_album_url}")
            
            yield scrapy.Request(
                url=full_album_url,
                callback=self.parse_album_page,
                meta={
                    'genre_name': genre_name,
                    'year': year,
                    'album_number': albums_scraped_this_page + i + 1
                }
            )
        
        # Check for pagination (but skip for test)
        next_page = response.css('a.next::attr(href)').get()
        if next_page and albums_scraped_this_page + len(album_links) < max_albums:
            self.logger.info(f"Found next page but skipping for test: {next_page}")
            # For test, we won't follow pagination
    
    def parse_album_page(self, response):
        """Parse album page using comprehensive extraction"""
        genre_name = response.meta['genre_name']
        year = response.meta['year']
        album_number = response.meta['album_number']
        
        self.logger.info(f"\n[Album {album_number}] Parsing: {response.url}")
        self.logger.info(f"  Genre: {genre_name}, Year: {year}")
        
        # Create album item
        album = AlbumItem()
        album['url'] = response.url
        album['scraped_at'] = datetime.utcnow()
        
        # Extract AOTY ID from URL
        album['aoty_id'] = self._extract_aoty_id(response.url)
        
        # 1. Extract Album Title
        album['title'] = self._extract_album_title(response)
        
        # 2. Extract Artist Name
        album['artist_name'] = self._extract_artist_name(response)
        
        # 3. Extract Release Date
        album['release_date'] = self._extract_release_date(response)
        
        # 4. Extract Critic Score
        album['critic_score'] = self._extract_critic_score(response)
        
        # 5. Extract User Score
        album['user_score'] = self._extract_user_score(response)
        
        # 6. Extract Critic Review Count
        album['critic_review_count'] = self._extract_critic_review_count(response)
        
        # 7. Extract User Review Count
        album['user_review_count'] = self._extract_user_review_count(response)
        
        # 8. Extract Genres
        album['genres'] = self._extract_genres(response)
        
        # 9. Extract Genre Tags (secondary genres)
        album['genre_tags'] = self._extract_genre_tags(response)
        
        # 10. Extract Cover Image URL
        album['cover_image_url'] = self._extract_cover_image(response)
        
        # 11. Extract Description
        album['description'] = self._extract_description(response)
        
        # Log what we found
        self.logger.info(f"  ✓ Extracted: {album.get('title', 'Unknown')} by {album.get('artist_name', 'Unknown')}")
        
        yield album
    
    # ===== EXTRACTION METHODS =====
    
    def _extract_aoty_id(self, url):
        """Extract AOTY ID from URL"""
        match = re.search(r'/album/(\d+-[^/]+)\.php', url)
        if match:
            return match.group(1)
        return None
    
    def _extract_album_title(self, response):
        """Extract album title"""
        selectors = [
            'h1.albumTitle span[itemprop="name"]::text',
            'meta[property="og:title"]::attr(content)',
            'h1::text',
        ]
        
        for selector in selectors:
            title = response.css(selector).get()
            if title:
                if ' - ' in title:
                    title = title.split(' - ', 1)[1].strip()
                return title.strip()
        
        return None
    
    def _extract_artist_name(self, response):
        """Extract artist name"""
        selectors = [
            '[itemprop="byArtist"] span[itemprop="name"] a::text',
            '.artist a::text',
            'meta[property="og:title"]::attr(content)',
        ]
        
        for selector in selectors:
            artist = response.css(selector).get()
            if artist:
                if ' - ' in artist:
                    artist = artist.split(' - ', 1)[0].strip()
                if artist.lower() not in ['discography', 'submit correction']:
                    return artist.strip()
        
        return None
    
    def _extract_release_date(self, response):
        """Extract release date"""
        release_text = response.css('.detailRow:contains("Release Date")').get()
        if release_text:
            date_match = re.search(r'>([A-Za-z]+)\s+(\d+),\s+(\d{4})<', release_text)
            if date_match:
                month, day, year = date_match.groups()
                return f"{month} {day}, {year}"
        
        date_parts = response.css('.detailRow a[href*="/releases/"]::text').getall()
        if len(date_parts) >= 2:
            month = date_parts[0]
            year = date_parts[1].strip()
            day_match = re.search(r'>(\d+),<', release_text or '')
            day = day_match.group(1) if day_match else "1"
            return f"{month} {day}, {year}"
        
        return None
    
    def _extract_critic_score(self, response):
        """Extract critic score"""
        score = response.css('[itemprop="ratingValue"] a::text').get()
        if score:
            try:
                return float(score)
            except ValueError:
                return None
        return None
    
    def _extract_user_score(self, response):
        """Extract user score"""
        score = response.css('.albumUserScore a::text').get()
        if score:
            try:
                return float(score)
            except ValueError:
                return None
        
        ratings = response.css('.rating::text').getall()
        for rating in ratings:
            if rating.strip() and rating.strip() != 'NR':
                try:
                    return float(rating.strip())
                except ValueError:
                    continue
        
        return None
    
    def _extract_critic_review_count(self, response):
        """Extract critic review count"""
        count = response.css('meta[itemprop="reviewCount"]::attr(content)').get()
        if count:
            try:
                return int(count)
            except ValueError:
                pass
        
        count = response.css('span[itemprop="ratingCount"]::text').get()
        if count:
            try:
                return int(count)
            except ValueError:
                pass
        
        text = response.css('.albumCriticScoreBox .numReviews::text').get()
        if text:
            match = re.search(r'(\d+)', text)
            if match:
                try:
                    return int(match.group(1))
                except ValueError:
                    pass
        
        return None
    
    def _extract_user_review_count(self, response):
        """Extract user review count"""
        text = response.css('.albumUserScoreBox .numReviews strong::text').get()
        if text:
            try:
                return int(text)
            except ValueError:
                pass
        
        link_text = response.css('.albumUserScoreBox .numReviews a::text').get()
        if link_text:
            match = re.search(r'(\d+)', link_text)
            if match:
                try:
                    return int(match.group(1))
                except ValueError:
                    pass
        
        return None
    
    def _extract_genres(self, response):
        """Extract primary genres"""
        genres = []
        
        meta_genres = response.css('meta[itemprop="genre"]::attr(content)').getall()
        genres.extend(meta_genres)
        
        genre_links = response.css('.detailRow a[href*="/genre/"]::text').getall()
        for genre in genre_links:
            if genre and genre not in genres:
                genres.append(genre.strip())
        
        seen = set()
        unique_genres = []
        for genre in genres:
            if genre and genre not in seen:
                seen.add(genre)
                unique_genres.append(genre)
        
        return unique_genres if unique_genres else None
    
    def _extract_genre_tags(self, response):
        """Extract secondary genre tags"""
        tags = response.css('.detailRow .secondary::text').getall()
        if tags:
            return [tag.strip() for tag in tags if tag.strip()]
        return None
    
    def _extract_cover_image(self, response):
        """Extract cover image URL"""
        selectors = [
            '.albumTopBox.cover img::attr(src)',
            'meta[property="og:image"]::attr(content)',
            'img[alt*=" - "]::attr(src)',
        ]
        
        for selector in selectors:
            image = response.css(selector).get()
            if image:
                return image
        
        return None
    
    def _extract_description(self, response):
        """Extract album description"""
        desc = response.css('meta[name="Description"]::attr(content)').get()
        if desc:
            return desc
        
        desc = response.css('meta[property="og:description"]::attr(content)').get()
        if desc:
            return desc
        
        return None