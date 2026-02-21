#!/bin/bash
# AOTY Crawler Startup Script

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is not installed. Please install Python 3.10+"
    exit 1
fi

# Check Python version
PYTHON_VERSION=$(python3 --version | cut -d' ' -f2 | cut -d'.' -f1,2)
if [ "$(echo "$PYTHON_VERSION < 3.10" | bc -l)" -eq 1 ]; then
    echo "❌ Python $PYTHON_VERSION is too old. Please install Python 3.10+"
    exit 1
fi

echo "✅ Python $PYTHON_VERSION detected"

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
source venv/bin/activate

# Install dependencies if requirements.txt exists
if [ -f "requirements.txt" ]; then
    echo "Installing dependencies..."
    pip install -r requirements.txt
fi

# Initialize database if it doesn't exist
if [ ! -f "data/aoty_database.db" ]; then
    echo "Initializing database..."
    python -m database.init_db
fi

echo "✅ AOTY Crawler is ready!"
echo ""
echo "Usage:"
echo "  python -m cli scrape          # Start scraping"
echo "  python -m cli search --help   # Search albums"
echo "  python -m cli stats           # Show statistics"
echo ""
