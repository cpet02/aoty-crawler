"""Offline end-to-end tests for the engine.

A small fictional neighbourhood around Spiderland, served by stub clients
that implement every method the engine and the candidate sources call, so
the whole pipeline - seed resolution and enrichment, seven candidate
sources, bulk fingerprinting, kinship, crowd tags, the deep MusicBrainz
lookups, Deezer / Wikidata / Discogs / Last.fm statistics, rescoring - runs
with no network and no key.
"""

import json
import os
import sys
import threading

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from radius import config
from radius.clients import ApiError, KeyRejected
from radius.engine import (
    SeedNotFound, Services, find_similar, parse_seed_text, search_albums,
)

# ---------------------------------------------------------------------------
# The fictional universe
# ---------------------------------------------------------------------------

# mbid -> (artist, artist mbid, title, year, primary type, secondary types,
#          [(tag, count, is_genre)], listeners, listens, engineer, label)
ALBUMS = {
    'rg-seed': ('Slint', 'a-slint', 'Spiderland', 1991, 'Album', [],
                [('post-rock', 9, True), ('math rock', 6, True), ('slowcore', 4, False), ('rock', 3, True)],
                5000, 150000, 'Brian Paulson', 'Touch and Go'),
    'rg-rodan': ('Rodan', 'a-rodan', 'Rusty', 1994, 'Album', [],
                 [('post-rock', 5, True), ('math rock', 4, True), ('post-hardcore', 3, True)],
                 3000, 60000, 'Brian Paulson', 'Quarterstick'),
    'rg-tortoise': ('Tortoise', 'a-tortoise', 'TNT', 1998, 'Album', [],
                    [('post-rock', 8, True), ('jazz', 2, True)],
                    8000, 120000, 'John McEntire', 'Thrill Jockey'),
    'rg-tortoise2': ('Tortoise', 'a-tortoise', 'Millions Now Living Will Never Die', 1996, 'Album', [],
                     [('post-rock', 7, True)], 6000, 90000, 'John McEntire', 'Thrill Jockey'),
    'rg-codeine': ('Codeine', 'a-codeine', 'Frigid Stars', 1990, 'Album', [],
                   [('slowcore', 6, False), ('indie rock', 3, True)],
                   2500, 70000, 'Mike McMackin', 'Sub Pop'),
    'rg-rodan-live': ('Rodan', 'a-rodan', 'Live at Lounge Ax', 1995, 'Album', ['Live'],
                      [('post-rock', 2, True)], 400, 4000, '', 'Quarterstick'),
    'rg-single': ('Codeine', 'a-codeine', 'Realize', 1992, 'Single', [],
                  [('slowcore', 1, False)], 300, 900, '', 'Sub Pop'),
    'rg-untagged': ('Nobody', 'a-nobody', 'Blank', 2001, 'Album', [], [], 10, 20, '', ''),
    'rg-pop': ('Big Pop Act', 'a-pop', 'Stadium', 2015, 'Album', [],
               [('pop', 9, True), ('rock', 5, True)], 900000, 30000000, 'Max Martin', 'Major'),
    'rg-talk': ('Talk Talk', 'a-talk', 'Laughing Stock', 1991, 'Album', [],
                [('post-rock', 6, True), ('art rock', 5, True)],
                20000, 500000, 'Phill Brown', 'Verve'),
}

# artist mbid -> (name, type, area, begin year, member person mbids | bands)
ARTISTS = {
    'a-slint': ('Slint', 'Group', 'United States', 1986, ['p-pajo', 'p-mcmahan']),
    'a-rodan': ('Rodan', 'Group', 'United States', 1992, ['p-noble']),
    'a-tortoise': ('Tortoise', 'Group', 'United States', 1990, ['p-pajo', 'p-mcentire']),
    'a-codeine': ('Codeine', 'Group', 'United States', 1989, ['p-engle']),
    'a-nobody': ('Nobody', 'Group', 'United States', 2000, []),
    'a-pop': ('Big Pop Act', 'Person', 'United States', 2010, []),
    'a-talk': ('Talk Talk', 'Group', 'United Kingdom', 1981, ['p-hollis']),
    'p-pajo': ('David Pajo', 'Person', 'United States', 1986, ['a-slint', 'a-tortoise']),
    'p-mcmahan': ('Brian McMahan', 'Person', 'United States', 1986, ['a-slint']),
    'p-noble': ('Jason Noble', 'Person', 'United States', 1992, ['a-rodan']),
    'p-mcentire': ('John McEntire', 'Person', 'United States', 1990, ['a-tortoise']),
    'p-engle': ('Stephen Immerwahr', 'Person', 'United States', 1989, ['a-codeine']),
    'p-hollis': ('Mark Hollis', 'Person', 'United Kingdom', 1981, ['a-talk']),
}

