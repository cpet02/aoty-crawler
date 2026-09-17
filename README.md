# Radius

Give it one album you like and it finds albums with a similar overall
fingerprint: genre and mood tags, artist lineage, listener kinship, audience
size, listener devotion, era, runtime, pacing, origin, career stage and more.

It runs on three keyless JSON APIs — MusicBrainz, ListenBrainz and Wikipedia —
behind a disk cache. **No scraping, no robots.txt question, no critic
scores.** An optional Last.fm key thickens the tag vectors if you have one.

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Streamlit](https://img.shields.io/badge/streamlit-1.x-red.svg)](https://streamlit.io/)

---

## Try it

```bash
python -m radius "Bon Iver - For Emma, Forever Ago"
```

```bash
python -m ui.launch
```

Then name an album, confirm it's the one you meant, and pick from three modes
(Closest / Sideways / Deep cuts) plus one "how far to roam" slider. Everything
else lives under **Fine-tuning** and can be ignored forever.

---

## How it works

1. **Resolve** the seed to a MusicBrainz release-group id.
2. **Gather candidates** two ways: MusicBrainz tag searches on the seed's own
   prominent tags, and the most-played albums of ListenBrainz's collaborative
   similar artists. Typically 300–500 candidates.
3. **Prefilter** to `pool_size` (default 120) by how many independent
   neighbourhoods surfaced each album.
4. **Fingerprint in bulk** — ListenBrainz returns metadata and listen counts
   for 25 mbids per request, so the pool costs ~10 calls, not ~400.
5. **Score** by weighted distance across 16 axes, keep what is inside the
   radius, cap albums per artist, then fetch tracklists for the finalists only.

Full detail, axis table, tuning flags and request-count math: [radius/README.md](radius/README.md).

---

## Services used

| Service | Key? | Used for |
|---|---|---|
| MusicBrainz | no | catalogue, tag search, tracklists. **1 req/sec, their hard limit** |
| ListenBrainz | no | tags, listen counts, similar artists. Bulk endpoints |
| Wikipedia / Wikidata | no | article text for the (off-by-default) prose axis |
| Last.fm | **optional** | crowd tags that thicken the vectors |

The Last.fm key lives in `.env` (gitignored). It is purely additive: delete it
and everything still runs, with thinner tags. Regenerate or revoke it at
<https://www.last.fm/api/accounts> whenever you like.

A cold run against the default 120-album pool costs roughly 70–90 requests
total across those services; the UI shows the exact per-service count and
cache-hit count for every run it makes. Repeat runs of the same or a
neighbouring seed reuse the disk cache (`data/cache/radius.sqlite`) and cost
close to nothing.

---

## Stack

| Component | Purpose |
|---|---|
| [Streamlit](https://streamlit.io/) | The UI |
| [Requests](https://requests.readthedocs.io/) | Cached, rate-limited HTTP to MusicBrainz/ListenBrainz/Wikipedia/Last.fm |
| Pandas | CSV export |

---

## Requirements

- Python 3.10+
- pip

---

## Installation

```bash
git clone https://github.com/cpet02/aoty-crawler.git
cd aoty-crawler

python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

pip install -r requirements.txt
```

Copy `.env.example` to `.env` if you want to set a Last.fm key or your own
contact string:

```bash
cp .env.example .env
```

---

## Project structure

```
radius/                      # The engine — see radius/README.md
├── clients.py                # Rate-limited, cached HTTP clients
├── cache.py                  # SQLite response cache
├── candidates.py             # Candidate gathering
├── albums.py                 # AlbumFeatures fingerprint
├── similarity.py             # Axes and distance function
├── engine.py                 # find_similar() — the whole pipeline
├── cli.py                    # python -m radius
└── taxonomy.py                # Vendored genre hierarchy
ui/                           # Streamlit app
│   ├── app.py                 # The whole UI
│   └── launch.py
tests/test_radius.py          # 30 tests, offline against stub clients
data/cache/                   # Response cache (gitignored)
```

---

## Testing

```bash
python -m pytest tests/ -q
```

All 30 tests run offline against stub clients — no network, no API key
needed.

---

## License

MIT — see [LICENSE](LICENSE).
