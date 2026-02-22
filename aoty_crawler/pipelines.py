# Pipelines for AOTY Crawler
# Data processing pipelines for cleaning, validation, and file-based storage

import logging
import json
import csv
import os
from datetime import datetime
from scrapy.exceptions import DropItem

logger = logging.getLogger(__name__)

# File-based storage configuration
# Can be overridden via environment variable or spider settings
OUTPUT_DIR = os.environ.get('OUTPUT_DIR', 'data/output')


class FileStoragePipeline:
    """
    Pipeline to store scraped items as JSON and CSV files
    Simple file-based storage without database
    
    Supports:
    - JSON and CSV output formats
    - Configurable output directory via OUTPUT_DIR setting
    - Error handling and validation
    - Proper logging of all operations
    """
    
    def __init__(self):
        self.albums = []
        self.artists = []
        self.genres = []
        self.reviews = []
        
    def process_item(self, item, spider):
        """Process scraped items and store in memory"""
        if 'aoty_id' in item and 'title' in item:
            # Album item
            self.albums.append(dict(item))
        elif 'aoty_id' in item and 'name' in item:
            # Artist item
            self.artists.append(dict(item))
        elif 'name' in item:
            # Genre item
            self.genres.append(dict(item))
        elif 'album_id' in item:
            # Review item
            self.reviews.append(dict(item))
        
        return item
    
    def close_spider(self, spider):
        """Write all data to JSON and CSV files when spider finishes"""
        timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        
        # Get output directory from spider settings or use default
        output_dir = spider.settings.get('OUTPUT_DIR', OUTPUT_DIR)
        os.makedirs(output_dir, exist_ok=True)
        
        logger.info(f"\n{'='*60}")
        logger.info(f"FILE STORAGE PIPELINE - Writing to: {output_dir}")
        logger.info(f"{'='*60}")
        
        files_written = 0
        files_failed = 0
        
        # Write albums
        if self.albums:
            # JSON output
            albums_json_file = os.path.join(output_dir, f'albums_{timestamp}.json')
            try:
                with open(albums_json_file, 'w', encoding='utf-8') as f:
                    json.dump(self.albums, f, indent=2, default=str)
                logger.info(f"✓ Saved {len(self.albums)} albums to JSON: {albums_json_file}")
                files_written += 1
            except Exception as e:
                logger.error(f"✗ Failed to write albums JSON: {e}")
                files_failed += 1
            
            # CSV output
            albums_csv_file = os.path.join(output_dir, f'albums_{timestamp}.csv')
            if self._write_csv(albums_csv_file, self.albums):
                logger.info(f"✓ Saved {len(self.albums)} albums to CSV: {albums_csv_file}")
                files_written += 1
            else:
                logger.error(f"✗ Failed to write albums CSV: {albums_csv_file}")
                files_failed += 1
        
        # Write artists
        if self.artists:
            artists_json_file = os.path.join(output_dir, f'artists_{timestamp}.json')
            try:
                with open(artists_json_file, 'w', encoding='utf-8') as f:
                    json.dump(self.artists, f, indent=2, default=str)
                logger.info(f"✓ Saved {len(self.artists)} artists to JSON: {artists_json_file}")
                files_written += 1
            except Exception as e:
                logger.error(f"✗ Failed to write artists JSON: {e}")
                files_failed += 1
            
            artists_csv_file = os.path.join(output_dir, f'artists_{timestamp}.csv')
            if self._write_csv(artists_csv_file, self.artists):
                logger.info(f"✓ Saved {len(self.artists)} artists to CSV: {artists_csv_file}")
                files_written += 1
            else:
                logger.error(f"✗ Failed to write artists CSV: {artists_csv_file}")
                files_failed += 1
        
        # Write genres
        if self.genres:
            genres_json_file = os.path.join(output_dir, f'genres_{timestamp}.json')
            try:
                with open(genres_json_file, 'w', encoding='utf-8') as f:
                    json.dump(self.genres, f, indent=2, default=str)
                logger.info(f"✓ Saved {len(self.genres)} genres to JSON: {genres_json_file}")
                files_written += 1
            except Exception as e:
                logger.error(f"✗ Failed to write genres JSON: {e}")
                files_failed += 1
            
            genres_csv_file = os.path.join(output_dir, f'genres_{timestamp}.csv')
            if self._write_csv(genres_csv_file, self.genres):
                logger.info(f"✓ Saved {len(self.genres)} genres to CSV: {genres_csv_file}")
                files_written += 1
            else:
                logger.error(f"✗ Failed to write genres CSV: {genres_csv_file}")
                files_failed += 1
        
        # Write reviews
        if self.reviews:
            reviews_json_file = os.path.join(output_dir, f'reviews_{timestamp}.json')
            try:
                with open(reviews_json_file, 'w', encoding='utf-8') as f:
                    json.dump(self.reviews, f, indent=2, default=str)
                logger.info(f"✓ Saved {len(self.reviews)} reviews to JSON: {reviews_json_file}")
                files_written += 1
            except Exception as e:
                logger.error(f"✗ Failed to write reviews JSON: {e}")
                files_failed += 1
            
            reviews_csv_file = os.path.join(output_dir, f'reviews_{timestamp}.csv')
            if self._write_csv(reviews_csv_file, self.reviews):
                logger.info(f"✓ Saved {len(self.reviews)} reviews to CSV: {reviews_csv_file}")
                files_written += 1
            else:
                logger.error(f"✗ Failed to write reviews CSV: {reviews_csv_file}")
                files_failed += 1
        
        logger.info(f"{'='*60}")
        logger.info(f"FILE STORAGE COMPLETE")
        logger.info(f"Files written: {files_written} | Files failed: {files_failed}")
        logger.info(f"Output directory: {output_dir}")
        logger.info(f"{'='*60}\n")
    
    def _write_csv(self, filename, data):
        """Write data to CSV file with proper error handling"""
        if not data:
            logger.warning(f"No data to write to CSV: {filename}")
            return False
        
        try:
            # Get all possible fieldnames from all items
            fieldnames = set()
            for item in data:
                fieldnames.update(item.keys())
            
            if not fieldnames:
                logger.warning(f"No fieldnames found for CSV: {filename}")
                return False
            
            # Convert sets/lists to JSON strings for CSV (preserves structure)
            def prepare_value(value):
                if isinstance(value, (list, tuple, set)):
                    # Use JSON for better data preservation
                    return json.dumps(list(value))
                elif isinstance(value, dict):
                    return json.dumps(value)
                return value
            
            with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=sorted(fieldnames))
                writer.writeheader()
                
                for item in data:
                    # Prepare item for CSV
                    csv_item = {k: prepare_value(v) for k, v in item.items()}
                    writer.writerow(csv_item)
            
            logger.info(f"Successfully wrote CSV: {filename}")
            return True
            
        except IOError as e:
            logger.error(f"IO Error writing CSV {filename}: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error writing CSV {filename}: {e}")
            return False


