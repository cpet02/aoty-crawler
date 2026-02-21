#!/usr/bin/env python3
"""
Test Spider for AOTY Crawler
A minimal spider to verify the setup works
"""

import scrapy
from aoty_crawler.items import AlbumItem, ArtistItem


class TestSpider(scrapy.Spider):
    name = "test"
    allowed_domains = ["albumoftheyear.org"]
    start_urls = [
        "https://www.albumoftheyear.org/album/183-kanye-west-the-beast.php",
        "https://www.albumoftheyear.org/artist/183-kanye-west/"
    ]
    
    custom_settings = {
        'DOWNLOAD_DELAY': 1,  # Be polite
        'USER_AGENT': 'AOTY-Test-Spider/1.0 (Testing Purposes)',
    }
    
    def parse(self, response):
        """Parse album or artist pages"""
        # Ensure response is text (handle binary responses)
        try:
            # Try to decode if needed (brotli/deflate can cause binary responses)
            if isinstance(response.body, bytes):
                try:
                    text = response.text  # Scrapy tries to decode based on headers
                except:
                    # Fallback: try common encodings
                    text = response.body.decode('utf-8', errors='replace')
                response = response.replace(body=text)
        except Exception as e:
            self.logger.warning(f"Could not decode response: {e}")
        
        # Check URL pattern first to determine page type
        url = response.url
        
        if '/album/' in url:
            # Definitely an album page
            album = self._parse_album(response)
            if album:
                yield album
            else:
                self.logger.warning(f"Failed to parse album page: {url}")
            return
            
        elif '/artist/' in url:
            # Definitely an artist page
            artist = self._parse_artist(response)
            if artist:
                yield artist
            else:
                self.logger.warning(f"Failed to parse artist page: {url}")
            return
        
        # Unknown page type - try both
        album = self._parse_album(response)
        if album:
            yield album
            return
            
        artist = self._parse_artist(response)
        if artist:
            yield artist
            return
        
        self.logger.warning(f"Could not parse page: {url}")
    
    def _parse_album(self, response):
        """Parse album page"""
        # Check if this looks like an album page
        # First check URL pattern
        if '/album/' not in response.url:
            # Not an album URL, but might still be an album page
            # Check for album-specific elements
            has_album_title = response.css('h1.albumTitle').get()
            has_album_scores = response.css('[itemprop="ratingValue"]').get()
            
            if not has_album_title and not has_album_scores:
                return None
        
        # Look for album title (common AOTY pattern)
        title = response.css('h1.albumTitle span[itemprop="name"]::text').get()
        if not title:
            # Try alternative selector
            title = response.css('meta[property="og:title"]::attr(content)').get()
            if title and ' - ' in title:
                # Extract just album name from "Artist - Album" format
                title = title.split(' - ', 1)[1]
        
        if not title:
            return None
        
        self.logger.info(f"Found album: {title}")
        
        album = AlbumItem()
        # Extract ID from URL - format: /album/183-sunn-o-monoliths-and-dimensions.php
        url_parts = response.url.split('/')
        for part in url_parts:
            if '-' in part and not part.startswith('http'):
                album['aoty_id'] = part.replace('.php', '')
                break
        else:
            album['aoty_id'] = response.url.split('/')[-1].replace('.php', '')
        
        album['title'] = title.strip()
        album['url'] = response.url
        album['scraped_at'] = response.meta.get('scraped_at')
        
        # Try to extract more fields
        # Extract artist using correct selector from debug analysis
        artist_name = response.css('[itemprop="byArtist"] span[itemprop="name"] a::text').get()
        
        if not artist_name:
            # Try alternative selector
            artist_name = response.css('a[href*="/artist/"]::text').get()
            # Filter out non-artist links (like "Discography")
            if artist_name and artist_name.lower() in ['discography', 'similar artists', 'follow']:
                artist_name = None
        
        if not artist_name:
            # Extract from og:title meta tag
            og_title = response.css('meta[property="og:title"]::attr(content)').get()
            if og_title and ' - ' in og_title:
                artist_name = og_title.split(' - ', 1)[0].strip()
                self.logger.info(f"Extracted artist from og:title: {artist_name}")
        
        album['artist_name'] = artist_name
        
        # Extract scores using correct selectors from debug analysis
        critic_score = response.css('[itemprop="ratingValue"] a::text').get()
        if critic_score:
            try:
                album['critic_score'] = float(critic_score)
                self.logger.info(f"Critic score: {critic_score}")
            except ValueError:
                self.logger.warning(f"Invalid critic score: {critic_score}")
        
        # User scores are in .rating divs
        user_scores = response.css('.rating::text').getall()
        if user_scores:
            # Usually first .rating is user score
            for score in user_scores:
                if score.strip() and score.strip() != 'NR':
                    try:
                        album['user_score'] = float(score.strip())
                        self.logger.info(f"User score: {score}")
                        break
                    except ValueError:
                        continue
        
        # Extract cover image
        album['cover_image_url'] = response.css('.albumCover img::attr(src)').get()
        
        # Extract description
        album['description'] = response.css('.fullWidth::text').get()
        
        return album
    
    def _parse_artist(self, response):
        """Parse artist page"""
        # Check if this looks like an artist page
        # First check URL pattern
        if '/artist/' not in response.url:
            # Not an artist URL, but might still be an artist page
            # Check for artist-specific elements
            has_artist_title = response.css('h1.artistTitle').get()
            has_artist_bio = response.css('.artistBio').get()
            
            if not has_artist_title and not has_artist_bio:
                return None
        
        # Look for artist name - try multiple selectors
        name = None
        name_selectors = [
            'h1.artistTitle::text',
            'h1::text',
            '[itemprop="name"]::text',
            'meta[property="og:title"]::attr(content)',
        ]
        
        for selector in name_selectors:
            name = response.css(selector).get()
            if name:
                # Filter out common non-artist names
                if name.lower() in ['discography', 'submit correction', 'similar artists', 'follow']:
                    continue
                self.logger.info(f"Found artist name with selector '{selector}': {name}")
                break
        
        if not name:
            return None
        
        # Additional validation: artist name should not be too short
        if len(name.strip()) < 2:
            self.logger.warning(f"Artist name too short: '{name}'")
            return None
        
        self.logger.info(f"Found artist: {name}")
        
        artist = ArtistItem()
        artist['aoty_id'] = response.url.split('/')[-2]  # Extract ID from URL
        artist['name'] = name.strip()
        artist['url'] = response.url
        artist['scraped_at'] = response.meta.get('scraped_at')
        
        # Try to extract album count
        album_count = response.css('.albumCount::text').get()
        if album_count:
            try:
                artist['album_count'] = int(''.join(filter(str.isdigit, album_count)))
            except ValueError:
                self.logger.warning(f"Could not parse album count: {album_count}")
        
        return artist
