"""Personal "to listen" bookmarks.

Bookmarks are stored in a flat JSON dict keyed by aoty_id, independent of any
scrape job or output file — a bookmark outlives the scrape that produced the
album, exactly like personal ratings (see ratings.py).
"""

import json
import os
from datetime import datetime

BOOKMARKS_FILENAME = 'bookmarks.json'


def bookmarks_path(data_dir):
    return os.path.join(data_dir, BOOKMARKS_FILENAME)


def load_bookmarks(data_dir):
    path = bookmarks_path(data_dir)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def save_bookmarks(bookmarks, data_dir):
    path = bookmarks_path(data_dir)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(bookmarks, f, indent=2)


def add_bookmark(data_dir, aoty_id, title=None, artist_name=None, genres=None, url=None):
    bookmarks = load_bookmarks(data_dir)
    existing = bookmarks.get(aoty_id, {})
    bookmarks[aoty_id] = {
        'title': title if title is not None else existing.get('title'),
        'artist_name': artist_name if artist_name is not None else existing.get('artist_name'),
        'genres': genres if genres is not None else existing.get('genres', []),
        'url': url if url is not None else existing.get('url'),
        'bookmarked_at': existing.get('bookmarked_at', datetime.utcnow().isoformat()),
    }
    save_bookmarks(bookmarks, data_dir)
    return bookmarks[aoty_id]


def remove_bookmark(data_dir, aoty_id):
    bookmarks = load_bookmarks(data_dir)
    if aoty_id in bookmarks:
        del bookmarks[aoty_id]
        save_bookmarks(bookmarks, data_dir)


def is_bookmarked(bookmarks, aoty_id):
    return aoty_id in bookmarks
