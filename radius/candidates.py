"""Candidate generation — deciding which albums are even worth scoring.

You can't fingerprint all of recorded music, so the seed picks its own
neighbourhood. Two sources, deliberately different in character:

* its prominent tags, via MusicBrainz release-group search — catches records
  that share the seed's descriptive vocabulary but have no connection to its
  artist, and
* ListenBrainz's collaborative similar artists, whose own most-listened
  albums come back in one request each — catches records that listeners
  themselves associate with it, including ones no tag vocabulary would link.

An album surfacing from several of those neighbourhoods at once is prima
facie closer, so the count of independent sources becomes the prefilter that
decides who gets fully fingerprinted — and it survives into the scoring as
the `co_tagging` axis.

Everything here keys on release-group mbids, which is what makes the bulk
metadata and popularity lookups possible later.
"""

from .clients import ApiError


class Candidate:
    __slots__ = ('mbid', 'artist', 'title', 'artist_mbid', 'weight', 'sources')

    def __init__(self, mbid, artist='', title='', artist_mbid=''):
        self.mbid = mbid
        self.artist = artist
        self.title = title
        self.artist_mbid = artist_mbid
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
    def __init__(self):
        self._by_mbid = {}

    def add(self, mbid, source, weight, artist='', title='', artist_mbid=''):
        if not mbid:
            return
        candidate = self._by_mbid.get(mbid)
        if candidate is None:
            candidate = Candidate(mbid, artist, title, artist_mbid)
            self._by_mbid[mbid] = candidate
        else:
            candidate.artist = candidate.artist or artist
            candidate.title = candidate.title or title
            candidate.artist_mbid = candidate.artist_mbid or artist_mbid
        candidate.add(source, weight)

    def drop(self, mbid):
        self._by_mbid.pop(mbid, None)

    def get(self, mbid):
        return self._by_mbid.get(mbid)

    def ranked(self, limit=None):
        ordered = sorted(
            self._by_mbid.values(), key=lambda c: c.prefilter_score, reverse=True
        )
        return ordered[:limit] if limit else ordered

    def __len__(self):
        return len(self._by_mbid)


def _credit_name(release_group):
    credits = release_group.get('artist-credit') or []
    if credits and isinstance(credits[0], dict):
        return (credits[0].get('artist') or {}).get('name') or credits[0].get('name') or ''
    return ''


def _credit_mbid(release_group):
    credits = release_group.get('artist-credit') or []
    if credits and isinstance(credits[0], dict):
        return (credits[0].get('artist') or {}).get('id') or ''
    return ''


def gather(seed, musicbrainz, listenbrainz, tags_to_expand=6,
           albums_per_tag=60, similar_artists=25, albums_per_artist=6,
           local_albums=None, progress=None):
    """Build a CandidatePool around a seed AlbumFeatures.

    Returns (pool, neighbour_names) — the neighbour set is the seed artist's
    own collaborative similar artists, which the `neighbours` axis reuses.
    """
    pool = CandidatePool()
    top_tags = seed.top_tags[:tags_to_expand]
    steps = [('tag', tag) for tag in top_tags] + [('similar', seed.artist)]
    neighbours = []

    def report(index, label):
        if progress:
            progress(index, len(steps), label)

    for index, (kind, value) in enumerate(steps):
        if kind == 'tag':
            report(index, f'tag: {value}')
            tag_weight = seed.profile.get(value, 0.5)
            try:
                results = musicbrainz.release_groups_by_tag(value, limit=albums_per_tag)
            except ApiError:
                continue
            for rank, release_group in enumerate(results):
                # Rank decay: the head of a tag search is far more on-topic
                # than its tail, which drifts toward whatever is popular.
                decay = 1.0 / (1.0 + rank / 12.0)
                pool.add(
                    release_group.get('id'), source=f'tag:{value}',
                    weight=tag_weight * decay,
                    artist=_credit_name(release_group),
                    title=release_group.get('title') or '',
                    artist_mbid=_credit_mbid(release_group),
                )
        else:
            report(index, f'listeners who like {value}')
            if not seed.artist_mbid:
                continue
            neighbours = listenbrainz.similar_artists(seed.artist_mbid)[:similar_artists]
            top_score = max(
                (float(n.get('score') or 0) for n in neighbours), default=0.0
            ) or 1.0
            for neighbour in neighbours:
                artist_mbid = neighbour.get('artist_mbid')
                name = neighbour.get('name') or neighbour.get('artist_name') or ''
                if not artist_mbid:
                    continue
                if progress:
                    progress(index, len(steps), f'albums by {name}')
                affinity = float(neighbour.get('score') or 0) / top_score
                for rank, entry in enumerate(
                    listenbrainz.top_release_groups(artist_mbid)[:albums_per_artist]
                ):
                    mbid = entry.get('release_group_mbid')
                    group = entry.get('release_group') or {}
                    decay = 1.0 / (1.0 + rank / 3.0)
                    pool.add(
                        mbid, source=f'artist:{name}',
                        weight=(0.35 + affinity) * decay,
                        artist=(entry.get('artist') or {}).get('name') or name,
                        title=group.get('name') or '',
                        artist_mbid=artist_mbid,
                    )

    for album in local_albums or []:
        mbid = album.get('mbid') or album.get('release_group_mbid')
        if mbid:
            pool.add(mbid, source='local', weight=0.5,
                     artist=album.get('artist_name') or '',
                     title=album.get('title') or '')

    pool.drop(seed.mbid)
    if progress:
        progress(len(steps), len(steps), f'{len(pool)} candidates')

    neighbour_names = frozenset(
        (n.get('name') or n.get('artist_name') or '').strip().lower()
        for n in neighbours if (n.get('name') or n.get('artist_name'))
    )
    return pool, neighbour_names