class DatabasePipeline:
    """
    Pipeline to store scraped items in the database
    Handles albums, artists, genres, and reviews
    """
    
    def __init__(self):
        self.engine = None
        self.session = None
        
    @classmethod
    def from_crawler(cls, crawler):
        """Initialize pipeline from crawler"""
        pipeline = cls()
        crawler.signals.connect(pipeline.spider_opened, signal='spider_opened')
        crawler.signals.connect(pipeline.spider_closed, signal='spider_closed')
        return pipeline
    
    def spider_opened(self, spider):
        """Open database connection when spider starts"""
        logger.info("Opening database connection...")
        self.engine = create_database_engine()
        self.session = get_session(self.engine)
    
    def spider_closed(self, spider):
        """Close database connection when spider finishes"""
        if self.session:
            self.session.close()
            logger.info("Database connection closed")
    
    def process_item(self, item, spider):
        """Process scraped items and store in database"""
        try:
            if 'aoty_id' in item and 'title' in item:
                self._process_album(item)
            elif 'aoty_id' in item and 'name' in item:
                self._process_artist(item)
            elif 'name' in item and 'aoty_id' in item:
                self._process_genre(item)
            elif 'album_id' in item:
                self._process_review(item)
            else:
                logger.warning(f"Unknown item type: {item}")
            
            return item
            
        except IntegrityError as e:
            logger.warning(f"Database integrity error: {e}")
            self.session.rollback()
            raise DropItem(f"Duplicate item found: {item}")
        except Exception as e:
            logger.error(f"Error processing item: {e}")
            self.session.rollback()
            raise DropItem(f"Failed to process item: {item}")
    
    def _process_album(self, item):
        """Process and store album item"""
        # Check if album already exists
        existing = self.session.query(Album).filter_by(aoty_id=item.get('aoty_id')).first()
        
        if existing:
            # Update existing album
            existing.title = item.get('title', existing.title)
            existing.critic_score = item.get('critic_score', existing.critic_score)
            existing.user_score = item.get('user_score', existing.user_score)
            existing.review_count = item.get('review_count', existing.review_count)
            existing.scraped_at = datetime.utcnow()
        else:
            # Create new album
            album = Album(
                aoty_id=item.get('aoty_id'),
                title=item.get('title'),
                artist_id=item.get('artist_id'),
                release_date=item.get('release_date'),
                critic_score=item.get('critic_score'),
                user_score=item.get('user_score'),
                review_count=item.get('review_count', 0),
                url=item.get('url'),
                scraped_at=datetime.utcnow(),
                cover_image_url=item.get('cover_image_url'),
                description=item.get('description'),
                tracklist=item.get('tracklist')
            )
            self.session.add(album)
            self.session.flush()  # Get the album ID
            
            # Process genres
            genres = item.get('genres', [])
            for genre_name in genres:
                genre = self._get_or_create_genre(genre_name)
                album.genres.append(genre)
    
    def _process_artist(self, item):
        """Process and store artist item"""
        # Check if artist already exists
        existing = self.session.query(Artist).filter_by(aoty_id=item.get('aoty_id')).first()
        
        if existing:
            # Update existing artist
            existing.name = item.get('name', existing.name)
            existing.album_count = item.get('album_count', existing.album_count)
            existing.scraped_at = datetime.utcnow()
        else:
            # Create new artist
            artist = Artist(
                aoty_id=item.get('aoty_id'),
                name=item.get('name'),
                url=item.get('url'),
                album_count=item.get('album_count', 0),
                scraped_at=datetime.utcnow(),
                image_url=item.get('image_url'),
                description=item.get('description')
            )
            self.session.add(artist)
    
    def _process_genre(self, item):
        """Process and store genre item"""
        # Check if genre already exists
        existing = self.session.query(Genre).filter_by(name=item.get('name')).first()
        
        if not existing:
            # Create new genre
            genre = Genre(
                aoty_id=item.get('aoty_id'),
                name=item.get('name'),
                url=item.get('url'),
                album_count=item.get('album_count', 0)
            )
            self.session.add(genre)
    
    def _process_review(self, item):
        """Process and store review item"""
        # Check if review already exists
        existing = self.session.query(Review).filter_by(
            album_id=item.get('album_id'),
            reviewer_name=item.get('reviewer_name'),
            review_text=item.get('review_text')
        ).first()
        
        if not existing:
            # Create new review
            review = Review(
                album_id=item.get('album_id'),
                reviewer_name=item.get('reviewer_name'),
                rating=item.get('rating'),
                review_text=item.get('review_text'),
                source=item.get('source', 'critic'),
                publication=item.get('publication'),
                review_date=item.get('review_date'),
                url=item.get('url'),
                helpful_count=item.get('helpful_count', 0)
            )
            self.session.add(review)
    
    def _get_or_create_genre(self, genre_name):
        """Get existing genre or create new one"""
        genre = self.session.query(Genre).filter_by(name=genre_name).first()
        if not genre:
            genre = Genre(name=genre_name)
            self.session.add(genre)
            self.session.flush()
        return genre


