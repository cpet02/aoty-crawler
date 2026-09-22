"""Tests for the candidate sources, fully offline.

Stub services return canned payloads in the shapes docs/API_NOTES.md
records; what matters is that every one of the seven sources lands in the
pool under the right label with the documented weights, that a service
failing costs only its own candidates, that the ListenBrainz worker really
receives the bands the MusicBrainz worker found, and that progress never
leaves the calling thread.
"""

import importlib
import os
import sys
import threading
import time
import types

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def _leaf(name):
    """Import radius.<name> even while radius/__init__.py cannot load (it
    imports the whole engine; these tests only need a few leaves). A healthy
    package never reaches the fallback."""
    try:
        return importlib.import_module(f'radius.{name}')
    except ImportError:
        if 'radius' in sys.modules:
            raise
        package = types.ModuleType('radius')
        package.__path__ = [os.path.join(ROOT, 'radius')]
        sys.modules['radius'] = package
        return importlib.import_module(f'radius.{name}')


candidates = _leaf('candidates')
AlbumFeatures = _leaf('albums').AlbumFeatures
ApiError = _leaf('clients').ApiError
KeyRejected = _leaf('clients').KeyRejected

gather = candidates.gather
CandidatePool = candidates.CandidatePool
SeedContext = candidates.SeedContext


# ---------------------------------------------------------------------------
# Canned payloads
# ---------------------------------------------------------------------------

def mb_hit(mbid, artist, artist_mbid, title, secondary=None, primary='Album'):
    hit = {'id': mbid, 'title': title, 'score': 100, 'primary-type': primary,
           'artist-credit': [{'name': artist, 'artist': {'id': artist_mbid, 'name': artist}}]}
    if secondary:
        hit['secondary-types'] = list(secondary)
    return hit


def lb_rg(mbid, title, artist, artist_mbid, rg_type='Album'):
    return {'release_group_mbid': mbid, 'total_user_count': 1000, 'total_listen_count': 5000,
            'release_group': {'name': title, 'type': rg_type},
            'artist': {'name': artist, 'artist_mbid': artist_mbid}}


def mb_rel(rtype, mbid, name, atype):
    return {'type': rtype, 'target-type': 'artist', 'direction': 'forward',
            'artist': {'id': mbid, 'name': name, 'type': atype}}


TAG_RESULTS = {
    ('post-rock',): [
        mb_hit('rg-laughing-stock', 'Talk Talk', 'a-talktalk', 'Laughing Stock'),
        mb_hit('rg-rusty', 'Rodan', 'a-rodan', 'Rusty'),
        mb_hit('rg-live-thing', 'Some Band', 'a-some', 'Live Thing', secondary=['Live']),
    ],
    ('math rock',): [mb_hit('rg-rusty', 'Rodan', 'a-rodan', 'Rusty')],
    ('slowcore',): [mb_hit('rg-whatfunlifewas', 'Bedhead', 'a-bedhead', 'WhatFunLifeWas')],
    ('post-rock', 'math rock'): [
        mb_hit('rg-rusty', 'Rodan', 'a-rodan', 'Rusty'),
        mb_hit('rg-spiderland', 'Slint', 'a-slint', 'Spiderland'),
        mb_hit('rg-tweez', 'Slint', 'a-slint', 'Tweez'),
    ],
    ('post-rock', 'slowcore'): [mb_hit('rg-whatfunlifewas', 'Bedhead', 'a-bedhead', 'WhatFunLifeWas')],
}

