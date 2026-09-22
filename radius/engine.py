"""Seed in, ranked neighbourhood out.

The pipeline, and why it is staged this way (docs/DESIGN.md):

    S0  resolve   typed text -> one release-group mbid per seed, then a bulk
                  fingerprint (tags, popularity, artist) from ListenBrainz
    S1  enrich    everything we can know about the seed(s): credits,
                  personnel, tracklist, fans, critic scores. With several
                  seeds, a blended centroid to compare against
    S2  gather    the neighbourhood: seven candidate sources (candidates.py)
    S3  bulk      prefilter the pool, fingerprint it in batches, add listener
                  kinship and crowd tags, score once, keep a shortlist
    S4  connect   the deep MusicBrainz lookups for the shortlist - who
                  played, who produced, where - then rescore, keep the top N
    S5  stats     the remaining statistics for the finalists (Deezer,
                  Wikidata, Last.fm, Discogs, canonicity) and a final rescore

Retrieve-then-rerank: an album has to reach the shortlist on bulk data
before the expensive lookups run for it, which is why the candidate sources
try so hard to put deeply connected records into the pool in the first
place. Every stage that adds data recomputes the distances, so enrichment
moves the ranking rather than decorating it.

Services are independent, so each stage runs one worker thread per service
(workers.py); MusicBrainz stays serial on its own thread at 1 rps. Progress
is only ever reported on the caller's thread. A failure on one album or one
service is written into result.notes and never sinks the run.
"""

import time
from collections import Counter
from dataclasses import dataclass, field

from . import candidates as candidates_mod
from . import credits
from . import tags as tagmod
from .albums import (
    NON_STUDIO_TYPES, AlbumFeatures, apply_artist, apply_artist_release_groups,
    apply_deezer, apply_discogs, apply_lastfm_info, apply_release,
    apply_release_group, apply_wikidata, blend, enrich_tags, from_metadata,
    looks_non_studio,
)
from .clients import (
    ApiError, DeezerClient, DiscogsClient, KeyRejected, LastFmClient,
    ListenBrainzClient, MusicBrainzClient, WikidataClient,
)
from .similarity import Evidence, SimilarityWeights, compare
from .workers import run_workers

# The three plain-English intentions the UI offers, as engine settings.
MODES = {
    'closest': {'lateral': False, 'obscurity': 'any'},
    'sideways': {'lateral': True, 'obscurity': 'any'},
    'deep_cuts': {'lateral': False, 'obscurity': 'more_obscure'},
}
MAX_SEEDS = 4
# How many of an album's tracks get a Deezer track lookup for BPM/loudness.
# Evenly spaced through the running order, so a long record is not judged
# by its opening alone.
DEEZER_TRACK_SAMPLE = 8
# Editions tried, best first, until one carries track lengths.
RELEASE_ATTEMPTS = 2
LATERAL_BONUS = 0.08


class SeedNotFound(RuntimeError):
    """The seed album couldn't be resolved, with suggestions if there are any."""

    def __init__(self, message, suggestions=()):
        super().__init__(message)
        self.suggestions = list(suggestions)


@dataclass
class Services:
    """The clients, sharing one cache.

    Four are keyless and do the real work. Last.fm needs a key and Discogs
    accepts a token; both are additive. Any client may be None (tests, or a
    deliberately switched-off service) and the engine skips what it lacks.
    """

    musicbrainz: object = None
    listenbrainz: object = None
    wikidata: object = None
    deezer: object = None
    lastfm: object = None
    discogs: object = None
    _genre_names: object = field(default=None, repr=False, compare=False)

    @classmethod
    def create(cls, cache=None, lastfm_key=None, discogs_token=None):
        musicbrainz = MusicBrainzClient(cache=cache)
        cache = cache or musicbrainz.cache
        return cls(
            musicbrainz=musicbrainz,
            listenbrainz=ListenBrainzClient(cache=cache),
            wikidata=WikidataClient(cache=cache),
            deezer=DeezerClient(cache=cache),
            lastfm=LastFmClient(api_key=lastfm_key, cache=cache),
            discogs=DiscogsClient(token=discogs_token, cache=cache),
        )

    def _clients(self):
        return [client for client in (self.musicbrainz, self.listenbrainz, self.wikidata,
                                      self.deezer, self.lastfm, self.discogs)
                if client is not None]

    @property
    def tag_enrichment(self):
        return bool(self.lastfm is not None and getattr(self.lastfm, 'configured', False))

    @property
    def discogs_enabled(self):
        """Discogs runs by default only with a token: keyless it is held to
        25 requests a minute, which makes it the slowest stage by far."""
        return bool(self.discogs is not None and getattr(self.discogs, 'token', ''))

    @property
    def requests_made(self):
        return sum(getattr(client, 'calls_made', 0) for client in self._clients())

    @property
    def cache_hits(self):
        return sum(getattr(client, 'cache_hits', 0) for client in self._clients())

    def genre_names(self):
        """MusicBrainz's genre whitelist plus the vendored taxonomy's names:
        the set that decides whether a crowd tag is a genre or a mood."""
        if self._genre_names is None:
            names = set(tagmod.taxonomy_genre_names())
            if self.musicbrainz is not None:
                try:
                    names |= set(self.musicbrainz.genre_names() or ())
                except ApiError:
                    pass
            self._genre_names = frozenset(names)
        return self._genre_names


