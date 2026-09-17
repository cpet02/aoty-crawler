"""Seed in, ranked neighbourhood out.

The flow, and why it's staged this way:

1. Resolve the seed. Typed-in text becomes one release-group mbid via
   MusicBrainz, then a full fingerprint.
2. Gather candidates from the seed's own tag searches and from the albums
   that listeners of similar artists actually play (see candidates.py).
3. Prefilter. Fingerprinting everything found would be thousands of albums,
   so the pool is cut to `pool_size` by how many of the seed's neighbourhoods
   independently surfaced each one.
4. Fingerprint the survivors **in bulk** — ListenBrainz returns metadata and
   listen counts for 25 mbids per request, so a 120-album pool costs about
   ten calls rather than several hundred.
5. Compute idf across that pool, so "rare" is measured against this
   neighbourhood rather than against all music, and rank by distance.
6. Enrich only the finalists with the expensive per-album extras: tracklists
   from MusicBrainz at one request a second, and Wikipedia prose.

Tag vectors are thickened with Last.fm's crowd tags at two points — the seed
before candidates are gathered, so the richer vocabulary widens the search,
and the shortlist before scoring. That step is skipped entirely when no
Last.fm key is configured, and nothing else changes.

Every step reads through the disk cache, so a second run of the same seed —
or of a neighbouring one — is nearly free and touches almost no network.
"""

from dataclasses import dataclass, field

from . import candidates as candidates_mod
from . import tags as tagmod
from .albums import (
    AlbumFeatures, attach_prose, attach_tracklist, enrich_tags, from_metadata,
)
from .clients import (
    ApiError, LastFmClient, ListenBrainzClient, MusicBrainzClient,
    WikipediaClient,
)
from .similarity import SimilarityWeights, compare


class SeedNotFound(RuntimeError):
    """The seed album couldn't be resolved, with suggestions if there are any."""

    def __init__(self, message, suggestions=()):
        super().__init__(message)
        self.suggestions = list(suggestions)


@dataclass
class Services:
    """The clients, sharing one cache.

    The first three are keyless and do all the real work. Last.fm is optional
    and additive: present, it thickens tag vectors; absent, nothing else
    changes.
    """

    musicbrainz: MusicBrainzClient = None
    listenbrainz: ListenBrainzClient = None
    wikipedia: WikipediaClient = None
    lastfm: LastFmClient = None

    @classmethod
    def create(cls, cache=None, lastfm_key=None):
        musicbrainz = MusicBrainzClient(cache=cache)
        cache = cache or musicbrainz.cache
        return cls(
            musicbrainz=musicbrainz,
            listenbrainz=ListenBrainzClient(cache=cache),
            wikipedia=WikipediaClient(cache=cache),
            lastfm=LastFmClient(api_key=lastfm_key, cache=cache),
        )

    @property
    def tag_enrichment(self):
        return bool(self.lastfm is not None and self.lastfm.configured)

    @property
    def requests_made(self):
        return sum(
            getattr(client, 'calls_made', 0)
            for client in (self.musicbrainz, self.listenbrainz,
                           self.wikipedia, self.lastfm)
            if client is not None
        )

    @property
    def cache_hits(self):
        return sum(
            getattr(client, 'cache_hits', 0)
            for client in (self.musicbrainz, self.listenbrainz,
                           self.wikipedia, self.lastfm)
            if client is not None
        )

    @property
    def requests_by_service(self):
        """{service name: live requests made}, for services actually used."""
        named = (('MusicBrainz', self.musicbrainz), ('ListenBrainz', self.listenbrainz),
                 ('Wikipedia', self.wikipedia), ('Last.fm', self.lastfm))
        return {
            name: client.calls_made for name, client in named
            if client is not None and client.calls_made > 0
        }


@dataclass
class SimilarityResult:
    seed: AlbumFeatures
    matches: list = field(default_factory=list)
    considered: int = 0
    fingerprinted: int = 0
    requests_made: int = 0
    cache_hits: int = 0
    weights: SimilarityWeights = None
    notes: list = field(default_factory=list)

    def rows(self):
        return [match.as_row() for match in self.matches]


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
        credits = release_group.get('artist-credit') or []
        name = ''
        if credits and isinstance(credits[0], dict):
            name = (credits[0].get('artist') or {}).get('name') or ''
        found.append({
            'artist': name,
            'album': release_group.get('title') or '',
            'mbid': release_group.get('id') or '',
            'year': (release_group.get('first-release-date') or '')[:4],
            'type': release_group.get('primary-type') or '',
        })
    return found


