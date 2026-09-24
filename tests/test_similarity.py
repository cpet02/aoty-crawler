"""Offline tests for the similarity axes, the weighted mean and the reasons.

Every AlbumFeatures here is built by hand in the shapes albums.py and
credits.py produce (personnel keyed by mbid, circle dicts keyed by person
key), so the axes are exercised without a client or a payload in sight.
"""

import importlib
import os
import sys
import types

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def _import_under_test():
    try:
        from radius import albums, similarity
        return albums, similarity
    except ImportError:
        # radius/__init__.py imports the engine, which until it is rewritten
        # asks albums.py for v1 helpers that no longer exist. The modules
        # under test never needed the package initialiser, so load the
        # package skeleton without running it.
        for name in [n for n in sys.modules if n == 'radius' or n.startswith('radius.')]:
            del sys.modules[name]
        package = types.ModuleType('radius')
        package.__path__ = [os.path.join(ROOT, 'radius')]
        sys.modules['radius'] = package
        return importlib.import_module('radius.albums'), importlib.import_module('radius.similarity')


albums, similarity = _import_under_test()
AlbumFeatures = albums.AlbumFeatures
SimilarityWeights = similarity.SimilarityWeights
Evidence = similarity.Evidence
Match = similarity.Match
compare = similarity.compare
axis_distances = similarity.axis_distances
explain = similarity.explain

ALL_AXES = (
    'genre', 'mood', 'definition', 'personnel', 'circle', 'co_listening', 'kinship',
    'lineage', 'convergence', 'reach', 'devotion', 'canonicity', 'acclaim', 'era',
    'scale', 'pacing', 'energy', 'origin', 'career',
)
SYMMETRIC_AXES = tuple(a for a in ALL_AXES if a not in similarity.EVIDENCE_AXES)

VECTORS = {
    'genre': {'post-rock': 1.0, 'math rock': 0.8},
    'mood': {'melancholic': 0.5, 'spoken word': 0.3},
    'lineage': {'louisville': 1.0, 'post-hardcore': 0.7},
}
NEIGHBOURS = frozenset(f'artist {i}' for i in range(100))


def _features(**overrides):
    base = dict(
        artist='Slint', title='Spiderland', mbid='rg-spiderland', artist_mbid='art-slint',
        listeners=50_000, listen_count=400_000, artist_listeners=80_000, artist_top_listeners=80_000,
        profile={'post-rock': 1.0, 'math rock': 0.8, 'melancholic': 0.5, 'spoken word': 0.3},
        genres={'post-rock': 1.0, 'math rock': 0.8},
        moods={'melancholic': 0.5, 'spoken word': 0.3},
        artist_profile={'louisville': 1.0, 'post-hardcore': 0.7},
        artist_neighbours=NEIGHBOURS,
        year=1991, artist_area='United States', artist_type='Group', artist_debut_year=1986,
        track_count=6, runtime_seconds=2400, mean_track_seconds=400.0, track_length_spread=0.3,
    )
    base.update(overrides)
    return AlbumFeatures(**base)


def _connected(**overrides):
    """A record with every axis measurable, including the evidence ones."""
    base = dict(
        personnel={'p-pajo': 'David Pajo', 'p-mcmahan': 'Brian McMahan', 'art-slint': 'Slint'},
        personnel_relations={'p-pajo': 'member of band', 'p-mcmahan': 'member of band', 'art-slint': 'artist'},
        producers={'steve albini': 'Steve Albini'},
        engineers={'bob weston': 'Bob Weston'},
        studios={'electrical audio': 'Electrical Audio'},
        labels={'touch and go': 'Touch and Go'},
        fans=3_000, lastfm_listeners=120_000,
        bpm_mean=98.0, gain_mean=-9.5, acclaim=0.85,
    )
    base.update(overrides)
    return _features(**base)


