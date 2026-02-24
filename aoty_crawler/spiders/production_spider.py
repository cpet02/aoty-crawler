#!/usr/bin/env python3
"""
Production Spider - Complete AOTY scraping solution
Combines genre navigation with comprehensive album extraction
"""

import scrapy
import re
import os
import json
from datetime import datetime
from aoty_crawler.items import AlbumItem


class ProductionSpider(scrapy.Spider):
    name = "production"
    allowed_domains = ["albumoftheyear.org"]
    
    # Configuration (can be overridden via CLI)
    DEFAULT_START_YEAR = 2026
    DEFAULT_YEARS_BACK = 1
    DEFAULT_ALBUMS_PER_YEAR = 10  # Small for testing, increase to 250 for production
    DEFAULT_GENRE = None  # None = scrape all genres
    
    custom_settings = {
        'DOWNLOAD_DELAY': 3,
        'USER_AGENT': 'AOTY-Production-Spider/1.0 (Music Data Collection)',
        'ROBOTSTXT_OBEY': True,
        'CONCURRENT_REQUESTS': 1,
    }
    
    def __init__(self, genre=None, start_year=None, years_back=None, 
                 albums_per_year=None, test_mode=False, resume=False, 
                 resume_file=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Set configuration
        self.target_genre = genre or self.DEFAULT_GENRE
        self.start_year = int(start_year) if start_year else self.DEFAULT_START_YEAR
        self.years_back = int(years_back) if years_back else self.DEFAULT_YEARS_BACK
        self.albums_per_year = int(albums_per_year) if albums_per_year else self.DEFAULT_ALBUMS_PER_YEAR
        self.test_mode = test_mode
        self.resume_mode = resume
        
        # Calculate year range
        self.end_year = self.start_year - self.years_back + 1
        
        # Track progress
        self.albums_scraped = 0
        self.genres_scraped = 0
        
        # Resume functionality
        self.scraped_urls = set()
        if self.resume_mode:
            self._load_resume_data(resume_file)
        
        self.logger.info(f"\n{'='*60}")
        self.logger.info("PRODUCTION SPIDER CONFIGURATION")
        self.logger.info(f"{'='*60}")
        self.logger.info(f"Target Genre: {self.target_genre or 'ALL GENRES'}")
        self.logger.info(f"Year Range: {self.start_year} to {self.end_year}")
        self.logger.info(f"Albums per Year: {self.albums_per_year}")
        self.logger.info(f"Test Mode: {self.test_mode}")
        self.logger.info(f"Resume Mode: {self.resume_mode}")
        if self.resume_mode:
            self.logger.info(f"Already scraped URLs: {len(self.scraped_urls)}")
        self.logger.info(f"{'='*60}\n")
    
    def _load_resume_data(self, resume_file=None):
        """Load previously scraped URLs from JSON files"""
        try:
            output_dir = self.settings.get('OUTPUT_DIR', 'data/output')
            
            if resume_file:
                # Load from specified file
                files_to_check = [resume_file]
            else:
                # Find all JSON files in output directory
                files_to_check = []
                if os.path.exists(output_dir):
                    for filename in os.listdir(output_dir):
                        if filename.startswith('albums_') and filename.endswith('.json'):
                            files_to_check.append(os.path.join(output_dir, filename))
            
            for filepath in files_to_check:
                if os.path.exists(filepath):
                    with open(filepath, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        for album in data:
                            if 'url' in album:
                                self.scraped_urls.add(album['url'])
            
            self.logger.info(f"Loaded {len(self.scraped_urls)} previously scraped URLs")
            
        except Exception as e:
            self.logger.warning(f"Could not load resume data: {e}")
    
    def start_requests(self):
        """Start at the genre page"""
        self.logger.info("Starting at genre page: https://www.albumoftheyear.org/genre.php")
        yield scrapy.Request(
            url="https://www.albumoftheyear.org/genre.php",
            callback=self.parse_genre_page
        )
    
    def parse_genre_page(self, response):
        """Parse genre page and extract genre links"""
        self.logger.info(f"Parsing genre page: {response.url}")
        
        # Try to find "All Genres" section first
        # Look for the "All Genres" heading and extract links from that section
        all_genres_links = []
        
        # Method 1: Look for "All Genres" heading and extract subsequent links
        all_genres_heading = response.xpath('//*[contains(text(), "All Genres")]/following::a[contains(@href, "/genre/") and not(contains(text(), "View More")) and not(contains(text(), "similar artists")) and not(contains(text(), "follow"))]/@href').getall()
        
        if all_genres_heading:
            self.logger.info(f"Found 'All Genres' section with {len(all_genres_heading)} genre links")
            all_genres_links = all_genres_heading
        else:
            # Method 2: Fallback - extract all genre links but filter more aggressively
            self.logger.info("'All Genres' section not found, using fallback method")
            
            # Get all genre links
            all_links = response.css('a[href*="/genre/"]::attr(href)').getall()
            
            # Filter out common non-genre links
            excluded_texts = ['view more', 'similar artists', 'follow', 'on this day', 'newsworthy', 'user updates', 'site updates', 'privacy policy', 'contact us', 'ad-free', 'highest rated', 'must hear albums', 'year end lists', 'new releases', 'random']
            
            for href in all_links:
                # Skip if it's a genre list page (we want individual genre pages)
                if '/genre/list' in href or '/genre.php' in href:
                    continue
                
                # Extract genre slug to check if it looks like a genre page
                match = re.search(r'/genre/\d+-(.+)/', href)
                if match:
                    all_genres_links.append(href)
            
            self.logger.info(f"Found {len(all_genres_links)} potential genre links (fallback method)")
        
        # Process the genre links
        genres_processed = set()
        
        for href in all_genres_links:
            # Get the text for this link (try to find the corresponding anchor tag)
            text = None
            for link in response.css('a[href="' + href + '"]'):
                text = link.css('::text').get()
                if text:
                    break
            
            if not text:
                # Try to extract text from the href itself
                match = re.search(r'/genre/\d+-(.+)/', href)
                if match:
                    text = match.group(1).replace('-', ' ').title()
            
            if not text:
                continue
            
            # Skip "View More" links and non-genre links
            if text.lower() in ['view more', 'similar artists', 'follow', 'on this day', 'newsworthy', 'user updates', 'site updates', 'privacy policy', 'contact us']:
                continue
            
            # Extract genre slug from URL: /genre/7-rock/ -> "rock"
            match = re.search(r'/genre/\d+-(.+)/', href)
            if not match:
                continue
            
            genre_slug = match.group(1)
            genre_name = text.strip()
            
            # Skip if we've already processed this genre
            if genre_slug in genres_processed:
                continue
            
            genres_processed.add(genre_slug)
            
            # If target genre is specified, only process that genre
            if self.target_genre:
                # Try multiple variations of the genre name
                target_genre_lower = self.target_genre.lower()
                genre_slug_lower = genre_slug.lower()
                genre_name_lower = genre_name.lower()
                
                # Check various possible matches
                matches = (
                    genre_slug_lower == target_genre_lower.replace(' ', '-') or
                    genre_slug_lower == target_genre_lower.replace('-', ' ') or
                    genre_slug_lower == target_genre_lower or
                    genre_slug_lower == target_genre_lower.replace(' ', '') or
                    genre_name_lower == target_genre_lower or
                    genre_name_lower == target_genre_lower.replace('-', ' ') or
                    target_genre_lower in genre_slug_lower or
                    target_genre_lower in genre_name_lower
                )
                
                if not matches:
                    continue
            
            self.logger.info(f"Found genre: {genre_name} (slug: {genre_slug})")
            
            # For each year in range, create ratings page URL
            for year in range(self.start_year, self.end_year - 1, -1):  # Go backwards
                ratings_url = f"/ratings/user-highest-rated/{year}/{genre_slug}/"
                full_url = response.urljoin(ratings_url)
                
                self.logger.info(f"  → Year {year}: {full_url}")
                
                yield scrapy.Request(
                    url=full_url,
                    callback=self.parse_ratings_page,
                    meta={
                        'genre_name': genre_name,
                        'genre_slug': genre_slug,
                        'year': year,
                        'albums_scraped_this_page': 0
                    }
                )
                
                # In test mode, just test first year
                if self.test_mode:
                    break
            
            # In test mode, just test first genre
            if self.test_mode:
                break
        
        self.logger.info(f"Total unique genres found: {len(genres_processed)}")
        self.genres_scraped = len(genres_processed)
    
    def parse_ratings_page(self, response):
        """Parse ratings page and extract album links"""
        genre_name = response.meta['genre_name']
        genre_slug = response.meta['genre_slug']
        year = response.meta['year']
        albums_scraped_this_page = response.meta.get('albums_scraped_this_page', 0)
        
        self.logger.info(f"\nParsing ratings page: {genre_name} - {year}")
        self.logger.info(f"URL: {response.url}")
        
        # Extract album links
        album_links = response.css('.albumListRow .albumListTitle a::attr(href)').getall()
        self.logger.info(f"Found {len(album_links)} album links on this page")
        
        # Filter out already scraped URLs in resume mode
        if self.resume_mode:
            filtered_links = []
            for link in album_links:
                full_url = response.urljoin(link)
                if full_url not in self.scraped_urls:
                    filtered_links.append(link)
                else:
                    self.logger.info(f"  Skipping already scraped: {full_url}")
            
            album_links = filtered_links
            self.logger.info(f"After filtering: {len(album_links)} new albums to scrape")
        
        # Limit number of albums based on configuration
        albums_to_scrape = min(
            len(album_links),
            self.albums_per_year - albums_scraped_this_page
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
                    'genre_slug': genre_slug,
                    'year': year,
                    'album_number': albums_scraped_this_page + i + 1
                }
            )
        
        # Check for pagination (next page)
        next_page = response.css('a.next::attr(href)').get()
        if next_page and albums_scraped_this_page + len(album_links) < self.albums_per_year:
            self.logger.info(f"Found next page: {next_page}")
            
            yield scrapy.Request(
                url=response.urljoin(next_page),
                callback=self.parse_ratings_page,
                meta={
                    'genre_name': genre_name,
                    'genre_slug': genre_slug,
                    'year': year,
                    'albums_scraped_this_page': albums_scraped_this_page + len(album_links)
                }
            )
    
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
        
        # Add metadata
        album['scrape_genre'] = genre_name
        album['scrape_year'] = year
        
        # Update counters
        self.albums_scraped += 1
        
        # Add to scraped URLs for resume functionality
        if self.resume_mode:
            self.scraped_urls.add(response.url)
        
        # Log progress
        self.logger.info(f"  ✓ Extracted: {album.get('title', 'Unknown')} by {album.get('artist_name', 'Unknown')}")
        self.logger.info(f"  Total albums scraped: {self.albums_scraped}")
        
        yield album
    
    # ===== EXTRACTION METHODS (reused from comprehensive_album_spider) =====
    
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
        # Try to find release date in detail rows
        detail_rows = response.css('.detailRow')
        for row in detail_rows:
            row_text = ' '.join(row.css('::text').getall())
            if 'Release Date' in row_text:
                # Extract date from this row
                date_match = re.search(r'>([A-Za-z]+)\s+(\d+),\s+(\d{4})<', row.get())
                if date_match:
                    month, day, year = date_match.groups()
                    return f"{month} {day}, {year}"
        
        # Fallback: try to extract from release links
        date_parts = response.css('.detailRow a[href*="/releases/"]::text').getall()
        if len(date_parts) >= 2:
            month = date_parts[0]
            year = date_parts[1].strip()
            # Try to find day from any detail row
            detail_text = ' '.join(response.css('.detailRow::text').getall())
            day_match = re.search(r'(\d+),', detail_text)
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
        # Method 1: Look for strong tag inside numReviews
        text = response.css('.albumUserScoreBox .numReviews strong::text').get()
        if text:
            try:
                # Remove commas before converting (handles "1,234" → 1234)
                clean_text = text.replace(',', '').strip()
                return int(clean_text)
            except ValueError:
                pass
        
        # Method 2: Look for link text with numbers
        link_text = response.css('.albumUserScoreBox .numReviews a::text').get()
        if link_text:
            # Match numbers with optional commas: "2,341" or "2341"
            match = re.search(r'([\d,]+)', link_text)
            if match:
                try:
                    # Strip commas and convert: "2,341" → 2341
                    clean_number = match.group(1).replace(',', '')
                    return int(clean_number)
                except ValueError:
                    pass
        
        # If both methods fail, return None
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
    
    def closed(self, reason):
        """Log final statistics when spider closes"""
        self.logger.info(f"\n{'='*60}")
        self.logger.info("SCRAPING COMPLETE!")
        self.logger.info(f"{'='*60}")
        self.logger.info(f"Total albums scraped: {self.albums_scraped}")
        self.logger.info(f"Total genres processed: {self.genres_scraped}")
        if self.resume_mode:
            self.logger.info(f"Total unique URLs scraped: {len(self.scraped_urls)}")
        self.logger.info(f"Finish reason: {reason}")
        self.logger.info(f"{'='*60}")