@dataclass
class SimilarityResult:
    seed: AlbumFeatures
    seeds: list = field(default_factory=list)
    matches: list = field(default_factory=list)
    considered: int = 0
    fingerprinted: int = 0
    shortlisted: int = 0
    requests_made: int = 0
    cache_hits: int = 0
    weights: SimilarityWeights = None
    notes: list = field(default_factory=list)
    timings: dict = field(default_factory=dict)
    sources: dict = field(default_factory=dict)

    def rows(self):
        return [match.as_row() for match in self.matches]


# ---------------------------------------------------------------------------
# Bookkeeping shared across stages
# ---------------------------------------------------------------------------

class _Notes:
    """Human-readable notes for the result: one-off messages, plus per-service
    failure counts that are rendered as a single line each rather than one
    note per album."""

    def __init__(self):
        self.messages = []
        self.failures = Counter()

    def add(self, message):
        if message and message not in self.messages:
            self.messages.append(message)

    def fail(self, what):
        self.failures[what] += 1

    def render(self):
        rendered = list(self.messages)
        for what, count in self.failures.most_common():
            rendered.append(f'{what} failed for {count} album{"s" if count != 1 else ""}.')
        return rendered


@dataclass
class _Caches:
    """Per-run memo of lookups that several albums share: an artist's
    personnel, crowd tags, similar artists and catalogue."""
    artists: dict = field(default_factory=dict)        # artist mbid -> personnel dict or None
    lastfm_artists: dict = field(default_factory=dict)  # for albums.enrich_tags
    kinship: dict = field(default_factory=dict)         # artist mbid -> (names, mbids, ranked)
    artist_albums: dict = field(default_factory=dict)   # artist mbid -> catalogue entries


def _check_outcomes(results, notes, state):
    """Turn worker outcomes into notes. A rejected Last.fm key switches
    Last.fm off for the rest of the run; a bug (anything that is not an
    ApiError) is re-raised rather than hidden."""
    for name, outcome in (results or {}).items():
        if isinstance(outcome, KeyRejected):
            notes.add(str(outcome))
            state['lastfm_ok'] = False
        elif isinstance(outcome, ApiError):
            notes.add(f'{name}: {outcome}')
        elif isinstance(outcome, Exception):
            raise outcome


def _evenly_spaced(items, count):
    items = list(items)
    if len(items) <= count:
        return items
    if count <= 1:
        return items[:1]
    step = (len(items) - 1) / float(count - 1)
    picked = []
    for index in range(count):
        item = items[int(round(index * step))]
        if item not in picked:
            picked.append(item)
    return picked


def _artist_key(features):
    return features.artist_mbid or features.artist.strip().casefold()


def _is_non_studio(candidate):
    if any((t or '').lower() in NON_STUDIO_TYPES for t in candidate.secondary_types):
        return True
    return looks_non_studio(candidate.title)


# ---------------------------------------------------------------------------
# S0: resolving what the user typed
# ---------------------------------------------------------------------------

def parse_seed_text(text):
    """'Artist - Album' -> {'artist', 'album'}; 'mbid:<id>' -> {'mbid'};
    anything else -> {'query'}. Dicts and AlbumFeatures pass through."""
    if isinstance(text, dict):
        return dict(text)
    if isinstance(text, AlbumFeatures):
        return {'features': text}
    text = (text or '').strip()
    if text.lower().startswith('mbid:'):
        return {'mbid': text[5:].strip()}
    if ' - ' in text:
        artist, _, album = (part.strip() for part in text.partition(' - '))
        if artist and album:
            return {'artist': artist, 'album': album}
    return {'query': text}


def _spec_label(spec):
    features = spec.get('features')
    if features is not None:
        return f'{features.artist} - {features.title}'
    if spec.get('artist') and spec.get('album'):
        return f"{spec['artist']} - {spec['album']}"
    return spec.get('query') or spec.get('mbid') or 'seed'


def search_albums(services, artist=None, album=None, query=None, limit=10):
    """Album search, for picking a seed by typing part of its name."""
    try:
        results = services.musicbrainz.find_album(
            artist=artist, album=album, query=query, limit=limit
        )
    except ApiError:
        return []
    found = []
    for release_group in results:
        if not isinstance(release_group, dict):
            continue
        credit = release_group.get('artist-credit') or []
        name, artist_mbid = '', ''
        if credit and isinstance(credit[0], dict):
            artist_block = credit[0].get('artist') or {}
            name = artist_block.get('name') or credit[0].get('name') or ''
            artist_mbid = artist_block.get('id') or ''
        found.append({
            'artist': name,
            'artist_mbid': artist_mbid,
            'album': release_group.get('title') or '',
            'mbid': release_group.get('id') or '',
            'year': (release_group.get('first-release-date') or '')[:4],
            'type': release_group.get('primary-type') or '',
            'secondary_types': list(release_group.get('secondary-types') or []),
            'disambiguation': release_group.get('disambiguation') or '',
        })
    return found