def _bare(**overrides):
    """A record with nothing measurable beyond a name."""
    base = dict(
        listeners=0, listen_count=0, artist_listeners=0, profile={}, genres={}, moods={},
        artist_profile={}, artist_neighbours=frozenset(), year=None, artist_area='',
        artist_type='', artist_debut_year=None, track_count=0, runtime_seconds=0,
        mean_track_seconds=0.0, track_length_spread=0.0,
    )
    base.update(overrides)
    return _features(**base)


def _distances(seed, other, evidence=None, seed_vectors=VECTORS, other_vectors=VECTORS):
    return axis_distances(seed, other, seed_vectors, other_vectors, evidence)


# ---------------------------------------------------------------------------
# Weights, labels, groups
# ---------------------------------------------------------------------------

def test_weights_cover_exactly_the_nineteen_axes_with_design_defaults():
    assert tuple(SimilarityWeights.axis_names()) == ALL_AXES
    defaults = SimilarityWeights().as_dict()
    assert defaults['genre'] == 1.0 and defaults['mood'] == 0.8 and defaults['definition'] == 0.1
    assert defaults['personnel'] == 0.9 and defaults['circle'] == 0.6 and defaults['co_listening'] == 0.5
    assert defaults['kinship'] == 0.7 and defaults['lineage'] == 0.45 and defaults['convergence'] == 0.3
    assert defaults['reach'] == 0.3 and defaults['devotion'] == 0.3 and defaults['canonicity'] == 0.15
    assert defaults['acclaim'] == 0.0
    assert defaults['era'] == 0.2 and defaults['scale'] == 0.15 and defaults['pacing'] == 0.15
    assert defaults['energy'] == 0.2 and defaults['origin'] == 0.15 and defaults['career'] == 0.15
    assert 'acclaim' not in SimilarityWeights().active()
    assert similarity.EVIDENCE_AXES == ('personnel', 'circle', 'co_listening')


def test_only_switches_everything_else_off():
    weights = SimilarityWeights.only('genre', era=0.5)
    assert weights.active() == {'genre': 1.0, 'era': 0.5}


def test_labels_and_groups_cover_every_axis_once():
    assert set(similarity.AXIS_LABELS) == set(ALL_AXES)
    assert list(similarity.AXIS_GROUPS) == ['Sound', 'Connection', 'Reception', 'Shape', 'Provenance']
    grouped = [axis for axes in similarity.AXIS_GROUPS.values() for axis in axes]
    assert sorted(grouped) == sorted(ALL_AXES)
    assert len(grouped) == len(ALL_AXES)


def test_every_axis_has_a_hover_tip():
    """Tips keyed to axis names that no longer exist are how the old UI's
    tooltips broke; this is the guard."""
    assert set(similarity.AXIS_HELP) == set(ALL_AXES)
    assert all(tip.strip() for tip in similarity.AXIS_HELP.values())


def test_presets_name_only_real_axes_and_build_valid_weights():
    for name, (tip, values) in similarity.PRESETS.items():
        assert tip.strip(), name
        assert set(values) <= set(ALL_AXES), name
        weights = SimilarityWeights.only(**values)
        assert weights.active() == values, name
        assert all(0 < value <= 2.0 for value in values.values()), name


# ---------------------------------------------------------------------------
# The weighted mean
# ---------------------------------------------------------------------------

def test_identical_albums_sit_at_distance_zero_with_full_coverage():
    seed, other = _connected(), _connected()
    evidence = Evidence(convergence=1.0, album_hits=3.0)
    match = compare(seed, other, VECTORS, VECTORS, SimilarityWeights(), evidence=evidence)
    assert match.distance == pytest.approx(0.0, abs=1e-9)
    assert match.coverage == pytest.approx(1.0)
    assert set(match.axes) == set(ALL_AXES)
    assert match.strengths == {'personnel': 1.0, 'circle': 1.0, 'co_listening': 1.0}
    assert match.similarity == pytest.approx(1.0)


def test_symmetric_only_weights_reach_full_coverage_without_evidence():
    match = compare(_features(), _features(), VECTORS, VECTORS, SimilarityWeights.only('genre', 'era', 'reach'))
    assert match.distance == pytest.approx(0.0, abs=1e-9)
    assert match.coverage == pytest.approx(1.0)


