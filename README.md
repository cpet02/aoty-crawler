# AOTY Music Data Crawler

A Python-based web scraping system to extract and analyze music album data from AlbumOfTheYear.org (AOTY) for personal music discovery and recommendation.

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)

## 🎯 Overview

This project enables **advanced filtering and music discovery** beyond what AOTY's native interface offers:

- ✅ **Multi-genre filtering** - Search albums across multiple genre tags simultaneously
- ✅ **Review count filtering** - Find hidden gems with specific review thresholds
- ✅ **Complex queries** - Combine criteria (genre + score + year + review count)
- ✅ **Personal database** - Build your own queryable music library
- ✅ **Web UI** - Interactive Streamlit dashboard to explore your data
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
- **Streamlit** - Interactive web dashboard

### Additional Libraries
- **Pandas** - Data analysis and CSV/JSON export
- **Loguru** - Enhanced logging
- **Pydantic** - Configuration validation
- **Tenacity** - Retry logic with exponential backoff

---

## 📋 Prerequisites

Before installing, make sure you have:

1. **Python 3.10 or higher**
   - Check: `python --version` or `python3 --version`
   - Download from: https://www.python.org/downloads/

2. **Google Chrome** (for Selenium)
   - The scraper uses Chrome for JavaScript rendering
   - Download from: https://www.google.com/chrome/

3. **pip** package manager
   - Usually comes with Python
   - Check: `pip --version` or `pip3 --version`

4. **Git** (optional, for cloning)
   - Download from: https://git-scm.com/downloads

---

## 🚀 Installation

### Step 1: Get the Code

**Option A: Using Git**
```bash
git clone https://github.com/yourusername/aoty-crawler.git
cd aoty-crawler
```

**Option B: Download ZIP**
1. Download the project ZIP file
2. Extract it to your desired location
3. Open terminal/command prompt and navigate to the folder:
   ```bash
   cd path/to/aoty-crawler
   ```

### Step 2: Create Virtual Environment

**Why?** Virtual environments prevent dependency conflicts with other Python projects.

**Windows:**
```bash
python -m venv venv
venv\Scripts\activate
```

**macOS/Linux:**
```bash
python3 -m venv venv
source venv/bin/activate
```

**Verify activation:** Your terminal prompt should now show `(venv)` at the start.

### Step 3: Install Dependencies

**Install main dependencies:**
```bash
pip install -r requirements.txt
```

**Install UI dependencies (for Streamlit dashboard):**
```bash
pip install -r ui/requirements.txt
```

### Common Installation Issues

#### Issue: `pip` command not found
**Solution:**
- Try `pip3` instead of `pip`
- Or use: `python -m pip install -r requirements.txt`

#### Issue: ChromeDriver errors
**Solution:**
- Make sure Google Chrome is installed
- Update Chrome to the latest version
- The `undetected-chromedriver` package will auto-download the correct driver

#### Issue: Permission errors on macOS/Linux
**Solution:**
```bash
# Use user install
pip install --user -r requirements.txt

# Or fix permissions
chmod +x *.sh
```

#### Issue: SSL certificate errors
**Solution:**
```bash
# Windows
pip install --trusted-host pypi.org --trusted-host files.pythonhosted.org -r requirements.txt

# macOS - install certificates
cd /Applications/Python\ 3.10/
./Install\ Certificates.command
```

#### Issue: Build errors (C++ compiler required)
**Solution:**
- **Windows:** Install Microsoft C++ Build Tools from https://visualstudio.microsoft.com/visual-cpp-build-tools/
- **macOS:** Install Xcode Command Line Tools: `xcode-select --install`
- **Linux:** Install build tools: `sudo apt-get install build-essential python3-dev`

---

## 📁 Project Structure

