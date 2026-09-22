"""Offline tests for the album fingerprint.

Building one from a ListenBrainz metadata entry, thickening it with a stub
Last.fm client, applying each parsed stage payload in the shapes
docs/INTERFACES.md documents for credits.py, blending several seeds, and
flattening the lot into a row. Every payload here is hand-built; nothing
touches the network.
"""

import importlib
import json
import os
import sys
import types

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def _import_under_test():
    try:
        from radius import albums, tags
        return albums, tags
    except ImportError:
        # radius/__init__.py imports the engine, and until the engine is
        # rewritten it asks albums.py for v1 helpers this rewrite removed.
        # The modules under test never needed the package initialiser, so
        # load the package skeleton without running it.
        for name in [n for n in sys.modules if n == 'radius' or n.startswith('radius.')]:
            del sys.modules[name]
        package = types.ModuleType('radius')
        package.__path__ = [os.path.join(ROOT, 'radius')]
        sys.modules['radius'] = package
        return importlib.import_module('radius.albums'), importlib.import_module('radius.tags')


albums, tags = _import_under_test()
AlbumFeatures = albums.AlbumFeatures


# ---------------------------------------------------------------------------
# Fixtures: hand-built payloads in the INTERFACES.md shapes
# ---------------------------------------------------------------------------

def spiderland_metadata():
    """One ListenBrainz release-group metadata entry (inc=tag artist release)."""
    return {
        'release_group': {
            'name': 'Spiderland', 'type': 'Album', 'date': '1991-03-27',
            'caa_id': 123, 'caa_release_mbid': 'rel-1',
            'rels': [{'type': 'discogs', 'url': 'https://www.discogs.com/master/38099'}],
        },
        'artist': {
            'name': 'Slint',
            'artists': [{
                'artist_mbid': 'art-slint', 'name': 'Slint', 'type': 'Group',
                'area': 'United States', 'begin_year': 1986, 'end_year': 1991,
                'gender': '', 'rels': {'official homepage': 'https://slint.example',
                                       'wikidata': 'https://www.wikidata.org/wiki/Q1'},
            }],
        },
        'tag': {
            'release_group': [
                {'tag': 'post-rock', 'count': 6, 'genre_mbid': 'g-post-rock'},
                {'tag': 'slowcore', 'count': 3},
                {'tag': 'melancholic', 'count': 2},
                {'tag': 'spoken word', 'count': 1},
            ],
            'artist': [
                {'tag': 'math rock', 'count': 4, 'genre_mbid': 'g-math-rock'},
                {'tag': 'louisville', 'count': 2},
            ],
        },
    }


def release_group_facts():
    return {
        'first_release_date': '1991-03-27', 'year': 1991, 'primary_type': 'Album',
        'secondary_types': [], 'editions': 14, 'release_countries': ['US', 'GB', 'XE'],
        'mb_genres': ['post-rock', 'math rock'], 'mb_rating': 4.4, 'mb_rating_votes': 31,
        'wikidata_id': 'Q1', 'discogs_master_id': '38099',
        'links': {'discogs': 'https://www.discogs.com/master/38099',
                  'wikidata': 'https://www.wikidata.org/wiki/Q1'},
    }


def release_shape():
    return {
        'release_mbid': 'rel-1', 'status': 'Official', 'date': '1991-03-27', 'country': 'US',
        'barcode': '036172077328', 'packaging': 'Jewel Case', 'formats': ['CD'],
        'disc_count': 1, 'track_count': 6,
        'titles': ['Breadcrumb Trail', 'Nosferatu Man', 'Don, Aman',
                   'Washer', 'For Dinner...', 'Good Morning, Captain'],
        'lengths_ms': [355000, 335000, 388000, 522000, 305000, 459000],
        'recording_mbids': ['rec-1', 'rec-2', 'rec-3', 'rec-4', 'rec-5', 'rec-6'],
        'runtime_seconds': 2364, 'mean_track_seconds': 394.0, 'track_length_spread': 0.19,
    }


def release_circle():
    return {
        'labels': {'touch and go': 'Touch and Go'}, 'catalog_numbers': ['TG64'],
        'producers': {'brian paulson': 'Brian Paulson'},
        'engineers': {'brian paulson': 'Brian Paulson'},
        'performers': {'will oldham': 'Will Oldham'},
        'studios': {'river north records': 'River North Records'},
        'credits': [{'role': 'producer', 'name': 'Brian Paulson', 'mbid': 'p-1',
                     'level': 'recording', 'source': 'musicbrainz'}],
    }


