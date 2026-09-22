"""Offline tests for the credit parsers, against saved live responses.

tests/fixtures holds real MusicBrainz, Deezer, Wikidata, Discogs and
Last.fm payloads (Slint's Spiderland, Nirvana's In Utero, Radiohead's OK
Computer), so every field path the parsers rely on is exercised against
what the services actually return rather than against a hand-written stub.
"""

import importlib.util
import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

try:
    from radius import credits
except ImportError:
    # radius/__init__.py pulls in the whole engine. credits.py depends on
    # nothing in the package, so its tests load it by path when a sibling
    # module is mid-rewrite rather than fail on someone else's import.
    _spec = importlib.util.spec_from_file_location(
        'radius.credits', os.path.join(ROOT, 'radius', 'credits.py'))
    credits = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(credits)

REVIEWER_SCALES = credits.REVIEWER_SCALES
artist_personnel = credits.artist_personnel
canonical_release_order = credits.canonical_release_order
deezer_facts = credits.deezer_facts
discogs_facts = credits.discogs_facts
lastfm_facts = credits.lastfm_facts
match_deezer_album = credits.match_deezer_album
parse_review_score = credits.parse_review_score
person_key = credits.person_key
release_circle = credits.release_circle
release_group_facts = credits.release_group_facts
release_shape = credits.release_shape
wikidata_facts = credits.wikidata_facts

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fixtures')

SLINT = '2869c510-2679-4a3f-bf15-e5e8b49f2f28'
PAJO = '85188c46-d3ed-4517-ba78-5d06ec764f1c'
TORTOISE = 'e0953daa-860f-4dc8-9f1a-b12587cdaf17'
PAPA_M = '6edbe0fb-734e-4b1d-9c64-73ebb04853e1'
AERIAL_M = '7f8f02bb-e2d9-4ee1-b5a6-b35ea4bdcac0'
NIRVANA_MEMBERS = {'kurt cobain', 'dave grohl', 'krist novoselic'}
SLINT_MEMBERS = {'brian mcmahan', 'david pajo', 'britt walford', 'todd brashear'}


def load(name):
    with open(os.path.join(FIXTURES, name + '.json'), encoding='utf-8') as handle:
        return json.load(handle)


# ---------------------------------------------------------------------------
# person_key
# ---------------------------------------------------------------------------

def test_person_key_normalises_across_sources():
    assert person_key('Steve Albini') == 'steve albini'
    assert person_key('  STEVE   ALBINI ') == 'steve albini'
    assert person_key('Bj\u00f6rk Gu\u00f0mundsd\u00f3ttir') == 'bjork gu\u00f0mundsdottir'
    assert person_key('The For Carnation') == 'for carnation'
    assert person_key("Guns N' Roses") == 'guns n roses'
    assert person_key('Jean-Michel Jarre') == person_key('Jean Michel Jarre')
    assert person_key("O'Brien") == 'o brien'
    assert person_key('AC/DC') == 'ac dc'
    assert person_key('') == ''
    assert person_key(None) == ''


# ---------------------------------------------------------------------------
# Release groups
# ---------------------------------------------------------------------------

def test_canonical_release_order_on_spiderland():
    rg = load('mb_rg_spiderland')
    order = canonical_release_order(rg)
    by_id = {release['id']: release for release in rg['releases']}

    assert len(order) == len(rg['releases'])
    assert len(set(order)) == len(order)
    assert set(order) == set(by_id)

    first = by_id[order[0]]
    assert first['status'] == 'Official'
    assert sum(medium['track-count'] for medium in first['media']) == 6
    assert first['media'][0]['format'] == 'CD'

    # The original 1991 US CD stands ahead of the 1991 vinyl and of every
    # 2014 box-set edition.
    cd_1991 = order.index('2c8cba8b-a80a-4d7f-9a7f-22c922f1a42e')
    vinyl_1991 = order.index('a16b871f-3b71-3bb0-9a9d-798b513a4fc0')
    box_2014 = order.index('104f994c-7c01-4fa9-b880-49bd2f29b115')
    assert cd_1991 < vinyl_1991 < box_2014
    # Releases with the modal track count all come before the 20-track and
    # 41-track sets.
    six_track = [rid for rid in order if sum(m['track-count'] for m in by_id[rid]['media']) == 6]
    assert order[:len(six_track)] == six_track