ARTIST_PAYLOADS = {
    'p-pajo': {'id': 'p-pajo', 'name': 'David Pajo', 'type': 'Person', 'relations': [
        mb_rel('member of band', 'g-tortoise', 'Tortoise', 'Group'),
        mb_rel('member of band', 'a-slint', 'Slint', 'Group'),
        mb_rel('is person', 'p-papa-m', 'Papa M', 'Person'),
        mb_rel('instrumental supporting musician', 'g-interpol', 'Interpol', 'Group'),
    ]},
    'p-mcmahan': {'id': 'p-mcmahan', 'name': 'Brian McMahan', 'type': 'Person', 'relations': [
        mb_rel('member of band', 'g-for-carnation', 'The For Carnation', 'Group'),
    ]},
    'g-actually-a-band': {'id': 'g-actually-a-band', 'name': 'Actually a Band', 'type': 'Group',
                          'relations': [mb_rel('member of band', 'p-someone', 'Someone', 'Person')]},
}

TOP_RGS = {
    'a-slint': [lb_rg('rg-spiderland', 'Spiderland', 'Slint', 'a-slint'),
                lb_rg('rg-tweez', 'Tweez', 'Slint', 'a-slint')],
    'a-rodan': [lb_rg('rg-rusty', 'Rusty', 'Rodan', 'a-rodan'),
                lb_rg('rg-fifteen-quiet-years', 'Fifteen Quiet Years', 'Rodan', 'a-rodan', 'Compilation')],
    'a-bedhead': [lb_rg('rg-whatfunlifewas', 'WhatFunLifeWas', 'Bedhead', 'a-bedhead')],
    'a-talktalk': [lb_rg('rg-laughing-stock', 'Laughing Stock', 'Talk Talk', 'a-talktalk'),
                   lb_rg('rg-spirit-of-eden', 'Spirit of Eden', 'Talk Talk', 'a-talktalk')],
    'g-collab': [lb_rg('rg-collab-album', 'Collab Album', 'Slint Allstars', 'g-collab')],
    'g-tortoise': [lb_rg('rg-millions', 'Millions Now Living Will Never Die', 'Tortoise', 'g-tortoise')],
    'p-papa-m': [lb_rg('rg-shark-cage', 'Live From a Shark Cage', 'Papa M', 'p-papa-m')],
    'g-for-carnation': [lb_rg('rg-for-carnation', 'The For Carnation', 'The For Carnation', 'g-for-carnation')],
    'g-actually-a-band': [lb_rg('rg-band-album', 'Band Album', 'Actually a Band', 'g-actually-a-band')],
    'g-interpol': [lb_rg('rg-turn-on', 'Turn On the Bright Lights', 'Interpol', 'g-interpol')],
}

SIMILAR_RECORDINGS = [
    {'recording_mbid': 'rec-x', 'score': 40, 'reference_mbid': 'rec-breadcrumb', 'release_mbid': 'rel-x'},
    {'recording_mbid': 'rec-x', 'score': 30, 'reference_mbid': 'rec-nosferatu', 'release_mbid': 'rel-x'},
    {'recording_mbid': 'rec-y', 'score': 20, 'reference_mbid': 'rec-breadcrumb', 'release_mbid': 'rel-y'},
    {'recording_mbid': 'rec-z', 'score': 10, 'reference_mbid': 'rec-breadcrumb', 'release_mbid': 'rel-z'},
]

RECORDING_METADATA = {
    'rec-x': {'recording': {'name': 'Bible Silver Corner'},
              'release': {'release_group_mbid': 'rg-rusty', 'name': 'Rusty', 'mbid': 'rel-x'},
              'artist': {'name': 'Rodan', 'artists': [{'artist_mbid': 'a-rodan', 'name': 'Rodan'}]}},
    'rec-y': {'recording': {'name': 'Tron'},
              'release': {'release_group_mbid': 'rg-fifteen-quiet-years', 'name': 'Fifteen Quiet Years'},
              'artist': {'artists': [{'artist_mbid': 'a-rodan', 'name': 'Rodan'}]}},
    # rec-z is absent: ListenBrainz simply omits recordings it cannot resolve.
}


# ---------------------------------------------------------------------------
# Stub services
# ---------------------------------------------------------------------------

