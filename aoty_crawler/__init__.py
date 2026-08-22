# AOTY Crawler Package
# Main package initialization

__version__ = "0.1.0"
__author__ = "AOTY Crawler Team"

from .items import AlbumItem, ArtistItem, GenreItem, ReviewItem, ScrapeJobItem
from .pipelines import FileStoragePipeline, DuplicateCheckPipeline, ValidationPipeline, LoggingPipeline
from .spiders import AlbumSpider, ArtistSpider, GenreSpider, YearSpider, ComprehensiveAlbumSpider, ProductionSpider

__all__ = [
    'AlbumSpider', 'ArtistSpider', 'GenreSpider', 'YearSpider',
    'ComprehensiveAlbumSpider', 'ProductionSpider',
    'AlbumItem', 'ArtistItem', 'GenreItem', 'ReviewItem', 'ScrapeJobItem',
    'FileStoragePipeline', 'DuplicateCheckPipeline', 'ValidationPipeline', 'LoggingPipeline',
]