def test_canonical_release_order_prefers_cd_over_vinyl_at_equal_date():
    payload = {'releases': [
        {'id': 'vinyl', 'status': 'Official', 'date': '1991-03-15', 'country': 'US',
         'media': [{'format': '12" Vinyl', 'track-count': 6}]},
        {'id': 'cd', 'status': 'Official', 'date': '1991-03-15', 'country': 'US',
         'media': [{'format': 'CD', 'track-count': 6}]},
        {'id': 'bootleg', 'status': 'Bootleg', 'date': '1990-01-01', 'country': 'US',
         'media': [{'format': 'CD', 'track-count': 6}]},
        {'id': 'undated', 'status': 'Official',
         'media': [{'format': 'CD', 'track-count': 6}]},
    ]}
    order = canonical_release_order(payload)
    assert order[0] == 'cd'
    assert order.index('cd') < order.index('vinyl')
    assert order.index('cd') < order.index('undated')          # missing date is worst
    assert order.index('undated') < order.index('vinyl')       # but format ranks before date
    assert order[-1] == 'bootleg'                                # non-official last
    # Input order does not matter.
    payload['releases'].reverse()
    assert canonical_release_order(payload)[0] == 'cd'


def test_canonical_release_order_uses_modal_official_track_count():
    payload = {'releases': [
        {'id': 'deluxe', 'status': 'Official', 'date': '1991',
         'media': [{'format': 'CD', 'track-count': 6}, {'format': 'CD', 'track-count': 14}]},
        {'id': 'plain-a', 'status': 'Official', 'date': '1995',
         'media': [{'format': 'CD', 'track-count': 6}]},
        {'id': 'plain-b', 'status': 'Official', 'date': '2004',
         'media': [{'format': 'Digital Media', 'track-count': 6}]},
    ]}
    assert canonical_release_order(payload) == ['plain-a', 'plain-b', 'deluxe']


def test_canonical_release_order_tolerates_empty_input():
    assert canonical_release_order({}) == []
    assert canonical_release_order(None) == []
    assert canonical_release_order({'releases': [{'status': 'Official'}]}) == []


def test_release_group_facts_on_spiderland():
    rg = load('mb_rg_spiderland')
    facts = release_group_facts(rg)
    assert facts['editions'] == len(rg['releases'])
    assert facts['wikidata_id'] == 'Q545227'
    assert facts['discogs_master_id'] == '38099'
    assert facts['mb_genres'][0] == 'post-rock'
    assert facts['mb_genres'] == ['post-rock', 'math rock', 'post-hardcore', 'rock']
    assert facts['mb_rating'] == pytest.approx(4.25)
    assert facts['mb_rating_votes'] == 15
    assert facts['secondary_types'] == []
    assert facts['primary_type'] == 'Album'
    assert facts['first_release_date'] == '1991-03-15'
    assert facts['year'] == 1991
    assert 'US' in facts['release_countries'] and 'XW' in facts['release_countries']
    assert facts['links']['allmusic'] == 'https://www.allmusic.com/album/mw0000267497'
    assert facts['links']['wikidata'].endswith('/Q545227')


def test_release_group_facts_empty_defaults():
    for payload in ({}, None, {'releases': None, 'rating': None, 'relations': None}):
        facts = release_group_facts(payload)
        assert facts['editions'] == 0
        assert facts['year'] is None
        assert facts['mb_rating'] is None
        assert facts['mb_genres'] == []
        assert facts['wikidata_id'] == ''
        assert facts['discogs_master_id'] == ''
        assert facts['links'] == {}
        assert facts['release_countries'] == []


# ---------------------------------------------------------------------------
# Releases: shape
# ---------------------------------------------------------------------------