SIMILAR_ARTISTS = {
    'a-slint': [('a-rodan', 900), ('a-codeine', 800), ('a-tortoise', 700), ('a-pop', 100)],
    'a-rodan': [('a-slint', 900), ('a-codeine', 500), ('a-tortoise', 400)],
    'a-tortoise': [('a-slint', 700), ('a-rodan', 400)],
    'a-codeine': [('a-slint', 800), ('a-rodan', 500)],
    'a-talk': [('a-slint', 300), ('a-codeine', 200)],
    'a-pop': [('a-nobody', 10)],
}

# Recordings people play alongside the seed's own: two Codeine tracks and
# one by Rodan.
SIMILAR_RECORDINGS = [('rec-rg-codeine-0', 50), ('rec-rg-codeine-1', 40), ('rec-rg-rodan-1', 30)]

WIKIDATA = {'rg-seed': 'Q545227', 'rg-rodan': 'Q900001'}
DISCOGS = {'rg-seed': '38099'}


def _album(mbid):
    return ALBUMS[mbid]


def _artist_name(mbid):
    return ARTISTS[mbid][0]


def _search_hit(mbid):
    artist, artist_mbid, title, year, ptype, secondary, tags, *_ = _album(mbid)
    hit = {
        'id': mbid, 'title': title, 'primary-type': ptype, 'score': 100,
        'first-release-date': f'{year}-01-01',
        'artist-credit': [{'name': artist, 'artist': {'id': artist_mbid, 'name': artist}}],
        'tags': [{'name': t, 'count': c} for t, c, _ in tags],
    }
    if secondary:
        hit['secondary-types'] = list(secondary)
    return hit


def _recording_relations(mbid):
    artist, artist_mbid, title, year, ptype, secondary, tags, listeners, listens, engineer, label = _album(mbid)
    relations = []
    if engineer:
        relations.append({
            'type': 'engineer', 'target-type': 'artist', 'direction': 'backward',
            'artist': {'id': f'eng-{engineer.lower()}', 'name': engineer, 'type': 'Person'},
            'attributes': [],
        })
    relations.append({
        'type': 'recorded at', 'target-type': 'place', 'direction': 'backward',
        'place': {'id': f'place-{label}', 'name': f'{label} Studio'},
    })
    return relations


