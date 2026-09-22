"""Bookmarks and ratings, keyed by MusicBrainz release-group id.

Why its own JSON file and not the cache: the cache is disposable (clear it
and every fact comes back on demand), while the library is the one thing in
data/ that cannot be regenerated. So it gets a small, human-readable file of
its own, written atomically (temp file, then os.replace) so a crash mid-save
never leaves half a library behind.

Why the mbid as key: it is the one identity every service here agrees on,
which is what lets a saved album be handed straight back to the engine as a
seed. Entries that came from the old AOTY-era ratings.json and bookmarks.json
have no mbid yet; they live under 'manual:<slug>' until the UI resolves them
through a MusicBrainz search, at which point resolve() moves them under the
real key and folds them into any entry already there.

Every public method reads the file fresh and writes it back under one lock.
The file is tiny, and this is what keeps several Library objects (Streamlit
reruns, a second browser tab) looking at the same library.
"""

import json
import math
import os
import re
import threading
from datetime import datetime, timezone

from . import config

FILE_NAME = 'library.json'
LEGACY_RATINGS_FILE = 'ratings.json'
LEGACY_BOOKMARKS_FILE = 'bookmarks.json'
VERSION = 1
MANUAL_PREFIX = 'manual:'

ENTRY_FIELDS = (
    'mbid', 'artist', 'title', 'year', 'image_url', 'url',
    'saved', 'saved_at', 'rating', 'rated_at', 'note', 'from_seed', 'source',
)
# The descriptive part of an entry, which rows and resolve() may fill. The
# state part (saved, rating, note) only changes through the methods for it.
_DETAIL_FIELDS = ('artist', 'title', 'year', 'image_url', 'url')

_LOCK = threading.Lock()


def _now():
    return datetime.now(timezone.utc).isoformat()


def slugify(text):
    return re.sub(r'[^a-z0-9]+', '-', str(text or '').lower()).strip('-')


def manual_key(artist, title):
    """The key an entry gets before it has an mbid.

    Same recipe as the old crawler's bookmark keys, so legacy records land on
    stable keys and a second import can never duplicate them.
    """
    return MANUAL_PREFIX + slugify(f'{artist or ""} {title or ""}')


def clamp_rating(value):
    """0..10 in half steps, or None when the value is not a number."""
    try:
        rating = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(rating):
        return None
    rating = min(10.0, max(0.0, rating))
    # floor(x + 0.5) rather than round(): halves go up, not to the even side.
    return math.floor(rating * 2 + 0.5) / 2.0


def _as_year(value):
    try:
        year = int(float(value))
    except (TypeError, ValueError):
        return None
    return year or None


def _empty():
    return {'version': VERSION, 'legacy_imported': False, 'entries': {}}


def _blank_entry():
    return {
        'mbid': None, 'artist': '', 'title': '', 'year': None,
        'image_url': '', 'url': '',
        'saved': False, 'saved_at': None,
        'rating': None, 'rated_at': None,
        'note': '', 'from_seed': None, 'source': 'radius',
    }


def _normalise(raw):
    """Coerce whatever is on disk into a well-formed entry, so a hand edit or
    an older shape degrades to defaults instead of breaking the UI."""
    entry = _blank_entry()
    for name in ENTRY_FIELDS:
        if name in raw:
            entry[name] = raw[name]
    entry['mbid'] = entry['mbid'] or None
    entry['year'] = _as_year(entry['year'])
    entry['saved'] = bool(entry['saved'])
    entry['rating'] = clamp_rating(entry['rating'])
    entry['note'] = str(entry['note'] or '')
    for name in ('artist', 'title', 'image_url', 'url'):
        entry[name] = str(entry[name] or '')
    return entry


def _detail(row, name):
    # AlbumFeatures.as_row() calls the title 'album'; entries call it 'title'.
    if name == 'title':
        return row.get('title') or row.get('album')
    return row.get(name)


def _apply_details(entry, row):
    for name in _DETAIL_FIELDS:
        value = _detail(row or {}, name)
        if value in (None, ''):
            continue
        entry[name] = _as_year(value) if name == 'year' else str(value)


def _key_for(row):
    row = row or {}
    return row.get('mbid') or manual_key(row.get('artist'), _detail(row, 'title'))


def _later(first, second):
    return max(first or '', second or '') or None