```
aoty-crawler/
├── aoty_crawler/              # Main scraping package
│   ├── spiders/               # Scrapy spiders
│   │   ├── production_spider.py
│   │   └── comprehensive_album_spider.py
│   ├── utils/                 # Utility functions
│   │   └── data_loader.py     # Data loading for UI
│   ├── items.py               # Data models
│   ├── pipelines.py           # Data processing pipelines
│   ├── middlewares.py         # Selenium & retry middleware
│   └── settings.py            # Scrapy configuration
├── cli/                       # Command-line interface
│   └── main.py                # CLI entry point
├── database/                  # Database models & initialization
│   ├── models.py
│   └── init_db.py
├── ui/                        # Streamlit web interface
│   ├── app.py                 # Main dashboard
│   ├── launch.py              # Launch script
│   └── requirements.txt       # UI-specific dependencies
├── data/                      # Output directory
│   └── output/                # Scraped data (JSON/CSV)
├── logs/                      # Application logs
├── requirements.txt           # Python dependencies
├── scrapy.cfg                 # Scrapy project config
└── README.md                  # This file
```

---

## 🎮 Usage

### Method 1: Using the CLI (Recommended for first run)

The CLI provides interactive commands for scraping and querying data.

**View available commands:**
```bash
python -m cli
```

**Scrape albums (example - 50 albums from 2024):**
```bash
python -m cli scrape --year 2024 --max-items 50
```

**Common scraping options:**
```bash
# Scrape specific year with limit
python -m cli scrape --year 2023 --max-items 100

# Scrape multiple years
python -m cli scrape --year 2023 --max-items 50
python -m cli scrape --year 2024 --max-items 50

# Scrape specific genres
python -m cli scrape --genre hip-hop --max-items 30
python -m cli scrape --genre electronic --max-items 30
```

**Query scraped data:**
```bash
# List all available genres
python -m cli list-genres

# Search by genre
python -m cli search --genre indie-rock

# Search with filters
python -m cli search --genre electronic --min-score 80 --year 2024
```

### Method 2: Using Streamlit UI (Best for exploring data)

**Launch the web dashboard:**

**Option A: Using the launch script**
```bash
python ui/launch.py
```

**Option B: Direct streamlit command**
```bash
streamlit run ui/app.py
```

**Option C: From the ui directory**
```bash
cd ui
streamlit run app.py
```

The dashboard will open in your browser (usually at `http://localhost:8501`)

**Features:**
- 📊 Interactive filtering by genre, score, and year
- 🎵 Visual album grid with scores and genres
- 📈 Statistics overview and genre distribution
- 🏆 Top albums by user score
- 🔍 Real-time search and filtering

### Method 3: Using Scrapy Directly

For advanced users who want full control:

```bash
# Run the production spider
scrapy crawl production -a year=2024 -a max_items=100

# Run comprehensive spider (more data)
scrapy crawl comprehensive_album -a year=2024 -a max_items=50
```

---

## 🐛 Troubleshooting

### Streamlit Won't Start

**Issue:** `streamlit: command not found`
**Solution:**
```bash
# Make sure you've installed UI dependencies
pip install -r ui/requirements.txt

# Verify streamlit is installed
pip list | grep streamlit

# If not installed, install it directly
pip install streamlit
```

**Issue:** `ModuleNotFoundError: No module named 'aoty_crawler'`
**Solution:**
```bash
# Run from project root directory, not from ui/ directory
cd /path/to/aoty-crawler
python ui/launch.py

# Or use the launch script which handles paths
python ui/launch.py
```

**Issue:** "No albums found" in Streamlit
**Solution:**
```bash
# You need to scrape data first
python -m cli scrape --year 2024 --max-items 50

# Verify data exists
ls data/output/
```

### Scraping Issues

**Issue:** ChromeDriver crashes or won't start
**Solution:**
1. Update Google Chrome to latest version
2. Clear ChromeDriver cache:
   ```bash
   # Windows
   del %USERPROFILE%\.wdm\drivers\chromedriver\*
   
   # macOS/Linux
   rm -rf ~/.wdm/drivers/chromedriver/*
   ```
