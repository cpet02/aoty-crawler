# Radius v2 — module interfaces

Exact names and shapes. `docs/DESIGN.md` says what and why; this file says
how the modules talk to each other so they can be written independently.
Anything not listed keeps its v1 signature. All dict keys are plain strings;
"mbid" always means a MusicBrainz id string; sets of people/labels/places are
`{mbid: name}` dicts so both matching (by mbid) and display (by name) work.

Conventions: functions never raise on missing data — they return `None`, `{}`,
`[]` or leave fields at their defaults. Only clients raise (`ApiError`), and
every caller in `engine.py` catches `ApiError` per item and appends a note.

---

## config.py (additions / removals)

```python
WIKIDATA_API_ROOT = 'https://www.wikidata.org/w/api.php'
DEEZER_API_ROOT   = 'https://api.deezer.com/'
DISCOGS_API_ROOT  = 'https://api.discogs.com/'

WIKIDATA_REQUESTS_PER_SECOND = float(os.getenv('RADIUS_WIKIDATA_RPS', '4'))
DEEZER_REQUESTS_PER_SECOND   = float(os.getenv('RADIUS_DEEZER_RPS', '5'))
DISCOGS_TOKEN                = os.getenv('DISCOGS_TOKEN', '')
DISCOGS_CONSUMER_KEY         = os.getenv('DISCOGS_CONSUMER_KEY', '')
DISCOGS_CONSUMER_SECRET      = os.getenv('DISCOGS_CONSUMER_SECRET', '')
DISCOGS_AUTHENTICATED        = bool(DISCOGS_TOKEN or (DISCOGS_CONSUMER_KEY and DISCOGS_CONSUMER_SECRET))
DISCOGS_REQUESTS_PER_MINUTE  = float(os.getenv('RADIUS_DISCOGS_RPM', '60' if DISCOGS_AUTHENTICATED else '25'))
LB_SIMILAR_RECORDING_ALGORITHM = os.getenv('RADIUS_LB_SIMILAR_RECORDING_ALGORITHM',
    'session_based_days_9000_session_300_contribution_5_threshold_15_limit_50_skip_30')
LISTENBRAINZ_REQUESTS_PER_SECOND default is 1 (their docs: never more than one call per second per application)

TTL_DAYS additions:
  'mb.rg.full': 120, 'mb.release.full': 365, 'mb.artist.full': 120, 'mb.genres': 365,
  'lb.similar.recording': 60, 'lb.metadata.recording': 120, 'wikidata.entities': 120, 'wikidata.labels': 365,
  'deezer.search': 120, 'deezer.album': 60, 'deezer.track': 365,
  'discogs.master': 180, 'discogs.release': 60,
  'lastfm.artist.similar': 90, 'lastfm.album.info': 30, 'lastfm.tag.albums': 30
Removed: WIKIPEDIA_API_ROOT, WIKIPEDIA_REQUESTS_PER_SECOND, TTL entries for
  mb.release.tracks, mb.rg.urls, wikipedia.extracts, wikidata.sitelinks.
USER_AGENT version bumps to 0.3.
```

## cache.py

Unchanged.

## clients.py

`_HttpClient` gains `extra_headers: dict = {}` merged into every request, and
`_request` treats a JSON body of the form `{"error": {...}}` (Deezer) as an
error: code 4 (quota) → back off and retry like a 429; anything else → the
method returns `None`. Every client keeps its own `requests.Session`; the
limiter lock and the cache lock make concurrent calls from several threads
safe.