def _absorb(base, incoming):
    """Fold one entry into another. The base keeps every detail it already
    has; the incoming entry fills the gaps, contributes the newer of two
    ratings, and its note is appended rather than lost."""
    for name in _DETAIL_FIELDS:
        if base[name] in (None, '') and incoming.get(name) not in (None, ''):
            base[name] = incoming[name]
    if incoming.get('saved'):
        base['saved'] = True
        base['saved_at'] = _later(base['saved_at'], incoming.get('saved_at'))
    if incoming.get('rating') is not None:
        newer = (incoming.get('rated_at') or '') > (base['rated_at'] or '')
        if base['rating'] is None or newer:
            base['rating'] = incoming['rating']
            base['rated_at'] = incoming.get('rated_at')
    note = incoming.get('note') or ''
    if note and note != base['note']:
        base['note'] = '\n'.join(part for part in (base['note'], note) if part)
    if base['from_seed'] is None:
        base['from_seed'] = incoming.get('from_seed')
    if not base['mbid']:
        base['mbid'] = incoming.get('mbid') or None


def _entry_for_row(entries, row, key=None):
    """Find or create the entry a row belongs to.

    When the row brings an mbid and a 'manual:' twin of the same album is
    sitting unresolved, the twin is folded in here: the user's old rating
    should follow the record the moment we know which record it is.
    """
    row = row or {}
    key = key or _key_for(row)
    entry = entries.get(key)
    if entry is None:
        entry = entries[key] = _blank_entry()
    _apply_details(entry, row)
    mbid = row.get('mbid') or (None if key.startswith(MANUAL_PREFIX) else key)
    if mbid:
        entry['mbid'] = mbid
        twin = manual_key(entry['artist'], entry['title'])
        if twin != key and twin in entries:
            _absorb(entry, entries.pop(twin))
            entry['source'] = 'radius'
    return key, entry


def _is_blank(entry):
    return not entry['saved'] and entry['rating'] is None and not entry['note']


def _prune(entries, key):
    # An entry with nothing to say about the album is dropped rather than
    # lingering as a ghost row in the Library view.
    entry = entries.get(key)
    if entry is not None and _is_blank(entry):
        del entries[key]


def _touched(entry):
    return max(entry.get('saved_at') or '', entry.get('rated_at') or '')


def _public(key, entry):
    # Callers get a copy that also carries its key, because a manual entry's
    # key is not recoverable from the entry alone.
    return dict(entry, key=key)


def _ordered(entries):
    indexed = list(enumerate(entries.items()))
    indexed.sort(key=lambda item: (_touched(item[1][1]), item[0]), reverse=True)
    return [_public(key, entry) for _, (key, entry) in indexed]


def _read_legacy(path):
    try:
        with open(path, encoding='utf-8') as handle:
            raw = json.load(handle)
    except (OSError, ValueError):
        return {}
    return raw if isinstance(raw, dict) else {}


def _legacy_entry(record, source):
    if not isinstance(record, dict):
        return None, None
    artist = record.get('artist_name') or record.get('artist') or ''
    title = record.get('title') or ''
    if not artist or not title:
        return None, None
    entry = _blank_entry()
    entry['artist'] = str(artist)
    entry['title'] = str(title)
    entry['url'] = str(record.get('url') or '')
    entry['source'] = source
    return manual_key(artist, title), entry