def fingerprint_many(services, mbids, with_popularity=True, genre_names=None, notes=None):
    """{mbid: AlbumFeatures} for many release groups, in bulk.

    This is the whole reason the project runs on ListenBrainz: metadata and
    listen counts for a batch of albums cost two requests, not two per album.
    """
    mbids = [m for m in dict.fromkeys(mbids) if m]
    if not mbids:
        return {}
    if genre_names is None:
        genre_names = services.genre_names()

    # Metadata is the fingerprint and has to succeed; the two popularity
    # calls only fill in statistics, so a failure there costs a number,
    # never the run.
    metadata = services.listenbrainz.metadata(mbids)
    popularity = {}
    if with_popularity:
        try:
            popularity = services.listenbrainz.popularity(mbids)
        except ApiError:
            if notes is not None:
                notes.fail('ListenBrainz popularity')

    built = {}
    for mbid in mbids:
        features = from_metadata(mbid, metadata.get(mbid), popularity.get(mbid), genre_names)
        if features is not None:
            built[mbid] = features

    # Canonicity needs each artist's own audience; one more bulk call covers
    # every artist in the batch at once.
    if with_popularity and built:
        artist_mbids = {f.artist_mbid for f in built.values() if f.artist_mbid}
        if artist_mbids:
            try:
                artist_counts = services.listenbrainz.artist_popularity(sorted(artist_mbids))
            except ApiError:
                artist_counts = {}
                if notes is not None:
                    notes.fail('ListenBrainz artist popularity')
            for features in built.values():
                entry = artist_counts.get(features.artist_mbid) or {}
                features.artist_listeners = entry.get('total_user_count') or 0
    return built


def resolve_seed(services, spec):
    """Turn one seed spec into a bulk-fingerprinted AlbumFeatures."""
    spec = parse_seed_text(spec)
    if spec.get('features') is not None:
        return spec['features']
    if spec.get('mbid'):
        built = fingerprint_many(services, [spec['mbid']])
        if built.get(spec['mbid']):
            return built[spec['mbid']]
        raise SeedNotFound(f"No usable album data for release group {spec['mbid']}.")

    results = search_albums(services, artist=spec.get('artist'), album=spec.get('album'),
                            query=spec.get('query'))
    if not results:
        raise SeedNotFound(
            'MusicBrainz has no album matching that. Check the spelling, or '
            'try "Artist - Album".'
        )

    # Prefer a proper studio album over a single, EP, live set or compilation
    # of the same name, then fall back through the rest until one has enough
    # tags to fingerprint.
    def preference(result):
        return (0 if (result.get('type') or '').lower() == 'album' else 1,
                1 if result.get('secondary_types') else 0)

    results.sort(key=preference)
    built = fingerprint_many(services, [r['mbid'] for r in results[:5]])
    for result in results[:5]:
        features = built.get(result['mbid'])
        if features is not None:
            return features

    raise SeedNotFound(
        'Found the album, but nobody has tagged it in MusicBrainz, so there '
        'is no fingerprint to compare against.',
        suggestions=results,
    )


# ---------------------------------------------------------------------------
# Per-album enrichment steps (S1, S4, S5)
# ---------------------------------------------------------------------------

def _musicbrainz_release_group(services, features, notes):
    """Editions, genres, rating and external ids; returns the canonical
    release order for the tracklist lookup."""
    if not features.mbid or services.musicbrainz is None:
        return []
    try:
        payload = services.musicbrainz.release_group(features.mbid)
    except ApiError:
        notes.fail('MusicBrainz release-group lookup')
        return []
    apply_release_group(features, credits.release_group_facts(payload))
    return credits.canonical_release_order(payload)


def _musicbrainz_release(services, features, order, notes):
    """The canonical edition's tracklist and credits. Tries the best editions
    in turn until one carries track lengths; if none does, the first is
    still applied for its titles and credits."""
    if services.musicbrainz is None:
        return False
    fallback = None
    for release_mbid in order[:RELEASE_ATTEMPTS]:
        try:
            payload = services.musicbrainz.release(release_mbid)
        except ApiError:
            notes.fail('MusicBrainz release lookup')
            continue
        shape = credits.release_shape(payload)
        circle = credits.release_circle(payload)
        if shape.get('runtime_seconds'):
            apply_release(features, shape, circle)
            return True
        if fallback is None:
            fallback = (shape, circle)
    if fallback is not None:
        apply_release(features, *fallback)
        return True
    return False


def _musicbrainz_artist(services, artist_mbid, caches, notes):
    """The personnel graph around one artist, memoised per run."""
    if not artist_mbid or services.musicbrainz is None:
        return None
    if artist_mbid in caches.artists:
        return caches.artists[artist_mbid]
    try:
        payload = services.musicbrainz.artist(artist_mbid)
    except ApiError:
        notes.fail('MusicBrainz artist lookup')
        caches.artists[artist_mbid] = None
        return None
    caches.artists[artist_mbid] = credits.artist_personnel(payload)
    return caches.artists[artist_mbid]