def artist_personnel():
    return {
        'mbid': 'art-slint', 'name': 'Slint', 'type': 'Group', 'gender': '',
        'area': 'Louisville', 'begin_year': 1986, 'end_year': 1991,
        'people': {
            'p-pajo': {'name': 'David Pajo', 'relation': 'member of band', 'type': 'Person'},
            'p-mcmahan': {'name': 'Brian McMahan', 'relation': 'member of band', 'type': 'Person'},
            'art-tortoise': {'name': 'Tortoise', 'relation': 'collaboration', 'type': 'Group'},
        },
        'links': {'discogs': 'https://www.discogs.com/artist/1', 'bandcamp': 'https://slint.bandcamp.com'},
        'mb_genres': ['post-rock'], 'tags': [{'name': 'post-rock', 'count': 5}],
    }


def deezer_facts():
    return {
        'deezer_id': 302127, 'fans': 5400, 'explicit': False, 'label': 'Touch And Go Records',
        'release_date': '1991-03-27', 'genres': ['Alternative'], 'nb_tracks': 6, 'duration': 2364,
        'url': 'https://www.deezer.com/album/302127',
        'bpm_mean': 104.5, 'bpm_spread': 0.21, 'gain_mean': -11.2, 'gain_spread': 1.4,
        'tracks_with_bpm': 6,
    }


def wikidata_facts():
    return {
        'critic_scores': {'Q31181': 1.0, 'Q48989591': 0.94},
        'acclaim': 0.97, 'spotify_id': 'sp-1', 'discogs_master_id': '38099',
        'allmusic_id': 'mw0000262061', 'aoty_id': '1234-slint-spiderland',
        'lastfm_id': 'Slint/Spiderland', 'publication_date': '1991-03-27',
        'duration_seconds': 2364, 'producer_qids': ['Q-paulson', 'Q-nobody'],
        'label_qids': ['Q-tg'], 'genre_qids': ['Q-post-rock'], 'performer_qids': ['Q-slint'],
        'enwiki_title': 'Spiderland',
    }


def wikidata_labels():
    return {'Q31181': 'AllMusic', 'Q48989591': 'Album of the Year',
            'Q-paulson': 'Brian Paulson', 'Q-tg': 'Touch and Go Records'}


def discogs_facts():
    return {
        'styles': ['Post Rock', 'Math Rock'], 'genres': ['Rock'], 'year': 1991,
        'main_release_id': 369276, 'have': 21000, 'want': 9800, 'rating': 4.6,
        'rating_votes': 1500, 'num_for_sale': 120, 'lowest_price': 14.99,
        'formats': ['Vinyl'], 'label': 'Touch And Go', 'country': 'US',
        'url': 'https://www.discogs.com/master/38099',
        'producers': {'brian paulson': 'Brian Paulson'},
        'engineers': {'bob weston': 'Bob Weston'},
    }


def lastfm_facts():
    return {'lastfm_listeners': 410000, 'lastfm_playcount': 7600000,
            'lastfm_url': 'https://www.last.fm/music/Slint/Spiderland'}


class StubLastFm:
    """A configured Last.fm client serving canned tags and counting calls."""

    configured = True

    def __init__(self, album=None, artist=None):
        self._album = album or []
        self._artist = artist or []
        self.artist_calls = 0

    def album_tags(self, artist, title):
        return list(self._album)

    def artist_tags(self, artist):
        self.artist_calls += 1
        return list(self._artist)


GENRE_NAMES = frozenset({'post-rock', 'slowcore', 'shoegaze', 'math rock'})


