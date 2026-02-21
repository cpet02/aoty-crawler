#!/usr/bin/env python3
"""
Comprehensive Album Spider - Extract ALL data from album pages
Based on HTML structure analysis from debug files
"""

import scrapy
import re
from datetime import datetime
from aoty_crawler.items import AlbumItem


class ComprehensiveAlbumSpider(scrapy.Spider):
    name = "comprehensive_album"
    allowed_domains = ["albumoftheyear.org"]
    
    # Test with a few different albums to ensure robustness
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
        # Check if this is an album page
        if '/album/' not in response.url:
            self.logger.warning(f"Not an album page: {response.url}")
            return
        
        self.logger.info(f"Parsing album page: {response.url}")
        
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
        self._log_extraction_results(album)
        
        yield album
    
    def _extract_aoty_id(self, url):
        """Extract AOTY ID from URL"""
        # URL format: https://www.albumoftheyear.org/album/123456-album-name.php
        match = re.search(r'/album/(\d+-[^/]+)\.php', url)
        if match:
            return match.group(1)
        return None
    
    def _extract_album_title(self, response):
        """Extract album title"""
        # Try multiple selectors
        selectors = [
            'h1.albumTitle span[itemprop="name"]::text',
            'meta[property="og:title"]::attr(content)',
            'h1::text',
        ]
        
        for selector in selectors:
            title = response.css(selector).get()
            if title:
                # Clean up if from og:title (Artist - Album format)
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
                # Clean up if from og:title (Artist - Album format)
                if ' - ' in artist:
                    artist = artist.split(' - ', 1)[0].strip()
                # Filter out non-artist names
                if artist.lower() not in ['discography', 'submit correction']:
                    return artist.strip()
        
        return None
    
    def _extract_release_date(self, response):
        """Extract release date"""
        # Look for release date in detail row
        release_text = response.css('.detailRow:contains("Release Date")').get()
        if release_text:
            # Extract date using regex
            date_match = re.search(r'>([A-Za-z]+)\s+(\d+),\s+(\d{4})<', release_text)
            if date_match:
                month, day, year = date_match.groups()
                return f"{month} {day}, {year}"
        
        # Try alternative: look for date links
        date_parts = response.css('.detailRow a[href*="/releases/"]::text').getall()
        if len(date_parts) >= 2:
            month = date_parts[0]
            year = date_parts[1].strip()
            # Try to find day
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
        
        # Alternative: look for .rating divs
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
        # Try meta tag first
        count = response.css('meta[itemprop="reviewCount"]::attr(content)').get()
        if count:
            try:
                return int(count)
            except ValueError:
                pass
        
        # Try span tag
        count = response.css('span[itemprop="ratingCount"]::text').get()
        if count:
            try:
                return int(count)
            except ValueError:
                pass
        
        # Try text extraction
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
        # Look in user score box
        text = response.css('.albumUserScoreBox .numReviews strong::text').get()
        if text:
            try:
                return int(text)
            except ValueError:
                pass
        
        # Alternative: extract from link text
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
        
        # Extract from meta tags
        meta_genres = response.css('meta[itemprop="genre"]::attr(content)').getall()
        genres.extend(meta_genres)
        
        # Extract from genre links (primary)
        genre_links = response.css('.detailRow a[href*="/genre/"]::text').getall()
        for genre in genre_links:
            if genre and genre not in genres:
                genres.append(genre.strip())
        
        # Remove duplicates while preserving order
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
        # Try multiple selectors
        selectors = [
            '.albumTopBox.cover img::attr(src)',
            'meta[property="og:image"]::attr(content)',
            'img[alt*=" - "]::attr(src)',  # Alt text often contains "Artist - Album"
        ]
        
        for selector in selectors:
            image = response.css(selector).get()
            if image:
                return image
        
        return None
    
    def _extract_description(self, response):
        """Extract album description"""
        # Try meta description
        desc = response.css('meta[name="Description"]::attr(content)').get()
        if desc:
            return desc
        
        # Try og:description
        desc = response.css('meta[property="og:description"]::attr(content)').get()
        if desc:
            return desc
        
        return None
    
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