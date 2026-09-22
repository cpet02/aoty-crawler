"""Candidate generation: deciding which albums are even worth scoring.

You cannot fingerprint all of recorded music, so the seed picks its own
neighbourhood. Seven sources, deliberately different in character, each
adding (mbid, source label, weight) to one CandidatePool:

* `tag:a`         MusicBrainz release-group search for each of the seed's top
                  tags - records that share its vocabulary but have no other
                  connection to it
* `tags:a+b`      the same search for every pair of the seed's top tags; a
                  conjunction ("post-rock" AND "slowcore") is a scene where a
                  single tag is a continent, so it weighs more
* `artist:name`   ListenBrainz's collaborative similar artists, each expanded
                  to their most-listened albums - what listeners themselves
                  pair with the seed, including records no tag would link
* `people:name`   the seed artist's personnel: the acts in its personnel graph
                  directly, and the other bands of each member (one
                  MusicBrainz artist lookup per member - the group lookup
                  gives members but not the members' other bands)
* `tracks`        the seed's own recordings -> recordings people play
                  alongside them -> the albums those recordings live on; the
                  same scores feed the co_listening axis through SeedContext
* `lastfm:name`   Last.fm's similar artists, when a key is configured
* `lastfm_tag:a`  Last.fm's tag charts, matched to ListenBrainz release
                  groups by artist mbid and title, when a key is configured

An album surfacing from several of these at once is prima facie closer, so
breadth of agreement is the prefilter that decides who gets fully
fingerprinted, and it survives into the scoring as the `convergence` axis.

The sources are grouped by the service they hammer and run as three worker
threads (MusicBrainz at its serial 1 rps, ListenBrainz, Last.fm), so a
gather takes as long as the slowest service rather than the sum. Only the
ListenBrainz worker can turn a member's bands into albums, and only the
MusicBrainz worker can find those bands, so the two meet at a
threading.Event: the MusicBrainz worker sets it once its personnel hop is
done and the ListenBrainz worker waits for it after everything else it can
do alone. Everything keys on release-group mbids, which is what makes the
bulk metadata and popularity lookups possible later.
"""

import threading
from collections import Counter
from dataclasses import dataclass, field
from itertools import combinations

from . import credits
from . import tags as tagmod
from .albums import NON_STUDIO_TYPES, canonical_title
from .clients import ApiError, KeyRejected
from .workers import run_workers

# Rank decay: weight 1 at the head of a list, 1/2 at the half-life rank, and
# a long tail. The head of a tag search is far more on-topic than its tail,
# which drifts toward whatever is popular; an artist's first few albums are
# the ones people mean by the artist.
TAG_SEARCH_HALF_LIFE = 12
# Every hit of an AND query scores 100 and comes back in no meaningful order
# (docs/API_NOTES.md), so the tail of a conjunction search is not much worse
# than its head and decays gently.
CONJUNCTION_HALF_LIFE = 30
ARTIST_ALBUMS_HALF_LIFE = 3

CONJUNCTION_BOOST = 1.4
ARTIST_BASE_WEIGHT = 0.35
PEOPLE_WEIGHT = 1.2
LASTFM_WEIGHT = 0.8
LASTFM_TAG_WEIGHT = 1.0

# How many of the seed's recordings are offered to the similar-recordings
# endpoint (10 per call, ~200 results across seeds - more seeds only dilute).
SIMILAR_RECORDING_SEEDS = 20
# The ListenBrainz worker gives the MusicBrainz worker this long to finish
# the personnel hop before carrying on without the members' bands.
PERSONNEL_HOP_TIMEOUT = 120.0

# Relations under which the related artist is an act the seed's people play
# in (as opposed to a person), when read from the person's side.
_BAND_RELATIONS = frozenset({'member of band', 'founder', 'subgroup', 'collaboration'})
_SUPPORT_RELATIONS = frozenset({
    'supporting musician', 'instrumental supporting musician', 'vocal supporting musician',
})


@dataclass
class SeedContext:
    """What the candidate gathering learnt about the seed itself, for the
    kinship and co_listening axes: its full-width similar-artist set and the
    recordings its listeners play alongside its own, already resolved to
    release groups and artists."""
    neighbour_names: frozenset = frozenset()
    neighbour_mbids: frozenset = frozenset()
    similar_recordings: dict = field(default_factory=dict)     # {recording_mbid: {'score','release_group_mbid','artist_mbid'}}
    co_listening_by_rg: Counter = field(default_factory=Counter)      # release_group_mbid -> weighted hits
    co_listening_by_artist: Counter = field(default_factory=Counter)  # artist_mbid -> weighted hits