def fully_enriched():
    features = albums.from_metadata(
        'rg-slint', spiderland_metadata(),
        {'total_user_count': 12000, 'total_listen_count': 90000}, GENRE_NAMES)
    albums.apply_release_group(features, release_group_facts())
    albums.apply_release(features, release_shape(), release_circle())
    albums.apply_artist(features, artist_personnel())
    albums.apply_deezer(features, deezer_facts())
    albums.apply_wikidata(features, wikidata_facts(), wikidata_labels())
    albums.apply_discogs(features, discogs_facts())
    albums.apply_lastfm_info(features, lastfm_facts())
    albums.apply_artist_release_groups(features, [
        {'release_group_mbid': 'rg-slint', 'total_user_count': 12000},
        {'release_group_mbid': 'rg-tweez', 'total_user_count': 4000},
    ])
    features.artist_neighbours = frozenset({'Rodan', 'Bedhead'})
    features.artist_neighbour_mbids = frozenset({'art-rodan', 'art-bedhead'})
    return features


# ---------------------------------------------------------------------------
# tags.py additions
# ---------------------------------------------------------------------------

def test_taxonomy_genre_names_are_normalised_parents_and_children():
    names = tags.taxonomy_genre_names()
    assert 'ambient' in names            # a parent
    assert 'dark ambient' in names       # a child
    assert all(name == tags.normalize_tag(name) for name in names)
    assert '' not in names


def test_split_profile_uses_only_the_name_set():
    genres, moods = tags.split_profile(
        {'post-rock': 1.0, 'melancholic': 0.5, 'Post Rock': 0.4}, frozenset({'post-rock'}))
    assert genres == {'post-rock': 1.0, 'Post Rock': 0.4}   # normalised before the lookup
    assert moods == {'melancholic': 0.5}


def test_split_profile_falls_back_to_the_taxonomy():
    genres, moods = tags.split_profile({'ambient': 1.0, 'hypnagogic': 0.3}, None)
    assert 'ambient' in genres and 'hypnagogic' in moods


# ---------------------------------------------------------------------------
# from_metadata
# ---------------------------------------------------------------------------

def test_tag_entries_carry_the_genre_flag_and_rescale():
    entries = albums.tag_entries([
        {'tag': 'folk', 'count': 8, 'genre_mbid': 'g1'},
        {'tag': 'chamber folk', 'count': 2},
    ])
    assert entries[0] == {'name': 'folk', 'count': 100.0, 'genre': True}
    assert entries[1]['count'] == pytest.approx(25.0)
    assert entries[1]['genre'] is False
    assert albums.tag_entries(None) == []


def test_from_metadata_splits_genres_by_flag_and_by_name_list():
    features = albums.from_metadata('rg-slint', spiderland_metadata(), None, GENRE_NAMES)
    assert features.artist == 'Slint' and features.title == 'Spiderland'
    assert features.mbid == 'rg-slint' and features.artist_mbid == 'art-slint'
    assert set(features.profile) == {'post-rock', 'slowcore', 'melancholic', 'spoken word'}
    assert set(features.genres) == {'post-rock', 'slowcore'}     # flag, then name list
    assert set(features.moods) == {'melancholic', 'spoken word'}
    assert features.genre_profile is features.genres
    assert features.mood_profile is features.moods
    assert features.year == 1991
    assert features.image_url.endswith('mbid-rel-1-123_thumb250.jpg')


def test_from_metadata_without_a_name_list_uses_the_taxonomy():
    features = albums.from_metadata('rg-slint', spiderland_metadata())
    assert 'post-rock' in features.genres        # flagged
    assert 'spoken word' in features.genres      # a taxonomy name
    assert 'slowcore' in features.moods          # not in the vendored taxonomy
    assert 'melancholic' in features.moods


def test_from_metadata_copies_the_artist_block():
    features = albums.from_metadata('rg-slint', spiderland_metadata())
    assert features.artist_area == 'United States'
    assert features.artist_type == 'Group'
    assert features.artist_debut_year == 1986
    assert features.artist_end_year == 1991
    assert features.artist_gender == ''
    assert features.artist_links == {'official homepage': 'https://slint.example',
                                     'wikidata': 'https://www.wikidata.org/wiki/Q1'}
    assert features.links == {'discogs': 'https://www.discogs.com/master/38099'}
    assert features.listeners == 0 and features.listen_count == 0


def test_untagged_record_falls_back_to_its_artist_tags_at_reduced_weight():
    metadata = spiderland_metadata()
    metadata['tag']['release_group'] = []
    features = albums.from_metadata('rg-slint', metadata, {'total_user_count': 5}, GENRE_NAMES)
    assert features.profile == {'math rock': pytest.approx(0.6), 'louisville': pytest.approx(0.3)}
    assert set(features.genres) == {'math rock'}      # the artist entry's genre flag still counts
    assert set(features.moods) == {'louisville'}
    assert features.listeners == 5


