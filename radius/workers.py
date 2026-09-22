"""Run per-service work on threads while progress stays on the caller's thread.

The engine's later stages talk to independent services — MusicBrainz at its
serial 1 rps, Deezer, Wikidata, Discogs, Last.fm — so running one thread per
service turns a minute of waiting into the length of the slowest one. The
catch is Streamlit: its widgets may only be touched from the thread that
runs the script, so a worker that called the progress callback directly
would crash the UI. Workers therefore only ever put events on a queue, and
the calling thread drains it and invokes the callback itself.
"""

import queue
import threading
from concurrent.futures import ThreadPoolExecutor

_FINISHED = object()


class _Cancelled(Exception):
    """Raised inside a worker at its next report to unwind it promptly."""


def run_workers(jobs, progress=None, stage=''):
    """jobs: {name: callable(report)}. Each callable runs on its own thread
    and may call report(done, total, label) from there. Events go onto a
    queue.Queue; the CALLING thread drains the queue and calls
    progress(stage, done, total, label) where done/total are summed over the
    latest report from every worker, and label is '<name>: <label>'. Returns
    {name: result}; if a job raises, its result is the exception instance
    (not re-raised). Never invokes progress from a worker thread (Streamlit
    requires this).

    If the progress callback itself raises — which is how Streamlit signals
    a rerun or a stop from a widget call — the workers are cancelled and the
    exception is re-raised once they are down. Without that, leaving the
    `with` block would wait on every worker's remaining rate-limited
    requests, freezing the app for minutes on a single stray click.
    """
    jobs = dict(jobs or {})
    if not jobs:
        return {}
    events = queue.Queue()
    latest = {name: (0, 0) for name in jobs}
    results = {}
    cancelled = threading.Event()
    interrupted = []

    def launch(name, job):
        def report(done, total, label=''):
            # A cancelled worker unwinds at its next report, so the wait is
            # bounded by one in-flight request rather than a whole job.
            if cancelled.is_set():
                raise _Cancelled()
            events.put((name, done, total, label))

        result = None
        try:
            result = job(report)
        except _Cancelled:
            result = None
        except Exception as exc:
            result = exc
        finally:
            # One sentinel per job, sent even if the job dies, is what lets
            # the drain loop below end without polling the futures.
            events.put((name, _FINISHED, result, None))

    with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
        for name, job in jobs.items():
            pool.submit(launch, name, job)
        remaining = len(jobs)
        while remaining:
            name, done, total, label = events.get()
            if done is _FINISHED:
                results[name] = total
                remaining -= 1
                continue
            latest[name] = (_count(done), _count(total))
            if progress is None or cancelled.is_set():
                continue
            try:
                progress(
                    stage,
                    sum(d for d, _ in latest.values()),
                    sum(t for _, t in latest.values()),
                    f'{name}: {label}' if label else name,
                )
            except BaseException as exc:  # noqa: BLE001 - re-raised below
                cancelled.set()
                interrupted.append(exc)
    if interrupted:
        raise interrupted[0]
    return results


def _count(value):
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0