class StubMusicBrainz:
    calls_made = 0
    cache_hits = 0

    def __init__(self):
        self.lookups = {'release_group': 0, 'release': 0, 'artist': 0}
        self.fail_release_group_for = set()

    def find_album(self, artist=None, album=None, query=None, limit=10):
        hits = []
        for mbid, data in ALBUMS.items():
            if artist and album:
                if data[0].casefold() == artist.casefold() and data[2].casefold() == album.casefold():
                    hits.append(_search_hit(mbid))
            elif query and query.casefold() in f'{data[0]} {data[2]}'.casefold():
                hits.append(_search_hit(mbid))
        return hits[:limit]

    def release_groups_by_tags(self, tags, limit=100, primary_type='album'):
        wanted = set(tags)
        hits = []
        for mbid, data in ALBUMS.items():
            names = {t for t, _, _ in data[6]}
            if wanted <= names and (not primary_type or data[4].lower() == primary_type):
                hits.append(_search_hit(mbid))
        return hits[:limit]

    def release_group(self, mbid):
        self.lookups['release_group'] += 1
        if mbid in self.fail_release_group_for:
            raise ApiError('boom')
        artist, artist_mbid, title, year, ptype, secondary, tags, *_ = _album(mbid)
        relations = []
        if mbid in WIKIDATA:
            relations.append({'type': 'wikidata', 'target-type': 'url',
                              'url': {'resource': f'https://www.wikidata.org/wiki/{WIKIDATA[mbid]}'}})
        if mbid in DISCOGS:
            relations.append({'type': 'discogs', 'target-type': 'url',
                              'url': {'resource': f'https://www.discogs.com/master/{DISCOGS[mbid]}'}})
        track_count = 6 if mbid == 'rg-seed' else 10
        return {
            'id': mbid, 'title': title, 'first-release-date': f'{year}-03-15',
            'primary-type': ptype, 'secondary-types': list(secondary),
            'artist-credit': [{'artist': {'id': artist_mbid, 'name': artist}}],
            'releases': [
                {'id': f'rel-{mbid}-vinyl', 'status': 'Official', 'date': f'{year}-03-15',
                 'country': 'US', 'media': [{'format': '12" Vinyl', 'track-count': track_count}]},
                {'id': f'rel-{mbid}', 'status': 'Official', 'date': f'{year}-03-15',
                 'country': 'US', 'media': [{'format': 'CD', 'track-count': track_count}]},
            ],
            'genres': [{'name': t, 'count': c} for t, c, g in tags if g],
            'tags': [{'name': t, 'count': c} for t, c, _ in tags],
            'rating': {'value': 4.2, 'votes-count': 12},
            'relations': relations,
        }

    def release(self, release_mbid):
        self.lookups['release'] += 1
        mbid = release_mbid.replace('rel-', '').replace('-vinyl', '')
        artist, artist_mbid, title, year, ptype, secondary, tags, listeners, listens, engineer, label = _album(mbid)
        track_count = 6 if mbid == 'rg-seed' else 10
        tracks = []
        for index in range(track_count):
            tracks.append({
                'title': f'{title} track {index + 1}', 'length': 240000 + index * 30000,
                'number': str(index + 1), 'position': index + 1,
                'recording': {'id': f'rec-{mbid}-{index}', 'length': 240000 + index * 30000,
                              'relations': _recording_relations(mbid)},
            })
        return {
            'id': release_mbid, 'status': 'Official', 'date': f'{year}-03-15', 'country': 'US',
            'barcode': '0000', 'title': title,
            'label-info': [{'label': {'id': f'lab-{label}', 'name': label}, 'catalog-number': 'CAT-1'}],
            'artist-credit': [{'artist': {'id': artist_mbid, 'name': artist,
                                          'type': ARTISTS[artist_mbid][1]}}],
            'media': [{'format': 'CD', 'track-count': track_count, 'tracks': tracks}],
            'relations': [],
        }

    def artist(self, mbid):
        self.lookups['artist'] += 1
        name, atype, area, begin, related = ARTISTS[mbid]
        relations = []
        for other in related:
            other_name, other_type = ARTISTS[other][0], ARTISTS[other][1]
            relations.append({
                'type': 'member of band', 'target-type': 'artist',
                'direction': 'forward' if atype == 'Person' else 'backward',
                'artist': {'id': other, 'name': other_name, 'type': other_type},
            })
        return {
            'id': mbid, 'name': name, 'type': atype, 'gender': '',
            'area': {'name': area}, 'life-span': {'begin': str(begin)},
            'relations': relations, 'genres': [], 'tags': [],
        }

    def genre_names(self):
        return frozenset({'post-rock', 'math rock', 'rock', 'post-hardcore', 'jazz',
                          'indie rock', 'pop', 'art rock'})


class StubListenBrainz:
    calls_made = 0
    cache_hits = 0

    def metadata(self, mbids, inc=None):
        out = {}
        for mbid in mbids:
            if mbid not in ALBUMS:
                continue
            artist, artist_mbid, title, year, ptype, secondary, tags, *_ = _album(mbid)
            name, atype, area, begin, _ = ARTISTS[artist_mbid]
            out[mbid] = {
                'release_group': {'name': title, 'date': f'{year}-01-01', 'type': ptype,
                                  'caa_id': 1, 'caa_release_mbid': f'rel-{mbid}', 'rels': []},
                'artist': {'name': artist, 'artists': [{
                    'name': artist, 'artist_mbid': artist_mbid, 'area': area, 'type': atype,
                    'begin_year': begin, 'rels': {'wikidata': 'https://www.wikidata.org/wiki/Q1'},
                }]},
                'tag': {
                    'release_group': [
                        dict({'tag': t, 'count': c}, **({'genre_mbid': f'g-{t}'} if g else {}))
                        for t, c, g in tags
                    ],
                    'artist': [{'tag': 'post-rock', 'count': 5, 'genre_mbid': 'g-post-rock'}]
                    if artist_mbid != 'a-pop' else [{'tag': 'pop', 'count': 5, 'genre_mbid': 'g-pop'}],
                },
            }
        return out

    def popularity(self, mbids):
        return {mbid: {'total_user_count': _album(mbid)[7], 'total_listen_count': _album(mbid)[8]}
                for mbid in mbids if mbid in ALBUMS}

    def artist_popularity(self, artist_mbids):
        return {mbid: {'total_user_count': 40000} for mbid in artist_mbids}

    def top_release_groups(self, artist_mbid):
        return [
            {'release_group_mbid': mbid, 'release_group': {'name': data[2], 'type': data[4]},
             'artist': {'name': data[0], 'artist_mbid': data[1]},
             'total_user_count': data[7], 'total_listen_count': data[8]}
            for mbid, data in ALBUMS.items() if data[1] == artist_mbid
        ]

    def similar_artists(self, artist_mbid, algorithm=None):
        return [{'artist_mbid': other, 'name': _artist_name(other), 'score': score,
                 'reference_mbid': artist_mbid}
                for other, score in SIMILAR_ARTISTS.get(artist_mbid, [])]

    def similar_recordings(self, recording_mbids, algorithm=None):
        if not any(str(mbid).startswith('rec-rg-seed') for mbid in recording_mbids):
            return []
        return [{'recording_mbid': mbid, 'score': score, 'reference_mbid': 'rec-rg-seed-0'}
                for mbid, score in SIMILAR_RECORDINGS]

    def recording_metadata(self, recording_mbids, inc=None):
        out = {}
        for rec in recording_mbids:
            rg = rec.rsplit('-', 1)[0].replace('rec-', '')
            if rg in ALBUMS:
                data = _album(rg)
                out[rec] = {
                    'recording': {'name': f'{data[2]} track'},
                    'artist': {'name': data[0], 'artists': [{'artist_mbid': data[1], 'name': data[0]}]},
                    'release': {'release_group_mbid': rg, 'name': data[2]},
                }
        return out