```python
class MusicBrainzClient(_HttpClient):
    def search_release_groups(self, query, limit=25, offset=0) -> list[dict]   # raw 'release-groups'
    def find_album(self, artist=None, album=None, query=None, limit=10) -> list[dict]
    def release_groups_by_tags(self, tags, limit=100, primary_type='album') -> list[dict]
        # query: tag:"a" AND tag:"b" [AND primarytype:album]; one tag is fine
    def release_group(self, mbid) -> dict      # inc=releases+media+url-rels+genres+tags+ratings+artist-credits
    def release(self, mbid) -> dict            # inc=recordings+artist-credits+labels+artist-rels+recording-level-rels+place-rels+media+release-groups
    def artist(self, mbid) -> dict             # inc=artist-rels+url-rels+genres+tags+ratings
    def release_groups_by_artist(self, artist_mbid, limit=100) -> list[dict]   # browse; raw 'release-groups'; namespace 'mb.rg.browse'
    def genre_names(self) -> frozenset[str]    # every MB genre name, lower-cased; cached 365 days, memoised in-process
    # removed: tracklist(), article_ref(), release_groups_by_tag()

class ListenBrainzClient(_HttpClient):
    # unchanged: metadata(), popularity(), artist_popularity(), top_release_groups(), similar_artists()
    # honours X-RateLimit-Remaining / X-RateLimit-Reset-In on api.listenbrainz.org responses (sleep when Remaining == 0)
    def similar_recordings(self, recording_mbids, algorithm=None) -> list[dict]
        # labs endpoint; the query param `recording_mbids` is REPEATED per seed (params as list of tuples), ≤ 10 seeds per call;
        # returns the flat list of raw entries {recording_mbid, recording_name, artist_credit_name, release_name, release_mbid,
        # caa_id, caa_release_mbid, score (int), reference_mbid}; [] on ApiError; guards non-JSON (HTML) error bodies
    def recording_metadata(self, recording_mbids, inc='artist release') -> dict   # {recording_mbid: raw entry}, batched 25, comma-joined

class WikidataClient(_HttpClient):            # replaces WikipediaClient
    def entities(self, qids, props='claims|labels|sitelinks') -> dict   # {qid: raw entity}, batched 50, drops entries with 'missing'
    def labels(self, qids) -> dict            # {qid: english label}; batched 50; namespace 'wikidata.labels'

class DeezerClient(_HttpClient):
    # Deezer signals errors INSIDE 200 responses: body {'error': {'code', 'message', 'type'}}; code 4 = quota → back off + retry,
    # anything else → the method returns [] / None
    def search_album(self, artist, title) -> list[dict]   # raw 'data' list; tries artist:"" album:"" then plain text
    def album(self, deezer_id) -> dict | None
    def track(self, track_id) -> dict | None

class DiscogsClient(_HttpClient):
    token: str                                # '' when keyless; sends 'Authorization: Discogs token=...' when set
    key: str, secret: str                     # consumer pair; sends 'Discogs key=..., secret=...' when both set and no token
    configured -> True                        # keyless works; credentials only raise the rate
    authenticated -> bool                     # token, or both halves of the key pair
    def master(self, master_id) -> dict | None            # params curr_abbr=USD
    def release(self, release_id) -> dict | None

class LastFmClient(_HttpClient):
    # unchanged: configured, album_tags(), artist_tags(); every list is normalised (single item dict → [dict], '' → [])
    def similar_artists(self, artist, limit=30) -> list[dict]   # [{'name': str, 'mbid': str ('' when unknown), 'match': float}]
    def tag_top_albums(self, tag, limit=50) -> list[dict]       # [{'name', 'mbid' (a RELEASE id or ''), 'artist', 'artist_mbid', 'rank': int}]
    def album_info(self, artist, album) -> dict                  # raw 'album' object, {} when unknown / no key
```

## tags.py

```python
def taxonomy_genre_names() -> frozenset[str]      # every parent and child of GENRE_HIERARCHY, normalised
def split_profile(profile, genre_names) -> tuple[dict, dict]   # (genres, moods); a tag is genre iff normalised name in genre_names
# unchanged: normalize_tag, TAG_ALIASES, is_descriptive, tag_profile, era_year, era_hint,
#            specificity, root_genres, subgenre_tags, build_idf, weighted_vector, cosine, shared_tags, hierarchy_index
```

## credits.py (new; pure functions over raw client payloads)