class StubMusicBrainz:
    def __init__(self, fail_search=False, artist_delay=0.0):
        self.queries = []
        self.artist_calls = []
        self.fail_search = fail_search
        self.artist_delay = artist_delay

    def release_groups_by_tags(self, tags, limit=100, primary_type='album'):
        tags = [tags] if isinstance(tags, str) else list(tags)
        self.queries.append((tuple(tags), limit))
        if self.fail_search:
            raise ApiError('search down')
        return [dict(hit) for hit in TAG_RESULTS.get(tuple(tags), [])]

    def artist(self, mbid):
        self.artist_calls.append(mbid)
        if self.artist_delay:
            time.sleep(self.artist_delay)
        if mbid not in ARTIST_PAYLOADS:
            raise ApiError('no such artist')
        return ARTIST_PAYLOADS[mbid]


class StubListenBrainz:
    def __init__(self, fail_similar=False, fail_recordings=False):
        self.top_rg_calls = []
        self.similar_recording_calls = []
        self.metadata_calls = []
        self.fail_similar = fail_similar
        self.fail_recordings = fail_recordings

    def similar_artists(self, artist_mbid, algorithm=None):
        if self.fail_similar:
            raise ApiError('labs down')
        if artist_mbid != 'a-slint':
            return []
        return [{'artist_mbid': 'a-rodan', 'name': 'Rodan', 'score': 900},
                {'artist_mbid': 'a-bedhead', 'name': 'Bedhead', 'score': 450},
                {'artist_mbid': '', 'name': 'Nobody Known', 'score': 100},
                {'artist_mbid': 'a-talktalk', 'name': 'Talk Talk', 'score': 90}]

    def top_release_groups(self, artist_mbid):
        self.top_rg_calls.append(artist_mbid)
        return [dict(entry) for entry in TOP_RGS.get(artist_mbid, [])]

    def similar_recordings(self, recording_mbids, algorithm=None):
        self.similar_recording_calls.append(list(recording_mbids))
        if self.fail_recordings:
            raise ApiError('labs down')
        return [dict(entry) for entry in SIMILAR_RECORDINGS]

    def recording_metadata(self, recording_mbids, inc='artist release'):
        self.metadata_calls.append(list(recording_mbids))
        return {mbid: RECORDING_METADATA[mbid] for mbid in recording_mbids if mbid in RECORDING_METADATA}


class StubLastFm:
    def __init__(self, configured=True, reject_key=False):
        self.configured = configured
        self.reject_key = reject_key
        self.calls = []

    def similar_artists(self, artist, limit=30):
        self.calls.append(('similar', artist, limit))
        if self.reject_key:
            raise KeyRejected('bad key')
        return [{'name': 'Rodan', 'mbid': 'a-rodan', 'match': 1.0},
                {'name': 'June of 44', 'mbid': '', 'match': 0.9},
                {'name': 'Bedhead', 'mbid': 'a-bedhead', 'match': 0.5}]

    def tag_top_albums(self, tag, limit=50):
        self.calls.append(('tag', tag, limit))
        if self.reject_key:
            raise KeyRejected('bad key')
        if tag != 'post-rock':
            return []
        return [{'name': 'Laughing Stock', 'mbid': '', 'artist': 'Talk Talk', 'artist_mbid': 'a-talktalk', 'rank': 1},
                {'name': 'Spirit of Eden (Remastered)', 'mbid': 'rel-1', 'artist': 'Talk Talk',
                 'artist_mbid': 'a-talktalk', 'rank': 2},
                {'name': 'Not On ListenBrainz', 'mbid': '', 'artist': 'Talk Talk', 'artist_mbid': 'a-talktalk', 'rank': 3},
                {'name': 'No Artist Mbid', 'mbid': '', 'artist': 'Whoever', 'artist_mbid': '', 'rank': 4},
                {'name': 'Spiderland', 'mbid': '', 'artist': 'Slint', 'artist_mbid': 'a-slint', 'rank': 5}]


