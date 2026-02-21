# Database models for AOTY Crawler
# SQLAlchemy ORM models for the database

from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Text, ForeignKey, Table, Index
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker
from datetime import datetime
import os

Base = declarative_base()

# Association table for many-to-many relationship between albums and genres
album_genres = Table(
    'album_genres',
    Base.metadata,
    Column('album_id', Integer, ForeignKey('albums.id', ondelete='CASCADE'), primary_key=True),
    Column('genre_id', Integer, ForeignKey('genres.id', ondelete='CASCADE'), primary_key=True)
)


class Album(Base):
    """Album model"""
    __tablename__ = 'albums'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    aoty_id = Column(String, unique=True, nullable=False)  # e.g., "123456-album-name"
    title = Column(String, nullable=False)
    artist_id = Column(Integer, ForeignKey('artists.id'), nullable=False)
    release_date = Column(DateTime)
    critic_score = Column(Float)  # 0-100
    user_score = Column(Float)  # 0-100
    review_count = Column(Integer, default=0)
    url = Column(String, unique=True, nullable=False)
    scraped_at = Column(DateTime, default=datetime.utcnow)
    cover_image_url = Column(Text)
    description = Column(Text)
    tracklist = Column(Text)
    
    # Relationships
    artist = relationship("Artist", back_populates="albums")
    genres = relationship("Genre", secondary=album_genres, back_populates="albums")
    reviews = relationship("Review", back_populates="album", cascade="all, delete-orphan")
    
    # Indexes for performance
    __table_args__ = (
        Index('idx_albums_critic_score', 'critic_score'),
        Index('idx_albums_user_score', 'user_score'),
        Index('idx_albums_review_count', 'review_count'),
        Index('idx_albums_release_date', 'release_date'),
    )


class Artist(Base):
    """Artist model"""
    __tablename__ = 'artists'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    aoty_id = Column(String, unique=True, nullable=False)  # e.g., "183-kanye-west"
    name = Column(String, nullable=False)
    url = Column(String, unique=True, nullable=False)
    album_count = Column(Integer, default=0)
    scraped_at = Column(DateTime, default=datetime.utcnow)
    image_url = Column(Text)
    description = Column(Text)
    
    # Relationships
    albums = relationship("Album", back_populates="artist", cascade="all, delete-orphan")
    
    # Indexes
    __table_args__ = (
        Index('idx_artists_name', 'name'),
    )


class Genre(Base):
    """Genre model"""
    __tablename__ = 'genres'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, unique=True, nullable=False)  # e.g., "Hip Hop", "Electronic"
    
    # Relationships
    albums = relationship("Album", secondary=album_genres, back_populates="genres")
    
    # Indexes
    __table_args__ = (
        Index('idx_genres_name', 'name'),
    )


class Review(Base):
    """Review model"""
    __tablename__ = 'reviews'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    album_id = Column(Integer, ForeignKey('albums.id', ondelete='CASCADE'), nullable=False)
    reviewer_name = Column(String)
    rating = Column(Float)  # 0-10 or 0-100 depending on source
    review_text = Column(Text)
    source = Column(String)  # "critic" or "user"
    publication = Column(String)  # e.g., "Pitchfork", "NME"
    review_date = Column(DateTime)
    url = Column(String)
    helpful_count = Column(Integer, default=0)
    
    # Relationships
    album = relationship("Album", back_populates="reviews")
    
    # Indexes
    __table_args__ = (
        Index('idx_reviews_album_id', 'album_id'),
        Index('idx_reviews_source', 'source'),
    )


class ScrapeJob(Base):
    """Scrape job tracking model"""
    __tablename__ = 'scrape_jobs'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    job_type = Column(String, nullable=False)  # "full_crawl", "genre_update", etc.
    status = Column(String, nullable=False)  # "running", "completed", "failed"
    start_time = Column(DateTime, default=datetime.utcnow)
    end_time = Column(DateTime, nullable=True)
    items_scraped = Column(Integer, default=0)
    errors_count = Column(Integer, default=0)
    last_url = Column(String, nullable=True)
    
    def __repr__(self):
        return f"<ScrapeJob(id={self.id}, type={self.job_type}, status={self.status})>"


# Database utility functions
def get_database_url():
    """Get database URL from environment or use default"""
    return os.environ.get('DATABASE_URL', 'sqlite:///data/aoty_database.db')


def create_database_engine(database_url=None):
    """Create and return a database engine"""
    if database_url is None:
        database_url = get_database_url()
    
    # For SQLite, ensure the directory exists
    if database_url.startswith('sqlite:///'):
        db_path = database_url.replace('sqlite:///', '')
        db_dir = os.path.dirname(db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir)
    
    engine = create_engine(database_url, echo=False)
    return engine


def create_tables(engine):
    """Create all tables in the database"""
    Base.metadata.create_all(engine)


def get_session(engine):
    """Get a new database session"""
    Session = sessionmaker(bind=engine)
    return Session()


# Initialize database
def init_database():
    """Initialize the database and create tables"""
    engine = create_database_engine()
    create_tables(engine)
    print("Database initialized successfully!")
    return engine
