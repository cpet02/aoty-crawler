# AOTY Crawler - CLI Quick Reference

## Basic Usage

### Scrape All Genres
```bash
python -m cli scrape
```

### Scrape Specific Genre
```bash
python -m cli scrape --genre rock
python -m cli scrape --genre hip-hop
python -m cli scrape --genre electronic
```

### Scrape Multiple Years
```bash
python -m cli scrape --genre rock --start-year 2020 --years-back 5
# Scrapes: 2020, 2019, 2018, 2017, 2016
```

### Control Albums Per Year
```bash
python -m cli scrape --genre pop --albums-per-year 100
# Default is 250, use lower numbers for faster testing
```

### Custom Output Directory
```bash
python -m cli scrape --output-dir ./my_music_data
python -m cli scrape --output-dir /mnt/external_drive/aoty_data
```

### Test Mode (Quick Testing)
```bash
python -m cli scrape --test-mode --limit 5
# Scrapes only 5 albums, faster delays, useful for testing
```

### Resume Previous Scrape
```bash
python -m cli scrape --resume
# Automatically loads previously scraped URLs and continues
```

### List Available Genres
```bash
python -m cli list-genres
# Shows all genres available on AOTY with their slugs
```

---

## Combined Examples

### Production Scrape: 10 Years of Rock
```bash
python -m cli scrape \
  --genre rock \
  --start-year 2015 \
  --years-back 10 \
  --albums-per-year 250 \
  --output-dir ./rock_data
```

### Quick Test: 3 Years of Hip-Hop
```bash
python -m cli scrape \
  --genre hip-hop \
  --start-year 2023 \
  --years-back 3 \
  --test-mode \
  --limit 10
```

### Resume with Custom Output
```bash
python -m cli scrape \
  --genre electronic \
  --resume \
  --output-dir ./electronic_data
```

---

## Output Files

### Default Location
```
data/output/
├── albums_20260221_035842.json
├── albums_20260221_035842.csv
├── artists_20260221_035842.json
├── artists_20260221_035842.csv
├── genres_20260221_035842.json
└── genres_20260221_035842.csv
```

### Custom Location
```bash
python -m cli scrape --output-dir ./my_data
# Files go to: ./my_data/albums_*.json, etc.
```

---

## File Formats

### JSON Format
```json
[
  {
    "title": "Album Name",
    "artist_name": "Artist Name",
    "user_score": 80.0,
    "genres": ["Rock", "Alternative"],
    "scrape_genre": "Rock",
    "scrape_year": 2026,
    ...
  }
]
```

### CSV Format
```
title,artist_name,user_score,genres,scrape_genre,scrape_year,...
Album Name,Artist Name,80.0,"[""Rock"", ""Alternative""]",Rock,2026,...
```

**Note:** Lists in CSV are JSON-encoded to preserve structure

---

## Environment Variables

### Set Output Directory via Environment
```bash
export OUTPUT_DIR=/path/to/output
python -m cli scrape --genre rock
# Files will go to /path/to/output/
```

### Combine with CLI Override
```bash
export OUTPUT_DIR=/default/path
python -m cli scrape --output-dir /override/path
# Uses /override/path (CLI takes precedence)
```

---

## Troubleshooting

### CSV Files Not Created
- Check logs for error messages
- Verify output directory has write permissions
- Ensure disk space is available

### Genre Not Found
```bash
python -m cli list-genres
# Use the exact slug from the list
```

### Resume Not Working
```bash
python -m cli scrape --resume --resume-file albums_20260221_035842.json
# Specify exact file if auto-detection fails
```

### Slow Scraping
```bash
python -m cli scrape --test-mode --limit 5
# Test with fewer albums first
# Then increase --albums-per-year gradually
```

---

## Parameter Reference

| Parameter | Type | Default | Example |
|-----------|------|---------|---------|
| `--genre` | string | None (all) | `rock`, `hip-hop` |
| `--start-year` | int | 2026 | `2020` |
| `--years-back` | int | 1 | `5` |
| `--albums-per-year` | int | 250 | `100` |
| `--output-dir` | path | `data/output` | `./my_data` |
| `--test-mode` | flag | False | (no value) |
| `--limit` | int | 10 | `5` (test mode only) |
| `--resume` | flag | False | (no value) |
| `--resume-file` | path | Auto | `albums_*.json` |

---

## Performance Tips

1. **Start small:** Use `--test-mode --limit 5` first
2. **Increase gradually:** Bump up `--albums-per-year` after testing
3. **Use multiple runs:** Scrape different genres in separate commands
4. **Monitor output:** Check logs for errors or warnings
5. **Resume capability:** Use `--resume` to continue interrupted scrapes

---

## Common Workflows

### Workflow 1: Scrape Everything
```bash
# First, see what genres exist
python -m cli list-genres

# Then scrape all genres (takes hours)
python -m cli scrape

# Check output
ls -lh data/output/
```

### Workflow 2: Build Genre Collection
```bash
# Scrape rock
python -m cli scrape --genre rock --output-dir ./rock_collection

# Scrape pop
python -m cli scrape --genre pop --output-dir ./pop_collection

# Scrape electronic
python -m cli scrape --genre electronic --output-dir ./electronic_collection
```

### Workflow 3: Historical Analysis
```bash
# Scrape last 10 years of all genres
python -m cli scrape \
  --start-year 2015 \
  --years-back 10 \
  --output-dir ./historical_data

# Analyze the CSV files
# (use your favorite data tool: pandas, Excel, etc.)
```

### Workflow 4: Incremental Updates
```bash
# Initial scrape
python -m cli scrape --genre rock --output-dir ./rock_data

# Later: Resume and add more
python -m cli scrape --genre rock --resume --output-dir ./rock_data

# Or scrape newer years
python -m cli scrape --genre rock --start-year 2026 --years-back 2 --output-dir ./rock_data
```