class Services:
    def __init__(self, musicbrainz=None, listenbrainz=None, lastfm=None):
        self.musicbrainz = musicbrainz or StubMusicBrainz()
        self.listenbrainz = listenbrainz or StubListenBrainz()
        self.lastfm = lastfm
        self.wikidata = self.deezer = self.discogs = None


def make_seed(**overrides):
    base = dict(
        artist='Slint', title='Spiderland', mbid='rg-spiderland', artist_mbid='a-slint',
        artist_type='Group',
        profile={'post-rock': 1.0, 'math rock': 0.8, 'slowcore': 0.6, 'spoken word': 0.4,
                 'melancholic': 0.2},
        personnel={'a-slint': 'Slint', 'p-pajo': 'David Pajo', 'p-mcmahan': 'Brian McMahan',
                   'g-collab': 'Slint Allstars'},
        personnel_relations={'a-slint': 'artist', 'p-pajo': 'member of band',
                             'p-mcmahan': 'member of band', 'g-collab': 'collaboration'},
        recording_mbids=['rec-breadcrumb', 'rec-nosferatu'],
    )
    base.update(overrides)
    return AlbumFeatures(**base)


def sources_of(pool, mbid):
    candidate = pool.get(mbid)
    return set(candidate.sources) if candidate else set()


def decay(rank, half_life):
    return 1.0 / (1.0 + rank / half_life)


# ---------------------------------------------------------------------------
# Tag searches
# ---------------------------------------------------------------------------

def test_single_tag_searches_use_tag_weight_times_rank_decay():
    services = Services()
    pool, _ = gather(make_seed(), services)
    assert (('post-rock',), 100) in services.musicbrainz.queries
    assert (('math rock',), 100) in services.musicbrainz.queries
    assert (('slowcore',), 100) in services.musicbrainz.queries
    # Only the top 3 tags get a single search.
    assert ('spoken word',) not in [tags for tags, _ in services.musicbrainz.queries]

    laughing = pool.get('rg-laughing-stock')
    assert 'tag:post-rock' in laughing.sources
    rusty = pool.get('rg-rusty')
    assert {'tag:post-rock', 'tag:math rock'} <= rusty.sources
    # Tag hits alone: rank 0 of post-rock (weight 1.0) is 1.0, and the head
    # of a search outweighs its tail.
    pool_single, _ = gather(make_seed(artist_mbid='', personnel={}, recording_mbids=[]),
                            Services(), conjunction_tags=0)
    head = pool_single.get('rg-laughing-stock').weight
    tail = pool_single.get('rg-live-thing').weight
    assert head == pytest.approx(1.0)
    assert tail == pytest.approx(decay(2, candidates.TAG_SEARCH_HALF_LIFE))
    assert head > tail


def test_search_hits_keep_primary_and_secondary_types():
    pool, _ = gather(make_seed(), Services())
    live = pool.get('rg-live-thing')
    assert live.primary_type == 'Album'
    assert live.secondary_types == ('Live',)
    assert pool.get('rg-laughing-stock').secondary_types == ()


def test_conjunction_queries_cover_every_pair_of_the_top_four_tags():
    services = Services()
    pool, _ = gather(make_seed(), services)
    pairs = {frozenset(tags) for tags, _ in services.musicbrainz.queries if len(tags) == 2}
    # 'spoken word' is a root genre of the taxonomy, so it is skipped and
    # the next specific tag takes its place in the top four.
    top4 = ['post-rock', 'math rock', 'slowcore', 'melancholic']
    expected = {frozenset((a, b)) for i, a in enumerate(top4) for b in top4[i + 1:]}
    assert pairs == expected
    assert len(pairs) == 6
    # Weight: 1.4 x mean tag weight x rank decay, under the 'tags:a+b' label.
    whatfun = pool.get('rg-whatfunlifewas')
    assert 'tags:post-rock+slowcore' in whatfun.sources
    pool_conj, _ = gather(make_seed(artist_mbid='', personnel={}, recording_mbids=[]),
                          Services(), tags_to_expand=0)
    only_conj = pool_conj.get('rg-whatfunlifewas')
    assert only_conj.sources == {'tags:post-rock+slowcore'}
    assert only_conj.weight == pytest.approx(1.4 * (1.0 + 0.6) / 2)
    tweez = pool_conj.get('rg-tweez')   # rank 2 of post-rock+math rock
    assert tweez.weight == pytest.approx(1.4 * 0.9 * decay(2, candidates.CONJUNCTION_HALF_LIFE))
    assert pool_conj.get('rg-rusty').weight > tweez.weight