class StubWikidata:
    calls_made = 0
    cache_hits = 0

    def entities(self, qids, props=None):
        out = {}
        for qid in qids:
            if qid not in WIKIDATA.values():
                continue
            claims = {
                'P444': [{'mainsnak': {'snaktype': 'value', 'datavalue': {'value': '4'}}, 'rank': 'normal',
                          'qualifiers': {'P447': [{'snaktype': 'value', 'datavalue': {'value': {'id': 'Q31181'}}}]}}],
                'P2205': [{'mainsnak': {'snaktype': 'value', 'datavalue': {'value': 'spot1'}}, 'rank': 'normal'}],
            }
            if qid == 'Q545227':
                # Only the seed's entry names a producer and a label, so the
                # Rodan overlap stays the MusicBrainz engineer credit alone.
                claims['P162'] = [{'mainsnak': {'snaktype': 'value', 'datavalue': {'value': {'id': 'Q-paulson'}}}, 'rank': 'normal'}]
                claims['P264'] = [{'mainsnak': {'snaktype': 'value', 'datavalue': {'value': {'id': 'Q-tg'}}}, 'rank': 'normal'}]
            out[qid] = {'id': qid, 'labels': {'en': {'value': 'x'}}, 'claims': claims,
                        'sitelinks': {'enwiki': {'title': 'Spiderland'}}}
        return out

    def labels(self, qids):
        names = {'Q-paulson': 'Brian Paulson', 'Q-tg': 'Touch and Go', 'Q31181': 'AllMusic'}
        return {qid: names[qid] for qid in qids if qid in names}


class StubDeezer:
    calls_made = 0
    cache_hits = 0

    def search_album(self, artist, title):
        for mbid, data in ALBUMS.items():
            if data[0] == artist and data[2] == title:
                return [{'id': hash(mbid) & 0xffff, 'title': title, 'artist': {'name': artist},
                         'nb_tracks': 6 if mbid == 'rg-seed' else 10, 'record_type': 'album'}]
        return []

    def album(self, deezer_id):
        return {'id': deezer_id, 'fans': 1234, 'label': 'Touch And Go', 'nb_tracks': 6,
                'release_date': '1991-03-27', 'explicit_lyrics': False,
                'genres': {'data': [{'name': 'Rock'}]},
                'tracks': {'data': [{'id': deezer_id * 10 + i} for i in range(6)]}}

    def track(self, track_id):
        return {'id': track_id, 'bpm': 120.0 + (track_id % 3), 'gain': -10.5}


class StubDiscogs:
    calls_made = 0
    cache_hits = 0

    def __init__(self, token=''):
        self.token = token
        self.authenticated = bool(token)
        self.configured = True

    def master(self, master_id):
        return {'id': int(master_id), 'styles': ['Math Rock', 'Post Rock'], 'genres': ['Rock'],
                'year': 1991, 'main_release': 1, 'uri': 'https://www.discogs.com/master/1'}

    def release(self, release_id):
        return {'id': release_id, 'community': {'have': 100, 'want': 200,
                                                'rating': {'average': 4.5, 'count': 10}},
                'labels': [{'name': 'Touch And Go'}],
                'extraartists': [{'name': 'Brian Paulson', 'role': 'Recorded By'}]}