def fingerprint_many(services, mbids, with_popularity=True):
    """{mbid: AlbumFeatures} for many release groups, in bulk.

    This is the whole reason the project runs on ListenBrainz: metadata and
    listen counts for a batch of albums cost two requests, not two per album.
    """
    mbids = [m for m in dict.fromkeys(mbids) if m]
    if not mbids:
        return {}

    metadata = services.listenbrainz.metadata(mbids)
    popularity = services.listenbrainz.popularity(mbids) if with_popularity else {}

    built = {}
    for mbid in mbids:
        features = from_metadata(mbid, metadata.get(mbid), popularity.get(mbid))
        if features is not None:
            built[mbid] = features

    # Canonicity needs each artist's own audience; one more bulk call covers
    # every artist in the batch at once.
    if with_popularity and built:
        artist_mbids = {f.artist_mbid for f in built.values() if f.artist_mbid}
        if artist_mbids:
            artist_counts = services.listenbrainz.artist_popularity(sorted(artist_mbids))
            for features in built.values():
                entry = artist_counts.get(features.artist_mbid) or {}
                features.artist_listeners = entry.get('total_user_count') or 0
    return built


def resolve_seed(services, artist=None, album=None, query=None, mbid=None):
    """Turn whatever the user typed into one fingerprinted seed album."""
    if mbid:
        built = fingerprint_many(services, [mbid])
        if built.get(mbid):
            return built[mbid]
        raise SeedNotFound(f'No usable album data for release group {mbid}.')

    results = search_albums(services, artist=artist, album=album, query=query)
    if not results:
        raise SeedNotFound(
            'MusicBrainz has no album matching that. Check the spelling, or '
            'try "Artist - Album".'
        )

    # Prefer a proper album over a single or EP of the same name, then fall
    # back through the rest until one has enough tags to fingerprint.
    results.sort(key=lambda r: 0 if (r.get('type') or '').lower() == 'album' else 1)
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


def _vectors_for(features, idf, artist_idf, prose_idf):
    """The four idf-weighted vectors a comparison needs."""
    return {
        'genre': tagmod.weighted_vector(features.genre_profile, idf),
        'mood': tagmod.weighted_vector(features.mood_profile, idf),
        'lineage': tagmod.weighted_vector(features.artist_profile, artist_idf),
        'prose': {
            term: weight * prose_idf.get(term, 1.0)
            for term, weight in features.prose.items()
        },
    }