3. Reinstall undetected-chromedriver:
   ```bash
   pip uninstall undetected-chromedriver
   pip install undetected-chromedriver
   ```

**Issue:** "Cloudflare protection detected"
**Solution:**
- This is normal; the scraper uses `undetected-chromedriver` to handle this
- If it persists, increase delays in `settings.py`:
  ```python
  DOWNLOAD_DELAY = 3  # Increase from 2
  CONCURRENT_REQUESTS = 1  # Reduce from 2
  ```

**Issue:** No data being scraped
**Solution:**
1. Check logs in `logs/aoty_crawler.log`
2. Verify you have internet connection
3. Test with a small sample:
   ```bash
   python -m cli scrape --year 2024 --max-items 5
   ```
4. Check if AOTY website is accessible: https://www.albumoftheyear.org

### General Python Issues

**Issue:** Virtual environment not activating
**Solution:**
```bash
# Windows - try different activation methods
venv\Scripts\activate.bat
# or
venv\Scripts\Activate.ps1  # PowerShell

# macOS/Linux
source venv/bin/activate
# or
. venv/bin/activate
```

**Issue:** Import errors
**Solution:**
```bash
# Reinstall all dependencies
pip install --upgrade -r requirements.txt
pip install --upgrade -r ui/requirements.txt

# Check Python version (must be 3.10+)
python --version
```

---

## 📊 Data Output

Scraped data is saved in `data/output/` in both JSON and CSV formats:

- **JSON files:** `albums_YYYY.json` - Full album data with all fields
- **CSV files:** `albums_YYYY.csv` - Tabular format for spreadsheet analysis

### Data Fields

Each album record includes:
- `title` - Album name
- `artist_name` - Artist/band name
- `scrape_year` - Release year
- `genres` - List of genre tags
- `critic_score` - Critic score (0-100)
- `user_score` - User score (0-100)
- `critic_review_count` - Number of critic reviews
- `user_review_count` - Number of user reviews
- `cover_image_url` - Album cover URL
- `aoty_url` - Link to AOTY page

---

## 🔧 Configuration

### Rate Limiting

The scraper is configured to be respectful to AOTY servers. Settings in `aoty_crawler/settings.py`:

```python
DOWNLOAD_DELAY = 2  # 2 seconds between requests
CONCURRENT_REQUESTS = 2  # Max 2 simultaneous requests
CONCURRENT_REQUESTS_PER_DOMAIN = 1  # 1 request per domain at a time
```

**To slow down even more (recommended for large scrapes):**
```python
DOWNLOAD_DELAY = 3
CONCURRENT_REQUESTS = 1
```

### Environment Variables

Create a `.env` file (copy from `.env.example`):
```bash
cp .env.example .env
```

Available settings:
```env
# Database
DATABASE_URL=sqlite:///aoty_albums.db

# Logging
LOG_LEVEL=INFO

# Scraping
MAX_RETRY_TIMES=3
DOWNLOAD_TIMEOUT=30
```

---

## 🗑️ Superfluous Files (Safe to Delete)

The following files in the root directory are leftover documentation/testing files and can be safely deleted:

### Development/Testing Files (Delete These)
- `BUG_FIXES_SUMMARY.md` - Development notes
- `CLI_QUICK_REFERENCE.md` - Draft CLI docs (info now in README)
- `DETAILED_CHANGES.md` - Development changelog
- `FIXES_APPLIED.md` - Development notes
- `NEXT_STEPS.md` - Development TODO
- `QUICK_FIX_SUMMARY.txt` - Development notes
- `README_FIXES.md` - Draft README notes
- `TESTING_GUIDE.md` - Developer testing notes
- `TEST_PLAN.md` - Developer testing notes
- `VERIFICATION_CHECKLIST.md` - Development checklist
- `WORK_COMPLETED.txt` - Development notes
- `comprehensive_test.py` - Test script (use pytest instead)
- `quick_verification.py` - Test script
- `test_filtering.py` - Test script
- `test_genres.py` - Test script
- `test_import.py` - Test script
- `test_regex_fix.py` - Test script
- `verify_all_criteria.py` - Test script

