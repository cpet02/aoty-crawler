# Handoff — Radius

Written 2026-09-16. Everything below is uncommitted working-tree state.

## What changed and why

The AOTY crawler got this project's IP blocked, and the goal shifted: instead
of scraping a site to filter a local table, **take one album you like and find
albums with a similar overall fingerprint**. That is `radius/`, a new
standalone package. The crawler still works and is untouched, but Radius needs
nothing from it — no scraped data, and not a single import from
`aoty_crawler/`.

Radius does not scrape anything. It reads documented JSON APIs through a disk
cache, one request per fact, at rates below what each service publishes.

## Try it

```bash
python -m radius "Portishead - Dummy"
```

```bash
python -m ui.launch
```

Then click **🧭 Similar**. The UI is one search box, three modes (Closest /
Sideways / Deep cuts) and one "how far to roam" slider; everything else lives
under **Fine-tuning** and can be ignored forever.

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

Full detail, axis table and tuning flags: [radius/README.md](radius/README.md).

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

## State of things

- **30 tests pass** (`python -m pytest tests/ -q`), all offline against stub
  clients. No network, no key needed.
- Verified live end to end, in both the CLI and the browser UI.
- `data/cache/radius.sqlite` holds every response fetched so far; deleting it
  costs only time, never correctness.

## Known weaknesses — read before extending

1. **`prose` is switched off and deserves to be.** The plumbing works
   (MusicBrainz → Wikidata → Wikipedia, all batched), but album article ledes
   are boilerplate, so shared wording reflects how Wikipedia writes about
   albums rather than what they sound like. Measured against *Spiderland*,
   **Lemonade** scored a closer prose match than **Mogwai**. Fixing it needs a
   better text source, not better weighting. Enable with `--weight prose=1`.
2. **Tag sparsity is the core limitation.** MusicBrainz tags are accurate but
   thin. The Last.fm key mostly fixes this; without it the `mood` axis is
   weak, which matters because mood tags are where the intangible qualities
   live.
3. **MusicBrainz's 1 req/sec is the speed floor.** It sets cold-run time,
   mostly through tag searches and finalists' tracklists. Do not raise it.
   `--no-enrich` skips tracklists if you want speed.
4. **`reach` is ListenBrainz's population**, far smaller than a streaming
   service's, so treat it as a relative ranking, not absolute popularity.
5. **Similar-artist scores carry popularity bias** — famous artists surface as
   "similar" to many things. The per-artist cap and idf mitigate it; it isn't
   fully solved.

## If you pick this up again

Good next steps, roughly in value order:

- **Seed from several albums at once** — average their fingerprints. The
  engine is already vector-based, so this is mostly plumbing in `find_similar`.
- **Save a fingerprint you liked** and reuse it as a standing filter.
- **Feed your own listening history in** — ListenBrainz can import from
  Last.fm, and `user.getTopAlbums`-style data would let Radius learn which
  axes *you* actually care about instead of using hand-set defaults.
- **Replace the prose source** with something written about the music rather
  than about its release (reviews, liner notes) to redeem that axis.
- The old rating/bookmark features in `aoty_crawler/utils/` still assume AOTY
  ids and scraped rows; they'd need rewiring to work with Radius results.

## Files

New: `radius/` (11 modules + README), `tests/test_radius.py`, this file.
Changed: `ui/app.py` (new Similar view), `README.md`, `requirements.txt`
(`requests`), `.env.example`.

Nothing is committed. `git status` shows the full set.