def test_nothing_to_go_on_gives_none():
    metadata = spiderland_metadata()
    metadata['tag'] = {}
    assert albums.from_metadata('rg-slint', metadata) is None
    assert albums.from_metadata('rg-x', None) is None


# ---------------------------------------------------------------------------
# enrich_tags
# ---------------------------------------------------------------------------

def test_enrich_tags_merges_and_resplits():
    features = albums.from_metadata('rg-slint', spiderland_metadata(), None, GENRE_NAMES)
    lastfm = StubLastFm(
        album=[{'name': 'shoegaze', 'count': 70}, {'name': 'dreamy', 'count': 40},
               {'name': 'post-rock', 'count': 100}],
        artist=[{'name': 'louisville scene', 'count': 30}],
    )
    assert albums.enrich_tags(features, lastfm, genre_names=GENRE_NAMES) is True
    assert features.profile['post-rock'] == 1.0            # max of both sources
    assert set(features.genres) == {'post-rock', 'slowcore', 'shoegaze'}
    assert set(features.moods) == {'melancholic', 'spoken word', 'dreamy'}
    assert 'louisville scene' in features.artist_profile


def test_enrich_tags_keeps_listenbrainz_classes_for_tags_it_already_had():
    features = albums.from_metadata('rg-slint', spiderland_metadata(), None, GENRE_NAMES)
    # 'melancholic' was a mood; a wider genre list must not reclassify it,
    # and 'slowcore' was a genre even though this list no longer has it.
    lastfm = StubLastFm(album=[{'name': 'melancholic', 'count': 90}])
    albums.enrich_tags(features, lastfm, genre_names=frozenset({'melancholic'}))
    assert 'melancholic' in features.moods
    assert 'slowcore' in features.genres


def test_enrich_tags_shares_one_artist_lookup_and_needs_a_key():
    lastfm = StubLastFm(album=[{'name': 'dreamy', 'count': 10}],
                        artist=[{'name': 'louisville scene', 'count': 10}])
    cache = {}
    one = AlbumFeatures('Slint', 'Spiderland', profile={'post-rock': 1.0})
    two = AlbumFeatures('Slint', 'Tweez', profile={'post-rock': 1.0})
    albums.enrich_tags(one, lastfm, cache, GENRE_NAMES)
    albums.enrich_tags(two, lastfm, cache, GENRE_NAMES)
    assert lastfm.artist_calls == 1
    assert 'louisville scene' in two.artist_profile
    unconfigured = StubLastFm()
    unconfigured.configured = False
    assert albums.enrich_tags(one, unconfigured) is False
    assert albums.enrich_tags(one, None) is False


# ---------------------------------------------------------------------------
# apply_* stages
# ---------------------------------------------------------------------------

def test_apply_release_group_fills_catalogue_facts():
    features = AlbumFeatures('Slint', 'Spiderland', year=1990)
    albums.apply_release_group(features, release_group_facts())
    assert features.year == 1990                        # never overwritten
    assert features.release_type == 'Album'
    assert features.editions == 14
    assert features.release_countries == frozenset({'US', 'GB', 'XE'})
    assert features.first_release_date == '1991-03-27'
    assert features.mb_genres == ['post-rock', 'math rock']
    assert features.mb_rating == 4.4 and features.mb_rating_votes == 31
    assert features.wikidata_id == 'Q1' and features.discogs_master_id == '38099'
    assert features.links['wikidata'] == 'https://www.wikidata.org/wiki/Q1'
    assert 'rg' in features.enriched


def test_apply_release_group_year_and_secondary_types():
    features = AlbumFeatures('A', 'Something', release_type='Album')
    facts = release_group_facts()
    facts['secondary_types'] = ['Live']
    albums.apply_release_group(features, facts)
    assert features.year == 1991
    assert features.secondary_types == ('Live',)
    assert not features.is_studio
    assert AlbumFeatures('A', 'Kid A', release_type='Album').is_studio