class Candidate:
    __slots__ = ('mbid', 'artist', 'title', 'artist_mbid', 'primary_type',
                 'secondary_types', 'weight', 'sources')

    def __init__(self, mbid, artist='', title='', artist_mbid='',
                 primary_type='', secondary_types=()):
        self.mbid = mbid
        self.artist = artist
        self.title = title
        self.artist_mbid = artist_mbid
        self.primary_type = primary_type
        self.secondary_types = tuple(secondary_types or ())
        self.weight = 0.0
        self.sources = set()

    def add(self, source, weight):
        self.sources.add(source)
        self.weight += weight

    @property
    def prefilter_score(self):
        # Breadth of agreement counts for more than any single source's rank.
        return self.weight * (1.0 + 0.35 * (len(self.sources) - 1))


class CandidatePool:
    """Every candidate seen so far, keyed by release-group mbid. Sources run
    on several threads and all add here, so the pool holds a lock."""

    def __init__(self):
        self._by_mbid = {}
        self._lock = threading.Lock()

    def add(self, mbid, source, weight, artist='', title='', artist_mbid='',
            primary_type='', secondary_types=()):
        if not mbid:
            return
        with self._lock:
            candidate = self._by_mbid.get(mbid)
            if candidate is None:
                candidate = Candidate(mbid, artist, title, artist_mbid,
                                      primary_type, secondary_types)
                self._by_mbid[mbid] = candidate
            else:
                candidate.artist = candidate.artist or artist
                candidate.title = candidate.title or title
                candidate.artist_mbid = candidate.artist_mbid or artist_mbid
                candidate.primary_type = candidate.primary_type or primary_type
                candidate.secondary_types = candidate.secondary_types or tuple(secondary_types or ())
            candidate.add(source, weight)

    def drop(self, mbid):
        with self._lock:
            self._by_mbid.pop(mbid, None)

    def get(self, mbid):
        with self._lock:
            return self._by_mbid.get(mbid)

    def ranked(self, limit=None):
        with self._lock:
            candidates = list(self._by_mbid.values())
        ordered = sorted(candidates, key=lambda c: c.prefilter_score, reverse=True)
        return ordered[:limit] if limit else ordered

    def __len__(self):
        with self._lock:
            return len(self._by_mbid)


def gather_sources_report(pool):
    """{source kind: how many candidates it contributed}, most first - the
    part of each source label before ':' ('tag', 'artist', 'people', ...)."""
    counts = Counter()
    for candidate in pool.ranked():
        for kind in {source.split(':', 1)[0] for source in candidate.sources}:
            counts[kind] += 1
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


# ---------------------------------------------------------------------------
# Small parsers over the raw payloads
# ---------------------------------------------------------------------------

def _decay(rank, half_life):
    return 1.0 / (1.0 + rank / float(half_life))


