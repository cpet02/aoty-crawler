#!/usr/bin/env python3
"""
Command-line interface for AOTY Crawler
"""

import argparse
import sys
import logging
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    """Main CLI entry point"""
    parser = argparse.ArgumentParser(
        description='AOTY Crawler - Music Data Collection Tool',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m cli scrape                    # Start scraping
  python -m cli scrape --genre hip-hop    # Scrape hip-hop genre
  python -m cli scrape --start-year 2025 --years-back 3 --albums-per-year 100
  python -m cli scrape --output-dir ./my_data --genre rock
  python -m cli list-genres               # List available genres
  python -m cli crawl test                # Run test spider
  python -m cli search --genres "Hip Hop,Electronic" --min-score 80
  python -m cli export --format csv --output results.csv
        """
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Crawl command (for running specific spiders)
    crawl_parser = subparsers.add_parser('crawl', help='Run a specific spider')
    crawl_parser.add_argument('spider', help='Name of the spider to run (e.g., test, album, artist)')
    
    # Scrape command
    scrape_parser = subparsers.add_parser('scrape', help='Start scraping')
    scrape_parser.add_argument('--genre', '-g', help='Genre to scrape')
    scrape_parser.add_argument('--start-year', type=int, help='Starting year for scraping')
    scrape_parser.add_argument('--years-back', type=int, default=1, help='Years to go back from start year')
    scrape_parser.add_argument('--albums-per-year', type=int, default=250, help='Albums per year to scrape')
    scrape_parser.add_argument('--test-mode', '-t', action='store_true', help='Test mode (limited scraping)')
    scrape_parser.add_argument('--limit', '-l', type=int, default=10, help='Limit number of items (test mode)')
    scrape_parser.add_argument('--output-dir', '-o', help='Output directory for scraped data')
    scrape_parser.add_argument('--resume', action='store_true', help='Resume from previous scrape')
    scrape_parser.add_argument('--resume-file', help='File to resume from (default: latest JSON in output dir)')
    scrape_parser.add_argument('--job-id', help='Job id to track this run under (default: auto-generated timestamp)')
    
    # List genres command
    list_genres_parser = subparsers.add_parser('list-genres', help='List available genres without scraping')
    
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
    export_parser.add_argument('--format', '-f', choices=['csv', 'json'], default='csv', help='Export format')
    export_parser.add_argument('--output', '-o', required=True, help='Output file path')
    export_parser.add_argument('--genres', help='Filter by genres')

    # Stats command
    stats_parser = subparsers.add_parser('stats', help='Show statistics from scraped data')

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
    from aoty_crawler.spiders import ComprehensiveAlbumSpider, ProductionSpider

    # Map spider names to classes
    spider_map = {
        'comprehensive_album': ComprehensiveAlbumSpider,
        'production': ProductionSpider,
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
    """Handle scrape command"""
    logger.info("Starting AOTY Crawler...")
    
    # Import Scrapy components
    from scrapy.crawler import CrawlerProcess
    from scrapy.utils.project import get_project_settings
    from aoty_crawler.spiders import ProductionSpider
    from aoty_crawler.utils import job_tracker

    # Get settings
    settings = get_project_settings()

    job_id = args.job_id or job_tracker.new_job_id()
    logger.info(f"Job ID: {job_id}")
    
    # Configure output directory
    if args.output_dir:
        import os
        os.makedirs(args.output_dir, exist_ok=True)
        settings.set('OUTPUT_DIR', args.output_dir, priority='cmdline')
        logger.info(f"Output directory set to: {args.output_dir}")
    
    # Configure for test mode
    if args.test_mode:
        settings.set('DOWNLOAD_DELAY', 0.5, priority='cmdline')
        settings.set('CONCURRENT_REQUESTS', 4, priority='cmdline')
        logger.info(f"Test mode: limiting to {args.limit} items")
    
    # Create crawler process
    process = CrawlerProcess(settings)
    
    # Configure spider parameters
    spider_kwargs = {
        'test_mode': args.test_mode,
        'job_id': job_id,
    }
    
    if args.genre:
        spider_kwargs['genre'] = args.genre
        logger.info(f"Scraping genre: {args.genre}")
    
    if args.start_year:
        spider_kwargs['start_year'] = args.start_year
        logger.info(f"Starting year: {args.start_year}")
    
    if args.years_back:
        spider_kwargs['years_back'] = args.years_back
        logger.info(f"Years back: {args.years_back}")
    
    if args.albums_per_year:
        spider_kwargs['albums_per_year'] = args.albums_per_year
        logger.info(f"Albums per year: {args.albums_per_year}")
    
    if args.test_mode:
        spider_kwargs['albums_per_year'] = args.limit
        logger.info(f"Test mode: limiting to {args.limit} albums per year")
    
    # Add resume functionality
    if args.resume:
        spider_kwargs['resume'] = True
        if args.resume_file:
            spider_kwargs['resume_file'] = args.resume_file
        logger.info("Resume mode enabled")
    
    # Add production spider
    process.crawl(ProductionSpider, **spider_kwargs)
    
    # Start scraping
    logger.info("Starting scraping process...")
    process.start()
    
    logger.info("Scraping completed!")
    return 0


def cmd_list_genres(args):
    """Handle list-genres command - list available genres without scraping

    Reads from the same genre catalog the UI's genre picker uses
    (aoty_crawler.utils.genres_manager, backed by data/genres_db.json), so
    the two never drift apart. That catalog starts from a hardcoded
    hierarchy and grows as scrapes discover new genres.
    """
    from aoty_crawler.utils.genres_manager import get_all_genres

    genre_names = get_all_genres()
    genres = [{'name': name, 'slug': name.lower().replace(' ', '-')} for name in genre_names]
    genres.sort(key=lambda x: x['name'].lower())

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


def cmd_search(args):
    """Handle search command - search scraped data using data loader"""
    logger.info("Searching scraped data...")
    
    # Import data loader
    from aoty_crawler.utils.data_loader import load_all_albums, filter_albums
    
    try:
        # Load all albums
        albums = load_all_albums()
        
        if not albums:
            logger.info("No albums found. Run 'python -m cli scrape' to scrape data first.")
            return 0
        
        # Build filter parameters
        filter_kwargs = {}
        
        # Parse genres
        if args.genres:
            genres = [g.strip() for g in args.genres.split(',')]
            if args.match_all:
                filter_kwargs['genres_all'] = genres
            else:
                filter_kwargs['genres'] = genres
        
        # Add score filters
        if args.min_score is not None:
            filter_kwargs['min_score'] = args.min_score
        if args.max_score is not None:
            filter_kwargs['max_score'] = args.max_score
        
        # Add review filters
        if args.min_reviews is not None:
            filter_kwargs['min_reviews'] = args.min_reviews
        
        # Add year filter
        if args.year is not None:
            filter_kwargs['year'] = args.year
        
        # Apply filters
        filtered = filter_albums(albums, **filter_kwargs)
        
        # Limit results
        if not args.show_all:
            filtered = filtered[:args.limit]
        
        # Display results
        if not filtered:
            logger.info("No albums found matching your criteria.")
            return 0
        
        logger.info(f"Found {len(filtered)} albums:")
        logger.info("-" * 80)
        
        for album in filtered:
            title = album.get('title', 'Unknown')
            artist = album.get('artist_name', 'Unknown')
            critic_score = album.get('critic_score')
            user_score = album.get('user_score')
            critic_reviews = album.get('critic_review_count')
            user_reviews = album.get('user_review_count')
            genres = album.get('genres', [])
            
            score_str = f"{critic_score}/100 (Critic), {user_score}/100 (User)" if critic_score or user_score else "N/A"
            reviews_str = f"Critic: {critic_reviews}, User: {user_reviews}" if critic_reviews or user_reviews else "N/A"
            
            print(f"🎵 {title}")
            print(f"   Artist: {artist}")
            print(f"   Score: {score_str}")
            print(f"   Reviews: {reviews_str}")
            print(f"   Genres: {', '.join(genres) if genres else 'N/A'}")
            print()
        
        return 0
        
    except Exception as e:
        logger.error(f"Search error: {e}")
        import traceback
        traceback.print_exc()
        return 1


def cmd_export(args):
    """Handle export command - export scraped data (from data/output/) to a single file"""
    logger.info(f"Exporting data to {args.output}...")

    from aoty_crawler.utils.data_loader import load_all_albums, filter_albums
    import pandas as pd

    try:
        albums = load_all_albums()

        if not albums:
            logger.info("No albums found. Run 'python -m cli scrape' to scrape data first.")
            return 0

        if args.genres:
            genres = [g.strip() for g in args.genres.split(',')]
            albums = filter_albums(albums, genres=genres)

        if not albums:
            logger.info("No albums found to export.")
            return 0

        # Flatten list fields for tabular export
        data = []
        for album in albums:
            row = dict(album)
            for field in ('genres', 'genre_tags'):
                if isinstance(row.get(field), list):
                    row[field] = ', '.join(row[field])
            data.append(row)

        df = pd.DataFrame(data)

        if args.format == 'csv':
            df.to_csv(args.output, index=False)
        elif args.format == 'json':
            df.to_json(args.output, orient='records', indent=2)

        logger.info(f"Exported {len(df)} albums to {args.format.upper()}: {args.output}")
        return 0

    except Exception as e:
        logger.error(f"Export error: {e}")
        import traceback
        traceback.print_exc()
        return 1


def cmd_stats(args):
    """Handle stats command - show statistics from scraped data"""
    logger.info("Scraped Data Statistics:")
    logger.info("=" * 40)
    
    # Import data loader
    from aoty_crawler.utils.data_loader import load_all_albums
    
    try:
        # Load all albums
        albums = load_all_albums()
        
        if not albums:
            logger.info("No albums found. Run 'python -m cli scrape' to scrape data first.")
            return 0
        
        # Basic counts
        album_count = len(albums)
        
        # Count albums with scores
        albums_with_critic_score = sum(1 for a in albums if a.get('critic_score') is not None)
        albums_with_user_score = sum(1 for a in albums if a.get('user_score') is not None)
        
        # Calculate average scores
        critic_scores = [a['critic_score'] for a in albums if a.get('critic_score') is not None]
        user_scores = [a['user_score'] for a in albums if a.get('user_score') is not None]
        
        avg_critic_score = sum(critic_scores) / len(critic_scores) if critic_scores else None
        avg_user_score = sum(user_scores) / len(user_scores) if user_scores else None
        
        # Count reviews
        total_critic_reviews = sum(a.get('critic_review_count') or 0 for a in albums)
        total_user_reviews = sum(a.get('user_review_count') or 0 for a in albums)
        
        # Get unique genres
        all_genres = set()
        for album in albums:
            all_genres.update(album.get('genres', []))
        
        # Top albums by critic score
        top_critic = sorted(albums, key=lambda x: x.get('critic_score') or 0, reverse=True)[:5]
        
        # Top albums by user score
        top_user = sorted(albums, key=lambda x: x.get('user_score') or 0, reverse=True)[:5]
        
        # Most reviewed albums
        most_reviewed = sorted(albums, key=lambda x: (x.get('critic_review_count') or 0) + (x.get('user_review_count') or 0), reverse=True)[:5]
        
        # Display statistics
        logger.info(f"Albums: {album_count}")
        logger.info(f"Albums with critic scores: {albums_with_critic_score}")
        logger.info(f"Albums with user scores: {albums_with_user_score}")
        logger.info(f"Genres: {len(all_genres)}")
        logger.info(f"Total critic reviews: {total_critic_reviews}")
        logger.info(f"Total user reviews: {total_user_reviews}")
        
        if avg_critic_score:
            logger.info(f"Average Critic Score: {avg_critic_score:.1f}")
        if avg_user_score:
            logger.info(f"Average User Score: {avg_user_score:.1f}")
        
        # Display top albums by critic score
        if top_critic:
            logger.info("\nTop 5 Albums by Critic Score:")
            for i, album in enumerate(top_critic, 1):
                title = album.get('title', 'Unknown')
                artist = album.get('artist_name', 'Unknown')
                score = album.get('critic_score')
                logger.info(f"{i}. {title} by {artist} ({score}/100)")
        
        # Display top albums by user score
        if top_user:
            logger.info("\nTop 5 Albums by User Score:")
            for i, album in enumerate(top_user, 1):
                title = album.get('title', 'Unknown')
                artist = album.get('artist_name', 'Unknown')
                score = album.get('user_score')
                logger.info(f"{i}. {title} by {artist} ({score}/100)")
        
        # Display most reviewed albums
        if most_reviewed:
            logger.info("\nTop 5 Most Reviewed Albums:")
            for i, album in enumerate(most_reviewed, 1):
                title = album.get('title', 'Unknown')
                artist = album.get('artist_name', 'Unknown')
                critic_rev = album.get('critic_review_count') or 0
                user_rev = album.get('user_review_count') or 0
                total_rev = critic_rev + user_rev
                logger.info(f"{i}. {title} by {artist} (Total: {total_rev}, Critic: {critic_rev}, User: {user_rev})")
        
        return 0
        
    except Exception as e:
        logger.error(f"Stats error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())