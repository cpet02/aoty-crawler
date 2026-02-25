#!/usr/bin/env python3
"""
Command-line interface for AOTY Crawler
"""

import argparse
import sys
import logging
import os
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Import spiders for crawl command
from aoty_crawler.spiders import HtmlDebugSpider, GenreTestSpider, ComprehensiveAlbumSpider, ProductionSpider, ProductionTestSpider


def main():
    """Main CLI entry point"""
    parser = argparse.ArgumentParser(
        description='AOTY Crawler - Music Data Collection Tool',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m cli scrape                                          # Start scraping all genres
  python -m cli scrape --genre hip-hop                          # Scrape hip-hop genre
  python -m cli scrape --genre rock --start-year 2020 --years-back 5  # Scrape 5 years of rock
  python -m cli scrape --genre pop --albums-per-year 100        # Scrape 100 albums per year
  python -m cli scrape --test-mode --limit 5                    # Test with 5 albums
  python -m cli scrape --output-dir ./my_data                   # Save to custom directory
  python -m cli scrape --resume                                 # Resume previous scrape
  python -m cli crawl production                                # Run production spider directly
        """
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Crawl command (for running specific spiders)
    crawl_parser = subparsers.add_parser('crawl', help='Run a specific spider')
    crawl_parser.add_argument('spider', help='Name of the spider to run (e.g., test, album, artist)')
    
    # Scrape command
    scrape_parser = subparsers.add_parser('scrape', help='Start scraping albums')
    scrape_parser.add_argument('--genre', '-g', help='Genre to scrape (e.g., rock, hip-hop, electronic)')
    scrape_parser.add_argument('--start-year', type=int, help='Starting year for scraping (default: 2026)')
    scrape_parser.add_argument('--years-back', type=int, default=1, help='Number of years to go back (default: 1)')
    scrape_parser.add_argument('--albums-per-year', type=int, default=250, help='Albums to scrape per year (default: 250)')
    scrape_parser.add_argument('--output-dir', '-o', help='Output directory for files (default: data/output)')
    scrape_parser.add_argument('--test-mode', '-t', action='store_true', help='Test mode (limited scraping)')
    scrape_parser.add_argument('--limit', '-l', type=int, default=10, help='Limit number of items (test mode only)')
    scrape_parser.add_argument('--resume', action='store_true', help='Resume from previous scrape')
    scrape_parser.add_argument('--resume-file', help='Specific resume file to load')
    
    # List genres command
    list_genres_parser = subparsers.add_parser('list-genres', help='List available genres')
    
    # Search command
    search_parser = subparsers.add_parser('search', help='Search albums')
    search_parser.add_argument('--genres', help='Comma-separated genres')
    search_parser.add_argument('--match-all', action='store_true', help='Match all genres')
    search_parser.add_argument('--min-score', type=float, help='Minimum score')
    search_parser.add_argument('--max-score', type=float, help='Maximum score')
    search_parser.add_argument('--min-reviews', type=int, help='Minimum review count')
    search_parser.add_argument('--year', type=int, help='Release year')
    search_parser.add_argument('--limit', type=int, default=20, help='Maximum results')
    search_parser.add_argument('--show-all', action='store_true', help='Show all results')
    
    # Export command
    export_parser = subparsers.add_parser('export', help='Export data')
    export_parser.add_argument('--format', '-f', choices=['csv', 'json', 'sqlite'], default='csv', help='Export format')
    export_parser.add_argument('--output', '-o', required=True, help='Output file path')
    export_parser.add_argument('--genres', help='Filter by genres')
    
    # Stats command
    stats_parser = subparsers.add_parser('stats', help='Show database statistics')
    
    # Init command
    init_parser = subparsers.add_parser('init', help='Initialize database')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 0
    
    try:
        if args.command == 'crawl':
            return cmd_crawl(args)
        elif args.command == 'scrape':
            return cmd_scrape(args)
        elif args.command == 'list-genres':
            return cmd_list_genres(args)
        elif args.command == 'search':
            return cmd_search(args)
        elif args.command == 'export':
            return cmd_export(args)
        elif args.command == 'stats':
            return cmd_stats(args)
        elif args.command == 'init':
            return cmd_init(args)
        else:
            parser.print_help()
            return 1
            
    except KeyboardInterrupt:
        logger.info("Operation cancelled by user")
        return 130
    except Exception as e:
        logger.error(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return 1


def cmd_crawl(args):
    """Handle crawl command - run a specific spider"""
    logger.info(f"Running spider: {args.spider}")
    
    # Import Scrapy components
    from scrapy.crawler import CrawlerProcess
    from scrapy.utils.project import get_project_settings
    from aoty_crawler.spiders import TestSpider, HtmlDebugSpider, GenreTestSpider, ComprehensiveAlbumSpider, ProductionSpider, ProductionTestSpider, AlbumSpider, ArtistSpider, GenreSpider, YearSpider
    
    # Map spider names to classes
    spider_map = {
        'html_debug': HtmlDebugSpider,
        'genre_test': GenreTestSpider,
        'comprehensive_album': ComprehensiveAlbumSpider,
        'production': ProductionSpider,
        'production_test': ProductionTestSpider,
    }
    
    # Get spider class
    spider_class = spider_map.get(args.spider)
    if not spider_class:
        logger.error(f"Unknown spider: {args.spider}")
        logger.info(f"Available spiders: {', '.join(spider_map.keys())}")
        return 1
    
    # Get settings
    settings = get_project_settings()
    
    # Create crawler process
    process = CrawlerProcess(settings)
    
    # Add spider
    process.crawl(spider_class)
    
    # Start scraping
    logger.info(f"Starting {args.spider} spider...")
    process.start()
    
    logger.info(f"{args.spider} spider completed!")
    return 0


def cmd_scrape(args):
    """Handle scrape command with full parameter support"""
    logger.info("Starting AOTY Crawler...")
    
    # Import Scrapy components
    from scrapy.crawler import CrawlerProcess
    from scrapy.utils.project import get_project_settings
    from aoty_crawler.spiders import ProductionSpider
    
    # Get settings
    settings = get_project_settings()
    
    # Configure output directory if specified
    if args.output_dir:
        output_dir = os.path.abspath(args.output_dir)
        settings.set('OUTPUT_DIR', output_dir, priority='cmdline')
        logger.info(f"Output directory: {output_dir}")
    
    # Configure for test mode
    if args.test_mode:
        settings.set('DOWNLOAD_DELAY', 0.5, priority='cmdline')
        settings.set('CONCURRENT_REQUESTS', 4, priority='cmdline')
        logger.info(f"Test mode: limiting to {args.limit} items per year")
    
    # Create crawler process
    process = CrawlerProcess(settings)
    
    # Configure spider parameters
    spider_kwargs = {
        'test_mode': args.test_mode,
    }
    
    # Add genre if specified
    if args.genre:
        spider_kwargs['genre'] = args.genre
        logger.info(f"Scraping genre: {args.genre}")
    
    # Add year parameters - always pass them
    if args.start_year:
        spider_kwargs['start_year'] = args.start_year
        logger.info(f"Starting year: {args.start_year}")
    
    # Always pass years_back and albums_per_year
    spider_kwargs['years_back'] = args.years_back
    logger.info(f"Years back: {args.years_back}")
    
    # Use limit for test mode, otherwise use albums_per_year
    if args.test_mode:
        spider_kwargs['albums_per_year'] = args.limit
        logger.info(f"Test mode: limiting to {args.limit} albums per year")
    else:
        spider_kwargs['albums_per_year'] = args.albums_per_year
        logger.info(f"Albums per year: {args.albums_per_year}")
    
    # Add resume parameters
    if args.resume:
        spider_kwargs['resume'] = True
        logger.info("Resume mode enabled")
        if args.resume_file:
            spider_kwargs['resume_file'] = args.resume_file
            logger.info(f"Resume file: {args.resume_file}")
    
    # Add production spider
    process.crawl(ProductionSpider, **spider_kwargs)
    
    # Start scraping
    logger.info("Starting scraping process...")
    process.start()
    
    logger.info("Scraping completed!")
    return 0


def cmd_list_genres(args):
    """Handle list-genres command - show available genres"""
    logger.info("Fetching available genres from AOTY...")
    logger.info("")
    logger.info("⚠️  The genre.php endpoint is protected and returns 403 Forbidden.")
    logger.info("   Please visit the following URL manually to see available genres:")
    logger.info("")
    logger.info("   https://www.albumoftheyear.org/genre.php")
    logger.info("")
    logger.info("   Or check the website's genre list directly in your browser.")
    logger.info("")
    return 0


def cmd_search(args):
    """Handle search command"""
    logger.info("Searching database...")
    
    # Import database models
    from database.models import (
        Album, Artist, Genre, Review, get_session, create_database_engine
    )
    from sqlalchemy import or_, and_
    
    # Create database session
    engine = create_database_engine()
    session = get_session(engine)
    
    try:
        # Build query
        query = session.query(Album).join(Artist)
        
        # Apply filters
        if args.genres:
            genres = [g.strip() for g in args.genres.split(',')]
            if args.match_all:
                # Match albums with ALL specified genres
                for genre_name in genres:
                    query = query.join(Genre, Album.genres).filter(Genre.name == genre_name)
            else:
                # Match albums with ANY of the specified genres
                genre_conditions = [Album.genres.any(Genre.name == g) for g in genres]
                query = query.filter(or_(*genre_conditions))
        
        if args.min_score:
            query = query.filter(Album.critic_score >= args.min_score)
        
        if args.max_score:
            query = query.filter(Album.critic_score <= args.max_score)
        
        if args.min_reviews:
            query = query.filter(Album.review_count >= args.min_reviews)
        
        if args.year:
            from datetime import datetime
            start_date = datetime(args.year, 1, 1)
            end_date = datetime(args.year, 12, 31)
            query = query.filter(Album.release_date >= start_date, Album.release_date <= end_date)
        
        # Execute query
        results = query.limit(args.limit).all()
        
        # Display results
        if not results:
            logger.info("No albums found matching your criteria.")
            return 0
        
        logger.info(f"Found {len(results)} albums:")
        logger.info("-" * 80)
        
        for album in results:
            print(f"🎵 {album.title}")
            print(f"   Artist: {album.artist.name}")
            print(f"   Score: {album.critic_score}/100 (Critic), {album.user_score}/100 (User)")
            print(f"   Reviews: {album.review_count}")
            print(f"   Year: {album.release_date.year if album.release_date else 'Unknown'}")
            print(f"   Genres: {', '.join(g.name for g in album.genres)}")
            print()
        
        return 0
        
    except Exception as e:
        logger.error(f"Search error: {e}")
        return 1
    finally:
        session.close()


def cmd_export(args):
    """Handle export command"""
    logger.info(f"Exporting data to {args.output}...")
    
    # Import database models
    from database.models import (
        Album, Artist, Genre, Review, get_session, create_database_engine
    )
    import pandas as pd
    
    # Create database session
    engine = create_database_engine()
    session = get_session(engine)
    
    try:
        # Get all albums
        albums = session.query(Album).all()
        
        if not albums:
            logger.info("No albums found to export.")
            return 0
        
        # Prepare data for export
        data = []
        for album in albums:
            album_data = {
                'title': album.title,
                'artist': album.artist.name if album.artist else 'Unknown',
                'critic_score': album.critic_score,
                'user_score': album.user_score,
                'review_count': album.review_count,
                'release_year': album.release_date.year if album.release_date else None,
                'genres': ', '.join(g.name for g in album.genres),
                'url': album.url,
                'scraped_at': album.scraped_at
            }
            data.append(album_data)
        
        # Create DataFrame
        df = pd.DataFrame(data)
        
        # Export based on format
        if args.format == 'csv':
            df.to_csv(args.output, index=False)
            logger.info(f"Exported {len(df)} albums to CSV: {args.output}")
        elif args.format == 'json':
            df.to_json(args.output, orient='records', indent=2)
            logger.info(f"Exported {len(df)} albums to JSON: {args.output}")
        elif args.format == 'sqlite':
            # Export to new SQLite database
            import sqlite3
            conn = sqlite3.connect(args.output)
            df.to_sql('albums', conn, index=False, if_exists='replace')
            conn.close()
            logger.info(f"Exported {len(df)} albums to SQLite: {args.output}")
        
        return 0
        
    except Exception as e:
        logger.error(f"Export error: {e}")
        return 1
    finally:
        session.close()


def cmd_stats(args):
    """Handle stats command"""
    logger.info("Database Statistics:")
    logger.info("=" * 40)
    
    # Import database models
    from database.models import (
        Album, Artist, Genre, Review, get_session, create_database_engine
    )
    
    # Create database session
    engine = create_database_engine()
    session = get_session(engine)
    
    try:
        # Get counts
        album_count = session.query(Album).count()
        artist_count = session.query(Artist).count()
        genre_count = session.query(Genre).count()
        review_count = session.query(Review).count()
        
        # Get average scores
        avg_critic_score = session.query(Album.critic_score).filter(Album.critic_score != None).average()
        avg_user_score = session.query(Album.user_score).filter(Album.user_score != None).average()
        
        # Get top albums
        top_albums = session.query(Album).order_by(Album.critic_score.desc()).limit(5).all()
        
        # Display statistics
        logger.info(f"Albums: {album_count}")
        logger.info(f"Artists: {artist_count}")
        logger.info(f"Genres: {genre_count}")
        logger.info(f"Reviews: {review_count}")
        
        if avg_critic_score:
            logger.info(f"Average Critic Score: {avg_critic_score:.1f}")
        if avg_user_score:
            logger.info(f"Average User Score: {avg_user_score:.1f}")
        
        # Display top albums
        if top_albums:
            logger.info("\nTop 5 Albums by Critic Score:")
            for i, album in enumerate(top_albums, 1):
                artist_name = album.artist.name if album.artist else 'Unknown'
                logger.info(f"{i}. {album.title} by {artist_name} ({album.critic_score}/100)")
        
        return 0
        
    except Exception as e:
        logger.error(f"Stats error: {e}")
        return 1
    finally:
        session.close()


def cmd_init(args):
    """Handle init command"""
    logger.info("Initializing database...")
    
    try:
        from database.models import init_database
        init_database()
        logger.info("Database initialized successfully!")
        return 0
    except Exception as e:
        logger.error(f"Initialization error: {e}")
        return 1


if __name__ == '__main__':
    sys.exit(main())
