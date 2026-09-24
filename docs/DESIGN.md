# Radius v2 — design

Mission: **given one album (or a blend of a few), find albums that are deeply
connected to it, and show every statistic we can get.** Not "sounds a bit
alike" but connected: by the people who made it, the circle it was produced
in, the listeners who pair them, the scene it came from — and then the whole
descriptive profile of each record laid side by side.

This document is the blueprint for the v2 rewrite. Every module, axis, data
source and UI element below is intended to exist exactly as described; if the
implementation diverges, update this file.

## Constraints (unchanged from v1)

* **Keyless JSON APIs first.** MusicBrainz, ListenBrainz, Wikidata, Deezer and
  Discogs all serve public data to an honest User-Agent with no key. Last.fm
  needs a key and Discogs credentials raise Discogs' rate; both are optional and
  purely additive — remove them and everything still runs.
* **Polite rates**, held per service by a spacing limiter:
  MusicBrainz 1 rps (their hard limit) · ListenBrainz 1 rps (their docs ask
  every client for at most one call a second; the client also honours the
  X-RateLimit headers) ·
  Wikidata 4 rps · Deezer 5 rps (their limit is 50 per 5 s) · Last.fm 4 rps ·
  Discogs 25/min keyless, 60/min with credentials. Verified shapes and quirks
  for every endpoint are in `docs/API_NOTES.md`.
* **Every response goes through the SQLite cache** (`data/cache/radius.sqlite`).
  One network request per fact, ever, until the TTL lapses.
* **No scraping, no HTML parsing.** The old AOTY crawler is removed entirely.
* **Offline tests.** `tests/` runs the whole pipeline against stub clients.
* Windows consoles: stdout is reconfigured to UTF-8 before printing.

## Repository layout after v2

```
radius/
  __init__.py, __main__.py
  config.py        tunables, rates, TTLs, stoplist, optional keys
  cache.py         SQLite response cache (unchanged)
  clients.py       MusicBrainzClient, ListenBrainzClient, WikidataClient,
                   DeezerClient, LastFmClient, DiscogsClient
  tags.py          normalisation, aliases, idf, genre/mood split
  taxonomy.py      vendored genre hierarchy — used ONLY for specificity and
                   root genres (lateral mode), never for the genre/mood split
  credits.py       NEW  pure functions over API payloads: canonical release
                   choice, tracklist shape, production circle, personnel graph,
                   Deezer / Wikidata / Discogs parsing
  albums.py        AlbumFeatures and its builders (from_metadata, enrichers)
  candidates.py    candidate sources and the CandidatePool
  similarity.py    axes, weights, Match, reasons
  engine.py        Services, find_similar(), stage concurrency
  library.py       NEW  bookmarks + ratings keyed by release-group mbid
  eval.py          NEW  golden set and hits@N runner
  cli.py           python -m radius
ui/app.py          rewritten: a single-purpose Radius app
ui/launch.py
tests/             test_radius.py, test_credits.py, test_library.py, ...
docs/DESIGN.md     this file
README.md          rewritten for Radius
```

Removed: `aoty_crawler/`, `cli/`, `scrapy.cfg`, `startup.sh`, `COMPLIANCE.md`,
`TERMS_OF_USE.md`, `HANDOFF.md`, `tests/test_setup.py`, `radius/text.py` and the
`prose` axis, the `titling` axis, the `local_albums` hook, `radius/README.md`
(folded into the top-level README). `requirements.txt` drops scrapy, selenium,
undetected-chromedriver and lxml.

## The fingerprint: everything we know about one album

`AlbumFeatures` (in `albums.py`) grows to hold all of this. "Stage" says when
it is filled (see Pipeline); everything is optional and an axis whose inputs
are missing on either side is dropped from the distance, never guessed.