def find_similar(artist=None, album=None, query=None, mbid=None,
                 weights=None, radius=0.55, top_n=25, pool_size=120,
                 tags_to_expand=6, albums_per_tag=60, similar_artists=25,
                 exclude_same_artist=True, studio_only=True, max_per_artist=2,
                 obscurity='any', lateral=False, local_albums=None,
                 enrich_results=True, with_prose=True, enrich_tags_with_lastfm=True,
                 services=None, progress=None, seed_features=None):
    """Find albums whose fingerprint sits within `radius` of the seed's.

    radius              0..1. 0.3 is a tight neighbourhood, 0.7 loose.
    pool_size           how many candidates get fully fingerprinted. Higher is
                        better and cheap, since fingerprints come in batches.
    obscurity           'any', 'more_obscure' (fewer listeners than the seed)
                        or 'better_known'.
    lateral             prefer records that share the seed's broad genre but
                        bring subgenres it doesn't have.
    studio_only         drop live albums, compilations and remix sets.
    max_per_artist      at most this many albums by any one artist in the
                        results. A strong neighbour otherwise fills the whole
                        list with its own discography, which is technically
                        correct and useless as a recommendation. 0 removes the
                        cap.
    enrich_results      fetch tracklists for finalists (one MusicBrainz second
                        each) to fill the scale, pacing and titling axes.
    enrich_tags_with_lastfm
                        thicken tag vectors with Last.fm crowd tags. Ignored
                        when no LASTFM_API_KEY is set.
    with_prose          fetch Wikipedia intros for finalists.
    local_albums        optional extra candidates, as dicts carrying an 'mbid'.
    seed_features       a pre-resolved seed, to skip re-resolving it.
    """
    services = services or Services.create()
    weights = weights or SimilarityWeights()

    def report(stage, done, total, label=''):
        if progress:
            progress(stage, done, total, label)

    report('seed', 0, 1, 'resolving seed album')
    seed = seed_features or resolve_seed(
        services, artist=artist, album=album, query=query, mbid=mbid
    )
    # Enrich the seed before gathering, not after: its tags are what the
    # candidate search expands on, so a thicker seed vocabulary widens the
    # neighbourhood rather than just scoring it differently.
    tag_cache = {}
    if enrich_tags_with_lastfm:
        report('seed', 0, 1, 'adding crowd tags')
        enrich_tags(seed, services.lastfm, tag_cache)
    report('seed', 1, 1, f'{seed.artist} — {seed.title}')

    pool, seed_neighbours = candidates_mod.gather(
        seed, services.musicbrainz, services.listenbrainz,
        tags_to_expand=tags_to_expand,
        albums_per_tag=albums_per_tag,
        similar_artists=similar_artists,
        local_albums=local_albums,
        progress=lambda done, total, label: report('candidates', done, total, label),
    )
    seed.artist_neighbours = seed_neighbours

    notes = []
    seed_artist = seed.artist.strip().lower()
    shortlist = []
    for candidate in pool.ranked():
        # Filter on what the cheap catalogue data already tells us, before
        # spending any requests on a fingerprint.
        if exclude_same_artist and candidate.artist.strip().lower() == seed_artist:
            continue
        if candidate.artist_mbid and seed.artist_mbid and exclude_same_artist \
                and candidate.artist_mbid == seed.artist_mbid:
            continue
        shortlist.append(candidate)
        if len(shortlist) >= pool_size:
            break

    if not shortlist:
        notes.append('No candidates survived the filters — try a wider pool.')
        return SimilarityResult(seed=seed, weights=weights, notes=notes,
                                considered=len(pool),
                                requests_made=services.requests_made,
                                cache_hits=services.cache_hits)

    top_prefilter = max(c.prefilter_score for c in shortlist) or 1.0

    report('fingerprint', 0, len(shortlist), f'{len(shortlist)} albums, in batches')
    built = fingerprint_many(services, [c.mbid for c in shortlist])
    report('fingerprint', len(shortlist), len(shortlist), f'{len(built)} fingerprinted')

    # Neighbour sets for the candidates' artists power the listener-kinship
    # axis. One request per distinct artist, cached, so a pool full of albums
    # by the same artists costs very little.
    if weights.neighbours > 0:
        artists = {f.artist_mbid for f in built.values() if f.artist_mbid}
        for index, artist_mbid in enumerate(sorted(artists)):
            report('kinship', index, len(artists), 'listener kinship')
            names = frozenset(
                (n.get('name') or n.get('artist_name') or '').strip().lower()
                for n in services.listenbrainz.similar_artists(artist_mbid)
                if (n.get('name') or n.get('artist_name'))
            )
            for features in built.values():
                if features.artist_mbid == artist_mbid:
                    features.artist_neighbours = names
        report('kinship', len(artists), len(artists), 'done')

    if enrich_tags_with_lastfm and services.tag_enrichment:
        targets = [built[c.mbid] for c in shortlist if c.mbid in built]
        for index, features in enumerate(targets):
            report('crowd tags', index, len(targets),
                   f'{features.artist} — {features.title}')
            try:
                enrich_tags(features, services.lastfm, tag_cache)
            except ApiError as exc:
                # A key that stops working mid-run shouldn't sink the run;
                # the MusicBrainz tags are still there to compare on.
                notes.append(f'Crowd tags unavailable: {exc}')
                break
        report('crowd tags', len(targets), len(targets), 'done')

    unique = []
    seen = {seed.key}
    for candidate in shortlist:
        features = built.get(candidate.mbid)
        if features is None or features.key in seen:
            continue
        if studio_only and not features.is_studio:
            continue
        seen.add(features.key)
        unique.append((candidate, features))

    if not unique:
        notes.append('Nothing in the candidate pool had enough tags to compare.')
        return SimilarityResult(seed=seed, weights=weights, notes=notes,
                                considered=len(pool),
                                requests_made=services.requests_made,
                                cache_hits=services.cache_hits)

    # idf over this neighbourhood: "rare" means rare among these candidates,
    # which is what makes a shared tag informative here.
    all_features = [f for _, f in unique] + [seed]
    idf = tagmod.build_idf([f.profile for f in all_features])
    artist_idf = tagmod.build_idf([f.artist_profile for f in all_features if f.artist_profile])

    # Prose is fetched before scoring only if it is actually weighted, since
    # it costs a MusicBrainz second per album to find the article.
    prose_pool = []
    if with_prose and weights.prose > 0:
        ranked_for_prose = sorted(
            unique, key=lambda pair: pair[0].prefilter_score, reverse=True
        )[:max(top_n * 2, 20)]
        prose_pool = [f for _, f in ranked_for_prose] + [seed]
        report('prose', 0, len(prose_pool), 'reading Wikipedia')
        attach_prose(prose_pool, services.musicbrainz, services.wikipedia)
        report('prose', len(prose_pool), len(prose_pool), 'done')
    prose_idf = tagmod.build_idf([f.prose for f in all_features if f.prose])

    seed_vectors = _vectors_for(seed, idf, artist_idf, prose_idf)
    lateral_bonus = 0.08 if lateral else 0.0

    matches = []
    for candidate, features in unique:
        if obscurity == 'more_obscure' and features.listeners >= seed.listeners:
            continue
        if obscurity == 'better_known' and features.listeners <= seed.listeners:
            continue
        if lateral and not (set(features.root_genres) & set(seed.root_genres)):
            continue
        match = compare(
            seed, features, seed_vectors,
            _vectors_for(features, idf, artist_idf, prose_idf),
            weights,
            co_tagging=candidate.prefilter_score / top_prefilter,
            lateral_bonus=lateral_bonus,
            sources=tuple(candidate.sources),
        )
        if match is None:
            continue
        if match.distance <= radius:
            matches.append(match)

    matches.sort(key=lambda m: (m.distance, -m.features.listeners))

    if max_per_artist and max_per_artist > 0:
        # Nearest-first, keeping only the first few albums by any one artist.
        # Without this a single close neighbour returns its entire
        # discography and crowds out everything else you'd want to hear.
        per_artist = {}
        spread = []
        for match in matches:
            artist_key = (match.features.artist_mbid
                          or match.features.artist.strip().lower())
            count = per_artist.get(artist_key, 0)
            if count >= max_per_artist:
                continue
            per_artist[artist_key] = count + 1
            spread.append(match)
        matches = spread

    matches = matches[:top_n]

    # The shape axes need a tracklist, which is the one genuinely expensive
    # lookup left, so it runs on finalists only — and then the affected
    # distances are recomputed so the extra data actually counts.
    if enrich_results and matches:
        shape_axes = weights.scale + weights.pacing + weights.titling
        if shape_axes > 0:
            attach_tracklist(seed, services.musicbrainz)
            for index, match in enumerate(matches):
                report('shape', index, len(matches),
                       f'{match.features.artist} — {match.features.title}')
                attach_tracklist(match.features, services.musicbrainz)
            report('shape', len(matches), len(matches), 'done')

            rescored = []
            for match in matches:
                features = match.features
                candidate = pool.get(features.mbid)
                updated = compare(
                    seed, features, seed_vectors,
                    _vectors_for(features, idf, artist_idf, prose_idf),
                    weights,
                    co_tagging=(candidate.prefilter_score / top_prefilter
                                if candidate else None),
                    lateral_bonus=lateral_bonus,
                    sources=match.sources,
                )
                rescored.append(updated or match)
            rescored.sort(key=lambda m: (m.distance, -m.features.listeners))
            matches = rescored

    if not matches:
        notes.append(
            f'Nothing inside radius {radius:.2f}. '
            f'{len(unique)} albums were fingerprinted — widen the radius.'
        )

    return SimilarityResult(
        seed=seed,
        matches=matches,
        considered=len(pool),
        fingerprinted=len(unique),
        requests_made=services.requests_made,
        cache_hits=services.cache_hits,
        weights=weights,
        notes=notes,
    )
