# Pipelines for AOTY Crawler
# Data processing pipelines for cleaning, validation, and file-based storage

import logging
import json
import csv
import os
from datetime import datetime
from scrapy.exceptions import DropItem
from aoty_crawler.utils import job_tracker

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
        # Use the spider's job_id (if it has one) so a job's status file and
        # its output files share the same token and can be linked up by a UI.
        timestamp = getattr(spider, 'job_id', None) or datetime.utcnow().strftime('%Y%m%d_%H%M%S')

        # Get output directory from spider settings or use default. Resolved
        # to an absolute path immediately: this pipeline runs inside whatever
        # process launched the crawl (CLI subprocess, UI, etc), and anything
        # stored below (job status output_files) may later be read back by a
        # different process with a different working directory (e.g. the
        # Streamlit server, which ui/launch.py runs with cwd=ui/). A relative
        # path here would resolve fine for the writer and silently fail for
        # every other reader.
        output_dir = os.path.abspath(spider.settings.get('OUTPUT_DIR', OUTPUT_DIR))
        os.makedirs(output_dir, exist_ok=True)

        logger.info(f"\n{'='*60}")
        logger.info(f"FILE STORAGE PIPELINE - Writing to: {output_dir}")
        logger.info(f"{'='*60}")

        files_written = 0
        files_failed = 0
        album_output_files = {}

        # Write albums
        if self.albums:
            # JSON output
            albums_json_file = os.path.join(output_dir, f'albums_{timestamp}.json')
            try:
                with open(albums_json_file, 'w', encoding='utf-8') as f:
                    json.dump(self.albums, f, indent=2, default=str)
                logger.info(f"✓ Saved {len(self.albums)} albums to JSON: {albums_json_file}")
                files_written += 1
                album_output_files['json'] = albums_json_file
            except Exception as e:
                logger.error(f"✗ Failed to write albums JSON: {e}")
                files_failed += 1

            # CSV output
            albums_csv_file = os.path.join(output_dir, f'albums_{timestamp}.csv')
            if self._write_csv(albums_csv_file, self.albums):
                logger.info(f"✓ Saved {len(self.albums)} albums to CSV: {albums_csv_file}")
                files_written += 1
                album_output_files['csv'] = albums_csv_file
            else:
                logger.error(f"✗ Failed to write albums CSV: {albums_csv_file}")
                files_failed += 1

        if album_output_files and hasattr(spider, 'job_id'):
            jobs_dir = getattr(spider, 'jobs_dir', None) or job_tracker.jobs_dir_for(output_dir)
            job_tracker.update_job(
                spider.job_id, jobs_dir,
                output_files=album_output_files,
                albums_count=len(self.albums),
            )
        
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