| Field | Source | Stage |
|---|---|---|
| artist, title, mbid, artist_mbid, url, image_url, year, release_type, secondary_types | LB metadata (bulk) + MB search | S3 |
| artist_area, artist_type, artist_debut_year, artist_end_year, artist_gender, artist_links (homepage, bandcamp, wikidata, streaming) | LB metadata artist block + `rels` | S3 |
| profile (all tags), genres (genre-flagged), moods (rest), artist_profile | LB tags (`genre_mbid` marks genres) + Last.fm tags classified against the MB genre list | S3 |
| listeners, listen_count, artist_listeners | LB popularity (bulk) | S3 |
| artist_neighbours (names), artist_neighbour_mbids — full 100-wide set | LB similar-artists | S3 |
| personnel: {mbid: name} of members, side projects, collaborations, "is person" links, plus the artist itself | MB artist lookup (`inc=artist-rels`) | S4 |
| editions (release-count), release_countries, first_release_date, mb_genres, mb_rating, mb_rating_votes, wikidata_id, discogs_master_id, external links | MB release-group lookup (`inc=releases+media+url-rels+genres+tags+ratings`) | S4 |
| canonical_release_mbid, track_count, runtime_seconds, mean_track_seconds, track_length_spread, track_titles, recording_mbids, format, label(s), catalog_numbers, release_country, release_date, barcode | MB release lookup (`inc=recordings+artist-credits+labels+artist-rels+recording-level-rels+place-rels+media`) | S4 |
| circle: producers, engineers (engineer/recording/mix/mastering), performers (guests not in the artist credit), studios (place-rels), labels — each {mbid: name} | same MB release lookup | S4 |
| artist_rg_listeners (sum over the artist's release groups) → canonicity denominator | LB top-release-groups | S5 |
| fans (Deezer), explicit, deezer_label, deezer_genres, deezer_release_date, bpm_mean, bpm_spread, gain_mean (dB), deezer_id | Deezer search → album → tracks | S5 |
| lastfm_listeners, lastfm_playcount | Last.fm album.getInfo (key only) | S5 |
| critic_scores {reviewer: 0..1}, acclaim (mean), spotify_id | Wikidata entity claims (P444 review score with P447 qualifier, P1902) | S5 |
| styles (Discogs), have, want, discogs_rating, discogs_votes | Discogs master → main release (keyless; credentials raise rate). Off by default without credentials | S5 |

Derived properties: `reach` (log10 listeners), `devotion` (listens per
listener), `canonicity` (listeners / artist_rg_listeners, falling back to
artist_listeners), `definition` (normalised tag entropy), `career_stage`,
`is_studio`, `root_genres`, `subgenres`, `top_tags`, `want_ratio` (want/have).

`as_row()` emits every one of these as flat columns for the table/CSV.

## Pipeline (`engine.find_similar`)

```
S0  resolve seed(s)      MB search → release-group mbid(s); blend if several
S1  seed enrichment      everything in the table above, for the seed only
S2  candidates           six sources, merged into one CandidatePool (below)
S3  bulk fingerprint     prefilter pool → pool_size (default 150); LB metadata
                         + popularity in batches of 25; LB similar-artists per
                         distinct artist; Last.fm tags per album (key only);
                         stage-1 score; keep shortlist M = max(2·top_n, 40)
S4  shortlist enrichment MB artist lookup per distinct artist (personnel),
                         MB release-group lookup (editions, genres, rating,
                         ids), MB release lookup of the canonical edition
                         (tracklist, credits, circle); rescore; keep top_n
S5  finalist enrichment  Deezer, Wikidata, Last.fm album info, LB top-RGs
                         (canonicity), Discogs (opt); final rescore
```

**Concurrency.** Services are independent, so S4 and S5 run one worker
thread per service (MusicBrainz work stays serial on its own thread, which is
what keeps it at 1 rps). Workers never touch Streamlit; they push progress
events onto a queue and the calling thread drains it and invokes the
`progress(stage, done, total, label)` callback. A failure in one service's
enrichment is logged into `result.notes` and never sinks the run.

**Rescoring.** Every stage that adds data recomputes `compare()` for the
affected albums, so enrichment actually moves the ranking. The two-stage
retrieve-then-rerank shape means an album must first reach the shortlist on
bulk data; the candidate sources below are what get deeply connected records
into the pool in the first place.

**Radius.** There is no hard distance cutoff by default: results are the top
`top_n`. `radius` remains an optional cap in the engine and CLI.

## Candidate sources (`candidates.py`)

Each source adds `(mbid, source_label, weight)` to the pool. An album surfacing
from several independent sources scores higher on the prefilter and on the
`convergence` axis.

| Source | How | Weight per hit |
|---|---|---|
| `tag:a` | MB release-group search for each of the seed's top 3 tags, `primarytype:album`, limit 100 | tag weight × rank decay |
| `tags:a+b` | MB search for pairwise conjunctions of the seed's top 4 tags (`tag:"a" AND tag:"b"`), limit 100 — far more on-topic than any single tag | 1.4 × mean tag weight × rank decay |
| `artist:name` | LB similar artists (top 20) → each artist's top 6 release groups | (0.35 + affinity) × rank decay |

"An artist's top release groups" is `candidates.artist_albums`: ListenBrainz's own endpoint when it answers (it went auth-only in 2026), else a MusicBrainz release-group browse filtered to studio albums and EPs and ranked by ListenBrainz's keyless bulk popularity. Single-tag and conjunction searches skip root genres of the taxonomy ("rock", "electronic"), which match most of recorded music.
| `people:name` | seed artist's personnel (members, side projects, collaborations; and for each member, their other bands — one MB artist lookup per member, capped at 8) → each act's top 6 release groups | 1.2 × rank decay |
| `tracks` | seed's recordings → LB similar-recordings (top 100 overall) → LB recording metadata → release group | score-normalised, summed per release group |
| `lastfm:name` | Last.fm artist.getSimilar (key only) → artists with an mbid → top 6 release groups | 0.8 × match × rank decay |
| `lastfm_tag:a` | Last.fm tag.getTopAlbums for the seed's top 3 tags (key only), ranked by listeners → artist mbid → that artist's ListenBrainz release groups, matched by title | 1.0 × rank decay |

The seed's own release groups are dropped; other albums by the seed artist are
dropped unless `exclude_same_artist=False`. `secondary_types` from MB search
results are kept on the Candidate so live/compilation records are filtered
before any fingerprint is spent. Results default to one album per artist
(`max_per_artist=1`): the best-connected record of each act, so a strong
neighbour cannot fill the list with its discography.

## Axes (`similarity.py`)

Two kinds of axis:

* **Symmetric** — a distance in 0..1 computed whenever both sides have data.
* **Evidence** — fires only when there is overlap. It enters the weighted mean
  at distance 0 with an effective weight of `w × strength`, `strength` in
  (0, 1]. No overlap means the axis is absent, not scored 1.0: not sharing a
  producer is weak evidence of anything, sharing one is strong evidence of
  closeness.

Distance is the weighted mean over present axes; `coverage` reports what share
of the requested weight was measurable.

| Axis | Group | Kind | Default weight | Definition |
|---|---|---|---|---|
| genre | Sound | sym | 1.00 | 1 − cosine over genre-flagged tags, idf-weighted over the pool, taxonomy specificity bonus |
| mood | Sound | sym | 0.80 | same over non-genre tags |
| definition | Sound | sym | 0.10 | \|entropy_a − entropy_b\| |
| personnel | Connection | evidence | 0.90 | shared = \|P_seed ∩ P_other\|; strength = min(1, shared / 2). Before the deep lookups, a candidate that arrived through the seed's own people graph is scored at strength 0.5 (it shares a person by construction), so a member's thinly tagged side project can reach the shortlist where its real personnel is fetched |
| circle | Connection | evidence | 0.60 | strength = min(1, 1.0·shared producers/engineers + 0.7·shared studios + 0.5·shared labels) |
| co_listening | Connection | evidence | 0.50 | from the seed's similar recordings: album_hits on this album, artist_hits by this artist; strength = min(1, (album_hits + 0.4·artist_hits) / 3) |
| kinship | Connection | sym | 0.70 | 1 − min(1, weighted_jaccard(neighbour sets) / 0.3); both sets full width, each name weighted by its idf across the pool so the famous acts ListenBrainz lists next to everything count little |
| lineage | Connection | sym | 0.45 | 1 − cosine over artist tag vectors |
| convergence | Connection | sym | 0.30 | 1 − prefilter_score / max prefilter in pool |
| reach | Reception | sym | 0.30 | mean of available: \|Δlog10 LB listeners\|/2, \|Δlog10 Deezer fans\|/2, \|Δlog10 Last.fm listeners\|/2 |
| devotion | Reception | sym | 0.30 | \|Δlog2 listens-per-listener\|/2 |
| canonicity | Reception | sym | 0.15 | \|Δlog2 canonicity\|/2, where canonicity = listeners / the artist's most-listened release group (1.0 for the calling card). Not a share of the artist total: ListenBrainz maps listens to release groups far less completely than to artists, so that ratio reads everything as a deep cut |
| acclaim | Reception | sym | 0.00 (off: Wikidata review scores are sparse; shown as a stat, rankable by choice) | \|Δ mean critic score\|/0.5 |
| era | Shape | sym | 0.20 | \|Δyear\|/25 |
| scale | Shape | sym | 0.15 | mean(\|Δruntime\|/3600 s, \|Δtracks\|/14) |
| pacing | Shape | sym | 0.15 | mean(\|Δmean track length\|/240 s, \|Δspread\|/0.8) |
| energy | Shape | sym | 0.20 | mean of available: \|Δbpm\|/60, \|Δgain\|/12 dB |
| origin | Provenance | sym | 0.15 | country mismatch (2/3) + act-type mismatch (1/3) |
| career | Provenance | sym | 0.15 | \|Δyears into career\|/15 |

Removed: `prose`, `titling`, `co_tagging` (renamed `convergence`), the
`neighbours` name (now `kinship`).

`lateral` mode still subtracts a bonus for records sharing a root genre while
bringing subgenres the seed lacks; `obscurity` still filters by listeners.

### Reasons

`similarity.explain(match, seed)` returns ordered, human-readable reasons,
strongest first. Cards show the top three; the compare panel shows all.

* personnel — "David Pajo is in both" / "Brian McMahan connects them"
* circle — "both produced by Steve Albini", "both recorded at Electrical Audio", "both on Touch and Go"
* co_listening — "3 of its tracks are played alongside the seed's"
* kinship — "12 similar artists in common: Rodan, Bedhead, June of 44…"
* genre / mood — "shares post-rock, math rock, spoken word"
* lineage — "same scene: Louisville post-hardcore"
* era, origin, career, reach, devotion — "same era", "both from the US", "similar-sized cult audience"

## Multi-seed blend

`find_similar(seeds=[...])` accepts up to four seed specs. Each is resolved
and fully enriched; the blend is an `AlbumFeatures` whose tag profiles are the
element-wise mean (renormalised to peak 1), numeric fields the mean, sets the
union, and whose artist mbids are all excluded from results. Candidates are
gathered per seed and merged. The UI shows every seed card.

## Library (`library.py`)

`data/library.json`: `{key: {mbid, artist, title, year, image_url, url, saved,
saved_at, rating, rated_at, note, from_seed}}`, keyed by release-group mbid.
Legacy `data/ratings.json` and `data/bookmarks.json` entries (keyed by AOTY
ids) are imported once as `manual:<slug>` entries with `mbid: null`; the UI
resolves them to mbids lazily through MusicBrainz search when the Library view
opens. Library albums can be used as seeds ("Seed from my library"), which is
how personal taste feeds the engine.

## Evaluation (`eval.py`)

A curated golden set of seeds with artists any listener would expect nearby.
`python -m radius.eval` runs each seed through the live engine (cached after
the first run), reports hits@N and mean reciprocal rank per seed, and can save
or diff a baseline. Every tuning change is measured against it.

## CLI

```
python -m radius "Slint - Spiderland" ["Talk Talk - Laughing Stock" ...]
  --mode closest|sideways|deep_cuts   --top N   --pool N   --per-artist N
  --weight axis=value (repeatable)    --only axis [axis...]   --list-axes
  --include-same-artist  --include-non-studio  --no-crowd-tags  --discogs
  --no-deep (skip S4/S5)  --radius X  --explain  --json PATH  --csv PATH  --quiet
```

## UI (`ui/app.py`)

One app, three views, dark theme, no scraper anywhere.

* **Find** — the landing view. A search box; when the query is ambiguous, up
  to six MusicBrainz matches to pick from. Seed chips (up to four, blendable).
  Mode: Closest / Sideways / Deep cuts. Results as cards: art, title, artist,
  year, match bar, top three reasons, stat chips (listeners, country, label,
  runtime). Each card has **Compare**, **Seed**, **+ Blend**, **Save**.
  Sidebar: filters applied to the current result set without re-running
  (era range, runtime range, country, band/solo, min listeners, "only
  connected" — at least one evidence axis fired); Fine-tuning expander with
  every axis weight and the engine knobs; recent seeds.
* **Compare** — a dialog (`st.dialog`) for one result: seed vs match, every
  statistic side by side in one table (year, country, type, label, producers,
  engineers, studios, personnel in common, listeners, listens each, fans,
  canonicity, editions, runtime, tracks, mean track, spread, BPM, loudness,
  explicit, genres, moods, lineage, critic scores, Discogs want/have), then a
  per-axis bar chart of distances, then all reasons.
* **Library** — saved and rated albums, seedable, with legacy import.
* A **Table** tab under the results with every `as_row()` column and CSV/JSON
  download. An **About** expander with cache stats, which keys are set, and a
  clear-cache button.

Services are created once per process (`st.cache_resource`), so several
browser tabs share the rate limiters.