def test_unmeasurable_axes_are_omitted_not_guessed():
    seed = _features()
    other = _features(year=None, artist_neighbours=frozenset(), artist_area='', listeners=0,
                      listen_count=0, artist_listeners=0, track_count=0, runtime_seconds=0,
                      artist_debut_year=None)
    distances, strengths = _distances(seed, other, other_vectors={'genre': VECTORS['genre']})
    for axis in ('era', 'kinship', 'origin', 'reach', 'devotion', 'canonicity', 'scale', 'pacing',
                 'career', 'energy', 'acclaim', 'convergence', 'mood', 'lineage',
                 'personnel', 'circle', 'co_listening'):
        assert axis not in distances, axis
    assert strengths == {}
    assert distances['genre'] == pytest.approx(0.0)
    assert 'definition' in distances


def test_compare_returns_none_when_nothing_enabled_is_measurable():
    assert compare(_bare(), _bare(), {}, {}, SimilarityWeights()) is None
    # Measurable, but the only axis that could be measured is switched off.
    seed, other = _features(year=1991), _features(year=2001)
    assert compare(seed, other, {}, {}, SimilarityWeights.only('acclaim')) is None


def test_coverage_counts_evidence_axes_at_full_weight():
    weights = SimilarityWeights.only('genre', personnel=1.0)
    seed = _features(personnel={'a': 'A'})
    unconnected = compare(seed, _features(personnel={'z': 'Z'}), VECTORS, VECTORS, weights)
    assert unconnected.coverage == pytest.approx(0.5)
    half = compare(seed, _features(personnel={'a': 'A'}), VECTORS, VECTORS, weights)
    assert half.strengths['personnel'] == pytest.approx(0.5)
    assert half.coverage == pytest.approx(0.75)


def test_evidence_axes_pull_the_mean_toward_zero_by_strength():
    weights = SimilarityWeights.only('era', personnel=1.0)
    seed = _features(year=1991, personnel={'a': 'A', 'b': 'B'})
    far = _features(year=2016, personnel={})
    assert compare(seed, far, VECTORS, VECTORS, weights).distance == pytest.approx(1.0)
    half = _features(year=2016, personnel={'a': 'A'})
    # era 1.0 at weight 1, personnel 0.0 at weight 0.5 -> 1/1.5
    assert compare(seed, half, VECTORS, VECTORS, weights).distance == pytest.approx(1 / 1.5)
    full = _features(year=2016, personnel={'a': 'A', 'b': 'B'})
    assert compare(seed, full, VECTORS, VECTORS, weights).distance == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# Evidence axes
# ---------------------------------------------------------------------------

def test_personnel_strength_scales_with_shared_people():
    seed = _features(personnel={'p-pajo': 'David Pajo', 'p-mcmahan': 'Brian McMahan', 'art-slint': 'Slint'})
    none = _features(personnel={'p-other': 'Someone Else'})
    distances, strengths = _distances(seed, none)
    assert 'personnel' not in distances and 'personnel' not in strengths

    one = _features(personnel={'p-pajo': 'David Pajo', 'art-papa': 'Papa M'})
    distances, strengths = _distances(seed, one)
    assert distances['personnel'] == 0.0
    assert strengths['personnel'] == pytest.approx(0.5)

    two = _features(personnel={'p-pajo': 'David Pajo', 'p-mcmahan': 'Brian McMahan'})
    _, strengths = _distances(seed, two)
    assert strengths['personnel'] == pytest.approx(1.0)
    three = _features(personnel={'p-pajo': 'David Pajo', 'p-mcmahan': 'Brian McMahan', 'art-slint': 'Slint'})
    _, strengths = _distances(seed, three)
    assert strengths['personnel'] == pytest.approx(1.0)