```python
def canonical_release_order(rg_payload) -> list[str]
    # release ids, best first: status Official > others; then |track_count − modal official track_count|;
    # then format preference CD, Digital Media, Vinyl, other; then earliest date. Empty list if none.

def release_group_facts(rg_payload) -> dict
    {'first_release_date': str, 'year': int|None, 'primary_type': str, 'secondary_types': [str],
     'editions': int, 'release_countries': [str], 'mb_genres': [str] (by count desc),
     'mb_rating': float|None, 'mb_rating_votes': int, 'wikidata_id': str, 'discogs_master_id': str,
     'links': {relation_type: url}}

def release_shape(release_payload) -> dict
    {'release_mbid', 'status', 'date', 'country', 'barcode', 'packaging', 'formats': [str],
     'disc_count': int, 'track_count': int, 'titles': [str], 'lengths_ms': [int],
     'recording_mbids': [str], 'runtime_seconds': int, 'mean_track_seconds': float,
     'track_length_spread': float}                                  # spread = coefficient of variation

def person_key(name) -> str                     # casefold, strip diacritics (NFKD), drop punctuation, collapse spaces, drop a leading 'the '
def release_circle(release_payload) -> dict
    # every people/place/label dict is keyed by person_key(name) → display name, so credits from MusicBrainz, Wikidata and
    # Discogs can be matched to each other by name; mbids are kept in 'credits' for display links
    {'labels': {key: name}, 'catalog_numbers': [str],
     'producers': {key: name}, 'engineers': {key: name},            # engineer, recording, mix, mastering, sound, audio, programming, remixer
     'performers': {key: name},                                     # performer/instrument/vocal/orchestra/conductor rels whose artist mbid is NOT in the release artist-credit
     'studios': {key: name},                                        # place-rels: recorded at, mixed at, mastered at, produced at, engineered at, remixed at (ignore 'manufactured at')
     'credits': [{'role': str, 'name': str, 'mbid': str, 'level': 'release'|'recording', 'source': 'musicbrainz'}]}
    # relations are read at release level AND under media[].tracks[].recording.relations; aggregate by artist id across tracks

def artist_personnel(artist_payload) -> dict
    {'mbid': str, 'name': str, 'type': str, 'gender': str, 'area': str, 'begin_year': int|None, 'end_year': int|None,
     'people': {mbid: {'name': str, 'relation': str, 'type': str}},   # member of band, is person, collaboration, founder,
                                                                         # subgroup, supporting musician (+instrumental/vocal), both directions
     'links': {relation_type: url}, 'mb_genres': [str], 'tags': [{'name','count'}]}

def match_deezer_album(hits, artist, title) -> dict | None      # normalised artist+title match; prefer record_type 'album'
def deezer_facts(album_payload, track_payloads=()) -> dict
    {'deezer_id': int, 'fans': int, 'explicit': bool|None, 'label': str, 'release_date': str, 'genres': [str],
     'nb_tracks': int, 'duration': int, 'url': str,
     'bpm_mean': float|None, 'bpm_spread': float|None, 'gain_mean': float|None, 'gain_spread': float|None,
     'tracks_with_bpm': int}                                       # bpm of 0 counts as missing

REVIEWER_SCALES = {'Q31181': 5, 'Q48989591': 100, 'Q150248': 100, 'Q1097006': 10, 'Q33511': 5, 'Q1044417': 10, 'Q11148': 5}
    # AllMusic /5, Album of the Year /100, Metacritic /100, Pitchfork /10, Rolling Stone /5, NME /10, The Guardian /5 — extend freely
def parse_review_score(text, reviewer_qid=None) -> float | None
    # explicit forms first: '8.7/10'→.87, '4/5'→.8, '77/100'→.77, '9 out of 10'→.9, 'A+'→1.0 'A'→.95 'A-'→.9 'B+'→.85 … 'F'→.1,
    # '★★★★'/'4 stars'/'4.5 stars' → n/5, 'favorable'/'mixed'/etc → None;
    # a bare number uses REVIEWER_SCALES[reviewer_qid] when known, else ≤5 → /5, ≤10 → /10, ≤100 → /100
def wikidata_facts(entity) -> dict
    {'critic_scores': {reviewer_qid: float}, 'acclaim': float|None, 'spotify_id': str, 'discogs_master_id': str,
     'allmusic_id': str, 'aoty_id': str, 'lastfm_id': str, 'publication_date': str, 'duration_seconds': int|None,
     'producer_qids': [str], 'label_qids': [str], 'genre_qids': [str], 'performer_qids': [str], 'enwiki_title': str}
    # P444 with qualifier P447 (skip statements carrying a P7887 aggregate qualifier from the mean but keep them in critic_scores under
    # the reviewer); skip rank 'deprecated'; qualifiers/references keys may be absent. Q-id labels are resolved by the engine via
    # WikidataClient.labels() and passed to albums.apply_wikidata(features, facts, labels)

def discogs_facts(master_payload, release_payload=None) -> dict
    {'styles': [str], 'genres': [str], 'year': int|None, 'main_release_id': int|None, 'have': int, 'want': int,
     'rating': float|None, 'rating_votes': int, 'num_for_sale': int, 'lowest_price': float|None,
     'formats': [str], 'label': str, 'country': str, 'url': str,
     'producers': {key: name}, 'engineers': {key: name}}           # from release extraartists[].role: Producer / Co-producer → producers;
                                                                    # Engineer, Mixed By, Mastered By, Recorded By, Remix → engineers (keys via person_key)

def lastfm_facts(album_payload) -> dict           # {'lastfm_listeners': int, 'lastfm_playcount': int, 'lastfm_url': str}
```

