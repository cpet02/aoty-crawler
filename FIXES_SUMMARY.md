# AOTY Crawler Bug Fixes Summary

## Bugs Fixed

### 1. **Genre Selection Tab Always Overrides to Browse** (UI Bug)
**Root Cause**: In `app.py`, `st.session_state.scrape_genre_tab` was being set inside both `with tab1:` and `with tab2:` blocks. Streamlit renders all tab blocks on every re-run, so `tab2`'s block always ran after `tab1`'s and overwrote the value to `'hierarchy'`.

**Solution**: Replaced tab-based approach with radio button approach:
- Removed session state tracking for tabs
- Used `selection_mode = st.radio("Genre selection mode", ["🔍 Search", "📂 Browse"], horizontal=True)`
- Simplified logic to use either search or browse mode based on radio selection

**File**: `ui/app.py`

### 2. **Spider Scraping Wrong Genres** (Scraper Bug)
**Three Compounding Problems**:

#### Problem A: `genre.php` returns 403 Forbidden
The genre.php endpoint is protected and returns 403 inconsistently.

#### Problem B: Substring matching catches everything with "pop" in the name
The substring match `target_genre_lower in genre_slug_lower` caused "pop" to match "toypop", "hypnagogic pop", "dream pop", etc.

#### Problem C: CLI conditionally skips passing parameters
The CLI only passed `years_back` if it wasn't 1, and only passed `albums_per_year` if it wasn't 250, causing the spider to fall back to defaults.

**Solutions**:

#### Solution A: Bypass `genre.php` entirely when target genre is specified
Modified `start_requests()` in `production_spider.py` to construct URLs directly from genre name:
```python
if self.target_genre:
    slug = self.target_genre.lower().replace(' ', '-')
    for year in range(self.start_year, self.end_year - 1, -1):
        url = f"https://www.albumoftheyear.org/ratings/user-highest-rated/{year}/{slug}/"
        yield scrapy.Request(url=url, callback=self.parse_ratings_page, ...)
```

#### Solution B: Fix substring matching to exact matching
Changed loose substring matching to exact matching in `parse_genre_page()`:
```python
# OLD (problematic):
matches = (target_genre_lower in genre_slug_lower or target_genre_lower in genre_name_lower)

# NEW (fixed):
matches = (
    genre_slug_lower == target_genre_lower.replace(' ', '-') or
    genre_slug_lower == target_genre_lower.replace('-', ' ').replace(' ', '-') or
    genre_name_lower == target_genre_lower
)
```

#### Solution C: Always pass parameters unconditionally
Modified `cmd_scrape()` in `cli/main.py` to always pass parameters:
```python
# Always pass years_back and albums_per_year
spider_kwargs['years_back'] = args.years_back
spider_kwargs['albums_per_year'] = args.limit if args.test_mode else args.albums_per_year
```

## Files Modified

1. **`ui/app.py`** - Fixed genre selection UI
2. **`aoty_crawler/spiders/production_spider.py`** - Fixed spider logic
3. **`cli/main.py`** - Fixed CLI parameter passing

## Testing

The fixes ensure:
1. Users can reliably select genres using either search or browse mode
2. When scraping a specific genre (e.g., "Pop"), the spider will only scrape that genre, not related genres
3. Parameters from the UI are correctly passed to the spider
4. The spider bypasses the problematic `genre.php` endpoint when a specific genre is selected

## How to Verify

1. **UI Test**: Run the Streamlit UI and verify genre selection works correctly with both search and browse modes
2. **Spider Test**: Run a scrape for "Pop" genre and verify it doesn't scrape "toypop", "hypnagogic pop", etc.
3. **CLI Test**: Verify parameters are correctly logged when starting a scrape

## Notes

- The spider still uses `genre.php` when scraping ALL genres (no target genre specified)
- The exact matching logic handles variations like "hip-hop" vs "hip hop" vs "Hip Hop"
- Special characters in genre names (like "&", "/", "'") are preserved in slug generation