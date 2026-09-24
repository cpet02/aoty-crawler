# Radius

Name an album. Radius finds the records most deeply connected to it, and
shows every statistic behind the verdict.

Not "sounds a bit alike": connected. By the people who made it (a member's
side project, the band a producer went on to record), by the production
circle (same engineer, same studio, same label), by the listeners who play
its tracks alongside others, by the scene it came from, and then by the
whole descriptive profile of each record laid side by side: tags, audience,
devotion, era, runtime, tempo, loudness, critic scores, collector demand.

```bash
python -m radius "Slint - Spiderland"
python -m radius "Slint - Spiderland" "Talk Talk - Laughing Stock"   # blend two seeds
python ui/launch.py                                                  # the app
```

**No API key required.** Radius reads five keyless JSON APIs, MusicBrainz,
ListenBrainz, Wikidata, Deezer and Discogs, through a disk cache at a rate
below what each service asks for. A Last.fm key and Discogs credentials are
optional and purely additive. Nothing is scraped.

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Streamlit](https://img.shields.io/badge/streamlit-1.x-red.svg)](https://streamlit.io/)

---

## Install

```bash
git clone https://github.com/cpet02/aoty-crawler.git
cd aoty-crawler
python -m venv venv
venv\Scripts\activate            # macOS/Linux: source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env             # then paste your keys into .env
```

`.env` is the only setup. Fill in `LASTFM_API_KEY`, `DISCOGS_CONSUMER_KEY`
and `DISCOGS_CONSUMER_SECRET` (see [Configuration](#configuration)), or
leave any of them blank to run without that service's extras. It is
gitignored, so each machine keeps its own copy.

Python 3.10 or newer. The first run of a seed takes a few minutes, because
MusicBrainz is held to one request per second and the deep lookups ask it
about every shortlisted record; every response is cached, so the same seed
again, or a neighbouring one, takes seconds.

## The app

```bash
python ui/launch.py            # http://localhost:8501
```

* **Find.** Type `Artist - Album`. If MusicBrainz has several matches you
  pick the one you meant. Up to four seeds can be blended into one
  fingerprint. Results are cards: match bar, a *connected* badge when a real
  connection fired, the three strongest reasons, and the key statistics.
  Every card can become the next seed, join the blend, or be saved.
* **Compare.** Seed and match side by side: every statistic in one table,
  every axis as a bar, every reason.
* **Filters** narrow the current result without re-running: year, runtime,
  country, band or solo, audience size, "only connected".
* **Fine-tuning** exposes every axis weight and every engine knob. Hover a
  slider's name for what it does; five presets (Sound, People, Listeners,
  Era & place, Stature) and a reset button set them in one click.
* **Library.** Saved and rated records, seedable alone or blended. The old
  ratings and bookmarks are imported once.
* **Every statistic** is one table under the results, with CSV and JSON
  export.

## How it works

1. **Resolve** the seed to a MusicBrainz release group and fingerprint it in
   full: tags, personnel, credits, canonical tracklist, audience, fans,
   critic scores.
2. **Gather** the neighbourhood from seven sources: MusicBrainz tag searches
   and tag conjunctions, ListenBrainz's collaborative similar artists, the
   seed artist's personnel graph (members' other bands, side projects,
   aliases), the recordings listeners play alongside the seed's own tracks,
   and, with a key, Last.fm's similar artists and tag charts. Typically
   400 to 700 candidates.
3. **Fingerprint in bulk.** ListenBrainz returns metadata and listen counts
   for 25 albums per request, so the pool costs a handful of calls. Listener
   kinship and crowd tags are added, everything is scored once, and a
   shortlist survives.
4. **Trace the connections.** For the shortlist only, the deep MusicBrainz
   lookups: who played, who produced, where, on what label, how many
   editions. Rescore, keep the top N.
5. **Gather the statistics** for the finalists: Deezer fans, BPM and
   loudness, Wikidata critic scores and producers, Last.fm listeners,
   Discogs styles and want/have, the artist's whole catalogue. Rescore
   again.

Services are independent, so each stage runs one worker thread per
service; MusicBrainz stays serial at 1 rps. Design detail, the interface
contract and every verified API quirk live in [docs/](docs/).

## The fingerprint

Nineteen axes in five groups. Distance is a weighted mean over the axes
measurable for both records; an axis with no data on either side is dropped,
never guessed. Three axes are *evidence*: they only pull when there is an
overlap, because not sharing a producer says nothing while sharing one says
a lot.

| Group | Axes |
|---|---|
| Sound | genre, mood, definition (how easy the record is to place) |
| Connection | **personnel**, **circle** (producers, engineers, studios, labels), **co-listening**, kinship (similar-artist overlap), lineage (the artist's own tags), convergence (how many sources surfaced it) |
| Reception | reach (ListenBrainz, Deezer and Last.fm audiences), devotion (listens per listener), canonicity (share of the artist's audience), acclaim (off by default: Wikidata review scores are sparse) |
| Shape | era, scale (runtime, tracks), pacing (mean track length and how uneven), energy (BPM, loudness) |
| Provenance | origin (country, band or solo), career stage |

```bash
python -m radius --list-axes
python -m radius "Radiohead - Kid A" --weight personnel=1.5 --weight era=0
python -m radius "Duster - Stratosphere" --only kinship co_listening personnel
```

## CLI

```
python -m radius SEED [SEED ...]

  --mode closest|sideways|deep_cuts   sideways: same broad genre, corners the seed
                                      is not in; deep_cuts: less heard than the seed
  -n, --top N          results (25)          --pool N       candidates fingerprinted (150)
  --shortlist N        deep-checked (1.5x N) --per-artist N albums per artist (1)
  --weight AXIS=V      override a weight     --only AXIS..  score on these alone
  --include-same-artist  --include-non-studio  --no-crowd-tags  --discogs  --no-deep
  --radius X           optional distance cap --explain      every axis and statistic
  --json PATH  --csv PATH  --quiet
```

A seed is `"Artist - Album"`, `mbid:<release-group id>`, or free text.

## Measuring changes

`python -m radius.eval` runs a curated golden set (twelve seeds, the artists
any listener would expect nearby) through the live engine and reports hits
at N and mean reciprocal rank per seed. `--save` and `--compare` diff a
baseline, so a tuning change is a number, not an impression.

```bash
python -m radius.eval --compare docs/eval_baseline.json
```

The committed baseline, twelve seeds at 25 results each:

| | |
|---|---|
| Hit rate, mean over seeds | 0.366 |
| Mean reciprocal rank | 0.917 |

Read the hit rate against its ceiling: the golden sets name 20 to 32 artists
each, results are capped at 25 and at one album per artist, so no run can
score 1.0 on the larger sets. Mean reciprocal rank near 1 says the first
result is nearly always an artist you would have named yourself. Strongest
seed: Miles Davis at 15 of 24. Weakest: Talk Talk at 5 of 24.

## Configuration

Everything in `.env.example`. The one worth setting is `RADIUS_CONTACT`:
each service asks to be told who is calling, and that courtesy is what
keeps these APIs open. `LASTFM_API_KEY` thickens the tag vectors (mood
vocabulary above all) and adds two candidate sources.
`DISCOGS_CONSUMER_KEY` and `DISCOGS_CONSUMER_SECRET`, from an app registered
at discogs.com/settings/developers, raise Discogs' rate from 25 to 60
requests a minute and switch Discogs statistics on by default; without them
they are one checkbox away. A personal `DISCOGS_TOKEN` does the same.

Rates live in `radius/config.py`. MusicBrainz's one request per second is
their hard limit; do not raise it.

## Tests

```bash
python -m pytest tests -q
```

Fully offline: stub clients and saved API fixtures under `tests/fixtures`.

## Layout

```
radius/
  engine.py       the pipeline: Services, find_similar()
  candidates.py   the seven candidate sources
  similarity.py   the axes, weights, reasons
  albums.py       AlbumFeatures, the fingerprint
  credits.py      parsers for credits, personnel, Deezer, Wikidata, Discogs
  clients.py      rate-limited, cached clients
  workers.py      one thread per service, progress on the caller's thread
  tags.py         tag normalisation, idf, genre/mood split
  taxonomy.py     vendored genre hierarchy (root vs subgenre only)
  library.py      saved and rated albums
  eval.py         the golden set
  cli.py          python -m radius
ui/app.py         the Streamlit app
docs/             DESIGN.md, INTERFACES.md, API_NOTES.md
tests/
```

This project began as an AlbumOfTheYear scraper; that code is gone. Radius
needs nothing from it.

## License

MIT, see [LICENSE](LICENSE).
