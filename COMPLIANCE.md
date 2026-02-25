# Compliance

**AOTY Crawler — Ethical Scraping Compliance**
Last updated: February 2026

This document explains how AOTY Crawler is designed to scrape responsibly and what users are expected to do to remain compliant.

---

## robots.txt Compliance

AOTY Crawler respects `robots.txt` by default via Scrapy's built-in `RobotsTxtMiddleware`. The setting `ROBOTSTXT_OBEY = True` is hardcoded in `aoty_crawler/settings.py` and should not be disabled.

On every run, the spider fetches and parses `https://www.albumoftheyear.org/robots.txt` before making any content requests. URLs disallowed by robots.txt are not crawled.

---

## Rate Limiting

The following defaults are set in `aoty_crawler/settings.py`:

| Setting | Value | Purpose |
|---|---|---|
| `DOWNLOAD_DELAY` | 3 seconds | Minimum pause between requests |
| `RANDOMIZE_DOWNLOAD_DELAY` | True | Adds jitter (0.5x–1.5x delay) to avoid patterns |
| `CONCURRENT_REQUESTS` | 1 | One request at a time |
| `CONCURRENT_REQUESTS_PER_DOMAIN` | 1 | One request per domain |
| `AUTOTHROTTLE_ENABLED` | True | Backs off automatically under load |

These settings intentionally keep throughput lower than a typical human browser session. Do not increase `CONCURRENT_REQUESTS` or reduce `DOWNLOAD_DELAY` below 2 seconds for any sustained scraping session.

---

## Data Scope

This tool only accesses **publicly visible pages** — pages that any anonymous visitor to AlbumOfTheYear.org can load in a browser without logging in. It does not:

- Access any authenticated or member-only content
- Submit forms or interact with the site in ways that modify data
- Scrape user profiles, private lists, or any non-public content
- Follow or interact with any user-generated content beyond public album pages

---

## Data Storage and Use

Scraped data is stored locally on the user's machine in `data/output/`. This project does not:

- Transmit scraped data to any external server
- Provide any hosted service using scraped data
- Publish or redistribute scraped data

Users are responsible for how they store and use the data they collect. Bulk redistribution of scraped content is not permitted under these compliance guidelines.

---

## User Agent

The spider identifies itself with a descriptive User-Agent string:

```
AOTY-Production-Spider/1.0 (Music Data Collection)
```

This is intentionally non-deceptive. The crawler does not impersonate a standard browser.

---

## Legal Basis

Web scraping of publicly accessible content has been upheld in several jurisdictions (notably *hiQ Labs v. LinkedIn*, 9th Circuit, 2022) when the data is publicly visible and the scraping causes no harm to the target service. However, the legal landscape varies by jurisdiction and the target site's own terms.

**Users are solely responsible for ensuring their use of this tool complies with:**

- AlbumOfTheYear.org's Terms of Service
- Applicable laws in their jurisdiction (including the Computer Fraud and Abuse Act in the US, and equivalent legislation elsewhere)
- GDPR or other data protection regulations if collecting or processing data about individuals

This project is intended for personal, non-commercial research only. Any commercial use is outside the intended scope and may carry additional legal risk.

---

## Reporting Concerns

If you believe this tool is being used in a manner that violates these guidelines, or if you represent AlbumOfTheYear.org and have concerns about this project, please open an issue or contact the author directly through GitHub:

https://github.com/cpet02/aoty-crawler/issues
