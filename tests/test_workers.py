"""Tests for the per-service worker runner.

What matters: jobs really overlap, progress never leaves the caller's
thread (Streamlit's rule), a job's exception becomes its result instead of
killing the run, and done/total add up across workers.
"""

import importlib
import os
import sys
import threading
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def _leaf(name):
    """Import radius.<name> even while radius/__init__.py cannot load (it
    imports the whole engine; this test only needs the workers leaf). A
    healthy package never reaches the fallback."""
    try:
        return importlib.import_module(f'radius.{name}')
    except ImportError:
        if 'radius' in sys.modules:
            raise
        package = types.ModuleType('radius')
        package.__path__ = [os.path.join(ROOT, 'radius')]
        sys.modules['radius'] = package
        return importlib.import_module(f'radius.{name}')


run_workers = _leaf('workers').run_workers


def test_jobs_run_concurrently():
    a_started, b_started = threading.Event(), threading.Event()

    def job_a(report):
        a_started.set()
        return b_started.wait(timeout=2)

    def job_b(report):
        b_started.set()
        return a_started.wait(timeout=2)

    results = run_workers({'a': job_a, 'b': job_b})
    # Run serially, whichever went first would have timed out waiting.
    assert results == {'a': True, 'b': True}


def test_progress_is_called_on_the_calling_thread_only():
    caller = threading.get_ident()
    seen = []

    def job(report):
        report(1, 2, 'first')
        report(2, 2, 'second')
        return 'ok'

    def progress(stage, done, total, label):
        seen.append((threading.get_ident(), stage, done, total, label))

    results = run_workers({'mb': job}, progress=progress, stage='S4')
    assert results == {'mb': 'ok'}
    assert seen
    assert all(ident == caller for ident, *_ in seen)
    assert seen[-1][1:] == ('S4', 2, 2, 'mb: second')


def test_exceptions_become_results():
    def bad(report):
        raise ValueError('boom')

    def good(report):
        return 42

    results = run_workers({'bad': bad, 'good': good})
    assert results['good'] == 42
    assert isinstance(results['bad'], ValueError)
    assert str(results['bad']) == 'boom'


def test_done_and_total_aggregate_across_workers():
    a_reported = threading.Event()
    seen = []

    def job_a(report):
        report(1, 4, 'x')
        a_reported.set()
        return 'a'

    def job_b(report):
        a_reported.wait(timeout=2)
        report(2, 6, 'y')
        return 'b'

    run_workers({'a': job_a, 'b': job_b},
                progress=lambda *args: seen.append(args), stage='S5')
    assert ('S5', 1, 4, 'a: x') in seen
    assert seen[-1] == ('S5', 3, 10, 'b: y')


def test_no_jobs_and_no_progress_are_fine():
    assert run_workers({}) == {}
    assert run_workers({'a': lambda report: report(1, 1, 'done') or 'r'}) == {'a': 'r'}