def test_release_shape_on_spiderland():
    shape = release_shape(load('mb_release_spiderland'))
    assert shape['release_mbid'] == '2c8cba8b-a80a-4d7f-9a7f-22c922f1a42e'
    assert shape['track_count'] == 6
    assert len(shape['titles']) == 6
    assert shape['titles'][0] == 'Breadcrumb Trail'
    assert len(shape['lengths_ms']) == 6
    assert 39 * 60 <= shape['runtime_seconds'] <= 40 * 60
    assert shape['recording_mbids'][0] == '8971961f-143b-4aba-8721-550eeb56073d'
    assert len(shape['recording_mbids']) == 6
    assert shape['track_length_spread'] > 0
    assert 300 < shape['mean_track_seconds'] < 500
    assert shape['formats'] == ['CD']
    assert shape['disc_count'] == 1
    assert shape['status'] == 'Official'
    assert shape['date'] == '1991-03-15'
    assert shape['country'] == 'US'


def test_release_shape_only_positive_lengths_feed_the_numbers():
    payload = {'id': 'r', 'media': [{'format': 'CD', 'track-count': 3, 'tracks': [
        {'title': 'a', 'length': 60000, 'recording': {'id': 'rec-a'}},
        {'title': 'b', 'length': None, 'recording': {'id': 'rec-b', 'length': None}},
        {'title': 'c', 'recording': {'id': 'rec-c', 'length': 120000}},
    ]}]}
    shape = release_shape(payload)
    assert shape['track_count'] == 3
    assert shape['lengths_ms'] == [60000, 0, 120000]
    assert shape['runtime_seconds'] == 180
    assert shape['mean_track_seconds'] == pytest.approx(90.0)
    assert shape['track_length_spread'] == pytest.approx(30.0 / 90.0)
    assert shape['recording_mbids'] == ['rec-a', 'rec-b', 'rec-c']


def test_release_shape_empty_defaults():
    for payload in ({}, None):
        shape = release_shape(payload)
        assert shape['track_count'] == 0
        assert shape['runtime_seconds'] == 0
        assert shape['mean_track_seconds'] == 0.0
        assert shape['track_length_spread'] == 0.0
        assert shape['recording_mbids'] == []
        assert shape['formats'] == []


# ---------------------------------------------------------------------------
# Releases: circle
# ---------------------------------------------------------------------------

def test_release_circle_on_in_utero():
    circle = release_circle(load('mb_release_in_utero'))
    assert 'steve albini' in circle['engineers']
    assert circle['engineers']['steve albini'] == 'Steve Albini'
    assert 'steve albini' in circle['producers']
    assert any('pachyderm' in key for key in circle['studios'])
    assert 'gateway mastering studios' in circle['studios']
    assert 'mpo' not in circle['studios']                         # manufactured at
    assert 'kera schaley' in circle['performers']
    assert not NIRVANA_MEMBERS & set(circle['performers'])
    assert 'geffen' in circle['labels']
    assert 'GED 24536' in circle['catalog_numbers']
    # Credits are aggregated by artist across the eleven tracks.
    roles = {(c['role'], c['name']) for c in circle['credits']}
    assert ('recording', 'Steve Albini') in roles
    assert ('instrument', 'Kera Schaley') in roles
    cello = [c for c in circle['credits'] if c['name'] == 'Kera Schaley'][0]
    assert cello['level'] == 'recording'
    assert cello['source'] == 'musicbrainz'
    assert cello['mbid'] == '31649596-23c3-4454-a7b0-30615ed1f504'
    assert 'cello' in cello['attributes']
    assert len([c for c in circle['credits'] if c['name'] == 'Kurt Cobain' and c['role'] == 'instrument']) == 1


def test_release_circle_on_spiderland():
    circle = release_circle(load('mb_release_spiderland'))
    assert circle['performers'] == {}
    assert any(key.startswith('touch and go') for key in circle['labels'])
    # 'Touch and Go Records' keys as 'touch and go', so Wikidata's and
    # Discogs' 'Touch and Go' land on the same label.
    assert circle['labels']['touch and go'] == 'Touch and Go Records'
    assert circle['catalog_numbers'] == ['TG64CD']
    assert circle['engineers'] == {'brian paulson': 'Brian Paulson'}
    assert circle['producers'] == {}
    assert circle['studios'] == {}
    names = {c['name'] for c in circle['credits']}
    assert 'Will Oldham' in names                                 # photography, credits only
    assert {c['role'] for c in circle['credits'] if c['level'] == 'release'} == {'engineer', 'photography'}
    assert SLINT_MEMBERS <= {person_key(c['name']) for c in circle['credits']}