# ---------------------------------------------------------------------------
# ListenBrainz: similar artists, similar recordings, personnel acts
# ---------------------------------------------------------------------------

def test_similar_artists_expand_to_top_albums_with_affinity_weights():
    services = Services()
    pool, context = gather(make_seed(), services, similar_artists=2)
    rusty = pool.get('rg-rusty')
    assert 'artist:Rodan' in rusty.sources
    fifteen = pool.get('rg-fifteen-quiet-years')
    assert 'artist:Rodan' in fifteen.sources
    # Rodan is the top neighbour (affinity 1): 0.35 + 1 at rank 0, then rank decay.
    pool_only, _ = gather(make_seed(profile={}, personnel={}, recording_mbids=[]),
                          Services(), similar_artists=2)
    assert pool_only.get('rg-rusty').weight == pytest.approx(1.35)
    assert pool_only.get('rg-fifteen-quiet-years').weight == pytest.approx(
        1.35 * decay(1, candidates.ARTIST_ALBUMS_HALF_LIFE))
    assert pool_only.get('rg-whatfunlifewas').weight == pytest.approx(0.35 + 450 / 900)
    # Only the top `similar_artists` neighbours are expanded...
    assert 'a-talktalk' not in services.listenbrainz.top_rg_calls
    # ...but the context keeps the full-width neighbour set.
    assert context.neighbour_names == {'rodan', 'bedhead', 'nobody known', 'talk talk'}
    assert context.neighbour_mbids == {'a-rodan', 'a-bedhead', 'a-talktalk'}


def test_similar_recordings_fill_context_counters_and_tracks_source():
    services = Services()
    pool, context = gather(make_seed(), services)
    assert services.listenbrainz.similar_recording_calls == [['rec-breadcrumb', 'rec-nosferatu']]
    assert services.listenbrainz.metadata_calls == [['rec-x', 'rec-y', 'rec-z']]
    # rec-x keeps its strongest tie (40, not 30); rec-z has no metadata and is left out.
    assert set(context.similar_recordings) == {'rec-x', 'rec-y'}
    assert context.similar_recordings['rec-x'] == {
        'score': 40, 'release_group_mbid': 'rg-rusty', 'artist_mbid': 'a-rodan'}
    assert context.co_listening_by_rg['rg-rusty'] == pytest.approx(1.0)
    assert context.co_listening_by_rg['rg-fifteen-quiet-years'] == pytest.approx(0.5)
    assert context.co_listening_by_artist == {'a-rodan': pytest.approx(1.5)}
    assert 'tracks' in pool.get('rg-rusty').sources
    pool_only, _ = gather(make_seed(profile={}, personnel={}, artist_mbid=''), Services())
    assert pool_only.get('rg-rusty').sources == {'tracks'}
    assert pool_only.get('rg-rusty').weight == pytest.approx(1.0)
    assert pool_only.get('rg-fifteen-quiet-years').weight == pytest.approx(0.5)


def test_similar_recordings_are_capped_and_seeds_limited():
    services = Services()
    seed = make_seed(recording_mbids=[f'rec-{i}' for i in range(40)])
    gather(seed, services, similar_recordings=1)
    assert len(services.listenbrainz.similar_recording_calls[0]) == candidates.SIMILAR_RECORDING_SEEDS
    assert services.listenbrainz.metadata_calls == [['rec-x']]


