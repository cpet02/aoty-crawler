# AOTY Crawler Items
# Define here the models for your scraped items
#
# See documentation in:
# https://docs.scrapy.org/en/latest/topics/items.html

import scrapy
from scrapy.item import Item, Field


class AlbumItem(Item):
    """Item representing an album from AOTY"""
    # Core identification
    aoty_id = Field()  # e.g., "123456-album-name"
    title = Field()
    artist_name = Field()
    url = Field()
    scraped_at = Field()
    
    # Release information
    release_date = Field()
    
    # Scores and reviews
    critic_score = Field()  # 0-100
    user_score = Field()  # 0-100
    critic_review_count = Field()
    user_review_count = Field()
    
    # Genres and tags
    genres = Field()  # List of primary genre names
    genre_tags = Field()  # List of secondary genre tags
    
    # Media and content
    cover_image_url = Field()
    description = Field()
    
    # Scraping metadata (for tracking)
    scrape_genre = Field()
    scrape_year = Field()
    
    # Optional fields (for future expansion)
    artist_id = Field()
    genre_ids = Field()  # List of genre IDs
    tracklist = Field()


class ArtistItem(Item):
    """Item representing an artist from AOTY"""
    aoty_id = Field()  # e.g., "183-kanye-west"
    name = Field()
    url = Field()
    album_count = Field()
    scraped_at = Field()
    image_url = Field()
    description = Field()


class GenreItem(Item):
    """Item representing a genre from AOTY"""
    aoty_id = Field()
    name = Field()
    url = Field()
    album_count = Field()


class ReviewItem(Item):
    """Item representing a review for an album"""
    album_id = Field()
    reviewer_name = Field()
    rating = Field()  # 0-10 or 0-100 depending on source
    review_text = Field()
    source = Field()  # "critic" or "user"
    publication = Field()  # e.g., "Pitchfork", "NME"
    review_date = Field()
    url = Field()
    helpful_count = Field()


class ScrapeJobItem(Item):
    """Item for tracking scrape jobs"""
    job_type = Field()  # "full_crawl", "genre_update", etc.
    status = Field()  # "running", "completed", "failed"
    start_time = Field()
    end_time = Field()
    items_scraped = Field()
    errors_count = Field()
    last_url = Field()
