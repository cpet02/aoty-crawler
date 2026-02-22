# Testing Guide - AOTY Crawler Fixes

## Quick Test Commands

### Test 1: Basic Functionality (5 minutes)
```bash
python -m cli scrape --test-mode --limit 2
```

**What to verify:**
- ✓ No errors during execution
- ✓ At least 2 albums are scraped
- ✓ Each album has:
  - Title (not None)
  - Artist name (not None)
  - URL (not None)
  - Scraped timestamp

**Expected output:**
```
Starting AOTY Crawler...
Test mode: limiting to 2 items per year
Starting scraping process...
[Album 1] Parsing: https://www.albumoftheyear.org/album/...
  ✓ Extracted: [Album Title] by [Artist Name]
  Total albums scraped: 1
[Album 2] Parsing: https://www.albumoftheyear.org/album/...
  ✓ Extracted: [Album Title] by [Artist Name]
  Total albums scraped: 2
Scraping completed!
```

---

### Test 2: Genre Filtering (5 minutes)
```bash
python -m cli scrape --genre rock --test-mode --limit 1
```

**What to verify:**
- ✓ Only rock albums are scraped
- ✓ Album has genre tag "rock" or similar
- ✓ All data fields are populated

**Expected output:**
```
Starting AOTY Crawler...
Scraping genre: rock
Test mode: limiting to 1 albums per year
...
Found genre: Rock (slug: rock)
  → Year 2026: https://www.albumoftheyear.org/ratings/user-highest-rated/2026/rock/
Parsing ratings page: Rock - 2026
Found 10+ album links on this page
Will scrape 1 albums from this page
[Album 1] Parsing: https://www.albumoftheyear.org/album/...
  ✓ Extracted: [Album Title] by [Artist Name]
```

---

### Test 3: Spider Direct Execution (3 minutes)
```bash
python -m cli crawl production
```

**What to verify:**
- ✓ No NameError or ImportError
- ✓ Spider starts and begins scraping
- ✓ Can be stopped with Ctrl+C

---

### Test 4: Data Extraction Verification (10 minutes)

Run a test scrape and check the output JSON file:

```bash
python -m cli scrape --test-mode --limit 1 --output-dir ./test_output
```

Then examine `test_output/albums_*.json`:

```bash
# On Windows
type test_output\albums_*.json

# On Linux/Mac
cat test_output/albums_*.json
```

**Verify each album has:**
```json
{
  "url": "https://www.albumoftheyear.org/album/...",
  "title": "Album Title",
  "artist_name": "Artist Name",
  "release_date": "Month Day, Year",
  "critic_score": 85.5,
  "user_score": 82.3,
  "critic_review_count": 45,
  "user_review_count": 123,
  "genres": ["Rock", "Alternative"],
  "cover_image_url": "https://...",
  "scraped_at": "2024-01-15T10:30:45.123456",
  "aoty_id": "12345-album-title"
}
```

**Critical fields to check:**
- ✓ `title` - NOT null/empty
- ✓ `artist_name` - NOT null/empty
- ✓ `release_date` - NOT null/empty (this was broken before)
- ✓ `critic_review_count` - NOT null (this was broken before)
- ✓ `user_review_count` - NOT null (this was broken before)
- ✓ `genres` - NOT empty list

---

## Detailed Test Scenarios

### Scenario 1: Regex Pattern Verification

**Test:** Release date extraction

```bash
python -m cli scrape --test-mode --limit 1 --output-dir ./test_output
```

**Check:** In the JSON output, verify `release_date` is populated
- ✓ Format should be: "Month Day, Year" (e.g., "January 15, 2024")
- ✓ Should NOT be null
- ✓ Should NOT be empty string

**Why this matters:** The regex fix changed `\\s` to `\s` and `\\d` to `\d`. If this wasn't fixed, the regex wouldn't match and dates would be null.

---

### Scenario 2: CSS Selector Verification

**Test:** Genre link extraction

```bash
python -m cli scrape --genre pop --test-mode --limit 1
```