## albums.py

`AlbumFeatures` keeps every v1 field except `prose` and `mean_title_words`, and adds
(all with empty defaults):

```
artist_end_year:int|None  artist_gender:str  artist_links:dict
genres:dict  moods:dict                          # the split of `profile`; genre_profile/mood_profile properties return these
artist_neighbour_mbids:frozenset  artist_neighbours_ranked:tuple   # display names, strongest first
personnel:dict  personnel_relations:dict         # {mbid: name}, {mbid: relation label}; includes the artist itself
editions:int  release_countries:frozenset  first_release_date:str
mb_genres:list  mb_rating:float|None  mb_rating_votes:int  wikidata_id:str  discogs_master_id:str  links:dict
canonical_release_mbid:str  track_titles:list  recording_mbids:list  formats:list
labels:dict  catalog_numbers:list  release_country:str  release_date:str  barcode:str
producers:dict  engineers:dict  performers:dict  studios:dict  credits:list
artist_rg_listeners:int  artist_top_listeners:int   # summed over the artist's release groups / the biggest one (canonicity denominator)
deezer_id:int|None  fans:int  explicit:bool|None  deezer_label:str  deezer_genres:list  deezer_url:str
bpm_mean:float|None  bpm_spread:float|None  gain_mean:float|None  gain_spread:float|None  tracks_with_bpm:int
lastfm_listeners:int  lastfm_playcount:int
critic_scores:dict  acclaim:float|None  spotify_id:str
styles:list  have:int  want:int  discogs_rating:float|None  discogs_votes:int  num_for_sale:int  lowest_price:float|None  discogs_url:str
enriched:set                                     # stage tags applied: 'rg','release','artist','deezer','wikidata','discogs','lastfm_info','canonicity'
```

Properties: `key, reach, devotion, canonicity (listeners / artist_top_listeners, None until known),
definition, career_stage, has_tracklist, is_studio, root_genres, subgenres, genre_profile, mood_profile,
top_tags, want_ratio (want/have or None), label (first label name or deezer_label), producer_names, studio_names`.
`as_row()` emits one flat column per field above (dicts joined as ', '-separated names).

```python
def tag_entries(raw) -> list[dict]                 # [{'name','count','genre': bool}] — genre iff entry has 'genre_mbid'
def from_metadata(mbid, metadata, popularity=None, genre_names=None) -> AlbumFeatures | None
def enrich_tags(features, lastfm, artist_cache=None, genre_names=None) -> bool     # re-splits genres/moods afterwards
def apply_release_group(features, facts)           # facts from credits.release_group_facts
def apply_release(features, shape, circle)         # from credits.release_shape / release_circle
def apply_artist(features, personnel)              # from credits.artist_personnel
def apply_deezer(features, facts)
def apply_wikidata(features, facts, labels=None)   # labels: {qid: name}; critic_scores keyed by reviewer name when known;
                                                   # producer/label Q-ids with labels are MERGED into features.producers / features.labels
                                                   # (keyed by credits.person_key) so a Wikidata-only producer still counts for the circle axis;
                                                   # links gains 'wikidata', 'spotify', 'allmusic', 'aoty', 'lastfm' urls when ids are present
def apply_discogs(features, facts)                 # styles/have/want/rating…; producers/engineers merged into the circle dicts the same way
def apply_lastfm_info(features, facts)
def apply_artist_release_groups(features, top_release_groups)   # sets artist_rg_listeners = Σ and artist_top_listeners = max of total_user_count
def blend(features_list) -> AlbumFeatures          # multi-seed centroid (DESIGN.md "Multi-seed blend")
# unchanged: canonical_title, album_key, looks_non_studio, jaccard, merge_profiles, NON_STUDIO_TYPES
```

## candidates.py