def _kinship(services, artist_mbid, caches):
    """(names, mbids, ranked) of an artist's ListenBrainz similar artists,
    full width, memoised per run. `names` are lower-cased for set
    comparison; `ranked` keeps the original names in score order."""
    if artist_mbid in caches.kinship:
        return caches.kinship[artist_mbid]
    entries = []
    if artist_mbid and services.listenbrainz is not None:
        entries = [e for e in (services.listenbrainz.similar_artists(artist_mbid) or [])
                   if isinstance(e, dict)]
    ranked = tuple(
        (e.get('name') or e.get('artist_name') or '').strip()
        for e in entries if (e.get('name') or e.get('artist_name'))
    )
    names = frozenset(name.lower() for name in ranked)
    mbids = frozenset(e['artist_mbid'] for e in entries if e.get('artist_mbid'))
    caches.kinship[artist_mbid] = (names, mbids, ranked)
    return caches.kinship[artist_mbid]


def _set_kinship(features, kinship):
    features.artist_neighbours, features.artist_neighbour_mbids, features.artist_neighbours_ranked = kinship


def _canonicity(services, features, caches):
    """The canonicity denominators from the artist's catalogue."""
    if not features.artist_mbid:
        return
    entries = candidates_mod.artist_albums(services, features.artist_mbid, features.artist,
                                           cache=caches.artist_albums)
    if entries:
        apply_artist_release_groups(features, entries)


def _deezer(services, features, notes):
    deezer = services.deezer
    if deezer is None or not features.artist or not features.title:
        return
    try:
        hits = deezer.search_album(features.artist, features.title)
        hit = credits.match_deezer_album(hits, features.artist, features.title,
                                         features.track_count or None)
        if not hit:
            return
        album = deezer.album(hit.get('id'))
        if not album:
            return
        tracks = [t for t in ((album.get('tracks') or {}).get('data') or [])
                  if isinstance(t, dict) and t.get('id')]
        details = []
        for track in _evenly_spaced(tracks, DEEZER_TRACK_SAMPLE):
            detail = deezer.track(track['id'])
            if detail:
                details.append(detail)
    except ApiError:
        notes.fail('Deezer lookup')
        return
    apply_deezer(features, credits.deezer_facts(album, details))


def _wikidata(services, features_list, notes):
    """One batched entity fetch for every album that has a Q-id, one labels
    call for every producer, label and reviewer id they mention."""
    wikidata = services.wikidata
    if wikidata is None:
        return
    by_qid = {}
    for features in features_list:
        if features.wikidata_id:
            by_qid.setdefault(features.wikidata_id, []).append(features)
    if not by_qid:
        return
    try:
        entities = wikidata.entities(list(by_qid))
    except ApiError:
        notes.fail('Wikidata lookup')
        return
    facts = {qid: credits.wikidata_facts(entity) for qid, entity in entities.items()}
    wanted = set()
    for fact in facts.values():
        wanted |= set(fact.get('critic_scores') or ())
        wanted |= set(fact.get('producer_qids') or ())
        wanted |= set(fact.get('label_qids') or ())
    labels = {}
    if wanted:
        try:
            labels = wikidata.labels(sorted(wanted))
        except ApiError:
            notes.fail('Wikidata labels')
    for qid, fact in facts.items():
        for features in by_qid.get(qid, ()):
            apply_wikidata(features, fact, labels)


def _discogs(services, features):
    discogs = services.discogs
    if discogs is None or not features.discogs_master_id:
        return
    master = discogs.master(features.discogs_master_id)
    if not master:
        return
    release = discogs.release(master['main_release']) if master.get('main_release') else None
    apply_discogs(features, credits.discogs_facts(master, release))


def _lastfm_info(services, features, notes):
    lastfm = services.lastfm
    if lastfm is None or not getattr(lastfm, 'configured', False):
        return
    try:
        info = lastfm.album_info(features.artist, features.title)
    except KeyRejected:
        raise
    except ApiError:
        notes.fail('Last.fm album info')
        return
    if info:
        apply_lastfm_info(features, credits.lastfm_facts(info))


