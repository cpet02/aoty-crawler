#!/usr/bin/env python3
"""
Genre Test Spider - Test the genre page structure
"""

import scrapy
import os
import json
from datetime import datetime


class GenreTestSpider(scrapy.Spider):
    name = "genre_test"
    allowed_domains = ["albumoftheyear.org"]
    
    # Start with the genre page
    start_urls = [
        "https://www.albumoftheyear.org/genre.php",
    ]
    
    custom_settings = {
        'DOWNLOAD_DELAY': 3,
        'USER_AGENT': 'AOTY-Genre-Test/1.0 (Testing Purposes)',
    }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.debug_dir = 'debug_html/genre_test'
        os.makedirs(self.debug_dir, exist_ok=True)
    
    def parse(self, response):
        """Parse the genre page and save analysis"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        # Save HTML
        filename = f"{self.debug_dir}/genre_page_{timestamp}.html"
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(response.text)
        
        self.logger.info(f"Saved genre page HTML to {filename}")
        
        # Analyze genre links
        analysis = self.analyze_genre_links(response)
        
        # Save analysis
        analysis_file = f"{self.debug_dir}/genre_analysis_{timestamp}.json"
        with open(analysis_file, 'w', encoding='utf-8') as f:
            json.dump(analysis, f, indent=2, default=str)
        
        self.logger.info(f"Saved genre analysis to {analysis_file}")
        
        # Print findings
        self.print_genre_findings(analysis)
        
        # Test one genre link if found
        if analysis.get('genre_links'):
            test_genre = analysis['genre_links'][0]
            self.logger.info(f"Testing genre link: {test_genre['url']}")
            yield scrapy.Request(
                url=test_genre['url'],
                callback=self.parse_genre_page,
                meta={'genre_name': test_genre['name']}
            )
    
    def analyze_genre_links(self, response):
        """Analyze genre links on the page"""
        analysis = {
            'url': response.url,
            'status': response.status,
            'title': response.css('title::text').get(),
            'genre_links': [],
            'all_links_count': 0,
            'potential_genre_selectors': [],
        }
        
        # Look for genre links using different selectors
        selectors_to_try = [
            'a[href*="/genre/"]',
            '.genreList a',
            '.genre a',
            'a.genre',
            'li a',
            '.list a',
        ]
        
        for selector in selectors_to_try:
            links = response.css(selector)
            if links:
                analysis['potential_genre_selectors'].append({
                    'selector': selector,
                    'count': len(links),
                    'sample': links[:3].getall()
                })
        
        # Try to extract genre links from the most promising selector
        genre_links = response.css('a[href*="/genre/"]')
        analysis['all_links_count'] = len(genre_links)
        
        for link in genre_links[:10]:  # Check first 10 links
            href = link.css('::attr(href)').get()
            text = link.css('::text').get()
            
            if href and text and '/genre/' in href:
                full_url = response.urljoin(href)
                analysis['genre_links'].append({
                    'name': text.strip(),
                    'url': full_url,
                    'href': href,
                    'text': text.strip()
                })
        
        return analysis
    
    def print_genre_findings(self, analysis):
        """Print genre findings to console"""
        self.logger.info(f"\n{'='*60}")
        self.logger.info(f"GENRE PAGE ANALYSIS")
        self.logger.info(f"{'='*60}")
        self.logger.info(f"Page Title: {analysis['title']}")
        self.logger.info(f"Status Code: {analysis['status']}")
        
        if analysis['potential_genre_selectors']:
            self.logger.info(f"\nPotential Genre Selectors:")
            for selector_info in analysis['potential_genre_selectors']:
                self.logger.info(f"  {selector_info['selector']}: {selector_info['count']} links")
        
        self.logger.info(f"\nFound {len(analysis['genre_links'])} genre links:")
        for i, genre in enumerate(analysis['genre_links'][:5], 1):
            self.logger.info(f"  {i}. {genre['name']} -> {genre['url']}")
        
        if len(analysis['genre_links']) > 5:
            self.logger.info(f"  ... and {len(analysis['genre_links']) - 5} more")
        
        self.logger.info(f"{'='*60}\n")
    
    def parse_genre_page(self, response):
        """Parse a specific genre page"""
        genre_name = response.meta.get('genre_name', 'Unknown')
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        # Save HTML
        filename = f"{self.debug_dir}/genre_{genre_name}_{timestamp}.html"
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(response.text)
        
        self.logger.info(f"Saved {genre_name} genre page to {filename}")
        
        # Look for rating/highest-rated links
        rating_links = response.css('a[href*="/ratings/"]')
        
        self.logger.info(f"\nFound {len(rating_links)} rating links on {genre_name} page:")
        for link in rating_links[:5]:
            href = link.css('::attr(href)').get()
            text = link.css('::text').get()
            self.logger.info(f"  - {text}: {href}")
        
        # Look for user-highest-rated pattern
        user_highest_rated = response.css('a[href*="user-highest-rated"]')
        if user_highest_rated:
            self.logger.info(f"\nFound user-highest-rated links:")
            for link in user_highest_rated[:3]:
                href = link.css('::attr(href)').get()
                text = link.css('::text').get()
                self.logger.info(f"  - {text}: {href}")
                
                # Test one of these links
                if href and 'user-highest-rated' in href:
                    test_url = response.urljoin(href)
                    self.logger.info(f"Testing user-highest-rated URL: {test_url}")
                    yield scrapy.Request(
                        url=test_url,
                        callback=self.parse_ratings_page,
                        meta={'genre_name': genre_name}
                    )
                    break  # Just test one
    
    def parse_ratings_page(self, response):
        """Parse a ratings page"""
        genre_name = response.meta.get('genre_name', 'Unknown')
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        self.logger.info(f"\n{'='*60}")
        self.logger.info(f"RATINGS PAGE: {genre_name}")
        self.logger.info(f"URL: {response.url}")
        self.logger.info(f"{'='*60}")
        
        # Save HTML
        filename = f"{self.debug_dir}/ratings_{genre_name}_{timestamp}.html"
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(response.text)
        
        self.logger.info(f"Saved ratings page to {filename}")
        
        # Look for album entries
        album_selectors = [
            '.albumListRow',
            '.albumRow',
            '.albumItem',
            '.listRow',
            '.item',
        ]
        
        for selector in album_selectors:
            albums = response.css(selector)
            if albums:
                self.logger.info(f"\nFound {len(albums)} albums with selector: {selector}")
                
                # Check first album structure
                if albums:
                    first_album = albums[0]
                    self.logger.info(f"\nFirst album HTML snippet:")
                    self.logger.info(first_album.get()[:500])
                    
                    # Look for title
                    title = first_album.css('h2::text').get() or first_album.css('a::text').get()
                    self.logger.info(f"Title candidate: {title}")
                
                break  # Use first working selector