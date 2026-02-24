# SCRAPE FIX - CSS Selectors are Broken

## Problem
The production_spider.py is using outdated CSS selectors:
- `.albumListRow .albumListTitle a` - returns 0 results
- The website HTML structure has changed

## Solution
Need to update the selectors in `parse_ratings_page()` method.

The correct selectors should be:
1. For album links on ratings page: `a[href*="/album/"]` (more generic)
2. Or find the actual container class by inspecting the page

## Quick Test
Run this to see what's on the page:
```bash
python -m scrapy shell "https://www.albumoftheyear.org/ratings/user-highest-rated/2026/rock/"
```

Then in the shell:
```python
# Try different selectors
response.css('a[href*="/album/"]::attr(href)').getall()
response.css('.albumList a::attr(href)').getall()
response.css('table a[href*="/album/"]::attr(href)').getall()
response.css('tr a[href*="/album/"]::attr(href)').getall()
```

## Files to Update
- `aoty_crawler/spiders/production_spider.py` - Line ~250 in `parse_ratings_page()`

Change from:
```python
album_links = response.css('.albumListRow .albumListTitle a::attr(href)').getall()
```

To something like:
```python
album_links = response.css('a[href*="/album/"]::attr(href)').getall()
```

Then filter to only album pages (not artist pages, etc)