**Check:** 
- ✓ Should find "Pop" genre
- ✓ Should extract albums from pop genre
- ✓ Should NOT error with "No genres found"

**Why this matters:** The CSS selector fix removed escaped quotes. If this wasn't fixed, genre links wouldn't be found.

---

### Scenario 3: Review Count Extraction

**Test:** Numeric data extraction

```bash
python -m cli scrape --test-mode --limit 1 --output-dir ./test_output
```

**Check:** In JSON output, verify:
- ✓ `critic_review_count` is an integer (not null)
- ✓ `user_review_count` is an integer (not null)
- ✓ Both values are > 0

**Why this matters:** The regex fixes changed `\\d` to `\d`. If not fixed, these would be null.

---

### Scenario 4: CLI Stability

**Test:** All available commands

```bash
# Should not crash
python -m cli crawl html_debug
python -m cli crawl genre_test
python -m cli crawl comprehensive_album
python -m cli crawl production
python -m cli crawl production_test
```

**Check:**
- ✓ None of these commands should raise `NameError`
- ✓ None should raise `ImportError`
- ✓ Each should start the spider (or fail gracefully)

**Why this matters:** The import fixes removed non-existent spiders from the map. If not fixed, running these would crash.

---

## Regression Testing

### Test: Ensure No New Bugs

After fixes, verify:

1. **No breaking changes to API**
   ```bash
   python -m cli scrape --help
   ```
   Should show all options

2. **No performance degradation**
   ```bash
   python -m cli scrape --test-mode --limit 5
   ```
   Should complete in < 60 seconds

3. **No data loss**
   ```bash
   python -m cli scrape --test-mode --limit 1 --output-dir ./test1
   python -m cli scrape --test-mode --limit 1 --output-dir ./test2
   ```
   Both should produce identical data structure

---

## Expected Results Summary

| Test | Before Fix | After Fix |
|------|-----------|-----------|
| Basic scrape | Extracts 0 albums | Extracts N albums |
| Genre filtering | No genres found | Genres found correctly |
| Release dates | All null | Populated correctly |
| Review counts | All null | Populated correctly |
| CLI commands | NameError | Works correctly |
| Data completeness | ~30% fields | ~100% fields |

---

## Troubleshooting

### Issue: "No genres found"
- **Cause:** CSS selector still broken
- **Check:** Verify line 128 has `'a[href*="/genre/"]'` (no backslashes before quotes)

### Issue: Release dates are null
- **Cause:** Regex pattern still broken
- **Check:** Verify `_extract_release_date()` uses `\s` and `\d` (single backslash)

### Issue: Review counts are null
- **Cause:** Regex pattern still broken
- **Check:** Verify `_extract_critic_review_count()` and `_extract_user_review_count()` use `\d` (single backslash)

### Issue: NameError on CLI
- **Cause:** Invalid spider in map
- **Check:** Verify spider_map only contains: html_debug, genre_test, comprehensive_album, production, production_test

### Issue: ImportError
- **Cause:** Missing import
- **Check:** Verify imports don't include DebugSpider, TestSpider, AlbumSpider, etc.

---

## Performance Baseline

After fixes, expect:
- **Test mode (2 albums):** 30-60 seconds
- **Single genre (10 albums):** 2-5 minutes
- **Full scrape (all genres, 250 albums/year):** 30+ minutes

If significantly slower, check:
- Network connectivity
- Website responsiveness
- DOWNLOAD_DELAY setting (default: 3 seconds)

---

## Sign-Off Checklist

- [ ] Test 1: Basic functionality passes
- [ ] Test 2: Genre filtering passes
- [ ] Test 3: Spider execution passes
- [ ] Test 4: Data extraction complete
- [ ] Scenario 1: Release dates populated
- [ ] Scenario 2: Genres extracted
- [ ] Scenario 3: Review counts populated
- [ ] Scenario 4: CLI stable
- [ ] No regressions detected
- [ ] Performance acceptable

Once all checks pass, the fixes are verified and ready for production use.
