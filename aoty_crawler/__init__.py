# AOTY Crawler Package
# Main package initialization

__version__ = "0.1.0"
__author__ = "AOTY Crawler Team"

# Import core components
from .settings import *
from .items import *
from .pipelines import *
from .middlewares import *

# Import spiders
from .spiders import AlbumSpider, ArtistSpider, GenreSpider, YearSpider

# Import utilities
from .utils.selenium_helper import (
    SeleniumHelper, 
    CloudflareBypass, 
    create_selenium_driver,
    get_page_with_selenium,
    is_cloudflare_blocked
)

__all__ = [
    # Core components
    'AlbumSpider', 'ArtistSpider', 'GenreSpider', 'YearSpider', 'TestSpider',
    'AlbumItem', 'ArtistItem', 'GenreItem', 'ReviewItem',
    'FileStoragePipeline', 'DuplicateCheckPipeline',
    # Utilities
    'SeleniumHelper', 'CloudflareBypass', 
    'create_selenium_driver', 'get_page_with_selenium', 'is_cloudflare_blocked',
]
