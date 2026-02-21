#!/usr/bin/env python3
"""
Debug Spider - Save HTML to inspect structure
"""

import scrapy
import os


class DebugSpider(scrapy.Spider):
    name = "debug"
    allowed_domains = ["albumoftheyear.org"]
    start_urls = [
        "https://www.albumoftheyear.org/album/183-sunn-o-monoliths-and-dimensions.php",
    ]
    
    custom_settings = {
        'DOWNLOAD_DELAY': 1,
        'USER_AGENT': 'AOTY-Debug-Spider/1.0 (Testing Purposes)',
    }
    
    def parse(self, response):
        """Save HTML to file for inspection"""
        # Create output directory if it doesn't exist
        os.makedirs('debug_html', exist_ok=True)
        
        # Save the HTML content
        filename = 'debug_html/album_page.html'
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(response.text)
        
        self.logger.info(f"Saved HTML to {filename}")
        
        # Also save a snippet of the body for quick inspection
        body = response.css('body').get()
        if body:
            snippet = body[:500]  # First 500 chars
            self.logger.info(f"Body snippet: {snippet}")
        
        # Try to find the title element
        title = response.css('h1').get()
        self.logger.info(f"Found h1 elements: {title}")
        
        # List all CSS selectors that might work
        self.logger.info("Trying common selectors:")
        self.logger.info(f"  h1.albumTitle: {response.css('h1.albumTitle::text').get()}")
        self.logger.info(f"  h1: {response.css('h1::text').get()}")
        self.logger.info(f"  .albumTitle: {response.css('.albumTitle::text').get()}")
        self.logger.info(f"  title::text: {response.css('title::text').get()}")