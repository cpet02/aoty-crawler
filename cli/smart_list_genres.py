#!/usr/bin/env python3
"""
Smart genre list command that tries dynamic fetch first, falls back to hardcoded list
"""

def cmd_list_genres(args):
    """Handle list-genres command - list available genres without scraping"""
    import re
    import logging
    logger = logging.getLogger(__name__)
    
    logger.info("Fetching available genres from AOTY...")
    
    # Hardcoded genre list as fallback (updated from actual AOTY genre.php page)
    hardcoded_genres = [
        {'name': 'Alternative Rock', 'slug': 'alternative-rock'},
        {'name': 'Ambient', 'slug': 'ambient'},
        {'name': 'Ambient Pop', 'slug': 'ambient-pop'},
        {'name': 'Art Pop', 'slug': 'art-pop'},
        {'name': 'Black Metal', 'slug': 'black-metal'},
        {'name': "Children's Music", 'slug': 'childrens-music'},
        {'name': 'Contemporary Folk', 'slug': 'contemporary-folk'},
        {'name': 'Dance', 'slug': 'dance'},
        {'name': 'DJ Mix', 'slug': 'dj-mix'},
        {'name': 'Easy Listening', 'slug': 'easy-listening'},
        {'name': 'Electronic', 'slug': 'electronic'},
        {'name': 'Electronic Dance Music', 'slug': 'electronic-dance-music'},
        {'name': 'Epic Collage', 'slug': 'epic-collage'},
        {'name': 'Field Recordings', 'slug': 'field-recordings'},
        {'name': 'Folk', 'slug': 'folk'},
        {'name': 'Glitch Pop', 'slug': 'glitch-pop'},
        {'name': 'Hardcore Punk', 'slug': 'hardcore-punk'},
        {'name': 'Hip Hop', 'slug': 'hip-hop'},
        {'name': 'Hypnagogic Pop', 'slug': 'hypnagogic-pop'},
        {'name': 'Indie Pop', 'slug': 'indie-pop'},
        {'name': 'Indie Rock', 'slug': 'indie-rock'},
        {'name': 'Marching Band', 'slug': 'marching-band'},
        {'name': 'Metal', 'slug': 'metal'},
        {'name': 'Musical Parody', 'slug': 'musical-parody'},
        {'name': 'Musical Theatre & Entertainment', 'slug': 'musical-theatre-and-entertainment'},
        {'name': 'New Age', 'slug': 'new-age'},
        {'name': 'Pop', 'slug': 'pop'},
        {'name': 'Pop Rap', 'slug': 'pop-rap'},
        {'name': 'Pop Rock', 'slug': 'pop-rock'},
        {'name': 'Punk', 'slug': 'punk'},
        {'name': 'R&B', 'slug': 'r-and-b'},
        {'name': 'Rock', 'slug': 'rock'},
        {'name': 'Singer-Songwriter', 'slug': 'singer-songwriter'},
        {'name': 'Sound Effects', 'slug': 'sound-effects'},
        {'name': 'Spoken Word', 'slug': 'spoken-word'},
        {'name': 'Western Classical Music', 'slug': 'western-classical-music'},
    ]
    
    # Try to fetch genres dynamically from AOTY
    try:
        logger.info("Attempting to fetch genres dynamically from AOTY...")
        
        # Import Scrapy components
        from scrapy.crawler import CrawlerProcess
        from scrapy.utils.project import get_project_settings
        from aoty_crawler.spiders import ProductionSpider
        
        # Get settings
        settings = get_project_settings()
        settings.set('DOWNLOAD_DELAY', 1, priority='cmdline')
        settings.set('CONCURRENT_REQUESTS', 2, priority='cmdline')
        settings.set('ROBOTSTXT_OBEY', False, priority='cmdline')
        
        # Create crawler process
        process = CrawlerProcess(settings)
        
        # Create a custom spider for genre listing
        class GenreListSpider(ProductionSpider):
            name = "genre_list"
            
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.genres = []
                self._closed = False
                
            def parse_genre_page(self, response):
                self.logger.info(f"Parsing genre page: {response.url}")
                
                # Extract genre links
                genre_links = response.css('a[href*="/genre/"]')
                self.logger.info(f"Found {len(genre_links)} genre links")
                
                genres_processed = set()
                
                for link in genre_links:
                    href = link.css('::attr(href)').get()
                    text = link.css('::text').get()
                    
                    if not href or not text:
                        continue
                    
                    # Skip "View More" links and non-genre links
                    if text.lower() in ['view more', 'similar artists', 'follow']:
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
                    self.genres.append({
                        'name': genre_name,
                        'slug': genre_slug,
                        'url': response.urljoin(href)
                    })
                
                # Stop after first page
                self._closed = True
                self.crawler.engine.close_spider(self, 'genres_collected')
        
        # Add spider and run
        process.crawl(GenreListSpider)
        process.start()
        
        # Get the genres from the spider instance
        dynamic_genres = []
        for crawler in process.crawlers:
            if hasattr(crawler, 'spider') and hasattr(crawler.spider, 'genres'):
                dynamic_genres = crawler.spider.genres
                break
        
        if dynamic_genres:
            logger.info("Successfully fetched genres dynamically!")
            genres = dynamic_genres
            
            # Check for new genres not in hardcoded list
            hardcoded_slugs = {g['slug'] for g in hardcoded_genres}
            new_genres = [g for g in dynamic_genres if g['slug'] not in hardcoded_slugs]
            
            if new_genres:
                logger.info("")
                logger.info("⚠️  NEW GENRES DETECTED - Update the hardcoded list in cli/__main__.py:")
                for genre in new_genres:
                    logger.info(f"   {genre['name']} (slug: {genre['slug']})")
                logger.info("")
        else:
            logger.info("Dynamic fetch failed or returned no genres. Using hardcoded list.")
            genres = hardcoded_genres
            
    except Exception as e:
        logger.info(f"Dynamic fetch failed: {e}. Using hardcoded list.")
        genres = hardcoded_genres
    
    # Sort alphabetically
    genres.sort(key=lambda x: x['name'].lower())
    
    # Display results
    logger.info(f"Found {len(genres)} genres:")
    logger.info("=" * 60)
    
    for i, genre in enumerate(genres, 1):
        logger.info(f"{i:3d}. {genre['name']:30s} (slug: {genre['slug']})")
    
    logger.info("=" * 60)
    logger.info("To scrape a specific genre, use:")
    logger.info(f"  python -m cli scrape --genre rock")
    logger.info(f"  python -m cli scrape --genre hip-hop")
    if genres:
        logger.info(f"  python -m cli scrape --genre {genres[0]['slug']}")
    
    return 0