class StubLastFm:
    calls_made = 0
    cache_hits = 0

    def __init__(self, configured=True, reject_key=False):
        self.configured = configured
        self.reject_key = reject_key

    def _check(self):
        if self.reject_key:
            raise KeyRejected('Last.fm rejected the API key (error 10)')

    def album_tags(self, artist, album):
        self._check()
        return [{'name': 'melancholic', 'count': 80}, {'name': 'atmospheric', 'count': 40}]

    def artist_tags(self, artist):
        self._check()
        return [{'name': 'post-rock', 'count': 100}]

    def similar_artists(self, artist, limit=30):
        self._check()
        if artist == 'Slint':
            return [{'name': 'Rodan', 'mbid': 'a-rodan', 'match': 1.0},
                    {'name': 'Unknown', 'mbid': '', 'match': 0.5}]
        return []

    def tag_top_albums(self, tag, limit=50):
        self._check()
        if tag == 'slowcore':
            return [{'name': 'Frigid Stars', 'mbid': '', 'artist': 'Codeine',
                     'artist_mbid': 'a-codeine', 'rank': 1}]
        return []

    def album_info(self, artist, album):
        self._check()
        return {'name': album, 'artist': artist, 'listeners': '123456', 'playcount': '7890000',
                'url': 'https://www.last.fm/music/x'}


def stub_services(lastfm=None, discogs_token=''):
    return Services(
        musicbrainz=StubMusicBrainz(), listenbrainz=StubListenBrainz(),
        wikidata=StubWikidata(), deezer=StubDeezer(),
        lastfm=lastfm if lastfm is not None else StubLastFm(),
        discogs=StubDiscogs(token=discogs_token),
    )


def run(services=None, **kwargs):
    kwargs.setdefault('seeds', ['Slint - Spiderland'])
    kwargs.setdefault('top_n', 10)
    # The fixture universe has two Tortoise records on purpose; keep both
    # visible unless a test is about the per-artist cap itself.
    kwargs.setdefault('max_per_artist', 2)
    return find_similar(services=services or stub_services(), **kwargs)


def titles(result):
    return [m.features.title for m in result.matches]


def by_title(result, title):
    return next(m for m in result.matches if m.features.title == title)


# ---------------------------------------------------------------------------
# Seed resolution and enrichment
# ---------------------------------------------------------------------------

def test_parse_seed_text_forms():
    assert parse_seed_text('Slint - Spiderland') == {'artist': 'Slint', 'album': 'Spiderland'}
    assert parse_seed_text('mbid:rg-seed') == {'mbid': 'rg-seed'}
    assert parse_seed_text('spiderland') == {'query': 'spiderland'}
    assert parse_seed_text({'mbid': 'x'}) == {'mbid': 'x'}


def test_search_albums_shape():
    hits = search_albums(stub_services(), query='rusty')
    assert hits and hits[0]['artist'] == 'Rodan'
    assert hits[0]['artist_mbid'] == 'a-rodan'
    assert hits[0]['mbid'] == 'rg-rodan'
    assert 'secondary_types' in hits[0] and 'disambiguation' in hits[0]


def test_seed_is_fully_enriched():
    result = run()
    seed = result.seed
    assert seed.artist == 'Slint' and seed.year == 1991
    # personnel from the artist lookup
    assert 'p-pajo' in seed.personnel and seed.personnel['p-pajo'] == 'David Pajo'
    assert seed.personnel_relations['a-slint'] == 'artist'
    # tracklist and circle from the canonical (CD, not vinyl) release
    assert seed.has_tracklist and seed.track_count == 6
    assert seed.canonical_release_mbid == 'rel-rg-seed'
    assert 'brian paulson' in seed.engineers
    assert 'touch and go' in seed.labels
    assert seed.studio_names
    # editions, rating, ids from the release group
    assert seed.editions == 2 and seed.mb_rating == pytest.approx(4.2)
    assert seed.wikidata_id == 'Q545227' and seed.discogs_master_id == '38099'
    # kinship and canonicity from ListenBrainz
    assert 'rodan' in seed.artist_neighbours
    assert seed.artist_rg_listeners > 0
    # crowd tags and listeners from Last.fm
    assert 'melancholic' in seed.moods
    assert seed.lastfm_listeners == 123456
    # Deezer and Wikidata statistics
    assert seed.fans == 1234 and seed.bpm_mean and seed.gain_mean == pytest.approx(-10.5)
    assert seed.critic_scores.get('AllMusic') == pytest.approx(0.8)
    assert seed.spotify_id == 'spot1'
    # Wikidata's producer joins the circle under the same name key
    assert 'brian paulson' in seed.producers
    assert {'rg', 'release', 'artist', 'deezer', 'wikidata', 'lastfm_info', 'canonicity'} <= seed.enriched


