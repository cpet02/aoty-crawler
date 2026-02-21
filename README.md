# AOTY Music Data Crawler

A comprehensive Python-based web scraping and data management system to extract, store, and query music album data from AlbumOfTheYear.org (AOTY).

## ðŸŽ¯ Overview

This project enables advanced filtering and discovery capabilities beyond what AOTY's native interface offers, specifically addressing limitations like:
- Limited review count filtering options
- Single-genre search restriction (despite albums having multiple genre tags)
- No ability to create complex multi-criteria queries

## âœ… Technical Feasibility

Based on research conducted in February 2026:

- **robots.txt Compliance**: Respects AOTY's robots.txt directives
- **Cloudflare Protection**: Successfully works around using Selenium with undetected-chromedriver
- **No Official API**: Scraping is the only viable data access method
- **Rate Limiting**: Implements polite crawling with 3+ second delays

## ðŸ› ï¸ Technology Stack

### Core Components
- **Scrapy** - Efficient crawling and request management
- **Selenium + undetected-chromedriver** - JavaScript rendering and Cloudflare bypass
- **BeautifulSoup4** - HTML parsing
- **SQLAlchemy** - Database ORM
- **SQLite** - Primary database (PostgreSQL for scale)

### Additional Libraries
- Pandas - Data analysis and CSV export
- NumPy - Numerical operations
- Loguru - Better logging
- Pydantic - Configuration validation

## ðŸ“ Project Structure

```
aoty_crawler/
â”œâ”€â”€ scrapy.cfg
â”œâ”€â”€ requirements.txt
â”œâ”€â”€ README.md
â”œâ”€â”€ aoty_crawler/
â”‚   â”œâ”€â”€ __init__.py
â”‚   â”œâ”€â”€ __main__.py
â”‚   â”œâ”€â”€ settings.py
â”‚   â”œâ”€â”€ items.py
â”‚   â”œâ”€â”€ pipelines.py
â”‚   â”œâ”€â”€ middlewares.py
â”‚   â”œâ”€â”€ spiders/
â”‚   â”‚   â”œâ”€â”€ __init__.py
â”‚   â”‚   â”œâ”€â”€ album_spider.py
â”‚   â”‚   â”œâ”€â”€ artist_spider.py
â”‚   â”‚   â”œâ”€â”€ genre_spider.py
â”‚   â”‚   â””â”€â”€ year_spider.py
â”‚   â”œâ”€â”€ utils/
â”‚   â”‚   â”œâ”€â”€ __init__.py
â”‚   â”‚   â””â”€â”€ selenium_helper.py
â”‚   â””â”€â”€ __main__.py
â”œâ”€â”€ database/
â”‚   â”œâ”€â”€ __init__.py
â”‚   â”œâ”€â”€ models.py
â”‚   â”œâ”€â”€ init_db.py
â”‚   â””â”€â”€ migrations/
â”œâ”€â”€ cli/
â”‚   â”œâ”€â”€ __init__.py
â”‚   â”œâ”€â”€ __main__.py
â”‚   â””â”€â”€ main.py
â””â”€â”€ tests/
```

## ðŸš€ Getting Started

### Prerequisites
- Python 3.10+
- Chrome browser (for Selenium)
- pip package manager

### Installation

1. **Clone the repository**
```bash
cd aoty_crawler
```

2. **Create virtual environment**
```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or
venv\Scripts\activate  # Windows
```

3. **Install dependencies**
```bash
pip install -r requirements.txt
```

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
- Respect rate limits to avoid server load
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

---

**Happy Music Discovery! ðŸŽµ**