def test_shared_personnel_names_come_from_either_side():
    seed = _features(personnel={'p-pajo': 'David Pajo', 'p-x': ''})
    other = _features(personnel={'p-pajo': 'David Pajo', 'p-x': 'Britt Walford'})
    match = compare(seed, other, VECTORS, VECTORS, SimilarityWeights())
    assert match.shared_personnel == ['Britt Walford', 'David Pajo']


def test_circle_strength_by_role():
    empty = dict(producers={}, engineers={}, studios={}, labels={})

    seed = _features(**dict(empty, producers={'steve albini': 'Steve Albini'}))
    other = _features(**dict(empty, producers={'steve albini': 'Steve Albini'}))
    distances, strengths = _distances(seed, other)
    assert distances['circle'] == 0.0 and strengths['circle'] == pytest.approx(1.0)

    seed = _features(**dict(empty, labels={'touch and go': 'Touch and Go'}))
    other = _features(**dict(empty, labels={'touch and go': 'Touch and Go'}))
    _, strengths = _distances(seed, other)
    assert strengths['circle'] == pytest.approx(0.5)

    seed = _features(**dict(empty, studios={'electrical audio': 'Electrical Audio'}))
    other = _features(**dict(empty, studios={'electrical audio': 'Electrical Audio'}))
    _, strengths = _distances(seed, other)
    assert strengths['circle'] == pytest.approx(0.7)

    seed = _features(**dict(empty, studios={'electrical audio': 'Electrical Audio'},
                            labels={'touch and go': 'Touch and Go'}))
    other = _features(**dict(empty, studios={'electrical audio': 'Electrical Audio'},
                             labels={'touch and go': 'Touch and Go'}))
    _, strengths = _distances(seed, other)
    assert strengths['circle'] == pytest.approx(1.0)

    seed = _features(**dict(empty, producers={'a': 'A'}))
    other = _features(**dict(empty, labels={'l': 'L'}))
    distances, strengths = _distances(seed, other)
    assert 'circle' not in distances and 'circle' not in strengths


def test_circle_person_counts_across_producer_and_engineer_roles():
    seed = _features(producers={'steve albini': 'Steve Albini'}, engineers={})
    other = _features(producers={}, engineers={'steve albini': 'Steve Albini'})
    match = compare(seed, other, VECTORS, VECTORS, SimilarityWeights())
    assert match.strengths['circle'] == pytest.approx(1.0)
    assert match.shared_circle == {'engineers': ['Steve Albini']}
    assert 'Steve Albini worked on both' in match.reasons


def test_shared_circle_lists_only_non_empty_roles_with_display_names():
    seed = _connected()
    other = _connected(engineers={}, studios={})
    match = compare(seed, other, VECTORS, VECTORS, SimilarityWeights())
    assert match.shared_circle == {'producers': ['Steve Albini'], 'labels': ['Touch and Go']}


def test_co_listening_strength_from_evidence():
    seed, other = _features(), _features()
    _, strengths = _distances(seed, other, Evidence())
    assert 'co_listening' not in strengths
    _, strengths = _distances(seed, other, Evidence(album_hits=1.0))
    assert strengths['co_listening'] == pytest.approx(1 / 3)
    _, strengths = _distances(seed, other, Evidence(artist_hits=2.5))
    assert strengths['co_listening'] == pytest.approx(1 / 3)
    distances, strengths = _distances(seed, other, Evidence(album_hits=3.0, artist_hits=10.0))
    assert strengths['co_listening'] == pytest.approx(1.0)
    assert distances['co_listening'] == 0.0
    match = compare(seed, other, VECTORS, VECTORS, SimilarityWeights(), evidence=Evidence(album_hits=2, artist_hits=1))
    assert match.co_listening == (2.0, 1.0)


# ---------------------------------------------------------------------------
# Symmetric axes
# ---------------------------------------------------------------------------

