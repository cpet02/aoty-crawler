# AOTY Crawler - Test Plan for Fixed Issues

## 🎯 What Was Fixed
1. **CSV Export** - Now creates CSV files with proper error handling
2. **CLI Parameters** - All spider parameters now controllable from CLI
3. **Output Directory** - Can specify custom output location via `--output-dir`

---

## 🧪 Test Cases (Run These)

### TEST 1: CSV Export Works
**Command:**
```bash
cd C:\Users\chris\Documents\aoty-crawler
python -m cli scrape --test-mode --limit 2
```

**Expected Results:**
- ✅ Should complete without errors
- ✅ Should create `data/output/albums_TIMESTAMP.json`
- ✅ Should create `data/output/albums_TIMESTAMP.csv` (THIS IS NEW)
- ✅ Both files should have 2 albums
- ✅ CSV should have proper headers and data

**What to Check:**
```bash
# List files created
dir data\output\

# Check CSV file exists and has content
type data\output\albums_*.csv | head -5

# Verify CSV has headers
# Should see: title,artist_name,user_score,genres,scrape_genre,scrape_year,...
```

---

### TEST 2: Custom Output Directory
**Command:**
```bash
python -m cli scrape --test-mode --limit 2 --output-dir ./test_output
```

**Expected Results:**
- ✅ Should create `./test_output/` directory
- ✅ Should create `./test_output/albums_TIMESTAMP.json`
- ✅ Should create `./test_output/albums_TIMESTAMP.csv`
- ✅ Files should NOT be in `data/output/`

**What to Check:**
```bash
# Verify directory was created
dir test_output\

# Verify files are there
dir test_output\albums_*

# Verify data/output was NOT used
dir data\output\  # Should have old files, not new ones
```

---

### TEST 3: All CLI Parameters Work
**Command:**
```bash
python -m cli scrape \
  --genre rock \
  --start-year 2020 \
  --years-back 2 \
  --albums-per-year 50 \
  --output-dir ./param_test \
  --test-mode
```

**Expected Results:**
- ✅ Should scrape rock genre
- ✅ Should scrape years 2020 and 2019 (2 years back)
- ✅ Should limit to 50 albums per year (overridden by test mode)
- ✅ Should save to `./param_test/`
- ✅ Should log all parameters being used

**What to Check:**
```bash
# Check logs show correct parameters
# Look for lines like:
# - "Scraping genre: rock"
# - "Starting year: 2020"
# - "Years back: 2"
# - "Albums per year: 50"
# - "Output directory: ./param_test"

# Verify files were created
dir param_test\

# Check JSON to verify scrape_genre and scrape_year
# Should see "scrape_genre": "Rock" and "scrape_year": 2020 or 2019
```

---

### TEST 4: List Genres Command
**Command:**
```bash
python -m cli list-genres
```

**Expected Results:**
- ✅ Should display list of genres
- ✅ Should show genre name and slug
- ✅ Should complete without errors
- ✅ Should show 30+ genres

**What to Check:**
```bash
# Output should look like:
# 1. Rock                          (slug: rock)
# 2. Hip Hop                       (slug: hip-hop)
# 3. Electronic                    (slug: electronic)
# ... etc
```

---

### TEST 5: Resume Functionality
**Command 1:**
```bash
python -m cli scrape --genre rock --test-mode --limit 3 --output-dir ./resume_test
```

**Command 2 (after first completes):**
```bash
python -m cli scrape --genre rock --resume --test-mode --limit 3 --output-dir ./resume_test
```

**Expected Results:**
- ✅ First run: Creates 3 albums
- ✅ Second run: Skips the 3 already-scraped albums
- ✅ Should log "Already scraped" messages for skipped albums
- ✅ Should add new albums if available

**What to Check:**
```bash
# After first run
dir resume_test\
# Should have albums_TIMESTAMP1.json

# After second run
dir resume_test\
# Should have albums_TIMESTAMP1.json and albums_TIMESTAMP2.json
# Second file should have different albums (or be empty if all were already scraped)
```