### Files to Keep
- `README.md` - Main documentation (replace with this version)
- `requirements.txt` - Dependencies (ESSENTIAL)
- `scrapy.cfg` - Scrapy config (ESSENTIAL)
- `.env.example` - Environment template
- `.gitignore` - Git configuration
- `startup.sh` - Optional startup script

### Directories
- `test_output/` - Can be deleted (test outputs)
- `tests/` - Keep (contains official test suite)
- `logs/` - Keep but can clear `logs/aoty_crawler.log` if it gets large
- `data/output/` - Keep (contains your scraped data)

**Quick cleanup command:**
```bash
# Delete all the superfluous markdown and test files
rm -f BUG_FIXES_SUMMARY.md CLI_QUICK_REFERENCE.md DETAILED_CHANGES.md \
      FIXES_APPLIED.md NEXT_STEPS.md QUICK_FIX_SUMMARY.txt \
      README_FIXES.md TESTING_GUIDE.md TEST_PLAN.md \
      VERIFICATION_CHECKLIST.md WORK_COMPLETED.txt \
      comprehensive_test.py quick_verification.py test_filtering.py \
      test_genres.py test_import.py test_regex_fix.py verify_all_criteria.py

# Delete test output directory
rm -rf test_output/
```

---

## 📝 Examples

### Example 1: Build a 2024 indie rock collection
```bash
# Scrape indie rock albums from 2024
python -m cli scrape --genre indie-rock --year 2024 --max-items 100

# Launch UI to explore
python ui/launch.py
```

### Example 2: Find hidden gems
```bash
# Scrape albums, then search in CLI
python -m cli scrape --year 2023 --max-items 200
python -m cli search --min-score 75 --max-user-reviews 100
```

### Example 3: Multi-genre discovery
```bash
# Scrape different genres
python -m cli scrape --genre electronic --year 2024 --max-items 50
python -m cli scrape --genre hip-hop --year 2024 --max-items 50
python -m cli scrape --genre jazz --year 2024 --max-items 50

# Explore in Streamlit - filter by multiple genres
python ui/launch.py
```

---

## 🤝 Contributing

This is a personal project, but suggestions and bug reports are welcome!

1. Check existing issues
2. Create a detailed bug report or feature request
3. Include Python version, OS, and error messages

---

## ⚖️ Legal & Ethics

- **Personal use only** - This scraper is for personal music discovery
- **Respectful scraping** - Built-in rate limiting and robots.txt compliance
- **No commercial use** - Data is for personal analysis only
- **Attribution** - Data belongs to AlbumOfTheYear.org

---

## 📞 Support

### Quick Checklist
- [ ] Python 3.10+ installed?
- [ ] Virtual environment activated?
- [ ] Both `requirements.txt` and `ui/requirements.txt` installed?
- [ ] Google Chrome installed?
- [ ] Running commands from project root directory?
- [ ] Data scraped before launching UI?

### Still Having Issues?

1. **Check logs:** `logs/aoty_crawler.log`
2. **Check Python version:** `python --version` (must be 3.10+)
3. **Check installed packages:** `pip list`
4. **Check data exists:** `ls data/output/`
5. **Try a minimal scrape:** `python -m cli scrape --year 2024 --max-items 5`

---

## 🚀 Quick Start TL;DR

```bash
# 1. Setup
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows
pip install -r requirements.txt
pip install -r ui/requirements.txt

# 2. Scrape some data
python -m cli scrape --year 2024 --max-items 50

# 3. Launch dashboard
python ui/launch.py
```

---

## 📜 License

Personal Use - See LICENSE file

---

## 🎵 Happy Music Discovery!

Built with ❤️ for music lovers who want more control over their album discovery.