def test_kinship_saturates_at_jaccard_point_three_over_two_full_width_sets():
    # 100 names each, 47 in common: Jaccard 47/153 = 0.307, which the /0.3
    # scaling reads as full kinship.
    seed = _features(artist_neighbours=frozenset(f'artist {i}' for i in range(100)))
    other = _features(artist_neighbours=frozenset(f'artist {i}' for i in range(53, 153)))
    distances, _ = _distances(seed, other)
    assert distances['kinship'] == pytest.approx(0.0)
    fewer = _features(artist_neighbours=frozenset(f'artist {i}' for i in range(80, 180)))
    assert 0.0 < _distances(seed, fewer)[0]['kinship'] < 1.0
    disjoint = _features(artist_neighbours=frozenset(f'other {i}' for i in range(100)))
    assert _distances(seed, disjoint)[0]['kinship'] == pytest.approx(1.0)
    # Symmetric in its arguments.
    assert _distances(other, seed)[0]['kinship'] == _distances(seed, other)[0]['kinship']


def test_convergence_comes_from_evidence():
    seed, other = _features(), _features()
    assert 'convergence' not in _distances(seed, other)[0]
    assert 'convergence' not in _distances(seed, other, Evidence())[0]
    assert _distances(seed, other, Evidence(convergence=0.25))[0]['convergence'] == pytest.approx(0.75)
    assert _distances(seed, other, Evidence(convergence=1.0))[0]['convergence'] == pytest.approx(0.0)


def test_reach_is_the_mean_of_the_available_audience_readings():
    seed = _features(listeners=10_000, fans=0, lastfm_listeners=0)
    other = _features(listeners=100_000, fans=0, lastfm_listeners=0)
    assert _distances(seed, other)[0]['reach'] == pytest.approx(0.5)
    # Deezer fans agree, so they halve it; Last.fm only on one side is ignored.
    seed = _features(listeners=10_000, fans=1_000, lastfm_listeners=5_000)
    other = _features(listeners=100_000, fans=1_000, lastfm_listeners=0)
    assert _distances(seed, other)[0]['reach'] == pytest.approx(0.25)
    # No ListenBrainz listeners at all: the other readings still measure it.
    seed = _features(listeners=0, listen_count=0, fans=1_000)
    other = _features(listeners=0, listen_count=0, fans=100_000)
    assert _distances(seed, other)[0]['reach'] == pytest.approx(1.0)
    assert 'devotion' not in _distances(seed, other)[0]


def test_devotion_and_canonicity_are_log2_ratios_over_two():
    seed = _features(listeners=1_000, listen_count=4_000)       # 4 listens each
    other = _features(listeners=1_000, listen_count=16_000)     # 16 listens each
    assert _distances(seed, other)[0]['devotion'] == pytest.approx(1.0)
    seed = _features(listeners=10_000, artist_top_listeners=20_000)   # 0.5
    other = _features(listeners=5_000, artist_top_listeners=20_000)   # 0.25
    assert _distances(seed, other)[0]['canonicity'] == pytest.approx(0.5)
    # Measured against the artist's biggest record, never the artist total.
    other = _features(listeners=5_000, artist_top_listeners=10_000)
    assert _distances(seed, other)[0]['canonicity'] == pytest.approx(0.0)
    other = _features(listeners=5_000, artist_top_listeners=0, artist_listeners=20_000)
    assert 'canonicity' not in _distances(seed, other)[0]


def test_energy_components():
    seed = _features(bpm_mean=100.0, gain_mean=None)
    other = _features(bpm_mean=130.0, gain_mean=None)
    assert _distances(seed, other)[0]['energy'] == pytest.approx(0.5)
    seed = _features(bpm_mean=100.0, gain_mean=-8.0)
    other = _features(bpm_mean=130.0, gain_mean=-8.0)
    assert _distances(seed, other)[0]['energy'] == pytest.approx(0.25)
    # A gain of 0 dB is a measurement; a bpm of 0 is "not analysed".
    seed = _features(bpm_mean=0.0, gain_mean=0.0)
    other = _features(bpm_mean=120.0, gain_mean=-12.0)
    assert _distances(seed, other)[0]['energy'] == pytest.approx(1.0)
    seed = _features(bpm_mean=None, gain_mean=None)
    assert 'energy' not in _distances(seed, other)[0]


