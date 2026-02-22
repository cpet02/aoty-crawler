# AOTY Music Data Crawler

A Python-based web scraping system to extract and analyze music album data from AlbumOfTheYear.org (AOTY) for personal music discovery and recommendation.

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: Personal Use](https://img.shields.io/badge/license-Personal%20Use-green.svg)](LICENSE)

---

## 🎯 Overview

This project enables **advanced filtering and music discovery** beyond what AOTY's native interface offers:

- ✅ **Multi-genre filtering** - Search albums across multiple genre tags simultaneously
- ✅ **Review count filtering** - Find hidden gems with specific review thresholds
- ✅ **Complex queries** - Combine criteria (genre + score + year + review count)
- ✅ **Personal database** - Build your own queryable music library
- ✅ **Ethical scraping** - Full robots.txt compliance with respectful rate limiting

### Why This Project?

AOTY has limitations:
- Can only search one genre at a time
- Limited filtering options for review counts
- No way to save custom filtered results
- Albums have multiple genre tags, but search doesn't support multi-tag queries

This tool solves those problems for personal use.

---

## 🛠️ Technology Stack

### Core Components
- **Scrapy** - Web crawling framework with built-in rate limiting
- **Selenium** + **undetected-chromedriver** - JavaScript rendering & Cloudflare handling
- **BeautifulSoup4** - HTML parsing and data extraction
- **SQLAlchemy** - Database ORM for data management
- **SQLite** - Lightweight, portable database

### Additional Libraries
- **Pandas** - Data analysis and CSV/JSON export
- **Loguru** - Enhanced logging
- **Pydantic** - Configuration validation
- **Tenacity** - Retry logic with exponential backoff

---

## 📁 Project Structure

```
aoty-crawler/
├── aoty_crawler/           # Main scraping package
│   ├── spiders/            # Scrapy spiders
│   │   ├── production_spider.py      # Main production spider
│   │   ├── comprehensive_album_spider.py
│   │   └── debug_spider.py
│   ├── items.py            # Data models
│   ├── pipelines.py        # Data processing pipelines
│   ├── middlewares.py      # Selenium & retry middleware
│   └── settings.py         # Scrapy configuration
├── cli/                    # Command-line interface
│   └── main.py
├── database/               # Database models & initialization
│   ├── models.py
│   └── init_db.py
├── data/                   # Output directory (not in repo)
├── requirements.txt        # Python dependencies
├── scrapy.cfg             # Scrapy project config
└── README.md              # This file
```

---

## 🚀 Quick Start

### Prerequisites
- **Python 3.10+**
- **Google Chrome** (for Selenium)
- **pip** package manager

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/cpet02/aoty-crawler.git
   cd aoty-crawler
   ```

2. **Create virtual environment**
   ```bash
   python -m venv venv
   
   # Activate:
   # Windows:
   venv\Scripts\activate
   
   # Linux/Mac:
   source venv/bin/activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

<<<<<<< HEAD
4. **Initialize database**
```bash
python -m database.init_db
```

5. **Configure settings (optional)**
```bash
cp .env.example .env
# Edit .env with your preferences
```

## ðŸŽ® Usage

### Basic Commands

#### Initialize Database
```bash
python -m cli init
```

#### Start Scraping
```bash
# Scrape default genres
python -m cli scrape

# Scrape specific genre
python -m cli scrape --genre hip-hop

# Scrape specific year
python -m cli scrape --year 2024

# Test mode (limited scraping)
python -m cli scrape --test-mode --limit 10
```

#### Search Albums
```bash
# Search by genres
python -m cli search --genres "Hip Hop,Electronic"

# Search with multiple criteria
python -m cli search --genres "Jazz,Hip Hop" --match-all --min-score 80 --min-reviews 50

# Search by year
python -m cli search --year 2023 --min-score 75
```

#### Export Data
```bash
# Export to CSV
python -m cli export --format csv --output results.csv

# Export to JSON
python -m cli export --format json --output results.json

# Export to SQLite
python -m cli export --format sqlite --output export.db
```

#### Show Statistics
```bash
python -m cli stats
```

### Advanced Usage

#### Python API
```python
from aoty_crawler import AlbumSpider, init_database, get_session
from database.models import Album, Artist, Genre

# Initialize database
engine = init_database()
session = get_session(engine)

# Query albums
albums = session.query(Album).filter(Album.critic_score >= 80).all()

# Export to pandas DataFrame
import pandas as pd
df = pd.read_sql_query("SELECT * FROM albums", engine)
```

## ðŸ“Š Database Schema

### Tables
- **albums** - Album information with scores and metadata
- **artists** - Artist information and album counts
- **genres** - Genre categories
- **album_genres** - Many-to-many relationship between albums and genres
- **reviews** - Individual reviews (optional)
- **scrape_jobs** - Tracking for scraping jobs

### Key Features
- SQLite database (portable, serverless)
- Proper indexing for fast queries
- Foreign key relationships
- Cascade deletion

## ðŸŽ¯ Implementation Phases

### Phase 1: Foundation âœ… (Current)
- [x] Core scraping infrastructure
- [x] Database schema and models
- [x] Selenium middleware for Cloudflare bypass
- [x] Basic spiders for albums, artists, genres
- [x] CLI interface

### Phase 2: Data Extraction
- [ ] Expand spider coverage
- [ ] Implement data validation
- [ ] Add checkpoint/resume functionality
- [ ] Rate limiting strategies

### Phase 3: Query Engine
- [ ] Advanced filtering and search
- [ ] Multi-genre search
- [ ] Complex boolean queries
- [ ] Export functionality

### Phase 4: Polish & Optimization
- [ ] Performance optimization
- [ ] Error handling and logging
- [ ] Documentation
- [ ] Testing

## ðŸ“ˆ Success Metrics

1. **Coverage**: Successfully scrape 10,000+ albums across 20+ genres
2. **Accuracy**: >95% data extraction accuracy
3. **Performance**: Query execution <1 second for complex filters
4. **Reliability**: <1% scraping failure rate over 1,000 requests
5. **Usability**: CLI can execute 90% of desired queries in single command

## âš ï¸ Important Notes

### Ethical Considerations
- This tool is for personal use to enhance music discovery
- Do not republish AOTY's data
-       rate limits to avoid server load
- Do not use for commercial purposes without permission

### Compliance
- Always check AOTY's robots.txt and Terms of Service
- If restrictions are added, stop scraping and consider alternatives
- Store data locally; do not republish or redistribute

### Performance Expectations
- Scraping 10,000 albums at 3 sec/album = ~8-9 hours
- Plan long-running scrapes during off-peak hours
- Use `tmux` or `screen` to prevent session disconnects

### Data Freshness
- Album scores and review counts change over time
- Plan periodic refreshes for actively tracked albums

## ðŸ§ª Testing

```bash
# Run tests
pytest tests/

# Run specific test
pytest tests/test_spiders.py

# Run with coverage
pytest --cov=aoty_crawler tests/
```

## ðŸ“ Development

### Adding New Features
1. Create new spider in `aoty_crawler/spiders/`
2. Add pipeline in `aoty_crawler/pipelines.py`
3. Update database models in `database/models.py`
4. Add CLI command in `cli/main.py`

### Debugging
```bash
# Enable debug logging
python -m cli scrape --log-level DEBUG

# Test individual spider
python -m scrapy shell https://www.albumoftheyear.org/album/123456-album-name/
```

## ðŸ¤ Contributing

Contributions are welcome! Please follow these steps:
1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run tests
5. Submit a pull request

## ðŸ“„ License

This project is for personal, non-commercial use only. Please respect AOTY's Terms of Service.

## ðŸ™ Acknowledgments

- Inspired by existing AOTY scraping projects
- Uses undetected-chromedriver for Cloudflare bypass
- Built with Scrapy for efficient crawling

## ðŸ“ž Support

For issues and questions:
- Check the documentation
- Review the logs
- Open an issue on GitHub
=======
4. **Test the installation**
   ```bash
   python -m cli crawl test
   ```
>>>>>>> 889492061893d832851f46c1e19a96d2e0b3cd49

---

## 🎮 Usage

### Basic Scraping

**Run the production spider** (scrapes by genre and year):
```bash
# Scrape Rock albums from 2026 (test mode - 10 albums)
python -m cli crawl production --genre rock --start-year 2026 --years-back 1 --albums-per-year 10 --test-mode

# Scrape Hip-Hop albums from 2024-2026 (250 albums per year)
python -m cli crawl production --genre hip-hop --start-year 2026 --years-back 3 --albums-per-year 250
```

### Available Spiders

```bash
# Test spider (quick verification)
python -m cli crawl test

# Debug spider (detailed HTML analysis)
python -m cli crawl debug

# Production spider (full genre/year scraping)
python -m cli crawl production --genre [genre-slug] --start-year [year]
```

### Production Spider Options

```bash
python -m cli crawl production \
    --genre hip-hop \              # Genre slug (e.g., hip-hop, electronic, rock)
    --start-year 2026 \            # Starting year (default: current year)
    --years-back 5 \               # Number of years to scrape back
    --albums-per-year 250 \        # Albums to scrape per year (default: 10)
    --test-mode                    # Limit to first genre/year for testing
```

**Common Genre Slugs:**
- `rock`, `pop`, `hip-hop`, `electronic`, `jazz`, `metal`, `indie`, `folk`, `r-b`, `punk`

### Output Data

Scraped data is saved to `data/output/`:
- **JSON format**: `albums_YYYYMMDD_HHMMSS.json`
- Contains: artist, title, scores, genres, tags, release date, review counts

**Example Output:**
```json
{
  "artist_name": "Kendrick Lamar",
  "title": "GNX",
  "release_date": "November 22, 2024",
  "user_score": 85.0,
  "critic_score": 88.0,
  "user_review_count": 1247,
  "critic_review_count": 23,
  "genres": ["Hip Hop", "Conscious Hip Hop"],
  "genre_tags": ["West Coast Hip Hop", "Jazz Rap"],
  "url": "https://www.albumoftheyear.org/album/..."
}
```

---

## 📊 Data Analysis

### Export to CSV/Pandas

```python
import pandas as pd
import json

# Load scraped data
with open('data/output/albums_20260221_035652.json', 'r') as f:
    data = json.load(f)

# Create DataFrame
df = pd.DataFrame(data)

# Filter and analyze
high_rated = df[df['user_score'] > 80]
print(f"Found {len(high_rated)} albums with user score > 80")

# Export to CSV
df.to_csv('albums_export.csv', index=False)
```

### Query Examples

```python
# Find albums with 100+ user reviews and 85+ score
popular = df[(df['user_review_count'] > 100) & (df['user_score'] > 85)]

# Find albums with specific genre tags
jazz_hip_hop = df[df['genre_tags'].apply(lambda x: 'Jazz Rap' in x if x else False)]

# Group by genre
genre_stats = df.groupby('genres').agg({
    'user_score': 'mean',
    'user_review_count': 'sum'
})
```

---

## ⚙️ Configuration

### Rate Limiting (settings.py)

```python
DOWNLOAD_DELAY = 3              # 3 seconds between requests
RANDOMIZE_DOWNLOAD_DELAY = True # Varies 1.5-4.5 seconds
CONCURRENT_REQUESTS = 1         # One request at a time
AUTOTHROTTLE_ENABLED = True     # Dynamic throttling
ROBOTSTXT_OBEY = True          # Respect robots.txt
```

### User Agent

```python
USER_AGENT = "AOTY-Crawler/1.0 (Personal Project; Music Data Collection)"
```

---

## 🔍 Understanding the Workflow

1. **Genre Page** → Extracts all genre links
2. **Ratings Pages** → For each genre/year, gets album list
   - URL pattern: `/ratings/user-highest-rated/{year}/{genre}/`
3. **Album Pages** → Extracts detailed data for each album
   - Scores, review counts, genres, tags, release dates
4. **Data Output** → Saves to JSON files in `data/output/`

---

## ⚠️ Legal & Ethical Notice

### ✅ Compliance

- **Fully compliant** with `albumoftheyear.org/robots.txt`
- **Respectful rate limiting**: 3+ second delays between requests
- **Personal, non-commercial use only**
- **Data not redistributed or republished**
- Last ToS Review: **February 2026**

### ⚠️ Important Disclaimers

1. **This tool is for PERSONAL USE ONLY**
   - Music discovery and personal database creation
   - NOT for commercial purposes
   - NOT for republishing AOTY's data

2. **Respect the Source**
   - AOTY provides free access to music data
   - Do not abuse rate limits
   - Do not overwhelm their servers
   - Support AOTY if you find value in their service

3. **Monitor Changes**
   - Check robots.txt periodically
   - Respect any new restrictions
   - If asked to stop, comply immediately

4. **Data Storage**
   - Store data locally only
   - Do not create public databases with AOTY data
   - Do not redistribute scraped content

### 📧 Contact

If you're AOTY's operator and have concerns:
- Contact: [Your email - update this!]
- I'm happy to adjust or cease scraping

---

## 🎯 Performance Expectations

### Scraping Speed
- **10 albums**: ~30-45 seconds (with 3-second delays)
- **250 albums**: ~12-15 minutes
- **1,000 albums**: ~50-60 minutes
- **10,000 albums**: ~8-9 hours

### Storage
- **1,000 albums**: ~2-5 MB (JSON)
- **10,000 albums**: ~20-50 MB
- Includes all metadata, genres, tags, scores

### Recommendations
- Start with **test mode** (10 albums) to verify setup
- Run large scrapes **overnight** or during off-peak hours
- Use `tmux` or `screen` for long-running jobs
- Monitor logs in `logs/aoty_crawler.log`

---

## 🐛 Troubleshooting

### Chrome/Selenium Issues

**Error: "ChromeDriver not found"**
```bash
pip install --upgrade undetected-chromedriver
```

**Error: "Chrome version mismatch"**
- Update Chrome to latest version
- Reinstall undetected-chromedriver

### Scraping Issues

**Error: "403 Forbidden" or Cloudflare blocking**
- Already handled by undetected-chromedriver
- Check if rate limits are respected (3+ seconds)
- Try increasing `DOWNLOAD_DELAY` to 5 seconds

**No data scraped**
```bash
# Check logs
cat logs/aoty_crawler.log | tail -50

# Run debug spider to inspect HTML
python -m cli crawl debug
```

### Data Issues

**Empty/null fields in output**
- AOTY HTML structure may have changed
- Check `debug_html/` folder for saved pages
- Update selectors in spider if needed

---

## 🧪 Development

### Project Goals

**Phase 1: Core Scraping** ✅
- [x] Scrapy spider infrastructure
- [x] Selenium middleware for Cloudflare
- [x] Genre/year navigation
- [x] Album data extraction
- [x] JSON output

**Phase 2: Database (In Progress)**
- [ ] SQLite database integration
- [ ] SQLAlchemy models
- [ ] CLI search commands
- [ ] Data deduplication

**Phase 3: Advanced Features**
- [ ] Resume interrupted scrapes
- [ ] Incremental updates (new releases)
- [ ] Genre tag filtering
- [ ] Recommendation engine

### Adding Features

1. **New Spider**: Add to `aoty_crawler/spiders/`
2. **Data Fields**: Update `items.py`
3. **Processing**: Add pipeline in `pipelines.py`
4. **CLI Command**: Extend `cli/main.py`

### Testing

```bash
# Quick test (10 albums)
python -m cli crawl production --test-mode --albums-per-year 10

# Verify extraction
python quick_verification.py
```

---

## 📖 Further Reading

### Relevant Documentation
- [Scrapy Documentation](https://docs.scrapy.org/)
- [Selenium Documentation](https://selenium-python.readthedocs.io/)
- [Web Scraping Best Practices](https://www.scraperapi.com/blog/web-scraping-best-practices/)

### Similar Projects
- Search GitHub for "albumoftheyear scraper" for other approaches
- Many projects exist - this one emphasizes ethical scraping

---

## 🙏 Acknowledgments

- **AlbumOfTheYear.org** - For providing comprehensive music data
- **Scrapy** - Excellent web crawling framework
- **undetected-chromedriver** - Cloudflare bypass capability
- Inspired by the need for better music discovery tools

---

## 📜 License

**Personal Use Only**

This project is provided for educational and personal use. It is NOT licensed for:
- Commercial use
- Data redistribution
- Creating competing services
- Any use that violates AOTY's Terms of Service

By using this tool, you agree to:
- Use it responsibly and ethically
- Respect AOTY's servers and bandwidth
- Not republish or redistribute scraped data
- Cease use if requested by AOTY

---

## 🎵 Happy Music Discovery!

Built with ❤️ for music lovers who want to explore beyond the mainstream.

**Questions? Issues? Suggestions?**
- Open an issue on GitHub
- Check the logs in `logs/aoty_crawler.log`
- Review the troubleshooting section above
---

**Last Updated**: February 2026