def test_release_circle_guests_on_a_solo_record_are_everyone_else():
    payload = {
        'artist-credit': [{'artist': {'id': 'solo', 'name': 'Solo Act', 'type': 'Person'}}],
        'media': [{'tracks': [
            {'artist-credit': [{'artist': {'id': 'solo', 'name': 'Solo Act', 'type': 'Person'}}],
             'recording': {'id': 'rec', 'relations': [
                 {'type': 'vocal', 'target-type': 'artist', 'attributes': ['lead vocals'],
                  'artist': {'id': 'solo', 'name': 'Solo Act'}},
                 {'type': 'instrument', 'target-type': 'artist', 'attributes': ['drums'],
                  'artist': {'id': 'sess', 'name': 'Session Drummer'}},
             ]}},
        ]}],
    }
    circle = release_circle(payload)
    assert circle['performers'] == {'session drummer': 'Session Drummer'}


def test_release_circle_empty_defaults():
    for payload in ({}, None, {'relations': None, 'media': None, 'label-info': None}):
        circle = release_circle(payload)
        assert circle == {
            'labels': {}, 'catalog_numbers': [], 'producers': {}, 'engineers': {},
            'performers': {}, 'studios': {}, 'credits': [],
        }


# ---------------------------------------------------------------------------
# Artists
# ---------------------------------------------------------------------------

def test_artist_personnel_slint():
    personnel = artist_personnel(load('mb_artist_slint'))
    assert personnel['mbid'] == SLINT
    assert personnel['name'] == 'Slint'
    assert personnel['type'] == 'Group'
    assert personnel['begin_year'] == 1986
    assert personnel['end_year'] == 1992
    assert personnel['area'] == 'United States'
    assert personnel['people'][PAJO] == {'name': 'David Pajo', 'relation': 'member of band', 'type': 'Person'}
    assert len(personnel['people']) == 5
    assert personnel['mb_genres'][0] == 'post-rock'
    assert personnel['links']['wikidata'].endswith('/Q578979')
    assert personnel['tags'][0] == {'name': 'post-rock', 'count': 8}


def test_artist_personnel_pajo():
    personnel = artist_personnel(load('mb_artist_pajo'))
    assert personnel['type'] == 'Person'
    assert personnel['gender'] == 'Male'
    assert personnel['begin_year'] == 1968
    assert personnel['end_year'] is None
    people = personnel['people']
    assert people[SLINT]['relation'] == 'member of band'
    assert people[SLINT]['type'] == 'Group'
    assert people[TORTOISE]['name'] == 'Tortoise'
    assert people[PAPA_M] == {'name': 'Papa M', 'relation': 'is person', 'type': 'Person'}
    assert people[AERIAL_M]['relation'] == 'is person'
    # Gang of Four appears twice (vocals, guitar) and is kept once.
    assert len([p for p in people.values() if p['name'] == 'Gang of Four']) == 1
    assert 'b23e8a63-8f47-4882-b55b-df2c92ef400e' in people      # supporting musician for Interpol
    assert people['b23e8a63-8f47-4882-b55b-df2c92ef400e']['relation'] == 'instrumental supporting musician'


def test_artist_personnel_empty_defaults():
    for payload in ({}, None, {'relations': None, 'life-span': None}):
        personnel = artist_personnel(payload)
        assert personnel['people'] == {}
        assert personnel['links'] == {}
        assert personnel['begin_year'] is None
        assert personnel['mb_genres'] == []
        assert personnel['tags'] == []
        assert personnel['name'] == ''


# ---------------------------------------------------------------------------
# Deezer
# ---------------------------------------------------------------------------