def _number(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _credit(release_group):
    """(name, mbid) of the first credited artist on a MusicBrainz search hit."""
    credits_list = release_group.get('artist-credit') or []
    if credits_list and isinstance(credits_list[0], dict):
        artist = credits_list[0].get('artist') or {}
        return (artist.get('name') or credits_list[0].get('name') or '',
                artist.get('id') or '')
    return '', ''


def _top_rg_fields(entry, artist_name='', artist_mbid=''):
    """The pool.add keyword arguments for one artist-catalogue entry (the
    ListenBrainz top-release-group shape); the artist we asked about stands
    in when the entry omits it."""
    entry = entry if isinstance(entry, dict) else {}
    group = entry.get('release_group') or {}
    artist = entry.get('artist') or {}
    artists = artist.get('artists') or []
    first = artists[0] if artists and isinstance(artists[0], dict) else {}
    return {
        'mbid': entry.get('release_group_mbid') or '',
        'title': group.get('name') or '',
        'artist': artist.get('name') or first.get('name') or artist_name,
        'artist_mbid': artist.get('artist_mbid') or first.get('artist_mbid') or artist_mbid,
        'primary_type': group.get('type') or '',
        'secondary_types': tuple(t for t in (group.get('secondary_types') or ()) if isinstance(t, str)),
    }


_STUDIO_PRIMARY_TYPES = frozenset({'album', 'ep'})

# One lock per artist, so two workers asking for the same catalogue at the
# same moment do not both pay for it. The ListenBrainz and Last.fm sources
# overlap heavily, which is exactly when that happens.
_CATALOGUE_LOCKS = {}
_CATALOGUE_LOCKS_GUARD = threading.Lock()


def _catalogue_lock(artist_mbid):
    with _CATALOGUE_LOCKS_GUARD:
        return _CATALOGUE_LOCKS.setdefault(artist_mbid, threading.Lock())


def artist_albums(services, artist_mbid, artist_name='', cache=None, limit=25):
    """An artist's albums, most-listened first, in the ListenBrainz
    top-release-group shape: [{release_group_mbid, release_group: {name,
    type, secondary_types, date}, artist: {name, artist_mbid},
    total_user_count, total_listen_count}].

    ListenBrainz's own top-release-groups endpoint answers when it can (it
    went auth-only in 2026, so mostly it cannot, and the client returns []).
    Otherwise MusicBrainz browses the artist's release groups - one request,
    cached for two months - and ListenBrainz's keyless bulk popularity call
    ranks them. Live records, compilations and singles are left out.
    """
    if cache is not None and artist_mbid in cache:
        return cache[artist_mbid]
    if cache is not None and artist_mbid:
        with _catalogue_lock(artist_mbid):
            # Whoever held the lock may have just filled it in.
            if artist_mbid in cache:
                return cache[artist_mbid]
            return _fetch_artist_albums(services, artist_mbid, artist_name, cache, limit)
    return _fetch_artist_albums(services, artist_mbid, artist_name, cache, limit)


def _fetch_artist_albums(services, artist_mbid, artist_name, cache, limit):
    listenbrainz = services.listenbrainz
    entries = []
    if listenbrainz is not None and artist_mbid:
        try:
            entries = [e for e in (listenbrainz.top_release_groups(artist_mbid) or [])
                       if isinstance(e, dict)]
        except ApiError:
            entries = []
    if not entries and services.musicbrainz is not None and artist_mbid:
        try:
            groups = services.musicbrainz.release_groups_by_artist(artist_mbid) or []
        except ApiError:
            groups = []
        kept = []
        for group in groups:
            if not isinstance(group, dict) or not group.get('id'):
                continue
            if (group.get('primary-type') or '').lower() not in _STUDIO_PRIMARY_TYPES:
                continue
            secondary = [t for t in (group.get('secondary-types') or []) if isinstance(t, str)]
            if any(t.lower() in NON_STUDIO_TYPES for t in secondary):
                continue
            kept.append((group, secondary))
        kept = kept[:limit]
        counts = {}
        if kept and listenbrainz is not None:
            try:
                counts = listenbrainz.popularity([group['id'] for group, _ in kept]) or {}
            except ApiError:
                counts = {}
        for group, secondary in kept:
            count = counts.get(group['id']) or {}
            entries.append({
                'release_group_mbid': group['id'],
                'release_group': {'name': group.get('title') or '',
                                  'type': group.get('primary-type') or '',
                                  'secondary_types': secondary,
                                  'date': group.get('first-release-date') or ''},
                'artist': {'name': artist_name, 'artist_mbid': artist_mbid},
                'total_user_count': int(_number(count.get('total_user_count'))),
                'total_listen_count': int(_number(count.get('total_listen_count'))),
            })
        entries.sort(key=lambda e: (-e['total_user_count'], e['release_group']['date']))
    if cache is not None:
        cache[artist_mbid] = entries
    return entries


def expandable_tags(top_tags, count):
    """The seed's tags worth searching by: subgenres and moods, not roots.
    A root genre ("rock", "electronic") matches most of recorded music, so
    a search on it, or a conjunction with it, is a random sample; the
    taxonomy's depth tells the two apart. Falls back to the plain top tags
    when the seed carries nothing but roots."""
    specific = [tag for tag in top_tags if tagmod.specificity(tag) >= 1.0]
    chosen = specific if len(specific) >= 2 else list(top_tags)
    return chosen[:count]


def _seed_artist_mbids(seed):
    mbids = {seed.artist_mbid} | set(getattr(seed, 'seed_artist_mbids', ()) or ())
    mbids.discard('')
    mbids.discard(None)
    return mbids


def personnel_split(seed):
    """(acts, people) from the seed's personnel graph, each {mbid: name},
    the seed artist itself left out.

    The features only carry the relation label, not the related artist's
    type, so the type is read off the relation and which side of it the seed
    is on: a person's 'member of band' points at a band, a group's at a
    member. Anything filed under people is looked up on MusicBrainz, which
    corrects the guess when it was wrong (a "person" that turns out to be a
    group simply becomes an act).
    """
    excluded = _seed_artist_mbids(seed)
    seed_is_person = (seed.artist_type or '').casefold() == 'person'
    acts, people = {}, {}
    for mbid, name in (seed.personnel or {}).items():
        if not mbid or mbid in excluded:
            continue
        relation = ((seed.personnel_relations or {}).get(mbid) or '').casefold()
        if relation == 'artist':
            continue
        name = name or mbid
        if seed_is_person:
            # Everything a person is related to is an act: their bands, their
            # aliases, the acts they played for.
            acts[mbid] = name
        elif relation in ('subgroup', 'collaboration', 'is person'):
            acts[mbid] = name
        else:
            people[mbid] = name
    return acts, people


def _acts_of(person_mbid, person_name, payload, excluded):
    """The bands and aliases one person is in, from their MusicBrainz artist
    lookup, as {mbid: name}. A payload that turns out to describe a group
    yields the group itself."""
    info = credits.artist_personnel(payload)
    if not info['mbid'] and not info['people']:
        return {}
    if info['type'] and info['type'].casefold() != 'person':
        return {person_mbid: info['name'] or person_name}
    acts = {}
    for mbid, entry in info['people'].items():
        if mbid in excluded or mbid == person_mbid:
            continue
        relation = (entry.get('relation') or '').casefold()
        is_person = (entry.get('type') or '').casefold() == 'person'
        if relation == 'is person' or (relation in _BAND_RELATIONS and not is_person):
            acts[mbid] = entry.get('name') or mbid
    return acts


# ---------------------------------------------------------------------------
# gather
# ---------------------------------------------------------------------------

def gather(seed, services, tags_to_expand=3, conjunction_tags=4, albums_per_tag=100,
           similar_artists=20, albums_per_artist=6, personnel_acts=8,
           similar_recordings=100, lastfm_similar=12, lastfm_tag_albums=12,
           album_cache=None, progress=None):
    """Build a CandidatePool around an already-enriched seed AlbumFeatures.

    Returns (pool, SeedContext). Every source catches ApiError and carries
    on, so a service being down costs its candidates and nothing else; the
    seed's own release group(s) are dropped at the end. progress, when given,
    is called as progress('candidates', done, total, label) on this thread
    only. album_cache memoises artist catalogues across a run.
    """
    pool = CandidatePool()
    context = SeedContext()
    listenbrainz = services.listenbrainz
    excluded = _seed_artist_mbids(seed)
    top_tags = expandable_tags(seed.top_tags, max(tags_to_expand, conjunction_tags))
    direct_acts, people = personnel_split(seed)
    album_cache = album_cache if album_cache is not None else {}
    # The MusicBrainz worker publishes the members' bands here in one
    # assignment before setting the event, so the ListenBrainz worker never
    # reads a dict that is still being filled.
    hop = {'acts': {}}
    hop_done = threading.Event()

    def add_artist_albums(artist_mbid, artist_name, source, scale):
        entries = artist_albums(services, artist_mbid, artist_name, cache=album_cache)
        for rank, entry in enumerate(entries[:albums_per_artist]):
            fields = _top_rg_fields(entry, artist_name, artist_mbid)
            pool.add(fields['mbid'], source, scale * _decay(rank, ARTIST_ALBUMS_HALF_LIFE),
                     artist=fields['artist'], title=fields['title'],
                     artist_mbid=fields['artist_mbid'], primary_type=fields['primary_type'],
                     secondary_types=fields['secondary_types'])

    def tag_search(tags):
        weights = [seed.profile.get(tag, 0.5) for tag in tags]
        if len(tags) == 1:
            source, scale, half_life = f'tag:{tags[0]}', weights[0], TAG_SEARCH_HALF_LIFE
        else:
            source = f'tags:{tags[0]}+{tags[1]}'
            scale = CONJUNCTION_BOOST * sum(weights) / len(weights)
            half_life = CONJUNCTION_HALF_LIFE
        try:
            results = services.musicbrainz.release_groups_by_tags(list(tags), limit=albums_per_tag) or []
        except ApiError:
            return
        for rank, release_group in enumerate(results):
            if not isinstance(release_group, dict):
                continue
            name, mbid = _credit(release_group)
            pool.add(release_group.get('id'), source, scale * _decay(rank, half_life),
                     artist=name, title=release_group.get('title') or '', artist_mbid=mbid,
                     primary_type=release_group.get('primary-type') or '',
                     secondary_types=tuple(release_group.get('secondary-types') or ()))

    def musicbrainz_job(report):
        searches = [(tag,) for tag in top_tags[:tags_to_expand]]
        searches += list(combinations(top_tags[:conjunction_tags], 2))
        lookups = list(people.items())[:personnel_acts]
        total, done = len(searches) + len(lookups), 0
        try:
            for tags in searches:
                report(done, total, 'tag search: ' + ' + '.join(tags))
                tag_search(tags)
                done += 1
            found = {}
            for mbid, name in lookups:
                report(done, total, f'bands of {name}')
                try:
                    payload = services.musicbrainz.artist(mbid)
                except ApiError:
                    payload = {}
                for act_mbid, act_name in _acts_of(mbid, name, payload, excluded).items():
                    found.setdefault(act_mbid, act_name)
                done += 1
            hop['acts'] = found
        finally:
            hop_done.set()
        report(done, total, 'done')

    def similar_tracks(report, done, total):
        seeds = [mbid for mbid in (seed.recording_mbids or []) if mbid][:SIMILAR_RECORDING_SEEDS]
        if not seeds:
            return
        report(done, total, 'tracks played alongside its own')
        try:
            entries = listenbrainz.similar_recordings(seeds) or []
        except ApiError:
            return
        # The same recording can answer several seed tracks; its strongest
        # tie is the one that matters.
        best = {}
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            mbid, score = entry.get('recording_mbid'), _number(entry.get('score'))
            if mbid and score > 0:
                best[mbid] = max(best.get(mbid, 0.0), score)
        ranked = sorted(best.items(), key=lambda item: (-item[1], item[0]))[:similar_recordings]
        if not ranked:
            return
        top_score = ranked[0][1]
        report(done + 1, total, f'albums of {len(ranked)} co-listened tracks')
        try:
            metadata = listenbrainz.recording_metadata([mbid for mbid, _ in ranked]) or {}
        except ApiError:
            return
        for mbid, score in ranked:
            meta = metadata.get(mbid) or {}
            release = meta.get('release') or {}
            artist_block = meta.get('artist') or {}
            artists = artist_block.get('artists') or []
            first = artists[0] if artists and isinstance(artists[0], dict) else {}
            release_group_mbid = release.get('release_group_mbid') or ''
            artist_mbid = first.get('artist_mbid') or ''
            if not release_group_mbid and not artist_mbid:
                continue
            weight = score / top_score
            context.similar_recordings[mbid] = {
                'score': score, 'release_group_mbid': release_group_mbid, 'artist_mbid': artist_mbid,
            }
            if artist_mbid:
                context.co_listening_by_artist[artist_mbid] += weight
            if release_group_mbid:
                context.co_listening_by_rg[release_group_mbid] += weight
                pool.add(release_group_mbid, 'tracks', weight,
                         artist=artist_block.get('name') or release.get('album_artist_name')
                         or first.get('name') or '',
                         title=release.get('name') or '', artist_mbid=artist_mbid)

    def listenbrainz_job(report):
        done, total = 0, 3 + len(direct_acts)
        report(done, total, f'listeners who like {seed.artist}')
        neighbours = []
        if seed.artist_mbid:
            try:
                neighbours = [n for n in (listenbrainz.similar_artists(seed.artist_mbid) or [])
                              if isinstance(n, dict)]
            except ApiError:
                neighbours = []
        # The full-width set is what the kinship axis wants; only the head
        # gets expanded into albums.
        context.neighbour_names = frozenset(
            (n.get('name') or n.get('artist_name') or '').strip().lower()
            for n in neighbours if (n.get('name') or n.get('artist_name'))
        )
        context.neighbour_mbids = frozenset(n['artist_mbid'] for n in neighbours if n.get('artist_mbid'))
        expand = [n for n in neighbours if n.get('artist_mbid')][:similar_artists]
        top_score = max((_number(n.get('score')) for n in expand), default=0.0) or 1.0
        done, total = done + 1, total + len(expand)
        for neighbour in expand:
            name = neighbour.get('name') or neighbour.get('artist_name') or neighbour['artist_mbid']
            report(done, total, f'albums by {name}')
            affinity = _number(neighbour.get('score')) / top_score
            add_artist_albums(neighbour['artist_mbid'], name, f'artist:{name}', ARTIST_BASE_WEIGHT + affinity)
            done += 1

        similar_tracks(report, done, total)
        done += 2

        seen_acts = set(excluded)

        def acts_albums(acts):
            nonlocal done, total
            for mbid, name in acts.items():
                if mbid in seen_acts:
                    continue
                seen_acts.add(mbid)
                report(done, total, f'albums by {name}')
                add_artist_albums(mbid, name, f'people:{name}', PEOPLE_WEIGHT)
                done += 1

        acts_albums(direct_acts)
        if people:
            report(done, total, 'waiting for the members\' bands')
            hop_done.wait(timeout=PERSONNEL_HOP_TIMEOUT)
        found = hop['acts']
        total += len([mbid for mbid in found if mbid not in seen_acts])
        acts_albums(found)
        report(done, total, 'done')

    def lastfm_job(report):
        lastfm = services.lastfm
        chart_tags = top_tags[:tags_to_expand]
        done, total = 0, 1 + len(chart_tags)
        report(done, total, f'Last.fm artists like {seed.artist}')
        try:
            similar = lastfm.similar_artists(seed.artist, limit=lastfm_similar) if seed.artist else []
        except KeyRejected:
            return
        except ApiError:
            similar = []
        similar = [s for s in similar or [] if isinstance(s, dict) and s.get('mbid')]
        done, total = done + 1, total + len(similar)
        for entry in similar:
            name = entry.get('name') or entry['mbid']
            report(done, total, f'albums by {name} (Last.fm)')
            add_artist_albums(entry['mbid'], name, f'lastfm:{name}',
                              LASTFM_WEIGHT * _number(entry.get('match')))
            done += 1
        # A chart artist's release groups serve every chart they appear in.
        by_artist = {}
        for tag in chart_tags:
            report(done, total, f'Last.fm tag chart: {tag}')
            try:
                hits = lastfm.tag_top_albums(tag, limit=lastfm_tag_albums) or []
            except KeyRejected:
                return
            except ApiError:
                hits = []
            for position, hit in enumerate(hits):
                if not isinstance(hit, dict):
                    continue
                artist_mbid = hit.get('artist_mbid') or ''
                if not artist_mbid or artist_mbid in excluded or not hit.get('name'):
                    continue
                if artist_mbid not in by_artist:
                    by_artist[artist_mbid] = artist_albums(
                        services, artist_mbid, hit.get('artist') or '', cache=album_cache)
                wanted = canonical_title(hit['name']).casefold()
                rank = max(int(_number(hit.get('rank')) or position + 1) - 1, 0)
                for entry in by_artist[artist_mbid]:
                    fields = _top_rg_fields(entry, hit.get('artist') or '', artist_mbid)
                    if fields['title'] and canonical_title(fields['title']).casefold() == wanted:
                        pool.add(fields['mbid'], f'lastfm_tag:{tag}',
                                 LASTFM_TAG_WEIGHT * _decay(rank, TAG_SEARCH_HALF_LIFE),
                                 artist=fields['artist'], title=fields['title'],
                                 artist_mbid=fields['artist_mbid'],
                                 primary_type=fields['primary_type'])
                        break
            done += 1
        report(done, total, 'done')

    jobs = {}
    if services.musicbrainz is not None:
        jobs['musicbrainz'] = musicbrainz_job
    else:
        # Nothing will publish the members' bands, so release the
        # ListenBrainz worker rather than let it wait out the timeout.
        hop_done.set()
    if listenbrainz is not None:
        jobs['listenbrainz'] = listenbrainz_job
    lastfm = getattr(services, 'lastfm', None)
    if lastfm is not None and getattr(lastfm, 'configured', False):
        jobs['lastfm'] = lastfm_job

    latest = {'done': 0, 'total': 0}

    def relay(stage, done, total, label):
        latest['done'], latest['total'] = done, total
        progress(stage, done, total, label)

    results = run_workers(jobs, progress=relay if progress else None, stage='candidates')
    for outcome in results.values():
        # ApiError is caught at every call site; anything else is a bug and
        # must not be silently mistaken for an empty neighbourhood.
        if isinstance(outcome, Exception) and not isinstance(outcome, ApiError):
            raise outcome

    pool.drop(seed.mbid)
    for mbid in getattr(seed, 'seed_mbids', ()) or ():
        pool.drop(mbid)
    if progress:
        progress('candidates', latest['total'], latest['total'], f'{len(pool)} candidates')
    return pool, context