```python
@dataclass
class SeedContext:
    neighbour_names: frozenset = frozenset()
    neighbour_mbids: frozenset = frozenset()
    similar_recordings: dict = field(default_factory=dict)    # {recording_mbid: {'score','release_group_mbid','artist_mbid'}}
    co_listening_by_rg: Counter = ...                          # release_group_mbid → weighted hits
    co_listening_by_artist: Counter = ...                      # artist_mbid → weighted hits

class Candidate: mbid, artist, title, artist_mbid, primary_type, secondary_types, weight, sources, prefilter_score
class CandidatePool: add(mbid, source, weight, artist='', title='', artist_mbid='', primary_type='', secondary_types=()), drop, get, ranked, __len__

def artist_albums(services, artist_mbid, artist_name='', cache=None, limit=25) -> list[dict]
    # the artist's studio albums/EPs most-listened first, in the ListenBrainz top-release-group shape
    # ({release_group_mbid, release_group: {name, type, secondary_types, date}, artist: {name, artist_mbid},
    # total_user_count, total_listen_count}); LB endpoint when it answers, else MB browse + LB bulk popularity
def expandable_tags(top_tags, count) -> list[str]   # the seed's tags worth searching by: roots of the taxonomy skipped
def gather(seed, services, tags_to_expand=3, conjunction_tags=4, albums_per_tag=100, similar_artists=20,
           albums_per_artist=6, personnel_acts=8, similar_recordings=100, lastfm_similar=12, lastfm_tag_albums=12,
           album_cache=None, progress=None) -> tuple[CandidatePool, SeedContext]
    # the seven sources in DESIGN.md; `seed` is already enriched (personnel, recording_mbids known)
    # lastfm_tag:<tag> source (key only): Last.fm tag.getTopAlbums for the seed's top 3 tags → each hit's artist_mbid →
    # ListenBrainz top_release_groups(artist_mbid) → the release group whose canonical_title matches the Last.fm album name
```

## similarity.py

```python
EVIDENCE_AXES = ('personnel', 'circle', 'co_listening')
class SimilarityWeights: genre, mood, definition, personnel, circle, co_listening, kinship, lineage, convergence,
                         reach, devotion, canonicity, acclaim, era, scale, pacing, energy, origin, career
                         # defaults per DESIGN.md; as_dict(), active(), axis_names(), only()
AXIS_LABELS, AXIS_GROUPS   # groups: 'Sound', 'Connection', 'Reception', 'Shape', 'Provenance'

@dataclass
class Evidence:
    convergence: float | None = None      # candidate.prefilter_score / max in pool
    album_hits: float = 0.0               # co-listening hits on this album
    artist_hits: float = 0.0              # co-listening hits by this artist
    neighbour_idf: dict | None = None     # similar-artist name -> idf across the pool (kinship weighting)
    known_personnel: float = 0.0          # provisional personnel strength (0.5 for candidates from the people graph)

def axis_distances(seed, other, seed_vectors, other_vectors, evidence=None) -> tuple[dict, dict]
    # (distances, strengths): evidence axes appear in both with distance 0.0 and strength in (0, 1]; absent when no overlap
def compare(seed, other, seed_vectors, other_vectors, weights, evidence=None, lateral_bonus=0.0, sources=()) -> Match | None

@dataclass
class Match:
    features, distance, axes: dict, strengths: dict, shared_tags: list, distinct_tags: list,
    shared_neighbours: list, shared_personnel: list[str], shared_circle: dict[str, list[str]],   # role → names
    co_listening: tuple[float, float], sources: tuple, coverage: float, reasons: list[str]
    similarity property; as_row() = features.as_row() + similarity, distance, axes_measured, reasons, shared_*, found_via, d_<axis>…

def explain(seed, other, axes, strengths, shared_neighbours, shared_personnel, shared_circle, co_listening) -> list[str]
def describe_axes(match, limit=4) -> str
```

## engine.py

```python
@dataclass
class Services: musicbrainz, listenbrainz, wikidata, deezer, lastfm, discogs
    @classmethod create(cls, cache=None, lastfm_key=None, discogs_token=None, discogs_key=None, discogs_secret=None)
    tag_enrichment: bool      discogs_enabled: bool (credentials set)      requests_made, cache_hits
    def genre_names(self) -> frozenset      # MB list ∪ taxonomy names; taxonomy alone if MB fails

class SeedNotFound(RuntimeError): suggestions
def parse_seed_text(text) -> dict           # 'Artist - Album' → {'artist','album'}; else {'query'}
def search_albums(services, artist=None, album=None, query=None, limit=10) -> list[dict]
    # [{'artist','artist_mbid','album','mbid','year','type','secondary_types','disambiguation'}]
def resolve_seed(services, spec) -> AlbumFeatures            # spec: {'mbid'} or {'artist','album'} or {'query'}
def enrich_seed(services, seed, progress=None, with_lastfm=True)   # S1: everything

@dataclass
class SimilarityResult: seed, seeds: list, matches, considered, fingerprinted, shortlisted, requests_made, cache_hits,
                        weights, notes: list, timings: dict; rows()

def find_similar(seeds=None, *, artist=None, album=None, query=None, mbid=None, weights=None,
                 mode='closest', radius=None, top_n=25, pool_size=150, shortlist_size=None,
                 exclude_same_artist=True, studio_only=True, max_per_artist=1,
                 obscurity=None, lateral=None, deep=True, with_deezer=True, with_wikidata=True,
                 with_discogs=None, enrich_tags_with_lastfm=True,
                 services=None, progress=None, seed_features=None) -> SimilarityResult
    # seeds: list of specs/strings (up to 4); the keyword form is sugar for one seed
    # mode ∈ closest|sideways|deep_cuts sets lateral/obscurity unless given explicitly
    # with_discogs=None → services.discogs_enabled
    # progress(stage, done, total, label) is ALWAYS called on the caller's thread
```