def test_match_deezer_album_picks_the_original_over_the_remaster():
    hits = load('deezer_search_spiderland')['data']
    match = match_deezer_album(hits, 'Slint', 'Spiderland', track_count=6)
    assert match['id'] == 13254973
    assert match['nb_tracks'] == 6
    # Same answer without the track count and with the list reversed.
    assert match_deezer_album(list(reversed(hits)), 'Slint', 'Spiderland')['id'] == 13254973
    # The raw response body works too.
    assert match_deezer_album(load('deezer_search_spiderland'), 'slint', 'SPIDERLAND')['id'] == 13254973
    # Asking for the remaster gets the remaster.
    assert match_deezer_album(hits, 'Slint', 'Spiderland (Remastered)')['id'] == 13258113
    assert match_deezer_album(hits, 'Tortoise', 'Spiderland') is None
    assert match_deezer_album(hits, 'Slint', 'Tweez') is None
    assert match_deezer_album([], 'Slint', 'Spiderland') is None
    assert match_deezer_album(None, 'Slint', 'Spiderland') is None


def test_deezer_facts_on_spiderland():
    facts = deezer_facts(load('deezer_album_spiderland'), [load('deezer_track_breadcrumb')])
    assert facts['deezer_id'] == 13254973
    assert isinstance(facts['fans'], int) and facts['fans'] > 0
    assert facts['label'] == 'Touch and Go Records'
    assert facts['explicit'] is False
    assert facts['release_date'] == '1991-03-15'
    assert facts['genres'] == ['Alternative', 'Rock']
    assert facts['nb_tracks'] == 6
    assert facts['duration'] == 2371
    assert facts['url'] == 'https://www.deezer.com/album/13254973'
    assert facts['bpm_mean'] == pytest.approx(171.55)
    assert facts['bpm_spread'] == 0.0
    assert facts['gain_mean'] == pytest.approx(-20.2)
    assert facts['tracks_with_bpm'] == 1


def test_deezer_facts_treats_bpm_zero_as_missing():
    facts = deezer_facts({'id': 1}, [
        {'bpm': 0, 'gain': 0},
        {'bpm': 120.0, 'gain': -8.0},
        {'bpm': 140.0, 'gain': -10.0},
    ])
    assert facts['tracks_with_bpm'] == 2
    assert facts['bpm_mean'] == pytest.approx(130.0)
    assert facts['bpm_spread'] == pytest.approx(10.0)
    assert facts['gain_mean'] == pytest.approx(-9.0)
    assert facts['explicit'] is None


def test_deezer_facts_empty_defaults():
    for payload in ({}, None):
        facts = deezer_facts(payload)
        assert facts['deezer_id'] is None
        assert facts['fans'] == 0
        assert facts['explicit'] is None
        assert facts['bpm_mean'] is None
        assert facts['gain_mean'] is None
        assert facts['genres'] == []
        assert facts['tracks_with_bpm'] == 0


# ---------------------------------------------------------------------------
# Wikidata
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('text, reviewer, expected', [
    ('8.7/10', None, 0.87),
    ('4/5', None, 0.8),
    ('77/100', None, 0.77),
    ('9 out of 10', None, 0.9),
    ('A-', None, 0.9),
    ('A+', None, 1.0),
    ('F', None, 0.1),
    ('\u2605\u2605\u2605\u2605', None, 0.8),
    ('\u2605\u2605\u2605\u2605\u2606', None, 0.8),
    ('\u2605\u2605\u2605\u00bd', None, 0.7),
    ('4 stars', None, 0.8),
    ('4.5 stars', None, 0.9),
    ('4\u00bd stars', None, 0.9),
    ('5', 'Q31181', 1.0),
    ('94', None, 0.94),
    ('94', 'Q48989591', 0.94),
    ('8', 'Q1097006', 0.8),
    ('4', None, 0.8),
    ('7.5', None, 0.75),
    ('85%', None, 0.85),
    ('favorable', None, None),
    ('mixed', None, None),
    ('', None, None),
    (None, None, None),
])
def test_parse_review_score(text, reviewer, expected):
    result = parse_review_score(text, reviewer)
    if expected is None:
        assert result is None
    else:
        assert result == pytest.approx(expected)