def test_apply_release_copies_shape_and_circle():
    features = AlbumFeatures('Slint', 'Spiderland', labels={'x': 'Existing'})
    albums.apply_release(features, release_shape(), release_circle())
    assert features.canonical_release_mbid == 'rel-1'
    assert features.release_date == '1991-03-27' and features.release_country == 'US'
    assert features.barcode == '036172077328' and features.formats == ['CD']
    assert features.track_count == 6 and features.runtime_seconds == 2364
    assert features.mean_track_seconds == 394.0
    assert features.track_length_spread == pytest.approx(0.19)
    assert features.track_titles[0] == 'Breadcrumb Trail'
    assert features.recording_mbids == ['rec-1', 'rec-2', 'rec-3', 'rec-4', 'rec-5', 'rec-6']
    assert features.has_tracklist
    assert features.labels == {'x': 'Existing', 'touch and go': 'Touch and Go'}
    assert features.catalog_numbers == ['TG64']
    assert features.producers == {'brian paulson': 'Brian Paulson'}
    assert features.engineers == {'brian paulson': 'Brian Paulson'}
    assert features.performers == {'will oldham': 'Will Oldham'}
    assert features.studios == {'river north records': 'River North Records'}
    assert features.credits[0]['role'] == 'producer'
    assert 'release' in features.enriched
    # An empty shape never zeroes what is known.
    albums.apply_release(features, {'track_count': 0}, {})
    assert features.track_count == 6


def test_apply_artist_builds_the_personnel_graph():
    features = AlbumFeatures('Slint', 'Spiderland', artist_mbid='art-slint', artist_area='United States')
    albums.apply_artist(features, artist_personnel())
    assert features.personnel == {
        'art-slint': 'Slint', 'p-pajo': 'David Pajo', 'p-mcmahan': 'Brian McMahan',
        'art-tortoise': 'Tortoise',
    }
    assert features.personnel_relations['p-pajo'] == 'member of band'
    assert features.personnel_relations['art-tortoise'] == 'collaboration'
    assert features.personnel_relations['art-slint'] == 'artist'
    assert features.artist_area == 'United States'       # kept: was not empty
    assert features.artist_type == 'Group'
    assert features.artist_debut_year == 1986 and features.artist_end_year == 1991
    assert features.artist_links['bandcamp'] == 'https://slint.bandcamp.com'
    assert 'artist' in features.enriched


def test_apply_deezer_sets_the_deezer_fields():
    features = AlbumFeatures('Slint', 'Spiderland')
    albums.apply_deezer(features, deezer_facts())
    assert features.deezer_id == 302127 and features.fans == 5400
    assert features.explicit is False
    assert features.deezer_label == 'Touch And Go Records'
    assert features.deezer_release_date == '1991-03-27'
    assert features.deezer_genres == ['Alternative']
    assert features.deezer_url == 'https://www.deezer.com/album/302127'
    assert features.bpm_mean == 104.5 and features.bpm_spread == 0.21
    assert features.gain_mean == -11.2 and features.gain_spread == 1.4
    assert features.tracks_with_bpm == 6
    assert features.label == 'Touch And Go Records'          # no MB label yet
    assert 'deezer' in features.enriched


def test_apply_wikidata_resolves_labels_and_merges_the_circle():
    features = AlbumFeatures('Slint', 'Spiderland', wikidata_id='Q1',
                             producers={'brian paulson': 'Brian Paulson'})
    albums.apply_wikidata(features, wikidata_facts(), wikidata_labels())
    assert features.critic_scores == {'AllMusic': 1.0, 'Album of the Year': 0.94}
    assert features.acclaim == 0.97
    assert features.spotify_id == 'sp-1'
    assert features.discogs_master_id == '38099'
    assert features.producers == {'brian paulson': 'Brian Paulson'}   # same key, not duplicated
    assert features.labels == {'touch and go': 'Touch and Go Records'}
    assert features.first_release_date == '1991-03-27' and features.year == 1991
    assert features.links['wikidata'] == 'https://www.wikidata.org/wiki/Q1'
    assert features.links['spotify'] == 'https://open.spotify.com/album/sp-1'
    assert features.links['allmusic'].endswith('mw0000262061')
    assert features.links['aoty'].endswith('1234-slint-spiderland.php')
    assert features.links['lastfm'].endswith('Slint/Spiderland')
    assert features.links['wikipedia'].endswith('/wiki/Spiderland')
    assert 'wikidata' in features.enriched


