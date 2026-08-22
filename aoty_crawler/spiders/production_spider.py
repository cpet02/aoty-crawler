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
from aoty_crawler.spiders.album_extraction import AlbumExtractionMixin
from aoty_crawler.utils import job_tracker

# Non-genre links that turn up alongside real genre links on genre.php,
# keyed by their visible link text (lowercased). Used only by the "scrape
# ALL genres" path (parse_genre_page) below, which the UI doesn't currently
# expose (it always targets a single genre) — this list exists for whenever
# that path gets exercised again.
NON_GENRE_LINK_TEXTS = {
    'view more', 'similar artists', 'follow', 'on this day', 'newsworthy',
    'user updates', 'site updates', 'privacy policy', 'contact us',
    'ad-free', 'highest rated', 'must hear albums', 'year end lists',
    'new releases', 'random',
}


class ProductionSpider(AlbumExtractionMixin, scrapy.Spider):
    name = "production"
    allowed_domains = ["albumoftheyear.org"]

    # Configuration (can be overridden via CLI)
    DEFAULT_START_YEAR = datetime.utcnow().year
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
                 resume_file=None, job_id=None, *args, **kwargs):
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

        # Job tracking (completion-based progress, written for any UI to poll)
        self.job_id = job_id or job_tracker.new_job_id()
        # A single genre is targeted for the vast majority of runs, so the
        # total amount of work is known up front. When scraping ALL genres
        # the total isn't knowable until genre.php is parsed, so leave it
        # unset (None) and let consumers treat that as "unbounded".
        self.job_target_total = self.albums_per_year * self.years_back if self.target_genre else None

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
        """Start requests - bypass genre.php when target genre is specified"""
        # Absolute so the job status file's location doesn't depend on this
        # process's cwd (see the matching note in pipelines.py).
        self.output_dir = os.path.abspath(self.settings.get('OUTPUT_DIR', 'data/output'))
        self.jobs_dir = job_tracker.jobs_dir_for(self.output_dir)
        job_tracker.create_job(
            self.job_id,
            self.jobs_dir,
            params={
                'genre': self.target_genre,
                'start_year': self.start_year,
                'end_year': self.end_year,
                'years_back': self.years_back,
                'albums_per_year': self.albums_per_year,
                'test_mode': self.test_mode,
            },
            target_total=self.job_target_total,
        )

        if self.target_genre:
            # Bypass genre.php entirely - construct URL directly from genre name
            slug = self.target_genre.lower().replace(' ', '-')
            self.logger.info(f"Direct scrape for genre: {self.target_genre} (slug: {slug})")
            for year in range(self.start_year, self.end_year - 1, -1):
                url = f"https://www.albumoftheyear.org/ratings/user-highest-rated/{year}/{slug}/"
                self.logger.info(f"  → Year {year}: {url}")
                yield scrapy.Request(
                    url=url,
                    callback=self.parse_ratings_page,
                    meta={
                        'genre_name': self.target_genre,
                        'genre_slug': slug,
                        'year': year,
                        'albums_scraped_this_page': 0
                    }
                )
        else:
            # Only hit genre.php when scraping ALL genres
            self.logger.info("No genre specified - scraping all genres via genre.php")
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
            if text.lower() in NON_GENRE_LINK_TEXTS:
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
                
                # Check various possible matches - use exact matching to avoid substring issues
                matches = (
                    genre_slug_lower == target_genre_lower.replace(' ', '-') or
                    genre_slug_lower == target_genre_lower.replace('-', ' ').replace(' ', '-') or
                    genre_name_lower == target_genre_lower
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
        page_num = response.meta.get('page_num', 1)

        self.logger.info(f"\nParsing ratings page: {genre_name} - {year} (page {page_num})")
        self.logger.info(f"URL: {response.url}")

        job_tracker.update_job(
            self.job_id, self.jobs_dir,
            current_genre=genre_name, current_year=year,
        )

        # Extract album links
        album_links = response.css('.albumListRow .albumListTitle a::attr(href)').getall()
        self.logger.info(f"Found {len(album_links)} album links on this page")

        # If no albums found, we've gone past the last page - stop
        if not album_links:
            self.logger.info(f"No albums found on page {page_num}, stopping pagination")
            return

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

        for i, album_link in enumerate(album_links[:albums_to_scrape]):
            full_album_url = response.urljoin(album_link)
            self.logger.info(f"  [{albums_scraped_this_page + i + 1}/{self.albums_per_year}] Album: {full_album_url}")

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

        # Paginate if we still need more albums
        total_scraped = albums_scraped_this_page + len(album_links)
        if total_scraped < self.albums_per_year:
            next_page_num = page_num + 1
            next_url = f"https://www.albumoftheyear.org/ratings/user-highest-rated/{year}/{genre_slug}/{next_page_num}/"
            self.logger.info(f"Need more albums ({total_scraped}/{self.albums_per_year}), fetching page {next_page_num}: {next_url}")

            yield scrapy.Request(
                url=next_url,
                callback=self.parse_ratings_page,
                meta={
                    'genre_name': genre_name,
                    'genre_slug': genre_slug,
                    'year': year,
                    'albums_scraped_this_page': total_scraped,
                    'page_num': next_page_num
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
        self._extract_album_fields(response, album)

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

        job_tracker.update_job(
            self.job_id, self.jobs_dir,
            completed=self.albums_scraped,
            current_genre=genre_name, current_year=year,
        )

        yield album

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

        job_tracker.update_job(
            self.job_id, self.jobs_dir,
            status='completed' if reason == 'finished' else 'failed',
            completed=self.albums_scraped,
            ended_at=datetime.utcnow().isoformat(),
            finish_reason=reason,
        )