def test_personnel_acts_come_from_direct_groups_and_the_member_second_hop():
    services = Services(musicbrainz=StubMusicBrainz(artist_delay=0.2))
    pool, _ = gather(make_seed(), services)
    # The seed artist's own members are looked up (Person entries), the
    # collaboration act is not (it is an act already), nor is the artist.
    assert services.musicbrainz.artist_calls == ['p-pajo', 'p-mcmahan']
    # Direct act:
    assert 'people:Slint Allstars' in sources_of(pool, 'rg-collab-album')
    # Second hop: Pajo's band and alias, McMahan's band; the seed artist is
    # not an act, and a supporting-musician credit is not a band.
    assert 'people:Tortoise' in sources_of(pool, 'rg-millions')
    assert 'people:Papa M' in sources_of(pool, 'rg-shark-cage')
    assert 'people:The For Carnation' in sources_of(pool, 'rg-for-carnation')
    assert pool.get('rg-turn-on') is None
    calls = services.listenbrainz.top_rg_calls
    assert 'a-slint' not in calls
    assert calls.index('g-collab') < calls.index('g-tortoise')
    pool_only, _ = gather(make_seed(profile={}, artist_mbid='', recording_mbids=[]),
                          Services())
    assert pool_only.get('rg-millions').weight == pytest.approx(1.2)
    assert pool_only.get('rg-millions').sources == {'people:Tortoise'}


def test_personnel_lookups_are_capped():
    services = Services()
    pool, _ = gather(make_seed(), services, personnel_acts=1)
    assert services.musicbrainz.artist_calls == ['p-pajo']
    assert pool.get('rg-millions') is not None
    assert pool.get('rg-for-carnation') is None


def test_person_seed_treats_its_bands_as_direct_acts_without_lookups():
    services = Services()
    seed = make_seed(artist='David Pajo', mbid='rg-papa-m-album', artist_mbid='p-pajo',
                     artist_type='Person', profile={}, recording_mbids=[],
                     personnel={'p-pajo': 'David Pajo', 'g-tortoise': 'Tortoise', 'p-papa-m': 'Papa M'},
                     personnel_relations={'p-pajo': 'artist', 'g-tortoise': 'member of band',
                                          'p-papa-m': 'is person'})
    pool, _ = gather(seed, services)
    assert services.musicbrainz.artist_calls == []
    assert 'people:Tortoise' in sources_of(pool, 'rg-millions')
    assert 'people:Papa M' in sources_of(pool, 'rg-shark-cage')


def test_a_personnel_entry_that_is_really_a_group_becomes_an_act():
    services = Services()
    seed = make_seed(profile={}, recording_mbids=[],
                     personnel={'a-slint': 'Slint', 'g-actually-a-band': 'Actually a Band'},
                     personnel_relations={'a-slint': 'artist', 'g-actually-a-band': 'member of band'})
    pool, _ = gather(seed, services)
    assert services.musicbrainz.artist_calls == ['g-actually-a-band']
    assert 'people:Actually a Band' in sources_of(pool, 'rg-band-album')
    assert 'p-someone' not in services.listenbrainz.top_rg_calls


# ---------------------------------------------------------------------------
# Last.fm
# ---------------------------------------------------------------------------