def test_discogs_is_off_without_a_token_and_on_with_one():
    assert run().seed.have == 0
    assert run(stub_services(discogs_token='tok')).seed.have == 100
    assert run(with_discogs=True).seed.want == 200


def test_missing_seed_raises_with_a_usable_message():
    with pytest.raises(SeedNotFound):
        run(seeds=['nonsense that matches nothing'])


# ---------------------------------------------------------------------------
# The ranking
# ---------------------------------------------------------------------------

def test_end_to_end_ranks_connected_neighbours_first():
    result = run()
    names = titles(result)
    assert names, 'expected matches'
    # the seed, its artist, live records, singles and untagged albums are out
    assert 'Spiderland' not in names
    assert 'Live at Lounge Ax' not in names
    assert 'Realize' not in names
    assert 'Blank' not in names
    # the deeply connected records outrank the merely tagged and the far
    assert names.index('TNT') < names.index('Stadium')
    assert names.index('Rusty') < names.index('Stadium')
    assert names.index('Frigid Stars') < names.index('Stadium')
    for match in result.matches:
        assert 0.0 <= match.distance <= 1.0
        assert match.axes and match.reasons
    assert result.considered > 0 and result.fingerprinted > 0 and result.shortlisted > 0
    assert set(result.sources) >= {'tag', 'artist', 'people', 'tracks'}
    assert result.timings.get('connections') is not None


def test_evidence_axes_fire_on_real_connections():
    result = run()
    tortoise = by_title(result, 'TNT')
    assert tortoise.strengths.get('personnel') == pytest.approx(0.5)
    assert 'David Pajo' in tortoise.shared_personnel
    assert any('David Pajo' in reason for reason in tortoise.reasons)
    assert tortoise.connected

    rodan = by_title(result, 'Rusty')
    assert rodan.strengths.get('circle') == pytest.approx(1.0)
    assert rodan.shared_circle.get('engineers') == ['Brian Paulson']
    assert any('Brian Paulson' in reason for reason in rodan.reasons)

    codeine = by_title(result, 'Frigid Stars')
    assert codeine.strengths.get('co_listening', 0) > 0.5
    assert codeine.co_listening[0] > 1.0
    assert any('played alongside' in reason for reason in codeine.reasons)

    stadium = by_title(result, 'Stadium')
    assert not stadium.strengths
    assert not stadium.connected


def test_finalists_carry_the_full_statistics():
    result = run()
    rodan = by_title(result, 'Rusty').features
    assert rodan.has_tracklist and rodan.track_count == 10
    assert rodan.fans == 1234 and rodan.bpm_mean
    assert rodan.critic_scores.get('AllMusic') == pytest.approx(0.8)
    assert rodan.lastfm_listeners == 123456
    assert rodan.artist_rg_listeners > 0
    assert 'p-noble' in rodan.personnel
    row = by_title(result, 'Rusty').as_row()
    json.dumps(row)
    assert row['shared_engineers'] == 'Brian Paulson'
    assert row['reasons']


def test_multi_seed_blend_excludes_every_seed_artist():
    result = run(seeds=['Slint - Spiderland', 'Talk Talk - Laughing Stock'])
    assert len(result.seeds) == 2
    assert ' + ' in result.seed.artist
    assert set(result.seed.seed_artist_mbids) == {'a-slint', 'a-talk'}
    artists = {m.features.artist for m in result.matches}
    assert 'Slint' not in artists and 'Talk Talk' not in artists
    assert result.matches


def test_obscurity_filter_keeps_only_less_heard_records():
    result = run(mode='deep_cuts')
    assert result.matches
    for match in result.matches:
        assert match.features.listeners < result.seed.listeners


def test_one_artist_cannot_fill_the_whole_result_list():
    result = run(max_per_artist=1)
    artists = [m.features.artist for m in result.matches]
    assert len(artists) == len(set(artists))
    result = run(max_per_artist=0, studio_only=False)
    assert [m.features.artist for m in result.matches].count('Tortoise') == 2


