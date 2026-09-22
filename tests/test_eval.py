"""Offline tests for the golden-set evaluator.

A fake runner stands in for the engine and returns canned result objects
shaped like SimilarityResult (`.matches[].features.artist`, `.requests_made`),
so scoring, name folding, seed filtering and the save/compare round trip
are all exercised with no network and no engine.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from radius import eval as radius_eval
from radius.eval import (
    GOLDEN, compare_reports, evaluate, format_comparison, format_table,
    load_report, main, name_matches, normalise_name, save_report, score_seed,
    select_seeds,
)


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------

class _Features:
    def __init__(self, artist):
        self.artist = artist


class _Match:
    def __init__(self, artist):
        self.features = _Features(artist)


class _Result:
    def __init__(self, artists, requests_made=0):
        self.matches = [_Match(artist) for artist in artists]
        self.requests_made = requests_made


def fake_runner(table, requests_made=7):
    """A runner serving canned artist lists per seed text, recording calls."""
    calls = []

    def runner(seed_text, top_n, services, **kwargs):
        calls.append({'seed': seed_text, 'top_n': top_n,
                      'services': services, 'kwargs': kwargs})
        return _Result(table.get(seed_text, []), requests_made=requests_made)

    runner.calls = calls
    return runner


SLINT = 'Slint - Spiderland'
BURIAL = 'Burial - Untrue'


# ---------------------------------------------------------------------------
# Name folding
# ---------------------------------------------------------------------------

def test_normalisation_folds_case_punctuation_and_leading_the():
    assert normalise_name('The For Carnation') == 'for carnation'
    assert normalise_name("Rachel's") == 'rachels'
    assert normalise_name("D'Angelo") == normalise_name('DAngelo') == 'dangelo'
    assert normalise_name('Ab-Soul') == normalise_name('Ab Soul') == 'ab soul'
    assert normalise_name('Godspeed You! Black Emperor') == 'godspeed you black emperor'
    assert normalise_name('Anderson .Paak') == 'anderson paak'
    assert normalise_name('Crosby, Stills, Nash & Young') == 'crosby stills nash young'
    assert normalise_name('  Dinosaur   Jr. ') == 'dinosaur jr'
    assert normalise_name('') == ''
    assert normalise_name(None) == ''


def test_normalisation_strips_diacritics():
    assert normalise_name('Björk') == 'bjork'
    assert normalise_name('José González') == 'jose gonzalez'
    assert normalise_name('Sigur Rós') == 'sigur ros'


def test_the_is_only_dropped_at_the_start():
    assert normalise_name('The Roots') == 'roots'
    assert normalise_name('Theo Parrish') == 'theo parrish'
    assert normalise_name('Songs: Ohia') == 'songs ohia'


def test_expected_name_matches_equal_or_whole_inside_result():
    def hit(expected, artist):
        return name_matches(normalise_name(expected), normalise_name(artist))

    assert hit("Rachel's", "Rachel's")
    assert hit("Rachel's", 'Rachels')
    assert hit('Godspeed You! Black Emperor', 'Godspeed You Black Emperor!')
    assert hit('The Jesus and Mary Chain', 'Jesus & Mary Chain') is False
    assert hit('Bon Iver', 'Bon Iver & Friends')
    assert hit('Sufjan Stevens', 'Sufjan Stevens, Bryce Dessner & Nico Muhly')
    assert hit('The xx', 'xx')


def test_containment_is_word_bounded():
    def hit(expected, artist):
        return name_matches(normalise_name(expected), normalise_name(artist))

    assert not hit('Low', 'Lowell George')
    assert not hit('Air', 'The Airborne Toxic Event')
    assert not hit('Lamb', 'Lambchop')
    assert not hit('Alpha', 'Alphaville')
    assert hit('Low', 'Low & Dirty Three')
    assert not name_matches('', 'anything')
    assert not name_matches('anything', '')


# ---------------------------------------------------------------------------
# Scoring one seed
# ---------------------------------------------------------------------------

def test_score_counts_hits_in_rank_order_with_first_hit_mrr():
    expected = ['Rodan', 'Codeine', 'Bedhead', 'Swans']
    results = ['Some Band', 'Bedhead', 'Another', 'Rodan', 'Codeine']
    scored = score_seed(expected, results)
    assert scored['hits'] == 3
    assert scored['expected'] == 4
    assert scored['hit_rate'] == pytest.approx(0.75)
    assert scored['found'] == ['Bedhead', 'Rodan', 'Codeine']
    assert scored['missing'] == ['Swans']
    assert scored['mrr'] == pytest.approx(1 / 2)


def test_score_counts_each_expected_artist_once():
    # max_per_artist lets an act appear twice; that is still one hit.
    scored = score_seed(['Rodan'], ['Rodan', 'Rodan', 'Rodan'])
    assert scored['hits'] == 1
    assert scored['mrr'] == pytest.approx(1.0)


def test_score_with_no_hits_is_zero_not_an_error():
    scored = score_seed(['Rodan', 'Codeine'], ['Nobody', 'Else'])
    assert scored['hits'] == 0
    assert scored['hit_rate'] == 0.0
    assert scored['mrr'] == 0.0
    assert scored['found'] == []
    assert scored['missing'] == ['Rodan', 'Codeine']


def test_score_with_empty_results_and_empty_expectation():
    assert score_seed(['Rodan'], [])['hits'] == 0
    empty = score_seed([], ['Rodan'])
    assert empty['hits'] == 0 and empty['hit_rate'] == 0.0 and empty['mrr'] == 0.0


def test_score_folds_names_on_both_sides():
    scored = score_seed(["Rachel's", 'Godspeed You! Black Emperor', 'Björk'],
                        ['Rachels', 'Godspeed You Black Emperor!', 'Bjork'])
    assert scored['hits'] == 3
    # Found names are reported with the golden spelling, not the result's.
    assert scored['found'] == ["Rachel's", 'Godspeed You! Black Emperor', 'Björk']


# ---------------------------------------------------------------------------
# The golden set itself
# ---------------------------------------------------------------------------

def test_golden_set_shape():
    assert len(GOLDEN) == 12
    for entry in GOLDEN:
        assert set(entry) == {'seed', 'expect'}
        assert ' - ' in entry['seed']
        assert isinstance(entry['expect'], list) and entry['expect']
        assert all(isinstance(name, str) and name.strip() for name in entry['expect'])
        assert len(entry['expect']) == len(set(entry['expect'])), entry['seed']


def test_comma_bearing_artist_is_one_entry():
    joni = next(e for e in GOLDEN if e['seed'].startswith('Joni Mitchell'))
    assert 'Crosby, Stills, Nash & Young' in joni['expect']
    assert 'Stills' not in joni['expect']


def test_seed_filter_is_a_case_insensitive_substring():
    assert [e['seed'] for e in select_seeds(['slint'])] == [SLINT]
    assert [e['seed'] for e in select_seeds(['SLINT', 'untrue'])] == [SLINT, BURIAL]
    assert select_seeds(['nothing like this']) == []
    assert select_seeds(None) == GOLDEN
    assert select_seeds([]) == GOLDEN


# ---------------------------------------------------------------------------
# evaluate()
# ---------------------------------------------------------------------------

def test_engine_is_not_imported_at_module_level():
    """The engine is mid-rewrite; eval must import without it."""
    assert 'find_similar' not in vars(radius_eval)
    assert 'Services' not in vars(radius_eval)


def test_evaluate_runs_each_selected_seed_and_aggregates():
    runner = fake_runner({
        SLINT: ['Rodan', 'Nobody', 'Codeine'],
        BURIAL: ['Nobody', 'Four Tet'],
    })
    report = evaluate(top_n=10, seeds=['slint', 'burial'], runner=runner,
                      mode='closest', pool_size=50)

    assert [c['seed'] for c in runner.calls] == [SLINT, BURIAL]
    assert all(c['top_n'] == 10 for c in runner.calls)
    assert all(c['kwargs'] == {'mode': 'closest', 'pool_size': 50} for c in runner.calls)
    assert all(c['services'] is None for c in runner.calls)

    slint, burial = report['per_seed']
    assert slint['seed'] == SLINT
    assert slint['hits'] == 2 and slint['found'] == ['Rodan', 'Codeine']
    assert slint['expected'] == 24
    assert slint['mrr'] == pytest.approx(1.0)
    assert slint['requests'] == 7
    assert 'Swans' in slint['missing']
    assert burial['hits'] == 1 and burial['mrr'] == pytest.approx(1 / 2)

    assert report['top_n'] == 10
    assert report['hits_at_n'] == pytest.approx((2 / 24 + 1 / 30) / 2)
    assert report['mrr'] == pytest.approx((1.0 + 0.5) / 2)
    assert report['requests'] == 14


def test_evaluate_defaults_to_the_whole_golden_set():
    runner = fake_runner({})
    report = evaluate(runner=runner)
    assert [c['seed'] for c in runner.calls] == [e['seed'] for e in GOLDEN]
    assert len(report['per_seed']) == 12
    assert report['hits_at_n'] == 0.0 and report['mrr'] == 0.0


def test_evaluate_accepts_golden_style_entries_directly():
    custom = [{'seed': 'X - Y', 'expect': ['A', 'B']}]
    runner = fake_runner({'X - Y': ['B']})
    report = evaluate(seeds=custom, runner=runner)
    assert [row['seed'] for row in report['per_seed']] == ['X - Y']
    assert report['per_seed'][0]['found'] == ['B']
    assert report['hits_at_n'] == pytest.approx(0.5)


def test_evaluate_only_scores_the_top_n_results():
    runner = fake_runner({SLINT: ['Nobody'] * 5 + ['Rodan']})
    assert evaluate(top_n=5, seeds=['slint'], runner=runner)['per_seed'][0]['hits'] == 0
    assert evaluate(top_n=6, seeds=['slint'], runner=runner)['per_seed'][0]['hits'] == 1


def test_progress_is_called_before_each_run():
    order = []
    runner = fake_runner({})
    original = runner

    def tracking_runner(seed_text, top_n, services, **kwargs):
        order.append(('run', seed_text))
        return original(seed_text, top_n, services, **kwargs)

    def progress(index, total, seed_text):
        order.append(('progress', index, total, seed_text))

    evaluate(seeds=['slint', 'burial'], runner=tracking_runner, progress=progress)
    assert order == [
        ('progress', 0, 2, SLINT), ('run', SLINT),
        ('progress', 1, 2, BURIAL), ('run', BURIAL),
    ]


def test_requests_use_the_services_counter_when_there_is_one():
    class Counter:
        requests_made = 100

    services = Counter()

    def runner(seed_text, top_n, services, **kwargs):
        services.requests_made += 5
        return _Result(['Rodan'], requests_made=services.requests_made)

    report = evaluate(seeds=['slint', 'burial'], services=services, runner=runner)
    assert [row['requests'] for row in report['per_seed']] == [5, 5]
    assert report['requests'] == 10


def test_one_failing_seed_does_not_sink_the_run():
    def runner(seed_text, top_n, services, **kwargs):
        if seed_text == BURIAL:
            raise RuntimeError('MusicBrainz has no album matching that.')
        return _Result(['Rodan'])

    report = evaluate(seeds=['slint', 'burial'], runner=runner)
    slint, burial = report['per_seed']
    assert slint['hits'] == 1 and 'error' not in slint
    assert burial['hits'] == 0 and burial['mrr'] == 0.0
    assert burial['error'] == 'RuntimeError: MusicBrainz has no album matching that.'
    assert '! RuntimeError' in format_table(report)


# ---------------------------------------------------------------------------
# Save / compare
# ---------------------------------------------------------------------------

def test_save_and_load_round_trip(tmp_path):
    runner = fake_runner({SLINT: ['Rodan', 'Björk']})
    report = evaluate(seeds=['slint'], runner=runner)
    path = tmp_path / 'baseline.json'
    save_report(report, path)
    assert load_report(path) == report


def test_compare_reports_deltas_per_seed_and_aggregate():
    baseline = evaluate(seeds=['slint', 'burial'],
                        runner=fake_runner({SLINT: ['Rodan'], BURIAL: ['Four Tet']}))
    current = evaluate(seeds=['slint', 'radiohead'],
                       runner=fake_runner({SLINT: ['Rodan', 'Codeine', 'Low'],
                                           'Radiohead - Kid A': ['Beck']}))
    diff = compare_reports(current, baseline)

    rows = {row['seed']: row for row in diff['per_seed']}
    assert rows[SLINT] == {'seed': SLINT, 'before': 1, 'after': 3, 'delta': 2}
    assert rows['Radiohead - Kid A']['before'] is None
    assert rows['Radiohead - Kid A']['delta'] is None
    assert rows[BURIAL]['after'] is None
    assert diff['hits_at_n']['delta'] == pytest.approx(
        current['hits_at_n'] - baseline['hits_at_n'])
    assert diff['mrr']['before'] == pytest.approx(baseline['mrr'])
    assert diff['top_n'] == {'before': 25, 'after': 25}

    text = format_comparison(diff, label='baseline.json')
    assert 'vs baseline.json' in text
    assert '+2' in text
    assert 'new' in text
    assert 'hits@N' in text and 'mrr' in text


def test_comparison_warns_when_top_n_differs():
    baseline = evaluate(seeds=['slint'], top_n=10, runner=fake_runner({}))
    current = evaluate(seeds=['slint'], top_n=25, runner=fake_runner({}))
    text = format_comparison(compare_reports(current, baseline))
    assert 'top 10' in text and 'top 25' in text


def test_table_lists_hits_mrr_and_a_few_names():
    runner = fake_runner({SLINT: ['Rodan', 'June of 44', 'Codeine', 'Bedhead',
                                  'Tortoise', 'Papa M']})
    text = format_table(evaluate(seeds=['slint'], runner=runner))
    assert 'Slint - Spiderland' in text
    assert '6/24' in text
    assert '1.00' in text
    assert 'Rodan, June of 44, Codeine, Bedhead (+2)' in text
    assert 'missing:' in text and 'Sonic Youth' not in text.split('missing:')[1][:60]
    assert '1 seeds, hits@25 0.250, mrr 1.000, 7 requests' in text


# ---------------------------------------------------------------------------
# main()
# ---------------------------------------------------------------------------

@pytest.fixture
def canned_engine(monkeypatch):
    """Route main() through a fake runner so no engine or network is touched."""
    real_evaluate = radius_eval.evaluate
    runner = fake_runner({SLINT: ['Rodan', 'Codeine'], BURIAL: ['Four Tet']})
    monkeypatch.setattr(radius_eval, 'evaluate',
                        lambda **kwargs: real_evaluate(runner=runner, **kwargs))
    return runner


def test_main_prints_table_saves_and_compares(tmp_path, capsys, canned_engine):
    baseline = tmp_path / 'base.json'
    assert main(['--quiet', '--seed', 'slint', '--top', '10', '--save', str(baseline)]) == 0
    out = capsys.readouterr()
    assert 'Slint - Spiderland' in out.out
    assert '2/24' in out.out
    assert f'Wrote {baseline}' in out.out
    assert out.err == ''
    assert canned_engine.calls[-1]['top_n'] == 10
    assert load_report(baseline)['per_seed'][0]['hits'] == 2

    assert main(['--quiet', '--seed', 'slint', '--top', '10',
                 '--compare', str(baseline)]) == 0
    out = capsys.readouterr().out
    assert f'vs {baseline}' in out
    assert '+0' in out
    assert '(+0.000)' in out


def test_main_reports_progress_unless_quiet(capsys, canned_engine):
    main(['--seed', 'slint', '--seed', 'burial'])
    err = capsys.readouterr().err
    assert '[1/2] Slint - Spiderland' in err
    assert '[2/2] Burial - Untrue' in err


def test_main_rejects_a_filter_that_matches_nothing(capsys, canned_engine):
    with pytest.raises(SystemExit) as exc:
        main(['--quiet', '--seed', 'no such seed'])
    assert exc.value.code == 2
    assert 'no golden seed matches' in capsys.readouterr().err
    assert canned_engine.calls == []
