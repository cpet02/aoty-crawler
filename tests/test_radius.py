"""Offline tests for the similarity engine.

Stub clients serve canned ListenBrainz/MusicBrainz payloads, so the whole
pipeline — seed resolution, candidate gathering, bulk fingerprinting, idf,
ranking — runs with no network. None of these services need an API key, and
neither do the tests.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from radius import albums, tags, text
from radius.engine import SeedNotFound, Services, find_similar
from radius.similarity import SimilarityWeights, axis_distances, compare


# ---------------------------------------------------------------------------
# Tag handling
# ---------------------------------------------------------------------------

def test_collection_and_shelf_tags_are_dropped():
    assert not tags.is_descriptive('albums i own')
    assert not tags.is_descriptive('seen live')
    assert not tags.is_descriptive('my favourite records')
    assert not tags.is_descriptive('rock and indie')      # retailer shelf
    assert not tags.is_descriptive('américain')           # nationality
    assert tags.is_descriptive('chamber folk')
    assert tags.is_descriptive('melancholic')


def test_era_tags_are_parsed_not_described():
    assert tags.era_year('1997') == 1997
    assert tags.era_year('90s') == 1990
    assert tags.era_year('1980s') == 1980
    assert tags.era_year('00s') == 2000
    assert tags.era_year('shoegaze') is None
    # Era belongs to the era axis, not the descriptive vector.
    assert not tags.is_descriptive('1997')


def test_musicbrainz_vote_counts_rescale_but_keep_their_order():
    """MB counts are a handful of votes, not Last.fm's 0-100 scale. What has
    to survive rescaling is the ordering: broad genre above its subgenre."""
    entries = albums.tag_entries([
        {'tag': 'folk', 'count': 8},
        {'tag': 'chamber folk', 'count': 2},
        {'tag': 'indie', 'count': 4},
    ])
    profile = tags.tag_profile(entries)
    assert list(profile) == ['folk', 'indie', 'chamber folk']
    assert profile['folk'] == 1.0
    assert profile['chamber folk'] == pytest.approx(0.25)


def test_subgenres_outweigh_root_genres():
    assert tags.specificity('chamber folk') > tags.specificity('folk')


def test_idf_discounts_ubiquitous_tags():
    pool = [{'rock': 1.0, 'shoegaze': 1.0}, {'rock': 1.0}, {'rock': 1.0}]
    idf = tags.build_idf(pool)
    assert idf['shoegaze'] > idf['rock']


def test_aliases_collapse_spellings():
    assert tags.normalize_tag('Post Rock') == tags.normalize_tag('post-rock')
    assert tags.normalize_tag('Hip Hop') == tags.normalize_tag('hiphop')


# ---------------------------------------------------------------------------
# Fingerprint fields
# ---------------------------------------------------------------------------

def test_edition_noise_is_stripped_from_keys():
    assert (albums.album_key('Radiohead', 'OK Computer (Deluxe Edition)')
            == albums.album_key('Radiohead', 'OK Computer'))


def test_non_studio_is_caught_by_type_or_title():
    by_type = albums.AlbumFeatures('A', 'Something', release_type='Live')
    by_secondary = albums.AlbumFeatures('A', 'Something', release_type='Album',
                                        secondary_types=('Compilation',))
    by_title = albums.AlbumFeatures('A', 'Live at Leeds', release_type='Album')
    studio = albums.AlbumFeatures('A', 'Kid A', release_type='Album')
    assert not by_type.is_studio
    assert not by_secondary.is_studio
    assert not by_title.is_studio
    assert studio.is_studio


def test_definition_measures_tag_consensus():
    focused = albums.AlbumFeatures('A', 'One', profile={'black metal': 1.0, 'metal': 0.1})
    scattered = albums.AlbumFeatures('B', 'Two',
                                     profile={f'tag{i}': 1.0 for i in range(8)})
    assert focused.definition < scattered.definition


def test_canonicity_is_share_of_artist_audience():
    deep_cut = albums.AlbumFeatures('A', 'One', listeners=1_000, artist_listeners=100_000)
    calling_card = albums.AlbumFeatures('A', 'Two', listeners=90_000, artist_listeners=100_000)
    assert deep_cut.canonicity < calling_card.canonicity


def test_career_stage_needs_both_years():
    late = albums.AlbumFeatures('A', 'One', year=2000, artist_debut_year=1980)
    assert late.career_stage == 20
    assert albums.AlbumFeatures('A', 'Two', year=2000).career_stage is None


def test_metadata_year_is_read_from_a_date_field():
    features = albums.from_metadata('mbid-1', {
        'release_group': {'name': 'X', 'date': '2007-07-08', 'type': 'Album'},
        'artist': {'name': 'Y', 'artists': [{'name': 'Y', 'artist_mbid': 'a1'}]},
        'tag': {'release_group': [{'tag': 'folk', 'count': 3}]},
    })
    assert features.year == 2007


def test_prose_profile_drops_wiki_boilerplate():
    body = ('Recorded in a Wisconsin cabin over one winter. '
            'User-contributed text is available under the Creative Commons.')
    profile = text.prose_profile(text.clean_prose(body))
    assert 'wisconsin' in profile
    assert 'creative' not in profile


# ---------------------------------------------------------------------------
# Distance
# ---------------------------------------------------------------------------

def _features(**kwargs):
    base = dict(artist='X', title='Y', listeners=10_000, listen_count=30_000,
                profile={'folk': 1.0}, year=2010)
    base.update(kwargs)
    return albums.AlbumFeatures(**base)


def test_unmeasurable_axes_are_omitted_not_scored_as_perfect():
    seed = _features(year=None)
    other = _features(year=None)
    distances = axis_distances(seed, other, {'genre': {'folk': 1.0}},
                               {'genre': {'folk': 1.0}})
    assert 'era' not in distances
    # No tracklist on either side means no shape axes either.
    assert 'scale' not in distances
    assert 'pacing' not in distances
    # Neither has an area, so provenance can't be judged.
    assert 'origin' not in distances


def test_identical_albums_sit_at_distance_zero():
    vectors = {'genre': {'folk': 1.0}}
    match = compare(_features(), _features(), vectors, vectors, SimilarityWeights())
    assert match.distance == pytest.approx(0.0, abs=1e-9)


def test_disabled_axes_do_not_affect_distance():
    seed = _features(listeners=1_000)
    other = _features(listeners=5_000_000)
    vectors = {'genre': {'folk': 1.0}}
    match = compare(seed, other, vectors, vectors, SimilarityWeights.only('genre'))
    assert match.distance == pytest.approx(0.0, abs=1e-9)
    with_reach = SimilarityWeights.only('genre', reach=1.0)
    assert compare(seed, other, vectors, vectors, with_reach).distance > 0.4


def test_origin_axis_reads_area_and_act_type():
    vectors = {'genre': {'folk': 1.0}}
    weights = SimilarityWeights.only('origin')
    same = compare(_features(artist_area='United States', artist_type='Group'),
                   _features(artist_area='United States', artist_type='Group'),
                   vectors, vectors, weights)
    different = compare(_features(artist_area='United States', artist_type='Group'),
                        _features(artist_area='Japan', artist_type='Person'),
                        vectors, vectors, weights)
    assert same.distance == pytest.approx(0.0)
    assert different.distance == pytest.approx(1.0)


def test_compare_returns_none_when_nothing_enabled_is_measurable():
    seed = _features(year=None)
    assert compare(seed, _features(year=None), {}, {},
                   SimilarityWeights.only('era')) is None


# ---------------------------------------------------------------------------
# End to end, against stub services
# ---------------------------------------------------------------------------

SEED_MBID = 'rg-seed'
ALBUMS = {
    'rg-seed': ('Bon Iver', 'For Emma, Forever Ago', 'a-bon', 2007, 'Album',
                [('indie folk', 8), ('folk', 6), ('chamber folk', 2)]),
    'rg-fleet': ('Fleet Foxes', 'Fleet Foxes', 'a-fleet', 2008, 'Album',
                 [('indie folk', 7), ('folk', 5), ('chamber folk', 3)]),
    'rg-iron': ('Iron & Wine', 'Our Endless Numbered Days', 'a-iron', 2004, 'Album',
                [('indie folk', 5), ('singer-songwriter', 4)]),
    'rg-live': ('Fleet Foxes', 'Live at the Bowl', 'a-fleet', 2010, 'Live',
                [('indie folk', 4)]),
    'rg-untagged': ('Nobody', 'Untagged Record', 'a-nobody', 2011, 'Album', []),
}


class StubMusicBrainz:
    calls_made = 0
    cache_hits = 0

    def find_album(self, artist=None, album=None, query=None, limit=10):
        return [{
            'id': SEED_MBID, 'title': 'For Emma, Forever Ago',
            'primary-type': 'Album', 'first-release-date': '2007-07-08',
            'artist-credit': [{'artist': {'name': 'Bon Iver', 'id': 'a-bon'}}],
        }]

    def release_groups_by_tag(self, tag, limit=100):
        return [
            {'id': mbid, 'title': data[1], 'primary-type': data[4],
             'artist-credit': [{'artist': {'name': data[0], 'id': data[2]}}]}
            for mbid, data in ALBUMS.items() if mbid != SEED_MBID
        ]

    def tracklist(self, mbid):
        return ['One Two Three', 'Four'], [240000, 200000]

    def article_ref(self, mbid):
        # Half direct Wikipedia links, half Wikidata ids — which is what
        # MusicBrainz actually looks like these days.
        if mbid not in ALBUMS:
            return None
        if mbid == 'rg-fleet':
            return 'wikidata', 'Q-fleet'
        return 'wikipedia', ALBUMS[mbid][1]


class StubListenBrainz:
    calls_made = 0
    cache_hits = 0

    def metadata(self, mbids, inc=None):
        out = {}
        for mbid in mbids:
            if mbid not in ALBUMS:
                continue
            artist, title, artist_mbid, year, rtype, tag_list = ALBUMS[mbid]
            out[mbid] = {
                'release_group': {'name': title, 'date': f'{year}-01-01', 'type': rtype},
                'artist': {'name': artist, 'artists': [{
                    'name': artist, 'artist_mbid': artist_mbid,
                    'area': 'United States', 'type': 'Group', 'begin_year': year - 3,
                }]},
                'tag': {
                    'release_group': [{'tag': t, 'count': c} for t, c in tag_list],
                    'artist': [{'tag': 'indie folk', 'count': 5}],
                },
            }
        return out

    def popularity(self, mbids):
        return {
            mbid: {'total_user_count': 5000, 'total_listen_count': 150000}
            for mbid in mbids if mbid in ALBUMS
        }

    def artist_popularity(self, artist_mbids):
        return {mbid: {'total_user_count': 40000} for mbid in artist_mbids}

    def similar_artists(self, artist_mbid, algorithm=None):
        return [{'artist_mbid': 'a-fleet', 'name': 'Fleet Foxes', 'score': 900},
                {'artist_mbid': 'a-iron', 'name': 'Iron & Wine', 'score': 700}]

    def top_release_groups(self, artist_mbid):
        return [
            {'release_group_mbid': mbid, 'release_group': {'name': data[1]},
             'artist': {'name': data[0]}}
            for mbid, data in ALBUMS.items() if data[2] == artist_mbid
        ]


class StubWikipedia:
    calls_made = 0
    cache_hits = 0

    def titles_for_wikidata(self, ids):
        return {'Q-fleet': 'Fleet Foxes (album)'}

    def extracts(self, titles):
        return {title: f'{title} was recorded in a cabin one winter.'
                for title in titles}


def stub_services():
    return Services(musicbrainz=StubMusicBrainz(),
                    listenbrainz=StubListenBrainz(),
                    wikipedia=StubWikipedia())


def test_end_to_end_ranks_neighbours_without_network_or_key():
    result = find_similar(artist='Bon Iver', album='For Emma, Forever Ago',
                          services=stub_services(), radius=0.9, top_n=10)
    assert result.seed.artist == 'Bon Iver'
    assert result.seed.year == 2007
    assert result.matches, 'expected at least one match'
    names = [m.features.title for m in result.matches]
    # Same artist excluded by default; live records and untagged ones dropped.
    assert 'For Emma, Forever Ago' not in names
    assert 'Live at the Bowl' not in names
    # The closer tag profile should outrank the looser one.
    assert names.index('Fleet Foxes') < names.index('Our Endless Numbered Days')
    for match in result.matches:
        assert 0.0 <= match.distance <= 0.9
        assert match.axes


def test_album_with_no_tags_falls_back_to_its_artist_but_ranks_lower():
    """An untagged record is still placeable through its artist's tags, at
    reduced weight — but it must not outrank a properly tagged neighbour."""
    result = find_similar(artist='Bon Iver', album='For Emma, Forever Ago',
                          services=stub_services(), radius=0.95, top_n=10)
    names = [m.features.title for m in result.matches]
    if 'Untagged Record' in names:
        assert names.index('Fleet Foxes') < names.index('Untagged Record')


def test_album_with_neither_album_nor_artist_tags_is_dropped():
    assert albums.from_metadata('mbid-x', {
        'release_group': {'name': 'X', 'date': '2011-01-01'},
        'artist': {'name': 'Y', 'artists': [{'name': 'Y'}]},
        'tag': {},
    }) is None


def test_finalists_get_tracklists_so_shape_axes_engage():
    result = find_similar(artist='Bon Iver', album='For Emma, Forever Ago',
                          services=stub_services(), radius=0.9, top_n=5)
    top = result.matches[0]
    assert top.features.has_tracklist
    assert 'scale' in top.axes and 'pacing' in top.axes


def test_prose_axis_engages_through_both_article_routes():
    """MusicBrainz points at Wikipedia directly for some albums and at
    Wikidata for others; prose has to survive both.

    Prose ships switched off (see SimilarityWeights), so this asks for it
    explicitly — the plumbing still has to work for anyone who turns it up.
    """
    weights = SimilarityWeights(prose=1.0)
    result = find_similar(artist='Bon Iver', album='For Emma, Forever Ago',
                          services=stub_services(), radius=0.9, top_n=5,
                          weights=weights)
    assert result.seed.prose, 'seed should have prose'
    assert any('prose' in m.axes for m in result.matches)
    via_wikidata = [m for m in result.matches if m.features.title == 'Fleet Foxes']
    assert via_wikidata and via_wikidata[0].features.prose


def test_radius_bounds_the_result_set():
    wide = find_similar(artist='Bon Iver', album='For Emma, Forever Ago',
                        services=stub_services(), radius=0.9)
    tight = find_similar(artist='Bon Iver', album='For Emma, Forever Ago',
                         services=stub_services(), radius=0.05)
    assert len(tight.matches) <= len(wide.matches)


def test_more_obscure_filter_excludes_better_known_albums():
    services = stub_services()
    services.listenbrainz.popularity = lambda mbids: {
        mbid: {'total_user_count': 900 if mbid != SEED_MBID else 5000,
               'total_listen_count': 9000}
        for mbid in mbids if mbid in ALBUMS
    }
    result = find_similar(artist='Bon Iver', album='For Emma, Forever Ago',
                          services=services, radius=0.9, obscurity='more_obscure')
    assert result.matches
    for match in result.matches:
        assert match.features.listeners < result.seed.listeners


def test_missing_seed_raises_with_a_usable_message():
    services = stub_services()
    services.musicbrainz.find_album = lambda **kwargs: []
    with pytest.raises(SeedNotFound):
        find_similar(query='nonsense that matches nothing', services=services)


def test_one_artist_cannot_fill_the_whole_result_list():
    """A close neighbour returning its entire discography is technically
    correct and useless as a recommendation."""
    result = find_similar(artist='Bon Iver', album='For Emma, Forever Ago',
                          services=stub_services(), radius=0.95, top_n=10,
                          max_per_artist=1)
    artists = [m.features.artist for m in result.matches]
    assert len(artists) == len(set(artists))