def test_studio_only_filter_uses_secondary_types_and_titles():
    assert 'Live at Lounge Ax' not in titles(run())
    assert 'Live at Lounge Ax' in titles(run(studio_only=False, top_n=20))


def test_a_compilation_revealed_by_the_deep_lookups_is_dropped():
    """ListenBrainz does not serve secondary types, so a compilation with an
    innocent title only shows itself when MusicBrainz is asked in S4. It must
    not survive into the results on the strength of its bulk data."""
    services = stub_services()
    real_release_group = services.musicbrainz.release_group

    def release_group(mbid):
        payload = real_release_group(mbid)
        if mbid == 'rg-tortoise':
            payload['secondary-types'] = ['Compilation']
        return payload

    services.musicbrainz.release_group = release_group
    assert 'TNT' in titles(run())                      # passes the bulk filters
    assert 'TNT' not in titles(run(services))          # dropped once S4 reveals it
    assert 'TNT' in titles(run(stub_services(), deep=False))


def test_the_seed_artist_is_excluded_on_every_scoring_pass():
    """The same-artist filter is re-applied after each enrichment stage, not
    only before fingerprinting."""
    for kwargs in ({}, {'deep': False}, {'mode': 'sideways'}, {'mode': 'deep_cuts'}):
        result = run(**kwargs)
        assert result.matches
        for match in result.matches:
            assert match.features.artist_mbid != 'a-slint'
            assert match.features.artist != 'Slint'
    # The seed record itself is dropped by key even when its artist is allowed.
    allowed = run(exclude_same_artist=False, studio_only=False, top_n=20)
    assert allowed.matches
    assert 'Spiderland' not in titles(allowed)


def test_an_unknown_seed_audience_drops_the_obscurity_filter():
    """A seed ListenBrainz has no listener count for gives no threshold to
    compare against; deep cuts must degrade to a plain run rather than
    reject everything."""
    services = stub_services()
    real_popularity = services.listenbrainz.popularity

    def popularity(mbids):
        counts = real_popularity(mbids)
        counts.pop('rg-seed', None)          # the seed has no entry at all
        return counts

    services.listenbrainz.popularity = popularity
    result = run(services, mode='deep_cuts')
    assert result.seed.listeners == 0
    assert result.matches, 'deep cuts must not empty out on an unknown seed audience'


def test_a_seed_with_no_known_root_genre_still_works_sideways():
    """Sideways keeps to the seed's broad genre, but a seed tagged only with
    moods has no root to keep to, so the gate is dropped rather than
    rejecting every candidate."""
    services = stub_services()
    real_metadata = services.listenbrainz.metadata

    def metadata(mbids, inc=None):
        out = real_metadata(mbids, inc)
        entry = out.get('rg-seed')
        if entry:
            entry['tag']['release_group'] = [{'tag': 'hypnagogic', 'count': 9},
                                             {'tag': 'wintry', 'count': 4}]
            entry['tag']['artist'] = [{'tag': 'wintry', 'count': 5}]
        return out

    services.listenbrainz.metadata = metadata
    result = run(services, mode='sideways')
    assert not result.seed.root_genres
    assert result.matches, 'sideways must not empty out on a seed with no root genre'


def test_a_popularity_failure_becomes_a_note_not_a_crash():
    """The two popularity calls only fill in statistics. Losing them costs a
    number, never the run."""
    services = stub_services()

    def boom(mbids):
        raise ApiError('ListenBrainz is having a moment')

    services.listenbrainz.popularity = boom
    services.listenbrainz.artist_popularity = boom
    result = run(services)
    assert result.matches
    assert any('listener counts' in note for note in result.notes)
    # One bulk call covers the batch, so it must not be reported as a
    # per-album failure ('failed for 1 album') when 150 albums lost a number.
    assert not any('failed for' in note for note in result.notes)
    assert all(m.features.listeners == 0 for m in result.matches)


def test_a_refused_pool_batch_costs_its_albums_not_the_run(monkeypatch):
    """By the time the pool is fingerprinted, minutes of lookups are done.
    A batch ListenBrainz will not answer loses those albums, with a note,
    rather than throwing the whole run away."""
    monkeypatch.setattr(config, 'LB_BATCH_SIZE', 2)
    services = stub_services()
    real_metadata = services.listenbrainz.metadata
    refused = []

    def metadata(mbids, inc=None):
        if 'rg-tortoise2' in mbids:
            refused.extend(mbids)
            raise ApiError('ListenBrainz keeps sending a web page titled "Verifying your browser"')
        return real_metadata(mbids, inc)

    services.listenbrainz.metadata = metadata
    result = run(services)
    assert refused, 'the fixture pool should have reached the refused batch'
    assert result.matches
    assert not {m.features.mbid for m in result.matches} & set(refused)
    assert any(f'did not answer for {len(refused)} of' in note and 'Verifying your browser' in note
               for note in result.notes)