def test_lastfm_sources_when_configured():
    # MusicBrainz search and ListenBrainz similar artists are switched off so
    # only the two Last.fm sources can put anything in the pool.
    services = Services(musicbrainz=StubMusicBrainz(fail_search=True),
                        listenbrainz=StubListenBrainz(fail_similar=True),
                        lastfm=StubLastFm(configured=True))
    pool, _ = gather(make_seed(profile={'post-rock': 1.0}, personnel={}, recording_mbids=[]),
                     services)
    assert ('similar', 'Slint', 12) in services.lastfm.calls
    assert ('tag', 'post-rock', 12) in services.lastfm.calls
    # Similar artists with an mbid, weighted 0.8 x match x rank decay.
    rusty = pool.get('rg-rusty')
    assert rusty.sources == {'lastfm:Rodan'}
    assert rusty.weight == pytest.approx(0.8)
    assert pool.get('rg-whatfunlifewas').weight == pytest.approx(0.8 * 0.5)
    assert not any(s.startswith('lastfm:June') for c in pool.ranked() for s in c.sources)
    # Tag chart hits matched to the artist's ListenBrainz release groups by
    # canonical title (edition noise stripped), weighted by chart rank.
    laughing = pool.get('rg-laughing-stock')
    assert laughing.sources == {'lastfm_tag:post-rock'}
    assert laughing.weight == pytest.approx(1.0)
    spirit = pool.get('rg-spirit-of-eden')
    assert spirit.sources == {'lastfm_tag:post-rock'}
    assert spirit.weight == pytest.approx(decay(1, candidates.TAG_SEARCH_HALF_LIFE))
    assert spirit.artist_mbid == 'a-talktalk'
    # One ListenBrainz lookup per chart artist, and none for the seed artist.
    assert services.listenbrainz.top_rg_calls.count('a-talktalk') == 1
    assert 'a-slint' not in services.listenbrainz.top_rg_calls


def test_lastfm_sources_are_skipped_when_unconfigured():
    for lastfm in (StubLastFm(configured=False), None):
        services = Services(lastfm=lastfm)
        pool, _ = gather(make_seed(), services)
        if lastfm is not None:
            assert lastfm.calls == []
        labels = {s for c in pool.ranked() for s in c.sources}
        assert not any(s.startswith('lastfm') for s in labels)
        assert len(pool) > 0


def test_a_rejected_lastfm_key_stops_only_the_lastfm_sources():
    services = Services(lastfm=StubLastFm(configured=True, reject_key=True))
    pool, _ = gather(make_seed(), services)
    labels = {s for c in pool.ranked() for s in c.sources}
    assert not any(s.startswith('lastfm') for s in labels)
    assert 'tag:post-rock' in labels and 'artist:Rodan' in labels
    assert services.lastfm.calls == [('similar', 'Slint', 12)]


# ---------------------------------------------------------------------------
# Failure isolation, seed dropping, progress
# ---------------------------------------------------------------------------

def test_api_error_in_one_source_does_not_abort_the_others():
    services = Services(musicbrainz=StubMusicBrainz(fail_search=True))
    pool, context = gather(make_seed(), services)
    labels = {s for c in pool.ranked() for s in c.sources}
    assert not any(s.startswith('tag') for s in labels)
    assert 'artist:Rodan' in labels
    assert 'people:Tortoise' in labels
    assert 'tracks' in labels

    services = Services(listenbrainz=StubListenBrainz(fail_similar=True, fail_recordings=True))
    pool, context = gather(make_seed(), services)
    labels = {s for c in pool.ranked() for s in c.sources}
    assert 'tag:post-rock' in labels
    assert 'people:Tortoise' in labels
    assert not any(s.startswith('artist:') for s in labels)
    assert 'tracks' not in labels
    assert context.neighbour_names == frozenset()
    assert context.co_listening_by_rg == {}


def test_unexpected_exceptions_are_not_swallowed():
    class Broken(StubListenBrainz):
        def similar_artists(self, artist_mbid, algorithm=None):
            raise TypeError('bug')

    with pytest.raises(TypeError):
        gather(make_seed(), Services(listenbrainz=Broken()))


def test_the_seeds_own_release_groups_are_dropped():
    pool, _ = gather(make_seed(), Services())
    assert pool.get('rg-spiderland') is None
    # Other records by the seed artist stay: that filter belongs to the engine.
    assert pool.get('rg-tweez') is not None
    blend = make_seed(mbid='', artist_mbid='', seed_mbids=('rg-spiderland', 'rg-tweez'),
                      seed_artist_mbids=('a-slint',))
    pool, _ = gather(blend, Services())
    assert pool.get('rg-spiderland') is None
    assert pool.get('rg-tweez') is None
    assert pool.get('rg-rusty') is not None