def _stats_jobs(services, entries, notes, state, caches, with_deezer, with_wikidata, with_discogs):
    """The S5 worker jobs for a list of AlbumFeatures: every remaining
    statistic, one service per thread."""
    jobs = {}
    if with_deezer and services.deezer is not None:
        def deezer_job(report):
            for index, features in enumerate(entries):
                report(index, len(entries), f'{features.artist} - {features.title}')
                _deezer(services, features, notes)
            report(len(entries), len(entries), 'done')
        jobs['deezer'] = deezer_job
    if with_wikidata and services.wikidata is not None:
        def wikidata_job(report):
            report(0, 1, 'critic scores, producers, ids')
            _wikidata(services, entries, notes)
            report(1, 1, 'done')
        jobs['wikidata'] = wikidata_job
    if state.get('lastfm_ok'):
        def lastfm_job(report):
            for index, features in enumerate(entries):
                report(index, len(entries), f'{features.artist} - {features.title}')
                _lastfm_info(services, features, notes)
            report(len(entries), len(entries), 'done')
        jobs['lastfm'] = lastfm_job
    if services.listenbrainz is not None:
        def listenbrainz_job(report):
            for index, features in enumerate(entries):
                report(index, len(entries), f"{features.artist}'s catalogue")
                _canonicity(services, features, caches)
            report(len(entries), len(entries), 'done')
        jobs['listenbrainz'] = listenbrainz_job
    if with_discogs and services.discogs is not None:
        def discogs_job(report):
            for index, features in enumerate(entries):
                report(index, len(entries), f'{features.artist} - {features.title}')
                _discogs(services, features)
            report(len(entries), len(entries), 'done')
        jobs['discogs'] = discogs_job
    return jobs


def enrich_seed(services, seed, progress=None, with_lastfm=True, with_deezer=True,
                with_wikidata=True, with_discogs=None, notes=None, caches=None, state=None):
    """S1: everything the fingerprint can hold, for one seed.

    Two rounds of parallel workers. The first is the catalogue (MusicBrainz:
    release group, canonical edition with credits, artist personnel), the
    listeners (ListenBrainz: kinship and the artist's catalogue) and the
    crowd (Last.fm tags and listener counts). The second needs the first's
    ids and track count: Deezer, Wikidata and Discogs.
    """
    notes = notes if notes is not None else _Notes()
    caches = caches if caches is not None else _Caches()
    if state is None:
        state = {'lastfm_ok': with_lastfm and services.tag_enrichment}
    if with_discogs is None:
        with_discogs = services.discogs_enabled
    genre_names = services.genre_names()

    def musicbrainz_job(report):
        report(0, 3, 'release group')
        order = _musicbrainz_release_group(services, seed, notes)
        report(1, 3, 'tracklist and credits')
        _musicbrainz_release(services, seed, order, notes)
        report(2, 3, 'personnel')
        personnel = _musicbrainz_artist(services, seed.artist_mbid, caches, notes)
        if personnel:
            apply_artist(seed, personnel)
        report(3, 3, 'done')

    def listenbrainz_job(report):
        report(0, 2, 'listener kinship')
        _set_kinship(seed, _kinship(services, seed.artist_mbid, caches))
        report(1, 2, "artist's catalogue")
        _canonicity(services, seed, caches)
        report(2, 2, 'done')

    def lastfm_job(report):
        report(0, 2, 'crowd tags')
        enrich_tags(seed, services.lastfm, caches.lastfm_artists, genre_names)
        report(1, 2, 'listeners')
        _lastfm_info(services, seed, notes)
        report(2, 2, 'done')

    jobs = {}
    if services.musicbrainz is not None:
        jobs['musicbrainz'] = musicbrainz_job
    if services.listenbrainz is not None:
        jobs['listenbrainz'] = listenbrainz_job
    if state.get('lastfm_ok'):
        jobs['lastfm'] = lastfm_job
    _check_outcomes(run_workers(jobs, progress, stage='seed'), notes, state)

    jobs = _stats_jobs(services, [seed], notes, state, caches, with_deezer, with_wikidata, with_discogs)
    # Kinship and canonicity were already done above.
    jobs.pop('listenbrainz', None)
    _check_outcomes(run_workers(jobs, progress, stage='seed'), notes, state)
    return seed


# ---------------------------------------------------------------------------
# Scoring helpers
# ---------------------------------------------------------------------------

def _vectors_for(features, idf, artist_idf):
    """The three idf-weighted vectors a comparison needs."""
    return {
        'genre': tagmod.weighted_vector(features.genre_profile, idf),
        'mood': tagmod.weighted_vector(features.mood_profile, idf),
        'lineage': tagmod.weighted_vector(features.artist_profile, artist_idf),
    }


def _cap_per_artist(scored, max_per_artist):
    """Nearest-first, keeping only the first few albums by any one artist.
    Without this a single close neighbour returns its entire discography and
    crowds out everything else you'd want to hear."""
    if not max_per_artist or max_per_artist <= 0:
        return list(scored)
    per_artist = Counter()
    kept = []
    for candidate, match in scored:
        key = _artist_key(match.features)
        if per_artist[key] >= max_per_artist:
            continue
        per_artist[key] += 1
        kept.append((candidate, match))
    return kept


def _merge_pools(pools, contexts):
    """One pool and one SeedContext for several seeds: weights add up,
    sources union, co-listening counters sum."""
    merged = candidates_mod.CandidatePool()
    for pool in pools:
        for candidate in pool.ranked():
            share = candidate.weight / max(len(candidate.sources), 1)
            for source in sorted(candidate.sources):
                merged.add(candidate.mbid, source, share, artist=candidate.artist,
                           title=candidate.title, artist_mbid=candidate.artist_mbid,
                           primary_type=candidate.primary_type,
                           secondary_types=candidate.secondary_types)
    context = candidates_mod.SeedContext()
    names, mbids = set(), set()
    for each in contexts:
        names |= set(each.neighbour_names)
        mbids |= set(each.neighbour_mbids)
        context.similar_recordings.update(each.similar_recordings)
        context.co_listening_by_rg.update(each.co_listening_by_rg)
        context.co_listening_by_artist.update(each.co_listening_by_artist)
    context.neighbour_names = frozenset(names)
    context.neighbour_mbids = frozenset(mbids)
    return merged, context


