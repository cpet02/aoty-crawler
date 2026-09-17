# Radius — album similarity by fingerprint

Give it one album you like. It builds a **fingerprint** of that record,
gathers the albums in its neighbourhood, fingerprints those too, and ranks
them by distance from the seed.

**No scraping, and no API key required.** Three keyless JSON APIs —
MusicBrainz, ListenBrainz and Wikipedia — read through a disk cache, each held
below the rate it publishes. No HTML parsed, no robots.txt to worry about, and
no critic scores anywhere.

Last.fm is supported as an **optional** fourth source. Set `LASTFM_API_KEY` and
its crowd tags are merged into the tag vectors, which roughly doubles their
depth and is the difference between a workable `mood` axis and a thin one.
Leave it unset and everything still runs.

```bash
pip install -r ../requirements.txt
python -m radius "Bon Iver - For Emma, Forever Ago"
```

Or open the Streamlit app and click **🧭 Similar**.

## The fingerprint

Sixteen axes. Fourteen are on by default; the two marked *off* are wired up
but not weighted.

| Axis | What it measures |
|---|---|
| `genre` | the part of the tag vector the genre taxonomy recognises |
| `mood` | the rest of it — "melancholic", "mysterious", "hypnagogic" |
| `lineage` | the *artist's* tag vector: a scene and a pedigree |
| `neighbours` | overlap of ListenBrainz similar-artist sets — listener behaviour, not vocabulary |
| `co_tagging` | how many of the seed's own neighbourhoods independently surfaced it |
| `reach` | log10 distinct listeners |
| `devotion` | listens per listener — cult records run high here and low on reach |
| `canonicity` | this album's share of its artist's audience: calling card vs deep cut |
| `era` | release year |
| `scale` | runtime and track count |
| `pacing` | mean track length and how uneven it is |
| `definition` | entropy of the tag distribution: how easy the record is to place |
| `origin` | artist's country, and band vs solo |
| `career` | years into the artist's career when the record landed |
| `prose` *(off)* | bag-of-words over the Wikipedia article — see below |
| `titling` *(off)* | mean words per track title |

Tags come from MusicBrainz, merged with Last.fm's when a key is configured:
each source is normalised to 0..1 by prominence and the stronger claim wins,
so MusicBrainz's precise genre calls keep full weight while Last.fm fills in
the mood vocabulary it never had a word for. *Spiderland* goes from four tags
to ten this way — `slowcore`, `noise rock`, `spoken word` appear — and its
candidate pool grows from 342 to 480.

Tag weights come from MusicBrainz vote counts, rescaled per album, so tags
arrive ordered by prominence — which is what separates a genre from its
subgenre. Those weights are then scaled by inverse document frequency
**across the candidate pool**, so "rare" means rare in this neighbourhood,
and by a taxonomy bonus that favours subgenres over broad roots.

An axis with no data on either side is **dropped from the average**, not
scored as a match. Unknown is not the same as identical, and each result
reports how many axes it was actually judged on.

### Why `prose` is off

The idea is good and the plumbing works: MusicBrainz → Wikidata → Wikipedia,
all batched. The data isn't. Album article ledes are boilerplate — "the
fourth studio album by the Scottish band, released on…" — so the shared
vocabulary between two articles reflects how Wikipedia writes about albums,
not what the albums are like. Measured against *Spiderland*, **Lemonade**
scored a closer prose match than **Mogwai** did. It stays in the codebase
because a better text source would redeem it, but it is not switched on while
it ranks worse than nothing. Turn it up with `--weight prose=1` if you want
to experiment.

## Tuning

```bash
python -m radius --list-axes                       # axes and default weights
python -m radius "Radiohead - Kid A" --radius 0.35 # tighter neighbourhood
python -m radius "Slint - Spiderland" --weight mood=1.5 --weight genre=0.4
python -m radius "Talk Talk - Laughing Stock" --only genre mood neighbours
python -m radius "Duster - Stratosphere" --obscurity more_obscure --lateral
```

* `--radius` 0..1 — how far from the seed to reach. 0.3 tight, 0.7 loose.
* `--pool` how many candidates get fully fingerprinted. Higher is better and
  cheap, since fingerprints are fetched in batches.
* `--lateral` same broad genre, but favour subgenres the seed doesn't have.
* `--obscurity more_obscure | better_known` relative to the seed's audience.
* `--per-artist N` how many albums one artist may occupy (default 2). Without
  a cap, a single close neighbour returns its whole discography.
* `--no-crowd-tags` ignore the Last.fm key for this run.
* `--no-enrich` skip tracklists (drops the shape axes, saves a second per result).
* `--json` / `--csv` to write results out.

## Cost and caching

A cold run at the default pool of 120 is roughly 70–90 requests — most of the
work happens in ListenBrainz's bulk endpoints, which return metadata and
listen counts for 25 albums at a time, so fingerprinting is about ten calls
rather than several hundred. The slow part is MusicBrainz at its published
one request per second, used for tag searches and for finalists' tracklists.

Everything lands in `data/cache/radius.sqlite`, keyed by request, so
re-running the same seed is nearly free and neighbouring seeds reuse most of
it. Rate limits live in `config.py`; set `RADIUS_CONTACT` to your own address
or repo so these services can reach you if a run ever misbehaves.

## Known limits

* **MusicBrainz tags are sparse** — a well-known album might carry eight tags
  where Last.fm has eighty, and an obscure one may carry none, in which case
  it falls back to its artist's tags at reduced weight or is skipped. Setting
  `LASTFM_API_KEY` largely fixes this, and the `mood` axis in particular.
* **Listener counts are ListenBrainz's**, a smaller population than a major
  streaming service, so `reach` is best read as a relative ranking.

## Layout

| File | Role |
|---|---|
| `clients.py` | rate-limited, cached HTTP for MusicBrainz, ListenBrainz, Wikipedia |
| `cache.py` | SQLite response cache |
| `tags.py` | tag cleaning, prominence, idf, taxonomy depth |
| `text.py` | bag-of-words over article prose |
| `albums.py` | the `AlbumFeatures` fingerprint and how it's assembled |
| `candidates.py` | who is worth scoring at all |
| `similarity.py` | the axes and the distance function |
| `engine.py` | `find_similar()` — the whole pipeline |
| `cli.py` | `python -m radius` |
| `taxonomy.py` | vendored static genre hierarchy (offline data) |

`radius/` imports nothing from `aoty_crawler/` and needs no scraped data.
`tests/test_radius.py` runs the entire pipeline against stub clients, so the
suite needs no network.