## library.py

```python
class Library:
    def __init__(self, data_dir=None)          # data/library.json
    def all(self) -> list[dict]                # newest first
    def saved(self) -> list[dict]
    def rated(self) -> list[dict]
    def get(self, key) -> dict | None
    def is_saved(self, key) -> bool
    def rating_of(self, key) -> float | None
    def save_album(self, row, from_seed=None) -> dict      # row: AlbumFeatures.as_row() or Match.as_row(); key = row['mbid']
    def unsave(self, key)
    def rate(self, key, rating, row=None) -> dict          # 0..10, half steps
    def unrate(self, key)
    def set_note(self, key, note)
    def remove(self, key)
    def import_legacy(self) -> int                          # ratings.json + bookmarks.json → 'manual:<slug>' entries; idempotent
    def unresolved(self) -> list[dict]                      # entries with no mbid
    def resolve(self, key, mbid, **fields) -> dict          # re-keys a manual entry under its mbid
# entry: {'mbid','artist','title','year','image_url','url','saved','saved_at','rating','rated_at','note','from_seed','source'}
```

## eval.py

```python
GOLDEN: list[dict]     # [{'seed': 'Artist - Album', 'expect': ['Artist', ...]}, ...]
def evaluate(services=None, top_n=25, seeds=None, progress=None, **engine_kwargs) -> dict
    # {'per_seed': [{'seed','hits','expected','found': [...],'missing': [...],'mrr', 'requests'}], 'hits_at_n': float, 'mrr': float}
def main(argv=None) -> int      # --top N  --seed TEXT (filter)  --save PATH  --compare PATH  --quiet
```

## cli.py

Positional `seeds` (nargs='+'), plus the flags in DESIGN.md. Prints the seed
card, then each match with similarity, reasons and the stat line; `--explain`
prints every axis and every statistic per match.

## workers.py (as built)

One helper for running per-service work on threads while progress stays on
the caller's thread (Streamlit widgets may only be touched from the script
thread).

```python
def run_workers(jobs, progress=None, stage='') -> dict
    # jobs: {name: callable(report)}. Each callable runs on its own thread
    # (ThreadPoolExecutor, max_workers=len(jobs)) and may call
    # report(done, total, label='') from that thread as often as it likes.
    # Reports go onto a queue.Queue; the CALLING thread drains it and invokes
    # progress(stage, done, total, label) once per report, where done/total
    # are the sums of the latest report from every worker (a worker that has
    # not reported yet counts 0/0) and label is '<name>: <label>' (just
    # '<name>' when the label is empty). progress is never called from a
    # worker thread.
    # Returns {name: result}. A job that raises has the exception instance as
    # its result (not re-raised); other jobs keep running. {} for no jobs.
    # Every job sends one sentinel when it finishes (even if it died), which
    # is what ends the drain loop deterministically without polling futures.
    # If `progress` itself raises — which is how Streamlit signals a rerun or
    # a stop from a widget call, and it raises a BaseException — the workers
    # are CANCELLED (each unwinds at its next report, so the wait is bounded
    # by one in-flight request rather than a whole stage) and the exception is
    # re-raised once they are down. A cancelled job's result is None.
```

Intended use in `engine.py` S4/S5:

```python
results = run_workers({
    'musicbrainz': lambda report: enrich_shortlist_mb(...),   # serial 1 rps on its own thread
    'deezer':      lambda report: enrich_deezer(...),
    'wikidata':    lambda report: enrich_wikidata(...),
}, progress=progress, stage='S5')
for name, outcome in results.items():
    if isinstance(outcome, Exception):
        result.notes.append(f'{name}: {outcome}')
```
