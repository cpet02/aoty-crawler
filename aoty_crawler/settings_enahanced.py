# Enhanced settings for AOTY Crawler
# Adds output directory configuration

import os
from .settings import *

# Output directory configuration
OUTPUT_DIR = os.environ.get('OUTPUT_DIR', 'data/output')

# Ensure output directory exists
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Update pipeline settings to use OUTPUT_DIR
ITEM_PIPELINES = {
    "aoty_crawler.pipelines.FileStoragePipeline": 300,
    "aoty_crawler.pipelines.DuplicateCheckPipeline": 350,
    "aoty_crawler.pipelines.ValidationPipeline": 400,
    "aoty_crawler.pipelines.LoggingPipeline": 500,
}

# Add custom settings dictionary for easy access
CUSTOM_SETTINGS = {
    'OUTPUT_DIR': OUTPUT_DIR,
}