def _seed_specs(seeds, artist, album, query, mbid, seed_features):
    specs = []
    if seed_features is not None:
        items = seed_features if isinstance(seed_features, (list, tuple)) else [seed_features]
        specs.extend({'features': f} for f in items if f is not None)
    for item in seeds or []:
        if item:
            specs.append(parse_seed_text(item))
    if mbid:
        specs.append({'mbid': mbid})
    elif artist and album:
        specs.append({'artist': artist, 'album': album})
    elif query:
        specs.append({'query': query})
    return specs


# ---------------------------------------------------------------------------
# The pipeline
# ---------------------------------------------------------------------------

def find_similar(seeds=None, *, artist=None, album=None, query=None, mbid=None,
                 weights=None, mode='closest', radius=None, top_n=25, pool_size=150,
                 shortlist_size=None, exclude_same_artist=True, studio_only=True,
                 max_per_artist=1, obscurity=None, lateral=None, deep=True,
                 with_deezer=True, with_wikidata=True, with_discogs=None,
                 enrich_tags_with_lastfm=True, services=None, progress=None,
                 seed_features=None):
    """Find the albums most deeply connected to the seed(s).

    seeds               up to four seed specs: 'Artist - Album', 'mbid:<id>',
                        free text, {'artist','album'} / {'mbid'} / {'query'}
                        dicts, or AlbumFeatures. The keyword form (artist=,
                        album=, query=, mbid=) is sugar for one seed.
    mode                closest | sideways | deep_cuts, setting `lateral` and
                        `obscurity` unless those are given explicitly.
    radius              optional cap on distance (0..1); None means top_n only.
    pool_size           how many candidates get bulk-fingerprinted.
    shortlist_size      how many of those get the deep MusicBrainz lookups;
                        default max(1.5 * top_n, 30).
    deep                False skips S4/S5 - a fast, shallow run.
    with_discogs        None means "only when a Discogs token is configured".
    progress(stage, done, total, label) is always called on this thread.
    """
    services = services or Services.create()
    weights = weights or SimilarityWeights()
    settings = MODES.get(mode) or MODES['closest']
    if lateral is None:
        lateral = settings['lateral']
    if obscurity is None:
        obscurity = settings['obscurity']
    if with_discogs is None:
        with_discogs = services.discogs_enabled
    notes = _Notes()
    caches = _Caches()
    state = {'lastfm_ok': bool(enrich_tags_with_lastfm and services.tag_enrichment)}
    timings = {}

    def report(stage, done, total, label=''):
        if progress:
            progress(stage, done, total, label)

    def result(seed, seeds_list, matches=(), **extra):
        return SimilarityResult(
            seed=seed, seeds=list(seeds_list), matches=list(matches),
            requests_made=services.requests_made, cache_hits=services.cache_hits,
            weights=weights, notes=notes.render(), timings=timings, **extra,
        )

    # ---- S0 / S1: seeds ------------------------------------------------
    specs = _seed_specs(seeds, artist, album, query, mbid, seed_features)
    if not specs:
        raise SeedNotFound('Give a seed: "Artist - Album", or --artist X --album Y.')
    if len(specs) > MAX_SEEDS:
        notes.add(f'Only the first {MAX_SEEDS} seeds are used.')
        specs = specs[:MAX_SEEDS]

    started = time.monotonic()
    resolved = []
    for index, spec in enumerate(specs):
        report('seed', index, len(specs), f'resolving {_spec_label(spec)}')
        resolved.append(resolve_seed(services, spec))
    for index, features in enumerate(resolved):
        prefix = f'{features.artist} - {features.title}: '

        def relay(stage, done, total, label, prefix=prefix):
            report(stage, done, total, prefix + label)

        enrich_seed(services, features, progress=relay if progress else None,
                    with_lastfm=enrich_tags_with_lastfm, with_deezer=with_deezer,
                    with_wikidata=with_wikidata, with_discogs=with_discogs,
                    notes=notes, caches=caches, state=state)
    report('seed', len(resolved), len(resolved),
           ' + '.join(f'{f.artist} - {f.title}' for f in resolved))
    seed = resolved[0] if len(resolved) == 1 else blend(resolved)
    timings['seed'] = round(time.monotonic() - started, 1)

    seed_artist_mbids = {f.artist_mbid for f in resolved if f.artist_mbid}
    seed_artist_names = {f.artist.strip().casefold() for f in resolved if f.artist}
    seed_keys = {f.key for f in resolved}
    seed_mbids = {f.mbid for f in resolved if f.mbid}

    def is_seed_artist(artist_mbid, artist_name):
        return (artist_mbid and artist_mbid in seed_artist_mbids) or \
            (artist_name or '').strip().casefold() in seed_artist_names

    # ---- S2: candidates ------------------------------------------------
    started = time.monotonic()
    pools, contexts = [], []
    for features in resolved:
        pool, context = candidates_mod.gather(features, services, progress=report,
                                              album_cache=caches.artist_albums)
        pools.append(pool)
        contexts.append(context)
    if len(pools) == 1:
        pool, context = pools[0], contexts[0]
    else:
        pool, context = _merge_pools(pools, contexts)
    for each in seed_mbids:
        pool.drop(each)
    if not seed.artist_neighbours and context.neighbour_names:
        seed.artist_neighbours = context.neighbour_names
        seed.artist_neighbour_mbids = context.neighbour_mbids
    sources = candidates_mod.gather_sources_report(pool)
    considered = len(pool)
    timings['candidates'] = round(time.monotonic() - started, 1)

    # ---- S3: bulk fingerprint, kinship, crowd tags, first score ---------
    started = time.monotonic()
    shortlist = []
    for candidate in pool.ranked():
        # Filter on what the cheap catalogue data already says, before
        # spending any request on a fingerprint.
        if exclude_same_artist and is_seed_artist(candidate.artist_mbid, candidate.artist):
            continue
        if (candidate.primary_type or '').lower() == 'single':
            continue
        if studio_only and _is_non_studio(candidate):
            continue
        shortlist.append(candidate)
        if len(shortlist) >= pool_size:
            break
    if not shortlist:
        notes.add('No candidates survived the filters. Try a wider pool.')
        return result(seed, resolved, considered=considered, sources=sources)

    genre_names = services.genre_names()
    report('fingerprint', 0, len(shortlist), f'{len(shortlist)} albums, in batches')
    built = fingerprint_many(services, [c.mbid for c in shortlist],
                             genre_names=genre_names, notes=notes)
    report('fingerprint', len(shortlist), len(shortlist), f'{len(built)} fingerprinted')

    def kinship_job(report_):
        artists = sorted({f.artist_mbid for f in built.values() if f.artist_mbid})
        for index, artist_mbid in enumerate(artists):
            report_(index, len(artists), 'listener kinship')
            kinship = _kinship(services, artist_mbid, caches)
            for features in built.values():
                if features.artist_mbid == artist_mbid:
                    _set_kinship(features, kinship)
        report_(len(artists), len(artists), 'done')

    def crowd_job(report_):
        targets = [built[c.mbid] for c in shortlist if c.mbid in built]
        for index, features in enumerate(targets):
            report_(index, len(targets), f'crowd tags: {features.artist} - {features.title}')
            enrich_tags(features, services.lastfm, caches.lastfm_artists, genre_names)
        report_(len(targets), len(targets), 'done')

    jobs = {}
    if services.listenbrainz is not None:
        jobs['listenbrainz'] = kinship_job
    if state['lastfm_ok']:
        jobs['lastfm'] = crowd_job
    _check_outcomes(run_workers(jobs, progress, stage='enrich'), notes, state)

    unique = []
    seen = set(seed_keys)
    for candidate in shortlist:
        features = built.get(candidate.mbid)
        if features is None or features.key in seen:
            continue
        if studio_only and not features.is_studio:
            continue
        if (features.release_type or '').lower() == 'single':
            continue
        if exclude_same_artist and is_seed_artist(features.artist_mbid, features.artist):
            continue
        seen.add(features.key)
        unique.append((candidate, features))
    if not unique:
        notes.add('Nothing in the candidate pool had enough tags to compare.')
        return result(seed, resolved, considered=considered, sources=sources)

    # idf over this neighbourhood: "rare" means rare among these candidates,
    # which is what makes a shared tag informative here.
    idf = tagmod.build_idf([f.profile for _, f in unique] + [seed.profile])
    artist_idf = tagmod.build_idf(
        [f.artist_profile for _, f in unique if f.artist_profile]
        + ([seed.artist_profile] if seed.artist_profile else [])
    )
    seed_vectors = _vectors_for(seed, idf, artist_idf)
    vectors = {candidate.mbid: _vectors_for(f, idf, artist_idf) for candidate, f in unique}
    # Rarity of each similar artist across the pool, so kinship through the
    # famous acts that ListenBrainz lists next to everything counts little.
    neighbour_idf = tagmod.build_idf(
        [{name: 1.0 for name in f.artist_neighbours} for _, f in unique if f.artist_neighbours]
        + ([{name: 1.0 for name in seed.artist_neighbours}] if seed.artist_neighbours else [])
    )
    top_prefilter = max(candidate.prefilter_score for candidate, _ in unique) or 1.0
    lateral_bonus = LATERAL_BONUS if lateral else 0.0
    seed_roots = set(seed.root_genres)

    def evidence_for(candidate, features):
        # An album that came in through the seed's people graph shares a
        # person with it by construction; saying so before the deep lookups
        # is what lets a member's thinly tagged side project reach the
        # shortlist where its real personnel gets fetched.
        via_people = any(source.startswith('people:') for source in candidate.sources)
        return Evidence(
            convergence=candidate.prefilter_score / top_prefilter,
            album_hits=float(context.co_listening_by_rg.get(candidate.mbid, 0.0)),
            artist_hits=float(context.co_listening_by_artist.get(features.artist_mbid, 0.0))
            if features.artist_mbid else 0.0,
            neighbour_idf=neighbour_idf,
            known_personnel=0.5 if via_people else 0.0,
        )

    def score(entries):
        scored = []
        for candidate, features in entries:
            # Re-checked on every pass, not only before fingerprinting: the
            # deep lookups are where a record's real secondary types show up
            # (ListenBrainz does not serve them), so a compilation or live
            # set can only be recognised here, and an artist mbid that was
            # missing in the bulk data can turn out to be the seed's own.
            if studio_only and not features.is_studio:
                continue
            if exclude_same_artist and is_seed_artist(features.artist_mbid, features.artist):
                continue
            # A seed with no listener count gives no threshold to compare
            # against, and an empty root-genre set would reject everything;
            # in both cases the filter is dropped rather than applied.
            if obscurity == 'more_obscure' and seed.listeners \
                    and features.listeners >= seed.listeners:
                continue
            if obscurity == 'better_known' and seed.listeners \
                    and features.listeners <= seed.listeners:
                continue
            if lateral and seed_roots and not (set(features.root_genres) & seed_roots):
                continue
            match = compare(
                seed, features, seed_vectors, vectors[candidate.mbid], weights,
                evidence=evidence_for(candidate, features),
                lateral_bonus=lateral_bonus, sources=tuple(candidate.sources),
            )
            if match is not None:
                scored.append((candidate, match))
        scored.sort(key=lambda pair: (pair[1].distance, -pair[1].features.listeners))
        return _cap_per_artist(scored, max_per_artist)

    # A filter that cannot be applied is said out loud, so an unexpected
    # result set is never silently the wrong mode.
    if obscurity in ('more_obscure', 'better_known') and not seed.listeners:
        notes.add('The seed has no ListenBrainz listener count, so the obscurity '
                  'filter was skipped.')
    if lateral and not seed_roots:
        notes.add('The seed carries no recognised root genre, so the sideways '
                  'filter was skipped.')

    report('score', 0, 1, f'scoring {len(unique)} albums')
    scored = score(unique)
    report('score', 1, 1, f'{len(scored)} scored')
    shortlist_n = shortlist_size or max(int(1.5 * top_n), 30)
    scored = scored[:shortlist_n]
    timings['bulk'] = round(time.monotonic() - started, 1)

    # ---- S4: the connections -------------------------------------------
    if deep and scored and services.musicbrainz is not None:
        started = time.monotonic()
        entries = [(candidate, match.features) for candidate, match in scored]

        def musicbrainz_job(report_):
            artists = []
            for _, features in entries:
                if features.artist_mbid and features.artist_mbid not in caches.artists \
                        and features.artist_mbid not in artists:
                    artists.append(features.artist_mbid)
            total, done = len(artists) + 2 * len(entries), 0
            names = {features.artist_mbid: features.artist for _, features in entries}
            for artist_mbid in artists:
                report_(done, total, f'personnel: {names.get(artist_mbid, artist_mbid)}')
                _musicbrainz_artist(services, artist_mbid, caches, notes)
                done += 1
            for _, features in entries:
                personnel = caches.artists.get(features.artist_mbid)
                if personnel:
                    apply_artist(features, personnel)
            for _, features in entries:
                report_(done, total, f'{features.artist} - {features.title}: editions')
                order = _musicbrainz_release_group(services, features, notes)
                done += 1
                report_(done, total, f'{features.artist} - {features.title}: credits')
                _musicbrainz_release(services, features, order, notes)
                done += 1
            report_(total, total, 'done')

        _check_outcomes(run_workers({'musicbrainz': musicbrainz_job}, progress,
                                    stage='connections'), notes, state)
        scored = score(entries)
        timings['connections'] = round(time.monotonic() - started, 1)

    finalists = scored[:top_n]

    # ---- S5: the remaining statistics -----------------------------------
    if deep and finalists:
        started = time.monotonic()
        entries = [(candidate, match.features) for candidate, match in finalists]
        jobs = _stats_jobs(services, [f for _, f in entries], notes, state, caches,
                           with_deezer, with_wikidata, with_discogs)
        _check_outcomes(run_workers(jobs, progress, stage='stats'), notes, state)
        finalists = score(entries)[:top_n]
        timings['stats'] = round(time.monotonic() - started, 1)

    matches = [match for _, match in finalists]
    if radius is not None:
        matches = [match for match in matches if match.distance <= radius]
    if not matches:
        notes.add(
            f'{len(unique)} albums were fingerprinted but none qualified'
            + (f' inside radius {radius:.2f}' if radius is not None else '')
            + '. Try another mode or a wider pool.'
        )
    return result(seed, resolved, matches, considered=considered,
                  fingerprinted=len(unique), shortlisted=len(scored), sources=sources)
