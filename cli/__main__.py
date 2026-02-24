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
        'test': TestSpider,
        'debug': DebugSpider,
        'html_debug': HtmlDebugSpider,
        'genre_test': GenreTestSpider,
        'comprehensive_album': ComprehensiveAlbumSpider,
        'production': ProductionSpider,
        'production_test': ProductionTestSpider,
        'album': AlbumSpider,
        'artist': ArtistSpider,
        'genre': GenreSpider,
        'year': YearSpider
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
    
    # Get settings
    settings = get_project_settings()
    
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
    """Handle list-genres command - list available genres without scraping"""
    logger.info("Fetching available genres from AOTY...")
    
    # Hardcoded genre list (updated from actual AOTY genre.php page)
    # This avoids 403 errors and is more reliable since genres rarely change
    genres = [
        {'name': 'Alternative Rock', 'slug': 'alternative-rock'},
        {'name': 'Ambient', 'slug': 'ambient'},
        {'name': 'Ambient Pop', 'slug': 'ambient-pop'},
        {'name': 'Art Pop', 'slug': 'art-pop'},
        {'name': 'Black Metal', 'slug': 'black-metal'},
        {'name': 'Children\'s Music', 'slug': 'childrens-music'},
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