def test_a_pool_listenbrainz_will_not_fingerprint_at_all_fails_the_run():
    services = stub_services()
    real_metadata = services.listenbrainz.metadata

    def metadata(mbids, inc=None):
        if 'rg-seed' in mbids:
            return real_metadata(mbids, inc)
        raise ApiError('ListenBrainz keeps sending a web page')

    services.listenbrainz.metadata = metadata
    with pytest.raises(ApiError):
        run(services)


def test_a_service_given_up_on_is_named_and_gets_a_fresh_chance_next_run():
    services = stub_services()
    lb = services.listenbrainz
    lb.name, lb.unavailable, lb.last_failure, lb.resets = 'ListenBrainz', False, '', 0
    real_similar = lb.similar_artists

    def reset_outage():
        lb.resets += 1
        lb.unavailable, lb.last_failure = False, ''

    def similar_artists(artist_mbid, algorithm=None):
        lb.unavailable, lb.last_failure = True, 'HTTP 503 from labs'
        return real_similar(artist_mbid, algorithm)

    lb.reset_outage, lb.similar_artists = reset_outage, similar_artists
    result = run(services)
    assert lb.resets == 1
    assert any(note.startswith('ListenBrainz stopped answering partway through')
               and 'HTTP 503 from labs' in note for note in result.notes)
    lb.similar_artists = real_similar
    result = run(services)
    assert lb.resets == 2
    assert not any('stopped answering' in note for note in result.notes)


def test_a_musicbrainz_outage_never_reads_as_no_such_album():
    services = stub_services()

    def find_album(**kwargs):
        raise ApiError('MusicBrainz keeps sending a web page')

    services.musicbrainz.find_album = find_album
    with pytest.raises(ApiError):
        search_albums(services, query='rusty')
    with pytest.raises(ApiError):
        run(services)


def test_the_engine_runs_without_a_musicbrainz_client():
    """Services documents that a client may be absent and the engine skips
    what it lacks; the candidate sources have to honour that too."""
    services = stub_services()
    services.musicbrainz = None
    result = find_similar(seeds=[{'mbid': 'rg-seed'}], services=services, top_n=8,
                          max_per_artist=2)
    assert result.matches, 'ListenBrainz and Last.fm alone should still find neighbours'
    assert 'tag' not in result.sources and 'tags' not in result.sources


def test_radius_caps_the_result_set():
    result = run(radius=0.001)
    assert not result.matches
    assert any('none qualified' in note for note in result.notes)


def test_deep_false_skips_the_expensive_lookups():
    services = stub_services()
    result = run(services, deep=False)
    assert result.matches
    # only the seed got a release-group and release lookup
    assert services.musicbrainz.lookups['release_group'] == 1
    assert services.musicbrainz.lookups['release'] == 1
    assert 'connections' not in result.timings
    assert not by_title(result, 'Rusty').features.has_tracklist


def test_progress_is_only_ever_called_on_the_calling_thread():
    threads = set()
    stages = []

    def progress(stage, done, total, label):
        threads.add(threading.get_ident())
        stages.append(stage)

    run(progress=progress)
    assert threads == {threading.get_ident()}
    assert {'seed', 'candidates', 'fingerprint', 'enrich', 'score', 'connections', 'stats'} <= set(stages)


def test_failures_become_notes_not_exceptions():
    services = stub_services()
    services.musicbrainz.fail_release_group_for = {'rg-rodan', 'rg-tortoise'}
    result = run(services)
    assert result.matches
    assert any('MusicBrainz release-group lookup failed for 2 albums' in note for note in result.notes)


def test_rejected_lastfm_key_is_noted_and_the_run_continues():
    result = run(stub_services(lastfm=StubLastFm(reject_key=True)))
    assert result.matches
    assert any('rejected' in note for note in result.notes)
    assert 'melancholic' not in result.seed.moods


def test_without_a_lastfm_key_nothing_lastfm_happens():
    result = run(stub_services(lastfm=StubLastFm(configured=False)))
    assert result.matches
    assert result.seed.lastfm_listeners == 0
    assert 'lastfm' not in result.sources and 'lastfm_tag' not in result.sources
