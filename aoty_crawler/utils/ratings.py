"""Personal album ratings.

Ratings are stored in a flat JSON dict keyed by aoty_id, independent of any
scrape job or output file — a rating outlives the scrape that produced the
album, and can also point at an album that was never scraped at all (a
synthetic "manual:<slug>" id in that case, see manual_id()).
"""

import json
import os
import re
from datetime import datetime

RATINGS_FILENAME = 'ratings.json'


def ratings_path(data_dir):
    return os.path.join(data_dir, RATINGS_FILENAME)


def load_ratings(data_dir):
    path = ratings_path(data_dir)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def save_ratings(ratings, data_dir):
    path = ratings_path(data_dir)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(ratings, f, indent=2)


def slugify(text):
    return re.sub(r'[^a-z0-9]+', '-', (text or '').lower()).strip('-')


def manual_id(artist_name, title):
    return f"manual:{slugify(artist_name)}-{slugify(title)}"


def set_rating(data_dir, aoty_id, rating, title=None, artist_name=None, genres=None):
    ratings = load_ratings(data_dir)
    existing = ratings.get(aoty_id, {})
    ratings[aoty_id] = {
        'rating': round(float(rating), 1),
        'title': title if title is not None else existing.get('title'),
        'artist_name': artist_name if artist_name is not None else existing.get('artist_name'),
        'genres': genres if genres is not None else existing.get('genres', []),
        'rated_at': datetime.utcnow().isoformat(),
    }
    save_ratings(ratings, data_dir)
    return ratings[aoty_id]


def delete_rating(data_dir, aoty_id):
    ratings = load_ratings(data_dir)
    if aoty_id in ratings:
        del ratings[aoty_id]
        save_ratings(ratings, data_dir)