def test_apply_wikidata_without_labels_keeps_qids_for_scores_only():
    features = AlbumFeatures('A', 'B')
    albums.apply_wikidata(features, wikidata_facts())
    assert features.critic_scores == {'Q31181': 1.0, 'Q48989591': 0.94}
    assert features.producers == {}     # an unresolved Q-id is not a name


def test_apply_discogs_merges_community_stats_and_credits():
    features = AlbumFeatures('Slint', 'Spiderland', engineers={'brian paulson': 'Brian Paulson'})
    albums.apply_discogs(features, discogs_facts())
    assert features.styles == ['Post Rock', 'Math Rock']
    assert features.have == 21000 and features.want == 9800
    assert features.want_ratio == pytest.approx(9800 / 21000)
    assert features.discogs_rating == 4.6 and features.discogs_votes == 1500
    assert features.num_for_sale == 120 and features.lowest_price == 14.99
    assert features.discogs_url == 'https://www.discogs.com/master/38099'
    assert features.producers == {'brian paulson': 'Brian Paulson'}
    assert features.engineers == {'brian paulson': 'Brian Paulson', 'bob weston': 'Bob Weston'}
    assert features.labels == {'touch and go': 'Touch And Go'}
    assert features.release_country == 'US' and features.year == 1991
    assert features.formats == ['Vinyl']
    assert 'discogs' in features.enriched


def test_apply_lastfm_info():
    features = AlbumFeatures('Slint', 'Spiderland')
    albums.apply_lastfm_info(features, lastfm_facts())
    assert features.lastfm_listeners == 410000
    assert features.lastfm_playcount == 7600000
    assert features.links['lastfm'] == 'https://www.last.fm/music/Slint/Spiderland'
    assert 'lastfm_info' in features.enriched


def test_empty_payloads_are_no_ops_without_a_stage_tag():
    features = AlbumFeatures('A', 'B')
    for apply in (albums.apply_release_group, albums.apply_artist, albums.apply_deezer,
                  albums.apply_discogs, albums.apply_lastfm_info):
        apply(features, None)
        apply(features, {})
    albums.apply_release(features, None, None)
    albums.apply_wikidata(features, {})
    assert features.enriched == set()
    assert features == AlbumFeatures('A', 'B')


def test_canonicity_is_the_share_of_the_artists_biggest_record():
    features = AlbumFeatures('A', 'B', listeners=1000, artist_listeners=4000)
    # The artist total is not trusted: ListenBrainz maps listens to release
    # groups far less completely than to artists.
    assert features.canonicity is None
    albums.apply_artist_release_groups(features, [
        {'total_user_count': 1000}, {'total_user_count': 4000}, {'total_user_count': '0'}, 'junk',
    ])
    assert features.artist_rg_listeners == 5000
    assert features.artist_top_listeners == 4000
    assert features.canonicity == pytest.approx(0.25)
    assert 'canonicity' in features.enriched
    assert AlbumFeatures('A', 'B', listeners=10).canonicity is None
    assert AlbumFeatures('A', 'B', listeners=10, artist_top_listeners=5).canonicity == 1.0


def test_display_properties():
    features = AlbumFeatures('A', 'B', producers={'b': 'Zed', 'a': 'Amy'},
                             studios={'s': 'Sun Studio'}, deezer_label='Deezer Says')
    assert features.producer_names == ['Amy', 'Zed']
    assert features.studio_names == ['Sun Studio']
    assert features.label == 'Deezer Says'
    features.labels = {'touch and go': 'Touch and Go', 'other': 'Other'}
    assert features.label == 'Touch and Go'
    assert features.want_ratio is None
    assert AlbumFeatures('A', 'B', have=0, want=5).want_ratio is None


def test_person_key_matches_the_credits_recipe():
    key = albums._person_key
    assert key('Steve Albini') == 'steve albini'
    assert key('  The Beatles ') == 'beatles'
    assert key('Björk') == 'bjork'
    assert key('Jean-Michel Jarre') == key('Jean Michel Jarre')
    assert key('') == '' and key(None) == ''


# ---------------------------------------------------------------------------
# blend
# ---------------------------------------------------------------------------