def test_acclaim_is_measured_but_off_by_default():
    seed = _features(acclaim=0.9)
    other = _features(acclaim=0.4)
    assert _distances(seed, other)[0]['acclaim'] == pytest.approx(1.0)
    with_scores = compare(seed, other, VECTORS, VECTORS, SimilarityWeights())
    without = compare(_features(acclaim=None), _features(acclaim=None), VECTORS, VECTORS, SimilarityWeights())
    assert 'acclaim' in with_scores.axes
    assert with_scores.distance == pytest.approx(without.distance)
    assert with_scores.coverage == pytest.approx(without.coverage)
    assert compare(seed, other, VECTORS, VECTORS, SimilarityWeights.only('acclaim')).distance == pytest.approx(1.0)


def test_era_scale_pacing_and_career():
    seed = _features(year=1991, artist_debut_year=1986)
    other = _features(year=2016, artist_debut_year=2011)
    distances, _ = _distances(seed, other)
    assert distances['era'] == pytest.approx(1.0)
    assert distances['career'] == pytest.approx(0.0)
    other = _features(year=1991, artist_debut_year=1976)
    assert _distances(seed, other)[0]['career'] == pytest.approx(10 / 15)
    seed = _features(track_count=6, runtime_seconds=2400, mean_track_seconds=400.0, track_length_spread=0.3)
    other = _features(track_count=13, runtime_seconds=4200, mean_track_seconds=280.0, track_length_spread=0.7)
    distances, _ = _distances(seed, other)
    assert distances['scale'] == pytest.approx((1800 / 3600 + 7 / 14) / 2)
    assert distances['pacing'] == pytest.approx((120 / 240 + 0.4 / 0.8) / 2)
    untracked = _features(track_count=0, runtime_seconds=0, mean_track_seconds=0.0)
    assert 'scale' not in _distances(seed, untracked)[0]
    assert 'pacing' not in _distances(seed, untracked)[0]


def test_origin_reads_area_and_act_type():
    seed = _features(artist_area='United States', artist_type='Group')
    assert _distances(seed, _features(artist_area='united states ', artist_type='Group'))[0]['origin'] == 0.0
    assert _distances(seed, _features(artist_area='United States', artist_type='Person'))[0]['origin'] == pytest.approx(1 / 3)
    assert _distances(seed, _features(artist_area='Japan', artist_type='Group'))[0]['origin'] == pytest.approx(2 / 3)
    assert _distances(seed, _features(artist_area='Japan', artist_type='Person'))[0]['origin'] == pytest.approx(1.0)
    assert _distances(seed, _features(artist_area='Japan', artist_type=''))[0]['origin'] == pytest.approx(1.0)


def test_definition_needs_a_profile_on_both_sides():
    seed = _features(profile={'post-rock': 1.0, 'math rock': 1.0}, genres={}, moods={})
    flat = _features(profile={'post-rock': 1.0}, genres={}, moods={})
    assert _distances(seed, flat)[0]['definition'] == pytest.approx(1.0)
    assert 'definition' not in _distances(seed, _features(profile={}, genres={}, moods={}))[0]


# ---------------------------------------------------------------------------
# Lateral mode
# ---------------------------------------------------------------------------

def test_lateral_bonus_rewards_new_subgenres_under_a_shared_root():
    seed = _features(profile={'post-rock': 1.0})
    sideways = _features(profile={'post-rock': 0.8, 'shoegaze': 0.6})
    weights = SimilarityWeights.only('era')
    plain = compare(_features(year=1991), _features(year=1996), VECTORS, VECTORS, weights)
    assert plain.distance == pytest.approx(0.2)
    bonus = compare(_features(year=1991, profile={'post-rock': 1.0}),
                    _features(year=1996, profile={'post-rock': 0.8, 'shoegaze': 0.6}),
                    VECTORS, VECTORS, weights, lateral_bonus=0.08)
    assert bonus.distance == pytest.approx(0.12)
    # Same subgenres as the seed: nothing new, no bonus.
    same = compare(seed, _features(year=1996, profile={'post-rock': 1.0}),
                   VECTORS, VECTORS, weights, lateral_bonus=0.08)
    assert same.distance == pytest.approx(0.2)
    # A new subgenre under a different root gets nothing either.
    other_root = compare(seed, _features(year=1996, profile={'house': 1.0}),
                         VECTORS, VECTORS, weights, lateral_bonus=0.08)
    assert other_root.distance == pytest.approx(0.2)
    assert sideways.subgenres - seed.subgenres == {'shoegaze'}