class DuplicateCheckPipeline:
    """
    Pipeline to check for duplicate items before processing
    """
    
    def __init__(self):
        self.seen_albums = set()
        self.seen_artists = set()
        self.seen_genres = set()
        
    def process_item(self, item, spider):
        """Check for duplicates and drop if already seen"""
        if 'aoty_id' in item and 'title' in item:
            # Album item
            aoty_id = item.get('aoty_id')
            if aoty_id in self.seen_albums:
                raise DropItem(f"Duplicate album found: {aoty_id}")
            self.seen_albums.add(aoty_id)
            
        elif 'aoty_id' in item and 'name' in item:
            # Artist item
            aoty_id = item.get('aoty_id')
            if aoty_id in self.seen_artists:
                raise DropItem(f"Duplicate artist found: {aoty_id}")
            self.seen_artists.add(aoty_id)
            
        elif 'name' in item:
            # Genre item
            name = item.get('name')
            if name in self.seen_genres:
                raise DropItem(f"Duplicate genre found: {name}")
            self.seen_genres.add(name)
        
        return item


class ValidationPipeline:
    """
    Pipeline to validate scraped data
    """
    
    def process_item(self, item, spider):
        """Validate item data"""
        # Validate required fields for albums
        if 'aoty_id' in item and 'title' in item:
            if not item.get('aoty_id'):
                raise DropItem("Album missing aoty_id")
            if not item.get('title'):
                raise DropItem("Album missing title")
            if not item.get('url'):
                raise DropItem("Album missing URL")
        
        # Validate required fields for artists
        if 'aoty_id' in item and 'name' in item:
            if not item.get('aoty_id'):
                raise DropItem("Artist missing aoty_id")
            if not item.get('name'):
                raise DropItem("Artist missing name")
            if not item.get('url'):
                raise DropItem("Artist missing URL")
        
        # Validate required fields for reviews
        if 'album_id' in item:
            if not item.get('album_id'):
                raise DropItem("Review missing album_id")
        
        return item


class LoggingPipeline:
    """
    Pipeline to log scraping statistics
    """
    
    def __init__(self):
        self.albums_count = 0
        self.artists_count = 0
        self.genres_count = 0
        self.reviews_count = 0
        
    def process_item(self, item, spider):
        """Track item counts for logging"""
        if 'aoty_id' in item and 'title' in item:
            self.albums_count += 1
        elif 'aoty_id' in item and 'name' in item:
            self.artists_count += 1
        elif 'name' in item:
            self.genres_count += 1
        elif 'album_id' in item:
            self.reviews_count += 1
        
        return item
    
    def close_spider(self, spider):
        """Log final statistics when spider closes"""
        logger.info(f"=== Scraping Statistics ===")
        logger.info(f"Albums scraped: {self.albums_count}")
        logger.info(f"Artists scraped: {self.artists_count}")
        logger.info(f"Genres scraped: {self.genres_count}")
        logger.info(f"Reviews scraped: {self.reviews_count}")
        logger.info(f"===========================")