def test_progress_is_invoked_on_the_calling_thread_with_fetch_labels():
    caller = threading.get_ident()
    seen = []

    def progress(stage, done, total, label):
        seen.append((threading.get_ident(), stage, done, total, label))

    services = Services(lastfm=StubLastFm(configured=True))
    pool, _ = gather(make_seed(), services, progress=progress)
    assert seen
    assert all(ident == caller for ident, *_ in seen)
    assert all(stage == 'candidates' for _, stage, *_ in seen)
    labels = [label for *_, label in seen]
    assert any(label.startswith('musicbrainz: tag search: post-rock') for label in labels)
    assert any(label == 'musicbrainz: tag search: post-rock + math rock' for label in labels)
    assert any(label == 'musicbrainz: bands of David Pajo' for label in labels)
    assert any(label == 'listenbrainz: albums by Rodan' for label in labels)
    assert any(label == 'listenbrainz: tracks played alongside its own' for label in labels)
    assert any(label == 'listenbrainz: albums by Tortoise' for label in labels)
    assert any(label == 'lastfm: Last.fm tag chart: post-rock' for label in labels)
    assert labels[-1] == f'{len(pool)} candidates'
    assert seen[-1][2] == seen[-1][3] > 0


def test_gather_works_without_progress():
    pool, context = gather(make_seed(), Services())
    assert len(pool) > 0
    assert isinstance(context, SeedContext)


# ---------------------------------------------------------------------------
# The pool and the report
# ---------------------------------------------------------------------------

def test_pool_add_is_safe_across_threads():
    pool = CandidatePool()

    def worker(index):
        for _ in range(500):
            pool.add('rg-x', f'source:{index}', 0.5, artist='A', title='T')

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    candidate = pool.get('rg-x')
    assert candidate.weight == pytest.approx(4 * 500 * 0.5)
    assert candidate.sources == {f'source:{i}' for i in range(4)}
    assert len(pool) == 1


def test_pool_keeps_first_metadata_and_fills_blanks():
    pool = CandidatePool()
    pool.add('rg-1', 'tag:a', 1.0, artist='', title='Album', primary_type='')
    pool.add('rg-1', 'artist:x', 0.5, artist='Band', title='Other', artist_mbid='a-1',
             primary_type='Album', secondary_types=('Live',))
    pool.add('', 'tag:a', 1.0)
    candidate = pool.get('rg-1')
    assert (candidate.artist, candidate.title, candidate.artist_mbid) == ('Band', 'Album', 'a-1')
    assert candidate.primary_type == 'Album'
    assert candidate.secondary_types == ('Live',)
    assert candidate.weight == pytest.approx(1.5)
    assert candidate.prefilter_score == pytest.approx(1.5 * 1.35)
    assert len(pool) == 1
    assert pool.ranked() == [candidate]
    pool.drop('rg-1')
    assert len(pool) == 0


def test_gather_sources_report_groups_by_label_prefix():
    pool = CandidatePool()
    pool.add('rg-1', 'tag:post-rock', 1.0)
    pool.add('rg-1', 'tag:slowcore', 1.0)
    pool.add('rg-1', 'artist:Rodan', 1.0)
    pool.add('rg-2', 'tags:post-rock+slowcore', 1.0)
    pool.add('rg-3', 'tracks', 1.0)
    pool.add('rg-4', 'tag:slowcore', 1.0)
    report = candidates.gather_sources_report(pool)
    assert report == {'tag': 2, 'artist': 1, 'tags': 1, 'tracks': 1}
    assert list(report) == ['tag', 'artist', 'tags', 'tracks']
    assert candidates.gather_sources_report(CandidatePool()) == {}


def test_seed_context_defaults_are_independent():
    first, second = SeedContext(), SeedContext()
    first.co_listening_by_rg['x'] += 1
    first.similar_recordings['r'] = {}
    assert second.co_listening_by_rg == {}
    assert second.similar_recordings == {}
    assert second.neighbour_names == frozenset()
