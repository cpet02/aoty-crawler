# AOTY Crawler

A personal music data explorer built on [AlbumOfTheYear.org](https://www.albumoftheyear.org). Scrapes album data by genre and year, stores it locally, and exposes it through a Streamlit dashboard with multi-genre filtering — something AOTY's own interface doesn't support.

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Scrapy](https://img.shields.io/badge/scrapy-2.x-green.svg)](https://scrapy.org/)
[![Streamlit](https://img.shields.io/badge/streamlit-1.x-red.svg)](https://streamlit.io/)

---

## Why This Exists

AOTY is great but its search is limited — one genre at a time, no review-count filtering, no way to combine criteria. This project lets you build a local queryable copy of the data and explore it however you want.

**What you can do with it:**
- Filter albums by multiple genres simultaneously
- Set minimum critic/user score thresholds
- Filter by review count (find hidden gems or widely-reviewed releases)
- Browse by year
- Export to CSV/JSON for your own analysis

---

## Stack

| Component | Purpose |
|---|---|
| [Scrapy](https://scrapy.org/) | Web crawling with built-in rate limiting |
| [Streamlit](https://streamlit.io/) | Interactive dashboard UI |
| [SQLAlchemy](https://www.sqlalchemy.org/) + SQLite | Local database |
| [Selenium](https://selenium.dev/) + undetected-chromedriver | JS rendering fallback |
| Pandas | Data export and analysis |

---

## Requirements

- Python 3.10+
- Google Chrome (for Selenium fallback)
- pip

---

## Installation

```bash
git clone https://github.com/cpet02/aoty-crawler.git
cd aoty-crawler

python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

pip install -r requirements.txt
pip install -r ui/requirements.txt
mkdir logs
```

### Easy Setup (Recommended)

**Windows:**
```powershell
setup.bat
```

**Linux/Mac:**
```bash
chmod +x setup.sh
./setup.sh
```

This installs everything automatically. Then activate the venv:
- Windows: `venv\Scripts\activate`
- Linux/Mac: `source venv/bin/activate`

### Manual Setup

<details>
<summary>Click to expand manual installation steps</summary>
```bash
git clone https://github.com/cpet02/aoty-crawler.git
cd aoty-crawler

python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

pip install -r requirements.txt
pip install -r ui/requirements.txt
mkdir logs
```

</details>
---

## Quick Start

**1. Scrape some data**

```bash
# Scrape Pop albums from 2026 (250 albums, 1 year back)
python -m cli scrape --genre "Pop" --start-year 2026 --years-back 1 --albums-per-year 250

# Scrape Rock albums across 3 years
python -m cli scrape --genre "Rock" --start-year 2026 --years-back 3 --albums-per-year 100

# Test run (10 albums, stops quickly)
python -m cli scrape --genre "Jazz" --test-mode --limit 10
```

**2. Launch the dashboard**

```bash
python ui/launch.py
# Opens at http://localhost:8501
```

---

## CLI Reference

```
python -m cli scrape [options]

Options:
  --genre TEXT            Genre to scrape (e.g. "Pop", "Hip-Hop", "Electronic")
  --start-year INT        Starting year (default: current year)
  --years-back INT        How many years to go back (default: 1)
  --albums-per-year INT   Albums to collect per year (default: 250)
  --test-mode             Limit scrape to --limit albums for testing
  --limit INT             Album limit in test mode (default: 10)
  --resume                Resume a previous scrape
```

Genre names match what's shown on AOTY (e.g. `"Hip-Hop"`, `"Indie Rock"`, `"Electronic"`). Capitalisation is not strict but spacing matters — use the genre name as written on the site.

---

## Project Structure

```
aoty-crawler/
├── aoty_crawler/              # Scrapy package
│   ├── spiders/
│   │   ├── production_spider.py        # Main spider
│   │   └── comprehensive_album_spider.py
│   ├── utils/
│   │   ├── data_loader.py
│   │   └── selenium_helper.py
│   ├── items.py               # Data models
│   ├── pipelines.py           # Output pipeline (JSON + CSV)
│   ├── middlewares.py         # Retry + Selenium middleware
│   └── settings.py            # Scrapy config
├── cli/                       # CLI entry point
│   └── main.py
├── database/                  # SQLAlchemy models
│   └── models.py
├── ui/                        # Streamlit dashboard
│   ├── app.py                 # Main app
│   ├── genres_manager.py      # Genre hierarchy logic
│   ├── genres_db.json         # Bundled genre list
│   └── launch.py
├── data/output/               # Scraped output (gitignored)
├── logs/                      # Run logs (gitignored)
├── .env.example               # Config template
└── requirements.txt
```

---

## Data Output

Each scrape run writes two files to `data/output/`:

- `albums_YYYYMMDD_HHMMSS.json` — full records
- `albums_YYYYMMDD_HHMMSS.csv` — flat tabular format

**Fields per album:**

| Field | Description |
|---|---|
| `title` | Album title |
| `artist_name` | Artist name |
| `scrape_year` | Release year scraped |
| `scrape_genre` | Genre used to find it |
| `genres` | All genre tags on the album page |
| `genre_tags` | Secondary genre tags |
| `critic_score` | Critic aggregate score (0–100) |
| `user_score` | User aggregate score (0–100) |
| `critic_review_count` | Number of critic reviews |
| `user_review_count` | Number of user ratings |
| `release_date` | Release date string |
| `cover_image_url` | Album art URL |
| `url` | AOTY album page URL |

---

## Configuration

Default rate limiting is conservative and respectful. Settings in `aoty_crawler/settings.py`:

```python
DOWNLOAD_DELAY = 3           # seconds between requests
CONCURRENT_REQUESTS = 1      # one request at a time
ROBOTSTXT_OBEY = True        # always
```

Copy `.env.example` to `.env` to override settings without editing source:

```bash
cp .env.example .env
```

---

## Troubleshooting

**`ModuleNotFoundError: No module named 'aoty_crawler'`**
Run commands from the project root directory, not from inside a subdirectory.

**Scrape returns 0 albums**
The CSS selectors for the ratings page may have changed. Check `aoty_crawler/spiders/production_spider.py` → `parse_ratings_page()`. You can debug interactively with:
```bash
scrapy shell "https://www.albumoftheyear.org/ratings/user-highest-rated/2026/pop/"
```

**ChromeDriver crashes**
Update Chrome, then clear its cached driver:
```bash
rm -rf ~/.wdm/drivers/chromedriver/*
```

**Dashboard shows "No albums loaded"**
You need to run a scrape first. The UI only reads from `data/output/`.

---

## Legal

This project is for **personal, non-commercial use only**. See [TERMS_OF_USE.md](TERMS_OF_USE.md) and [COMPLIANCE.md](COMPLIANCE.md) for full details. Data scraped using this tool belongs to AlbumOfTheYear.org.

---

## License

MIT — see [LICENSE](LICENSE).