def test_blend_averages_profiles_and_unions_the_rest():
    one = AlbumFeatures('Slint', 'Spiderland', mbid='rg-1', artist_mbid='art-slint',
                        profile={'post-rock': 1.0, 'slowcore': 0.5},
                        genres={'post-rock': 1.0, 'slowcore': 0.5}, moods={},
                        artist_profile={'louisville': 1.0},
                        listeners=1000, listen_count=5000, year=1991,
                        runtime_seconds=2400, track_count=6, artist_debut_year=1986,
                        artist_area='US', artist_type='Group', release_type='Album',
                        personnel={'p-1': 'David Pajo'}, producers={'brian paulson': 'Brian Paulson'},
                        artist_neighbours=frozenset({'Rodan'}), recording_mbids=['rec-1'],
                        studios={'s-1': 'Studio One'}, labels={'touch and go': 'Touch and Go'},
                        fans=100, enriched={'rg'})
    two = AlbumFeatures('Talk Talk', 'Laughing Stock', mbid='rg-2', artist_mbid='art-tt',
                        profile={'post-rock': 0.5, 'ambient': 1.0},
                        genres={'post-rock': 0.5, 'ambient': 1.0}, moods={},
                        artist_profile={'new wave': 1.0},
                        listeners=3000, listen_count=0, year=1993,
                        runtime_seconds=0, track_count=6, artist_debut_year=None,
                        artist_area='GB', artist_type='Group', release_type='Album',
                        personnel={'p-2': 'Mark Hollis'}, producers={'tim friese greene': 'Tim Friese-Greene'},
                        artist_neighbours=frozenset({'Bark Psychosis'}), recording_mbids=['rec-1', 'rec-9'],
                        engineers={'phill brown': 'Phill Brown'}, acclaim=0.9, enriched={'wikidata'})
    blended = albums.blend([one, two])

    assert blended.artist == 'Slint + Talk Talk'
    assert blended.title == 'Spiderland + Laughing Stock'
    assert blended.mbid == '' and blended.artist_mbid == ''
    assert blended.seed_mbids == ('rg-1', 'rg-2')
    assert blended.seed_artist_mbids == ('art-slint', 'art-tt')
    # mean of (1.0, 0.5) = 0.75 for post-rock; (0, 1.0) = 0.5 for ambient; (0.5, 0) = 0.25 for
    # slowcore; renormalised so the peak sits at 1.0.
    assert blended.profile == {'post-rock': pytest.approx(1.0), 'slowcore': pytest.approx(1 / 3),
                               'ambient': pytest.approx(2 / 3)}
    assert blended.genres == blended.profile
    assert blended.moods == {}
    assert set(blended.artist_profile) == {'louisville', 'new wave'}
    assert blended.listeners == 2000
    assert blended.listen_count == 5000              # 0 means unknown, so it is ignored
    assert blended.year == 1992
    assert blended.runtime_seconds == 2400
    assert blended.track_count == 6
    assert blended.artist_debut_year == 1986
    assert blended.fans == 100
    assert blended.acclaim == pytest.approx(0.9)
    assert blended.personnel == {'p-1': 'David Pajo', 'p-2': 'Mark Hollis'}
    assert set(blended.producers) == {'brian paulson', 'tim friese greene'}
    assert blended.engineers == {'phill brown': 'Phill Brown'}
    assert blended.studios == {'s-1': 'Studio One'}
    assert blended.labels == {'touch and go': 'Touch and Go'}
    assert blended.artist_neighbours == frozenset({'Rodan', 'Bark Psychosis'})
    assert blended.recording_mbids == ['rec-1', 'rec-9']
    assert blended.artist_area == ''                 # seeds disagree
    assert blended.artist_type == 'Group'            # seeds agree
    assert blended.release_type == 'Album'
    assert blended.enriched == {'rg', 'wikidata'}
    assert blended.career_stage == 6


def test_blend_of_one_and_of_nothing():
    only = AlbumFeatures('A', 'B', mbid='rg-1', artist_mbid='art-1', profile={'folk': 0.4}, year=2001)
    blended = albums.blend([only])
    assert blended.profile == {'folk': pytest.approx(1.0)}
    assert blended.seed_mbids == ('rg-1',) and blended.seed_artist_mbids == ('art-1',)
    assert blended.year == 2001
    assert 'folk' in blended.genres                  # hand-built seed: split by the taxonomy
    assert albums.blend([]) is None
    assert albums.blend(None) is None


