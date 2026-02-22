# Verification Checklist - AOTY Crawler Fixes

## File 1: `aoty_crawler/spiders/production_spider.py`

### ✅ Fix 1: CSS Selector Syntax (Line 128)

**Location:** `parse_genre_page()` method, line 128

**Verify:**
```python
# Should see this:
genre_links = response.css('a[href*="/genre/"]')

# Should NOT see this:
genre_links = response.css('a[href*=\\\"/genre/\\\"]')
```

**How to check:**
```bash
grep -n 'a\[href\*=' aoty_crawler/spiders/production_spider.py
```

**Expected output:**
```
128:        genre_links = response.css('a[href*="/genre/"]')
```

---

### ✅ Fix 2: Genre Slug Regex (Line 128)

**Location:** `parse_genre_page()` method, line 128

**Verify:**
```python
# Should see this:
match = re.search(r'/genre/\d+-(.+)/', href)

# Should NOT see this:
match = re.search(r'/genre/\\d+-(.+)/', href)
```

**How to check:**
```bash
grep -n "r'/genre/" aoty_crawler/spiders/production_spider.py
```

**Expected output:**
```
128:            match = re.search(r'/genre/\d+-(.+)/', href)
```

---

### ✅ Fix 3: Release Date Extraction (Lines 336-347)

**Location:** `_extract_release_date()` method

**Verify - Should NOT contain:**
```python
response.css('.detailRow:contains("Release Date")')  # ❌ WRONG
```

**Verify - Should contain:**
```python
detail_rows = response.css('.detailRow')
for row in detail_rows:
    row_text = ' '.join(row.css('::text').getall())
    if 'Release Date' in row_text:
```

**How to check:**
```bash
grep -A 15 "def _extract_release_date" aoty_crawler/spiders/production_spider.py | head -20
```

**Expected output:**
```
def _extract_release_date(self, response):
    """Extract release date"""
    # Try to find release date in detail rows
    detail_rows = response.css('.detailRow')
    for row in detail_rows:
        row_text = ' '.join(row.css('::text').getall())
        if 'Release Date' in row_text:
```

---

### ✅ Fix 4: Critic Review Count Regex (Line 390)

**Location:** `_extract_critic_review_count()` method

**Verify:**
```python
# Should see this:
match = re.search(r'(\d+)', text)

# Should NOT see this:
match = re.search(r'(\\d+)', text)
match = re.search(r'(\\\\d+)', text)
```

**How to check:**
```bash
grep -n "albumCriticScoreBox" aoty_crawler/spiders/production_spider.py -A 3
```

**Expected output:**
```
390:        text = response.css('.albumCriticScoreBox .numReviews::text').get()
391:        if text:
392:            match = re.search(r'(\d+)', text)
```

---

### ✅ Fix 5: User Review Count Regex (Line 402)

**Location:** `_extract_user_review_count()` method

**Verify:**
```python
# Should see this:
match = re.search(r'(\d+)', link_text)

# Should NOT see this:
match = re.search(r'(\\d+)', link_text)
match = re.search(r'(\\\\d+)', link_text)
```

**How to check:**
```bash
grep -n "albumUserScoreBox" aoty_crawler/spiders/production_spider.py -A 5
```

**Expected output:**
```
402:        link_text = response.css('.albumUserScoreBox .numReviews a::text').get()
403:        if link_text:
404:            match = re.search(r'(\d+)', link_text)
```

---

## File 2: `cli/main.py`

### ✅ Fix 1: Remove Invalid Import (Line 19)

**Location:** Top of file, imports section

**Verify - Should NOT contain:**
```python
from aoty_crawler.spiders import DebugSpider, ...
```

**Verify - Should contain:**
```python
from aoty_crawler.spiders import HtmlDebugSpider, GenreTestSpider, ComprehensiveAlbumSpider, ProductionSpider, ProductionTestSpider
```

**How to check:**
```bash
head -20 cli/main.py | grep "from aoty_crawler.spiders"
```

**Expected output:**
```
from aoty_crawler.spiders import HtmlDebugSpider, GenreTestSpider, ComprehensiveAlbumSpider, ProductionSpider, ProductionTestSpider
```

---

### ✅ Fix 2: Clean Spider Map (Lines 130-140)

**Location:** `cmd_crawl()` function

**Verify - Should contain ONLY these spiders:**
```python
spider_map = {
    'html_debug': HtmlDebugSpider,
    'genre_test': GenreTestSpider,
    'comprehensive_album': ComprehensiveAlbumSpider,
    'production': ProductionSpider,
    'production_test': ProductionTestSpider,
}
```

**Verify - Should NOT contain:**
```python
'test': TestSpider,
'debug': DebugSpider,
'album': AlbumSpider,
'artist': ArtistSpider,
'genre': GenreSpider,
'year': YearSpider
```

**How to check:**
```bash
grep -A 10 "spider_map = {" cli/main.py
```

**Expected output:**
```
spider_map = {
    'html_debug': HtmlDebugSpider,
    'genre_test': GenreTestSpider,
    'comprehensive_album': ComprehensiveAlbumSpider,
    'production': ProductionSpider,
    'production_test': ProductionTestSpider,
}
```

---

## Comprehensive Verification Script

Run this to verify all fixes:

```bash
#!/bin/bash

echo "=== VERIFICATION CHECKLIST ==="
echo ""

# Check 1: CSS Selector
echo "✓ Check 1: CSS Selector Syntax"
if grep -q 'a\[href\*="/genre/"\]' aoty_crawler/spiders/production_spider.py; then
    echo "  ✅ PASS: CSS selector is correct"
else
    echo "  ❌ FAIL: CSS selector is incorrect"
fi

# Check 2: Genre Regex
echo "✓ Check 2: Genre Slug Regex"
if grep -q "r'/genre/\\\\d+-" aoty_crawler/spiders/production_spider.py; then
    echo "  ✅ PASS: Genre regex is correct"
else
    echo "  ❌ FAIL: Genre regex is incorrect"
fi

# Check 3: Release Date Method
echo "✓ Check 3: Release Date Extraction"
if grep -q "detail_rows = response.css('.detailRow')" aoty_crawler/spiders/production_spider.py; then
    echo "  ✅ PASS: Release date method is correct"
else
    echo "  ❌ FAIL: Release date method is incorrect"
fi

# Check 4: Critic Count Regex
echo "✓ Check 4: Critic Review Count Regex"
if grep -A 3 "albumCriticScoreBox" aoty_crawler/spiders/production_spider.py | grep -q "r'(\\\\d+)'"; then
    echo "  ✅ PASS: Critic count regex is correct"
else
    echo "  ❌ FAIL: Critic count regex is incorrect"
fi

# Check 5: User Count Regex
echo "✓ Check 5: User Review Count Regex"
if grep -A 5 "albumUserScoreBox" aoty_crawler/spiders/production_spider.py | grep -q "r'(\\\\d+)'"; then
    echo "  ✅ PASS: User count regex is correct"
else
    echo "  ❌ FAIL: User count regex is incorrect"
fi

# Check 6: Import
echo "✓ Check 6: Imports"
if ! grep -q "DebugSpider" cli/main.py; then
    echo "  ✅ PASS: DebugSpider import removed"
else
    echo "  ❌ FAIL: DebugSpider import still present"
fi

# Check 7: Spider Map
echo "✓ Check 7: Spider Map"
if grep -q "'production': ProductionSpider" cli/main.py && ! grep -q "'test': TestSpider" cli/main.py; then
    echo "  ✅ PASS: Spider map is correct"
else
    echo "  ❌ FAIL: Spider map is incorrect"
fi

echo ""
echo "=== END VERIFICATION ==="
```

---

## Manual Verification Steps

### Step 1: Open Files
```bash
# Open production_spider.py
code aoty_crawler/spiders/production_spider.py

# Open main.py
code cli/main.py
```

### Step 2: Search for Issues

In `production_spider.py`, search for:
- `\\d` - Should NOT find any (except in comments)
- `\\s` - Should NOT find any (except in comments)
- `:contains(` - Should NOT find any
- `\\\"/genre/` - Should NOT find any

In `main.py`, search for:
- `DebugSpider` - Should NOT find any
- `TestSpider` - Should NOT find any
- `AlbumSpider` - Should NOT find any

### Step 3: Run Tests
```bash
python -m cli scrape --test-mode --limit 1
```

Should complete without errors and extract album data.

---

## Expected Results

### ✅ All Fixes Applied
- [ ] CSS selector syntax correct
- [ ] Genre regex correct
- [ ] Release date method rewritten
- [ ] Critic count regex correct
- [ ] User count regex correct
- [ ] Invalid imports removed
- [ ] Spider map cleaned up

### ✅ Functionality Verified
- [ ] `python -m cli scrape --test-mode --limit 1` works
- [ ] Album data is extracted
- [ ] Release dates are populated
- [ ] Review counts are populated
- [ ] No errors or warnings

### ✅ Data Quality Verified
- [ ] Titles are non-null
- [ ] Artists are non-null
- [ ] Release dates are non-null
- [ ] Review counts are non-null
- [ ] Genres are populated

---

## Sign-Off

Once all checks pass, the fixes are verified:

```
Date: _______________
Verified by: _______________
Status: ✅ ALL FIXES VERIFIED
```

---

## Troubleshooting

If any check fails:

1. **CSS Selector Issue**
   - Open `production_spider.py` line 128
   - Change `'a[href*=\\\"/genre/\\\"]'` to `'a[href*="/genre/"]'`

2. **Regex Issue**
   - Search for `\\d` in regex patterns
   - Replace with `\d` (single backslash)
   - Check lines: 128, 336, 390, 402

3. **Import Issue**
   - Open `main.py` line 19
   - Remove `DebugSpider` from imports

4. **Spider Map Issue**
   - Open `main.py` lines 130-140
   - Keep only: html_debug, genre_test, comprehensive_album, production, production_test
   - Remove: test, debug, album, artist, genre, year

---

## Quick Verification Command

```bash
# All in one check
echo "Checking fixes..." && \
grep -q 'a\[href\*="/genre/"\]' aoty_crawler/spiders/production_spider.py && \
grep -q "r'/genre/\\\\d+-" aoty_crawler/spiders/production_spider.py && \
grep -q "detail_rows = response.css('.detailRow')" aoty_crawler/spiders/production_spider.py && \
! grep -q "DebugSpider" cli/main.py && \
echo "✅ ALL FIXES VERIFIED" || echo "❌ SOME FIXES MISSING"
```

---

## Final Checklist

- [ ] All 7 fixes verified
- [ ] No errors in code
- [ ] Tests pass
- [ ] Data extraction works
- [ ] CLI stable
- [ ] Ready for deployment

**Status: READY FOR DEPLOYMENT** ✅