# ---------------------------------------------------------------------------
# Reasons
# ---------------------------------------------------------------------------

def test_explain_orders_a_fully_connected_pair_strongest_first():
    seed = _connected()
    other = _connected(mbid='rg-other', title='Other', artist='Other Act', artist_mbid='art-other',
                       personnel={'p-pajo': 'David Pajo', 'p-mcmahan': 'Brian McMahan', 'art-other': 'Other Act'},
                       personnel_relations={'p-pajo': 'member of band', 'p-mcmahan': 'member of band',
                                            'art-other': 'artist'},
                       artist_neighbours=frozenset(f'artist {i}' for i in range(53, 153)))
    evidence = Evidence(convergence=1.0, album_hits=3.0)
    match = compare(seed, other, VECTORS, VECTORS, SimilarityWeights(), evidence=evidence)
    reasons = match.reasons
    assert len(reasons) <= 8
    assert reasons[0] == 'Brian McMahan and David Pajo are in both'
    assert reasons[1] == 'both produced by Steve Albini'
    assert reasons[2] == 'both engineered by Bob Weston'
    assert reasons[3] == 'both recorded at Electrical Audio'
    assert reasons[4] == 'both on Touch and Go'
    assert reasons[5] == "3 of its tracks are played alongside the seed's"
    assert reasons[6] == 'shares post-rock, math rock'
    assert reasons[7] == 'same mood: melancholic, spoken word'
    assert match.shared_neighbours == sorted(f'artist {i}' for i in range(53, 100))[:8]


def test_explain_symmetric_phrasings():
    seed = _features(personnel={}, producers={}, engineers={}, studios={}, labels={})
    other = _features(personnel={}, producers={}, engineers={}, studios={}, labels={},
                      artist_neighbours=frozenset(list(NEIGHBOURS)[:60] + [f'other {i}' for i in range(40)]))
    match = compare(seed, other, VECTORS, VECTORS, SimilarityWeights())
    reasons = match.reasons
    assert reasons[0] == 'shares post-rock, math rock'
    assert reasons[1] == 'same mood: melancholic, spoken word'
    kinship = [r for r in reasons if r.startswith('60 similar artists in common: ')][0]
    assert kinship.endswith('...')
    assert kinship.count(',') == 2
    assert 'same scene: louisville, post-hardcore' in reasons
    assert 'similar-sized audience' in reasons
    assert 'similarly devoted listeners' in reasons
    assert 'same era' in reasons
    assert len(reasons) == 8
    assert reasons.index('shares post-rock, math rock') < reasons.index('same era')


def test_explain_direct_call_uses_thresholds_and_caps():
    seed, other = _features(), _features()
    axes = {'era': 0.24, 'origin': 0.0, 'career': 0.0, 'reach': 0.1, 'devotion': 0.25,
            'genre': 0.36, 'kinship': 0.34}
    reasons = explain(seed, other, axes, {}, ['artist 1'], [], {}, (0.0, 0.0))
    assert 'same era' not in reasons
    assert 'shares post-rock, math rock' not in reasons
    assert 'similarly devoted listeners' not in reasons
    assert reasons[0] == '100 similar artists in common: artist 1...'
    assert 'both from United States' in reasons
    assert 'same career stage' in reasons
    assert 'similar-sized audience' in reasons
    assert len(reasons) == 4