class Library:
    def __init__(self, data_dir=None):
        self.data_dir = data_dir or config.DATA_ROOT
        self.path = os.path.join(self.data_dir, FILE_NAME)

    # -- storage -----------------------------------------------------------

    def _read(self):
        try:
            with open(self.path, encoding='utf-8') as handle:
                raw = json.load(handle)
        except (OSError, ValueError):
            return _empty()
        entries = raw.get('entries') if isinstance(raw, dict) else None
        if not isinstance(entries, dict):
            return _empty()
        data = _empty()
        data['legacy_imported'] = bool(raw.get('legacy_imported'))
        for key, value in entries.items():
            if isinstance(value, dict):
                data['entries'][key] = _normalise(value)
        return data

    def _write(self, data):
        os.makedirs(self.data_dir, exist_ok=True)
        temp = self.path + '.tmp'
        with open(temp, 'w', encoding='utf-8') as handle:
            json.dump(data, handle, indent=2, ensure_ascii=False, default=str)
        os.replace(temp, self.path)

    def _snapshot(self):
        with _LOCK:
            return self._read()

    def _change(self, apply):
        with _LOCK:
            data = self._read()
            result = apply(data)
            self._write(data)
        return result

    # -- reading -----------------------------------------------------------

    @property
    def legacy_imported(self):
        return self._snapshot()['legacy_imported']

    def all(self):
        return _ordered(self._snapshot()['entries'])

    def saved(self):
        return [entry for entry in self.all() if entry['saved']]

    def rated(self):
        return [entry for entry in self.all() if entry['rating'] is not None]

    def unresolved(self):
        return [entry for entry in self.all() if not entry['mbid']]

    def get(self, key):
        entry = self._snapshot()['entries'].get(key)
        return _public(key, entry) if entry is not None else None

    def is_saved(self, key):
        entry = self.get(key)
        return bool(entry and entry['saved'])

    def rating_of(self, key):
        entry = self.get(key)
        return entry['rating'] if entry else None

    # -- writing -----------------------------------------------------------

    def save_album(self, row, from_seed=None):
        def apply(data):
            key, entry = _entry_for_row(data['entries'], row)
            entry['saved'] = True
            entry['saved_at'] = _now()
            if from_seed is not None:
                entry['from_seed'] = from_seed
            return _public(key, entry)
        return self._change(apply)

    def unsave(self, key):
        def apply(data):
            entry = data['entries'].get(key)
            if entry is not None:
                entry['saved'] = False
                entry['saved_at'] = None
                _prune(data['entries'], key)
        self._change(apply)

    def rate(self, key, rating, row=None):
        value = clamp_rating(rating)

        def apply(data):
            entries = data['entries']
            if key in entries:
                entry_key, entry = key, entries[key]
                if row:
                    _apply_details(entry, row)
            elif row:
                entry_key, entry = _entry_for_row(entries, row, key)
            else:
                return None
            if value is None:
                entry['rating'], entry['rated_at'] = None, None
            else:
                entry['rating'], entry['rated_at'] = value, _now()
            result = _public(entry_key, entry)
            _prune(entries, entry_key)
            return result
        return self._change(apply)

    def unrate(self, key):
        def apply(data):
            entry = data['entries'].get(key)
            if entry is not None:
                entry['rating'], entry['rated_at'] = None, None
                _prune(data['entries'], key)
        self._change(apply)

    def set_note(self, key, note):
        def apply(data):
            entry = data['entries'].get(key)
            if entry is not None:
                entry['note'] = str(note or '').strip()
                _prune(data['entries'], key)
        self._change(apply)

    def remove(self, key):
        def apply(data):
            data['entries'].pop(key, None)
        self._change(apply)

    # -- legacy ------------------------------------------------------------

    def import_legacy(self):
        """Pull the old ratings.json and bookmarks.json in, once.

        Records become 'manual:<slug>' entries with no mbid, unless an entry
        for the same album already has one, in which case they fold into it.
        The library's own values win over legacy ones. Returns how many
        library entries were created or updated.
        """
        def apply(data):
            if data['legacy_imported']:
                return 0
            entries = data['entries']
            # Albums already in the library under a real mbid, by their slug,
            # so a legacy record for one of them never spawns a manual twin.
            by_slug = {
                manual_key(entry['artist'], entry['title']): key
                for key, entry in entries.items() if entry['mbid']
            }
            touched = set()

            def merge(key, incoming):
                target = by_slug.get(key, key)
                if target in entries:
                    _absorb(entries[target], incoming)
                else:
                    entries[target] = incoming
                touched.add(target)

            ratings = _read_legacy(os.path.join(self.data_dir, LEGACY_RATINGS_FILE))
            for record in ratings.values():
                key, entry = _legacy_entry(record, 'legacy_ratings')
                rating = clamp_rating(record.get('rating')) if entry else None
                if rating is None:
                    continue
                entry['rating'] = rating
                entry['rated_at'] = str(record.get('rated_at') or _now())
                merge(key, entry)

            bookmarks = _read_legacy(os.path.join(self.data_dir, LEGACY_BOOKMARKS_FILE))
            for record in bookmarks.values():
                key, entry = _legacy_entry(record, 'legacy_bookmarks')
                if entry is None:
                    continue
                entry['saved'] = True
                entry['saved_at'] = str(record.get('bookmarked_at') or _now())
                merge(key, entry)

            data['legacy_imported'] = True
            return len(touched)
        return self._change(apply)

    def resolve(self, key, mbid, **fields):
        """Move an entry under its mbid, now that a search has found it.

        If an entry already lives under that mbid the two merge, the existing
        one keeping its details and the resolved one contributing its saved
        state, rating and note. Extra fields ('year', 'image_url', 'url',
        'artist', 'title' or 'album') refresh the details from the search hit.
        """
        def apply(data):
            entries = data['entries']
            entry = entries.get(key)
            if entry is None:
                return None
            target = mbid or key
            if target != key:
                del entries[key]
                if target in entries:
                    _absorb(entries[target], entry)
                    entry = entries[target]
                else:
                    entries[target] = entry
            entry['mbid'] = mbid or entry['mbid']
            _apply_details(entry, fields)
            entry['source'] = 'radius'
            return _public(target, entry)
        return self._change(apply)
