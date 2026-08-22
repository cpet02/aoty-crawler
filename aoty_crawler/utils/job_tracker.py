"""
Scrape job tracking.

Each scrape run gets a job_id (timestamp) and a small JSON status file under
<output_dir>/jobs/<job_id>.json. The spider updates it as it works so a UI
(or anything else) can show completion-based progress and browse past runs
without needing a database or IPC beyond the filesystem.
"""

import glob
import json
import os
from datetime import datetime


def new_job_id():
    return datetime.utcnow().strftime('%Y%m%d_%H%M%S')


def jobs_dir_for(output_dir):
    path = os.path.join(output_dir, 'jobs')
    os.makedirs(path, exist_ok=True)
    return path


def _job_path(job_id, jobs_dir):
    return os.path.join(jobs_dir, f'{job_id}.json')


def create_job(job_id, jobs_dir, params, target_total):
    """Create the initial status file for a new job"""
    job = {
        'job_id': job_id,
        'status': 'running',
        'params': params,
        'target_total': target_total,
        'completed': 0,
        'current_genre': params.get('genre'),
        'current_year': None,
        'started_at': datetime.utcnow().isoformat(),
        'ended_at': None,
        'output_files': {},
    }
    _write(job_id, jobs_dir, job)
    return job


def update_job(job_id, jobs_dir, **fields):
    """Read-modify-write the job file with the given fields merged in"""
    job = load_job(job_id, jobs_dir) or {'job_id': job_id}
    job.update(fields)
    _write(job_id, jobs_dir, job)
    return job


def _write(job_id, jobs_dir, job):
    path = _job_path(job_id, jobs_dir)
    tmp_path = path + '.tmp'
    try:
        with open(tmp_path, 'w', encoding='utf-8') as f:
            json.dump(job, f, indent=2, default=str)
        os.replace(tmp_path, path)
    except Exception:
        pass


def load_job(job_id, jobs_dir):
    path = _job_path(job_id, jobs_dir)
    if not os.path.exists(path):
        return None
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None


def delete_job(job_id, jobs_dir):
    """Delete a job's status file and any output files it produced.
    Refuses to delete a job that's still running (caller should check)."""
    job = load_job(job_id, jobs_dir)
    if job is None:
        return

    for path in (job.get('output_files') or {}).values():
        try:
            if path and os.path.exists(path):
                os.remove(path)
        except OSError:
            pass

    try:
        os.remove(_job_path(job_id, jobs_dir))
    except OSError:
        pass


def list_jobs(jobs_dir):
    """List all known jobs, most recently started first"""
    jobs = []
    for path in glob.glob(os.path.join(jobs_dir, '*.json')):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                jobs.append(json.load(f))
        except Exception:
            continue
    jobs.sort(key=lambda j: j.get('started_at') or '', reverse=True)
    return jobs
