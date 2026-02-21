# NEXT TESTABLE STEPS

## Current Status
The test spider works but has selector issues. We need to:
1. Fix the artist selector in the test spider
2. Understand the HTML structure of AOTY pages
3. Build the genre navigation flow

## Step 1: Run HTML Debug Spider
Run this command to analyze the HTML structure:
```bash
python -m cli crawl html_debug
```

This will:
- Save HTML files to `debug_html/`
- Create analysis JSON files
- Print selector candidates to console

## Step 2: Run Genre Test Spider
Run this command to test genre navigation:
```bash
python -m cli crawl genre_test
```

This will:
1. Start at `https://www.albumoftheyear.org/genre.php`
2. Find genre links
3. Test one genre page
4. Look for "user-highest-rated" links
5. Test a ratings page

## Step 3: Test Fixed Test Spider
Run the original test to see if artist selector is fixed:
```bash
python -m cli crawl test
```

## Expected Outcomes

### From `html_debug`:
- HTML files saved in `debug_html/`
- Analysis of album page structure
- Correct selectors for:
  - Album title
  - Artist name  
  - Scores
  - Release date
  - Genres

### From `genre_test`:
- Understanding of genre page structure
- Working selector for genre links
- Path to "user-highest-rated" pages
- Album list structure on ratings pages

## Files Created

### New Spiders:
1. `html_debug_spider.py` - Analyzes HTML structure
2. `genre_test_spider.py` - Tests genre navigation

### Updated Files:
1. `test_spider.py` - Improved artist selector logic
2. `cli/main.py` - Added new spiders to CLI

## Next Steps After Testing

Once we have the correct selectors:
1. Create `AlbumSpider` with proper data extraction
2. Create `GenreSpider` to extract all genres
3. Create `YearSpider` for year-by-year navigation
4. Implement pagination logic
5. Add resume capability

## Testing Commands Summary

```bash
# Test HTML structure analysis
python -m cli crawl html_debug

# Test genre navigation
python -m cli crawl genre_test

# Test fixed artist selector
python -m cli crawl test

# List available spiders
python -m cli crawl --help
```

## Debug Output Locations
- HTML files: `debug_html/` and `debug_html/genre_test/`
- JSON analysis: Same directories
- Logs: `logs/aoty_crawler.log`
- Data output: `data/output/`