def test_reviewer_scales_cover_the_documented_reviewers():
    assert REVIEWER_SCALES['Q31181'] == 5
    assert REVIEWER_SCALES['Q48989591'] == 100
    assert REVIEWER_SCALES['Q1097006'] == 10


def test_wikidata_facts_ok_computer():
    facts = wikidata_facts(load('wikidata_entities')['entities']['Q202996'])
    assert facts['critic_scores']['Q31181'] == pytest.approx(1.0)
    assert facts['critic_scores']['Q48989591'] == pytest.approx(0.94)
    assert facts['acclaim'] == pytest.approx(1.0)               # the P7887 aggregate is excluded
    assert 'Q544301' in facts['producer_qids']
    assert facts['spotify_id'] == '2fGCAYUMssLKiUAoNdxGLx'
    assert facts['discogs_master_id'] == '21491'
    assert facts['allmusic_id'] == 'mw0000024289'
    assert facts['aoty_id'] == '362'
    assert facts['lastfm_id'] == 'Radiohead/OK+Computer'
    assert facts['publication_date'] == '1997-05-21'
    assert facts['duration_seconds'] == 3201
    assert facts['label_qids'] == ['Q208909', 'Q193023']
    assert facts['performer_qids'] == ['Q44190']
    assert len(facts['genre_qids']) >= 3
    assert facts['enwiki_title'] == 'OK Computer'


def test_wikidata_facts_spiderland_has_no_scores():
    facts = wikidata_facts(load('wikidata_entities')['entities']['Q545227'])
    assert facts['critic_scores'] == {}
    assert facts['acclaim'] is None
    assert facts['discogs_master_id'] == '38099'
    assert facts['spotify_id'] == '64v1yzdytF7Trfzswc0bRo'
    assert facts['producer_qids'] == ['Q2924978']
    assert facts['publication_date'] == '1991-03-27'
    assert facts['duration_seconds'] is None
    assert facts['enwiki_title'] == 'Spiderland'


def test_wikidata_facts_skips_deprecated_and_honours_precision():
    entity = {'claims': {
        'P444': [
            {'rank': 'deprecated', 'mainsnak': {'snaktype': 'value', 'datavalue': {'value': '1/10'}},
             'qualifiers': {'P447': [{'snaktype': 'value', 'datavalue': {'value': {'id': 'Q1097006'}}}]}},
            {'rank': 'normal', 'mainsnak': {'snaktype': 'value', 'datavalue': {'value': '8.7/10'}},
             'qualifiers': {'P447': [{'snaktype': 'value', 'datavalue': {'value': {'id': 'Q1097006'}}}]}},
            {'rank': 'normal', 'mainsnak': {'snaktype': 'value', 'datavalue': {'value': 'favorable'}}},
        ],
        'P577': [{'rank': 'normal', 'mainsnak': {'snaktype': 'value', 'datavalue': {
            'value': {'time': '+1991-00-00T00:00:00Z', 'precision': 9}}}}],
        'P2047': [{'rank': 'normal', 'mainsnak': {'snaktype': 'value', 'datavalue': {
            'value': {'amount': '+40', 'unit': 'http://www.wikidata.org/entity/Q7727'}}}}],
    }}
    facts = wikidata_facts(entity)
    assert facts['critic_scores'] == {'Q1097006': pytest.approx(0.87)}
    assert facts['acclaim'] == pytest.approx(0.87)
    assert facts['publication_date'] == '1991'
    assert facts['duration_seconds'] == 2400


def test_wikidata_facts_empty_defaults():
    for payload in ({}, None, {'claims': None, 'sitelinks': None}):
        facts = wikidata_facts(payload)
        assert facts['critic_scores'] == {}
        assert facts['acclaim'] is None
        assert facts['spotify_id'] == ''
        assert facts['producer_qids'] == []
        assert facts['duration_seconds'] is None
        assert facts['enwiki_title'] == ''


# ---------------------------------------------------------------------------
# Discogs
# ---------------------------------------------------------------------------

