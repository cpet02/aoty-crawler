# AOTY Spiders
# Web scraping spiders for AlbumOfTheYear.org

# Import all spiders
from .test_spider import TestSpider
from .debug_spider import DebugSpider
from .html_debug_spider import HtmlDebugSpider
from .genre_test_spider import GenreTestSpider
from .comprehensive_album_spider import ComprehensiveAlbumSpider
from .production_spider import ProductionSpider
from .production_test_spider import ProductionTestSpider

# Import placeholder spiders (to be implemented properly later)
# For now, create simple placeholder classes
import scrapy
from datetime import datetime
import re

# Placeholder AlbumSpider (will be replaced with real implementation)
class AlbumSpider(scrapy.Spider):
    """Placeholder Album Spider"""
    name = "album"
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.logger.warning("AlbumSpider is a placeholder. Use test spider for now.")

# Placeholder ArtistSpider
class ArtistSpider(scrapy.Spider):
    """Placeholder Artist Spider"""
    name = "artist"
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.logger.warning("ArtistSpider is a placeholder. Use test spider for now.")

# Placeholder GenreSpider
class GenreSpider(scrapy.Spider):
    """Placeholder Genre Spider"""
    name = "genre"
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.logger.warning("GenreSpider is a placeholder. Use genre_test spider for now.")

# Placeholder YearSpider
class YearSpider(scrapy.Spider):
    """Placeholder Year Spider"""
    name = "year"
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.logger.warning("YearSpider is a placeholder. Use test spider for now.")

__all__ = [
    'TestSpider', 
    'DebugSpider', 
    'HtmlDebugSpider', 
    'GenreTestSpider',
    'ComprehensiveAlbumSpider',
    'ProductionSpider',
    'ProductionTestSpider',
    'AlbumSpider', 
    'ArtistSpider', 
    'GenreSpider', 
    'YearSpider'
]