---

### TEST 6: Error Handling (CSV Write Failure)
**Command:**
```bash
# Create read-only directory to trigger error
mkdir readonly_test
# Make it read-only (Windows)
attrib +r readonly_test

python -m cli scrape --test-mode --limit 1 --output-dir ./readonly_test
```

**Expected Results:**
- ✅ Should fail gracefully
- ✅ Should log error message about write permission
- ✅ Should show "Files failed: X" in summary
- ✅ Should NOT crash

**What to Check:**
```bash
# Look for error messages in logs
# Should see something like:
# "✗ Failed to write albums CSV: Permission denied"
# "Files written: 1 | Files failed: 1"
```

---

## 📊 Test Results Template

Copy this and fill in as you test:

```
TEST 1: CSV Export
- [ ] Command ran successfully
- [ ] JSON file created: YES / NO
- [ ] CSV file created: YES / NO
- [ ] CSV has headers: YES / NO
- [ ] CSV has data: YES / NO
- [ ] Data looks correct: YES / NO
Notes: _______________________________________________

TEST 2: Custom Output Directory
- [ ] Command ran successfully
- [ ] Directory created: YES / NO
- [ ] Files in correct location: YES / NO
- [ ] Files NOT in data/output: YES / NO
Notes: _______________________________________________

TEST 3: All CLI Parameters
- [ ] Command ran successfully
- [ ] Genre parameter logged: YES / NO
- [ ] Year parameters logged: YES / NO
- [ ] Albums per year logged: YES / NO
- [ ] Output dir logged: YES / NO
- [ ] Files in correct location: YES / NO
Notes: _______________________________________________

TEST 4: List Genres
- [ ] Command ran successfully
- [ ] Genres displayed: YES / NO
- [ ] Slugs shown: YES / NO
- [ ] 30+ genres listed: YES / NO
Notes: _______________________________________________

TEST 5: Resume Functionality
- [ ] First run completed: YES / NO
- [ ] Second run started: YES / NO
- [ ] Already-scraped albums skipped: YES / NO
- [ ] New albums added: YES / NO
Notes: _______________________________________________

TEST 6: Error Handling
- [ ] Error caught gracefully: YES / NO
- [ ] Error message logged: YES / NO
- [ ] Program didn't crash: YES / NO
Notes: _______________________________________________
```

---

## 🚨 If Tests Fail

### CSV Not Created
1. Check `data/output/` directory exists
2. Check file permissions
3. Look for error messages in logs
4. Try with `--output-dir ./test` to use different location

### Parameters Not Working
1. Check CLI help: `python -m cli scrape --help`
2. Verify parameter names are correct
3. Check logs for parameter values
4. Try one parameter at a time

### List Genres Fails
1. Check internet connection
2. Check if albumoftheyear.org is accessible
3. Look for network errors in logs
4. Try again (might be temporary)

### Resume Not Working
1. Verify first scrape completed
2. Check JSON files exist in output directory
3. Try with `--resume-file` to specify exact file
4. Check logs for "Already scraped" messages

---

## ✅ Success Criteria

All tests pass when:
- ✅ CSV files are created alongside JSON files
- ✅ All CLI parameters are accepted and used
- ✅ Custom output directories work correctly
- ✅ List genres command works
- ✅ Resume functionality skips already-scraped albums
- ✅ Errors are handled gracefully with clear messages

---

## 📝 Next Steps After Testing

1. **If all tests pass:**
   - Code is ready for production use
   - Can now scrape large datasets
   - Can automate scraping with custom parameters

2. **If some tests fail:**
   - Note which tests failed
   - Check error messages in logs
   - Let me know which specific test failed and the error

3. **Optional enhancements:**
   - Add `--format` to choose JSON-only or CSV-only
   - Add `--validate` to verify output data
   - Add progress tracking for long scrapes
