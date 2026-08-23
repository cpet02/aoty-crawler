"""Recommendations built from a genre-affinity profile derived from your own
rating history, scored against albums already in the local scraped dataset.

Never looks outside the scraped dataset for candidates — the whole point is
using data already on disk as a comparison sample instead of the open web.
"""

import math
from collections import defaultdict

# Ratings above this pull a genre's affinity up; ratings below pull it down,
# so a low rating actively suppresses genres you've disliked rather than
# just contributing nothing.
RATING_MIDPOINT = 5.5


def build_genre_profile(ratings):
    profile = defaultdict(float)
    for r in ratings.values():
        weight = (r.get('rating') or 0) - RATING_MIDPOINT
        for genre in r.get('genres') or []:
            profile[genre] += weight
    return dict(profile)


def score_album(album, profile):
    genres = album.get('genres') or []
    if not genres or not profile:
        return 0.0
    dot = sum(profile.get(g, 0.0) for g in genres)
    album_norm = math.sqrt(len(genres))
    profile_norm = math.sqrt(sum(v * v for v in profile.values()))
    if album_norm == 0 or profile_norm == 0:
        return 0.0
    return dot / (album_norm * profile_norm)


def recommend(albums, ratings, top_n=25, min_user_reviews=0):
    """Rank unrated scraped albums by similarity to the rating-derived genre
    profile, breaking ties with AOTY's own user_score as a secondary signal."""
    rated_ids = set(ratings.keys())
    profile = build_genre_profile(ratings)
    if not profile:
        return []

    scored = []
    for album in albums:
        if album.get('aoty_id') in rated_ids:
            continue
        if (album.get('user_review_count') or 0) < min_user_reviews:
            continue
        sim = score_album(album, profile)
        if sim <= 0:
            continue
        scored.append((sim, album))

    scored.sort(key=lambda pair: (pair[0], pair[1].get('user_score') or 0), reverse=True)
    return [{**album, 'similarity': sim} for sim, album in scored[:top_n]]