# ---------------------------------------------------------------------------
# as_row
# ---------------------------------------------------------------------------

SAMPLE_ROW_KEYS = [
    'artist', 'album', 'year', 'mbid', 'artist_mbid', 'release_type', 'from', 'artist_type',
    'artist_gender', 'artist_end_year', 'artist_links', 'listeners', 'listens', 'listens_each',
    'canonicity', 'artist_rg_listeners', 'fans', 'lastfm_listeners', 'acclaim', 'critic_scores',
    'mb_rating', 'discogs_rating', 'have', 'want', 'want_ratio', 'tracks', 'runtime_min',
    'bpm_mean', 'gain_mean', 'explicit', 'genre_tags', 'mood_tags', 'lineage_tags', 'mb_genres',
    'styles', 'personnel', 'personnel_count', 'producers', 'engineers', 'performers', 'studios',
    'label', 'labels', 'neighbours', 'editions', 'release_countries', 'first_release_date',
    'canonical_release_mbid', 'formats', 'track_titles', 'recording_mbids', 'credits',
    'wikidata_id', 'discogs_master_id', 'spotify_id', 'deezer_id', 'links', 'enriched',
    'seed_mbids', 'url', 'image_url',
]


def test_as_row_is_flat_json_and_complete():
    row = fully_enriched().as_row()
    json.dumps(row)                                   # every value is a JSON scalar
    assert all(not isinstance(v, (dict, list, set, frozenset, tuple)) for v in row.values())
    for key in SAMPLE_ROW_KEYS:
        assert key in row, key
    assert row['artist'] == 'Slint' and row['album'] == 'Spiderland'
    assert row['genre_tags'] == 'post-rock, slowcore'
    assert row['mood_tags'] == 'melancholic, spoken word'
    assert row['producers'] == 'Brian Paulson'
    assert row['engineers'] == 'Bob Weston, Brian Paulson'
    assert row['studios'] == 'River North Records'
    assert row['label'] == 'Touch and Go'
    # Discogs' 'Touch And Go' and MusicBrainz's 'Touch and Go Records' land
    # on the same name key as 'Touch and Go', so the earliest name is kept.
    assert row['labels'] == 'Touch and Go'
    assert row['personnel_count'] == 4 and 'David Pajo' in row['personnel']
    assert row['neighbours'] == 'Bedhead, Rodan' and row['neighbours_count'] == 2
    assert row['release_countries'] == 'GB, US, XE'
    assert row['critic_scores'] == 'Album of the Year=0.94, AllMusic=1.0'
    assert row['canonicity'] == 1.0                  # 12000 / max(12000, 4000)
    assert row['listens_each'] == 7.5
    assert row['runtime_min'] == 39.4
    assert row['explicit'] is False
    assert row['want_ratio'] == round(9800 / 21000, 3)
    assert row['is_studio'] is True
    assert 'canonicity' in row['enriched'] and 'wikidata' in row['enriched']
    assert row['seed_mbids'] == ''


def test_as_row_order_is_stable_and_empty_is_fine():
    a = list(AlbumFeatures('A', 'B').as_row())
    b = list(fully_enriched().as_row())
    assert a == b
    empty = AlbumFeatures('A', 'B').as_row()
    json.dumps(empty)
    assert empty['listeners'] is None and empty['explicit'] is None
    assert empty['genre_tags'] == '' and empty['personnel_count'] == 0


def test_every_field_has_a_row_column():
    """Every dataclass field is represented in the row, under its own name or
    the flattened alias the UI has always used."""
    aliases = {
        'title': 'album', 'listen_count': 'listens', 'artist_area': 'from',
        'profile': 'tags', 'genres': 'genre_tags', 'moods': 'mood_tags',
        'artist_profile': 'lineage_tags', 'track_count': 'tracks',
        'runtime_seconds': 'runtime_min', 'artist_neighbours': 'neighbours',
        'artist_neighbour_mbids': 'neighbours_count', 'artist_neighbours_ranked': 'neighbours',
    }
    row = AlbumFeatures('A', 'B').as_row()
    for name in albums.FIELD_NAMES:
        assert aliases.get(name, name) in row, name