def test_explain_personnel_phrasings():
    seed = _features(personnel={'art-slint': 'Slint', 'p-pajo': 'David Pajo'},
                     personnel_relations={'art-slint': 'artist', 'p-pajo': 'member of band'})
    solo = _features(personnel={'p-pajo': 'David Pajo'}, personnel_relations={'p-pajo': 'artist'})
    reasons = compare(seed, solo, VECTORS, VECTORS, SimilarityWeights()).reasons
    assert reasons[0] == 'David Pajo connects them'
    band = _features(personnel={'p-pajo': 'David Pajo', 'art-tortoise': 'Tortoise'},
                     personnel_relations={'p-pajo': 'member of band', 'art-tortoise': 'artist'})
    reasons = compare(seed, band, VECTORS, VECTORS, SimilarityWeights()).reasons
    assert reasons[0] == 'David Pajo is in both'
    many = _features(personnel={f'p{i}': f'Person {i}' for i in range(5)})
    seed = _features(personnel={f'p{i}': f'Person {i}' for i in range(5)})
    reasons = compare(seed, many, VECTORS, VECTORS, SimilarityWeights()).reasons
    assert reasons[0] == 'Person 0, Person 1, Person 2 and 2 more are in both'


def test_explain_co_listening_phrasings():
    seed, other = _features(), _features()
    one = compare(seed, other, VECTORS, VECTORS, SimilarityWeights(), evidence=Evidence(album_hits=1.2))
    assert "1 of its tracks is played alongside the seed's" in one.reasons
    by_artist = compare(seed, other, VECTORS, VECTORS, SimilarityWeights(), evidence=Evidence(artist_hits=2.0))
    assert "2 of its artist's tracks are played alongside the seed's" in by_artist.reasons
    faint = compare(seed, other, VECTORS, VECTORS, SimilarityWeights(), evidence=Evidence(artist_hits=0.3))
    assert "listeners play its tracks alongside the seed's" in faint.reasons


# ---------------------------------------------------------------------------
# describe_axes and rows
# ---------------------------------------------------------------------------

def test_describe_axes_uses_labels_and_marks_evidence_as_shared():
    match = Match(features=_features(), distance=0.2,
                  axes={'genre': 0.1, 'era': 0.3, 'reach': 0.6, 'personnel': 0.0},
                  strengths={'personnel': 0.5})
    assert similarity.describe_axes(match) == (
        'people in common: shared, genre: close, era: near, audience size: far')
    assert similarity.describe_axes(match, limit=2) == 'people in common: shared, genre: close'


def test_match_row_carries_the_similarity_columns():
    seed = _connected()
    other = _connected(mbid='rg-other')
    match = compare(seed, other, VECTORS, VECTORS, SimilarityWeights(),
                    evidence=Evidence(convergence=0.5, album_hits=2.0), sources=('tag:post-rock', 'people:pajo'))
    row = match.as_row()
    assert row['mbid'] == 'rg-other'
    assert row['similarity'] == pytest.approx(round(match.similarity, 3))
    assert row['distance'] == pytest.approx(round(match.distance, 3))
    assert row['axes_measured'] == len(match.axes)
    assert row['connected'] is True
    assert row['reasons'] == ' | '.join(match.reasons)
    assert ' | ' in row['reasons']
    assert row['shared_personnel'] == 'Brian McMahan, David Pajo, Slint'
    assert row['shared_producers'] == 'Steve Albini'
    assert row['shared_engineers'] == 'Bob Weston'
    assert row['shared_studios'] == 'Electrical Audio'
    assert row['shared_labels'] == 'Touch and Go'
    assert row['co_listening_album_hits'] == 2.0
    assert row['found_via'] == 'people:pajo, tag:post-rock'
    assert row['d_convergence'] == pytest.approx(0.5)
    assert row['d_personnel'] == 0.0
    assert row['s_personnel'] == 1.0
    assert row['coverage'] == pytest.approx(round(match.coverage, 3))
    for axis in match.axes:
        assert f'd_{axis}' in row
