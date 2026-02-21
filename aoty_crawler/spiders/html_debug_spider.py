#!/usr/bin/env python3
"""
HTML Debug Spider - Save and analyze HTML structure to find correct selectors
"""

import scrapy
import os
import json
from datetime import datetime


class HtmlDebugSpider(scrapy.Spider):
    name = "html_debug"
    allowed_domains = ["albumoftheyear.org"]
    
    # Test with a few different album URLs to see patterns
    start_urls = [
        "https://www.albumoftheyear.org/album/183-sunn-o-monoliths-and-dimensions.php",
        "https://www.albumoftheyear.org/album/1608723-sarah-kinsley-fleeting.php",
        "https://www.albumoftheyear.org/album/123456-test-album.php",  # Will 404, good for testing
    ]
    
    custom_settings = {
        'DOWNLOAD_DELAY': 2,
        'USER_AGENT': 'AOTY-Debug-Spider/1.0 (Testing Purposes)',
        'ROBOTSTXT_OBEY': False,  # Temporarily disable for debugging
    }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.debug_dir = 'debug_html'
        os.makedirs(self.debug_dir, exist_ok=True)
    
    def parse(self, response):
        """Save HTML and analyze structure"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        # Save full HTML
        filename = f"{self.debug_dir}/page_{timestamp}.html"
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(response.text)
        
        self.logger.info(f"Saved HTML to {filename}")
        
        # Save analysis
        analysis = self.analyze_page(response)
        analysis_file = f"{self.debug_dir}/analysis_{timestamp}.json"
        with open(analysis_file, 'w', encoding='utf-8') as f:
            json.dump(analysis, f, indent=2, default=str)
        
        self.logger.info(f"Saved analysis to {analysis_file}")
        
        # Print key findings to console
        self.print_analysis(analysis, response.url)
    
    def analyze_page(self, response):
        """Analyze page structure to find selectors"""
        analysis = {
            'url': response.url,
            'status': response.status,
            'title': response.css('title::text').get(),
            'h1_elements': response.css('h1::text').getall(),
            'h2_elements': response.css('h2::text').getall(),
            'album_title_candidates': [],
            'artist_candidates': [],
            'score_candidates': [],
            'date_candidates': [],
            'genre_candidates': [],
            'all_links': [],
        }
        
        # Look for album title patterns
        for selector in [
            'h1.albumTitle',
            '.albumTitle',
            'h1',
            '.title',
            '[itemprop="name"]',
            'meta[property="og:title"]::attr(content)',
        ]:
            result = response.css(selector).getall()
            if result:
                analysis['album_title_candidates'].append({
                    'selector': selector,
                    'results': result[:3]  # First 3 results
                })
        
        # Look for artist patterns
        for selector in [
            '.artistName',
            '[itemprop="byArtist"]',
            '.albumTitle a',
            'a[href*="/artist/"]',
            'meta[property="music:musician"]::attr(content)',
        ]:
            result = response.css(selector).getall()
            if result:
                analysis['artist_candidates'].append({
                    'selector': selector,
                    'results': result[:3]
                })
        
        # Look for score patterns
        for selector in [
            '.score',
            '.rating',
            '[itemprop="ratingValue"]',
            '.criticScore',
            '.userScore',
        ]:
            result = response.css(selector).getall()
            if result:
                analysis['score_candidates'].append({
                    'selector': selector,
                    'results': result[:3]
                })
        
        # Look for date patterns
        for selector in [
            '.releaseDate',
            '[itemprop="datePublished"]',
            '.date',
            'time',
        ]:
            result = response.css(selector).getall()
            if result:
                analysis['date_candidates'].append({
                    'selector': selector,
                    'results': result[:3]
                })
        
        # Look for genre patterns
        for selector in [
            '.genre',
            '.tags a',
            '[itemprop="genre"]',
            '.category',
        ]:
            result = response.css(selector).getall()
            if result:
                analysis['genre_candidates'].append({
                    'selector': selector,
                    'results': result[:3]
                })
        
        # Collect some links for analysis
        links = response.css('a::attr(href)').getall()
        analysis['all_links'] = [
            link for link in links[:20] 
            if link and not link.startswith('#')
        ]
        
        return analysis
    
    def print_analysis(self, analysis, url):
        """Print key findings to console"""
        self.logger.info(f"\n{'='*60}")
        self.logger.info(f"ANALYSIS for: {url}")
        self.logger.info(f"{'='*60}")
        
        self.logger.info(f"Page Title: {analysis['title']}")
        self.logger.info(f"Status Code: {analysis['status']}")
        
        if analysis['h1_elements']:
            self.logger.info(f"\nH1 Elements: {analysis['h1_elements']}")
        
        # Album title candidates
        if analysis['album_title_candidates']:
            self.logger.info("\nAlbum Title Candidates:")
            for candidate in analysis['album_title_candidates']:
                self.logger.info(f"  {candidate['selector']}: {candidate['results'][:2]}")
        
        # Artist candidates
        if analysis['artist_candidates']:
            self.logger.info("\nArtist Candidates:")
            for candidate in analysis['artist_candidates']:
                self.logger.info(f"  {candidate['selector']}: {candidate['results'][:2]}")
        
        # Score candidates
        if analysis['score_candidates']:
            self.logger.info("\nScore Candidates:")
            for candidate in analysis['score_candidates']:
                self.logger.info(f"  {candidate['selector']}: {candidate['results'][:2]}")
        
        # Check if this is an album page
        is_album_page = 'album' in url
        self.logger.info(f"\nIs Album Page: {is_album_page}")
        
        # Check for common AOTY patterns
        has_album_title = any('album' in str(r).lower() for r in analysis['album_title_candidates'])
        self.logger.info(f"Has Album Title Pattern: {has_album_title}")
        
        self.logger.info(f"{'='*60}\n")