def test_discogs_facts_on_spiderland():
    master = load('discogs_master_38099')
    release = load('discogs_release_369276')
    facts = discogs_facts(master, release)
    assert facts['have'] == release['community']['have']
    assert facts['want'] == release['community']['want']
    assert facts['rating'] == pytest.approx(4.57)
    assert facts['rating_votes'] == release['community']['rating']['count']
    assert 'Math Rock' in facts['styles']
    assert facts['genres'] == ['Rock']
    assert facts['label'] == 'Touch And Go'
    assert facts['year'] == 1991
    assert facts['main_release_id'] == 369276
    assert facts['num_for_sale'] == master['num_for_sale']
    assert facts['lowest_price'] == pytest.approx(master['lowest_price'])
    assert facts['formats'] == ['Vinyl']
    assert facts['country'] == 'US'
    assert facts['url'] == master['uri']
    assert facts['engineers'] == {'brian paulson': 'Brian Paulson'}
    assert facts['producers'] == {}
    for mapping in (facts['producers'], facts['engineers']):
        assert isinstance(mapping, dict)
        for key, name in mapping.items():
            assert key == person_key(name) == key.lower()
            assert isinstance(name, str) and name


def test_discogs_facts_parses_extraartist_roles():
    release = {'extraartists': [
        {'name': 'Steve Albini', 'role': 'Recorded By, Mixed By'},
        {'name': 'Bob Weston (2)', 'role': 'Mastered By'},
        {'name': 'Nigel Godrich', 'role': 'Producer, Engineer'},
        {'name': 'Some Exec', 'role': 'Executive-Producer'},
        {'name': 'Another Exec', 'role': 'Executive Producer'},
        {'name': 'Co Prod', 'role': 'Co-producer'},
        {'name': 'Assistant', 'role': 'Engineer [Assistant]'},
        {'name': 'Guest', 'role': 'Cello [Uncredited]'},
        {'name': 'Remixer', 'role': 'Remix'},
    ]}
    facts = discogs_facts(None, release)
    assert facts['producers'] == {'nigel godrich': 'Nigel Godrich', 'co prod': 'Co Prod'}
    assert facts['engineers'] == {
        'steve albini': 'Steve Albini', 'bob weston': 'Bob Weston',
        'nigel godrich': 'Nigel Godrich', 'assistant': 'Assistant',
        'remixer': 'Remixer',
    }


def test_discogs_facts_empty_defaults():
    for master, release in (({}, {}), (None, None), ({}, None)):
        facts = discogs_facts(master, release)
        assert facts['have'] == 0 and facts['want'] == 0
        assert facts['rating'] is None
        assert facts['styles'] == []
        assert facts['year'] is None
        assert facts['main_release_id'] is None
        assert facts['label'] == ''
        assert facts['producers'] == {} and facts['engineers'] == {}


# ---------------------------------------------------------------------------
# Last.fm
# ---------------------------------------------------------------------------

def test_lastfm_facts_parses_string_counts():
    body = load('lastfm_album_info_spiderland')
    facts = lastfm_facts(body['album'])
    assert facts['lastfm_listeners'] == int(body['album']['listeners'])
    assert facts['lastfm_playcount'] == int(body['album']['playcount'])
    assert isinstance(facts['lastfm_listeners'], int)
    assert facts['lastfm_url'] == 'https://www.last.fm/music/Slint/Spiderland'
    # The whole response body is accepted too.
    assert lastfm_facts(body) == facts
    assert lastfm_facts({}) == {'lastfm_listeners': 0, 'lastfm_playcount': 0, 'lastfm_url': ''}
    assert lastfm_facts(None)['lastfm_listeners'] == 0


def test_module_exports_every_interface_name():
    for name in ('person_key', 'canonical_release_order', 'release_group_facts', 'release_shape',
                 'release_circle', 'artist_personnel', 'match_deezer_album', 'deezer_facts',
                 'REVIEWER_SCALES', 'parse_review_score', 'wikidata_facts', 'discogs_facts',
                 'lastfm_facts'):
        assert hasattr(credits, name)
