"""Disk cache for every outbound API response.

Keyed on the exact normalised request, so re-running a query — or seeding
from a neighbouring album that shares candidates — costs no requests at all.
The cache is the reason this stays polite: the network is hit once per fact.
"""

import json
import os
import sqlite3
import threading
import time

from . import config

# Returned when there is no usable entry, so that a cached JSON null is
# still a hit. `None` cannot do that job: it is a legitimate stored value.
MISS = object()

_SCHEMA = """
CREATE TABLE IF NOT EXISTS responses (
    key        TEXT PRIMARY KEY,
    payload    TEXT NOT NULL,
    fetched_at REAL NOT NULL
);
"""


class Cache:
    MISS = MISS

    def __init__(self, path=None):
        self.path = path or config.CACHE_PATH
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        # Streamlit reruns touch this from more than one thread, and each
        # connection is short-lived anyway, so guard with a lock rather than
        # sharing a connection across threads.
        self._lock = threading.Lock()
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    def _connect(self):
        return sqlite3.connect(self.path, timeout=30)

    @staticmethod
    def make_key(namespace, params):
        canonical = json.dumps(params, sort_keys=True, separators=(',', ':'))
        return f'{namespace}|{canonical}'

    def get(self, key, ttl_days, default=MISS):
        """The cached body, or `default` (MISS by default) when there is no
        usable entry. The sentinel matters because a stored body can itself
        be JSON null: returning None for both would make that entry read as
        a miss forever and re-issue its request on every call."""
        with self._lock, self._connect() as conn:
            row = conn.execute(
                'SELECT payload, fetched_at FROM responses WHERE key = ?', (key,)
            ).fetchone()
        if row is None:
            return default
        payload, fetched_at = row
        if ttl_days is not None and time.time() - fetched_at > ttl_days * 86400:
            return default
        try:
            return json.loads(payload)
        except json.JSONDecodeError:
            return default

    def put(self, key, value):
        blob = json.dumps(value, separators=(',', ':'))
        with self._lock, self._connect() as conn:
            conn.execute(
                'INSERT OR REPLACE INTO responses (key, payload, fetched_at) '
                'VALUES (?, ?, ?)',
                (key, blob, time.time()),
            )

    def stats(self):
        with self._lock, self._connect() as conn:
            count, oldest = conn.execute(
                'SELECT COUNT(*), MIN(fetched_at) FROM responses'
            ).fetchone()
        return {
            'entries': count or 0,
            'oldest_fetch': oldest,
            'path': self.path,
            'size_bytes': os.path.getsize(self.path) if os.path.exists(self.path) else 0,
        }

    def clear(self, namespace=None):
        with self._lock, self._connect() as conn:
            if namespace is None:
                deleted = conn.execute('DELETE FROM responses').rowcount
            else:
                deleted = conn.execute(
                    'DELETE FROM responses WHERE key LIKE ?', (f'{namespace}|%',)
                ).rowcount
        return deleted
