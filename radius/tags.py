"""Turning Last.fm's messy crowd tags into a usable descriptive vector.

Three jobs here:

1. Filter. Crowd tags are half collection-management ("albums i own") and
   half description ("chamber folk", "melancholic"). Only the second half
   carries signal, so `config.TAG_STOPLIST` drops the first.

2. Rank by prominence. Last.fm returns a 0-100 weighted count per tag, which
   is the genre-vs-subgenre ordering this project used to scrape for: the
   broad genre is nearly always tagged more often than the specific one, so it
   sorts first.

3. Weight by specificity. A tag shared by every candidate ("rock") tells you
   almost nothing about *which* album to pick; one held by a handful
   ("chamber folk") tells you a lot. Inverse document frequency over the
   candidate pool does that, and the vendored genre taxonomy adds a bonus for
   tags that are known subgenres rather than known roots (see
   radius/taxonomy.py — static offline data, nothing crawled).

The taxonomy is NOT what decides whether a tag is a genre or a mood any more.
That split comes from the sources: ListenBrainz marks its genre tags with a
`genre_mbid`, and everything else is classified against a flat set of genre
names (MusicBrainz's whitelist plus the taxonomy's own names, see
`taxonomy_genre_names` / `split_profile`). The hierarchy is only consulted
for depth - root vs subgenre - via `specificity`, `root_genres` and
`subgenre_tags`.
"""

import math
import re
from collections import Counter

from . import config
from .taxonomy import GENRE_HIERARCHY

_PUNCT = re.compile(r'[\s_/]+')

# Common spellings of the same idea, so the vector doesn't split its weight.
TAG_ALIASES = {
    'hip hop': 'hip-hop', 'hiphop': 'hip-hop', 'rap': 'hip-hop',
    'r&b': 'rnb', 'r and b': 'rnb',
    'lofi': 'lo-fi', 'low fi': 'lo-fi',
    'singer songwriter': 'singer-songwriter',
    'post rock': 'post-rock', 'post punk': 'post-punk',
    'post metal': 'post-metal', 'post hardcore': 'post-hardcore',
    'trip hop': 'trip-hop', 'synth pop': 'synthpop', 'dream pop': 'dream-pop',
    'electronica': 'electronic', 'electronic music': 'electronic',
    'alt rock': 'alternative rock',
    'idm': 'intelligent dance music',
}


def normalize_tag(tag):
    lowered = _PUNCT.sub(' ', (tag or '').strip().lower())
    lowered = re.sub(r'\s+', ' ', lowered).strip()
    return TAG_ALIASES.get(lowered, lowered)


def _build_hierarchy_index():
    """tag -> (root genre, depth). Depth 0 is a top-level genre, 1 a subgenre
    of one."""
    index = {}
    for parent, children in GENRE_HIERARCHY.items():
        index.setdefault(normalize_tag(parent), (parent, 0))
    for parent, children in GENRE_HIERARCHY.items():
        for child in children:
            # First parent wins for a subgenre listed under several roots, and
            # a tag that is itself a top-level genre stays at depth 0.
            index.setdefault(normalize_tag(child), (parent, 1))
    return index


_HIERARCHY_INDEX = None


def hierarchy_index():
    global _HIERARCHY_INDEX
    if _HIERARCHY_INDEX is None:
        _HIERARCHY_INDEX = _build_hierarchy_index()
    return _HIERARCHY_INDEX


_TAXONOMY_GENRE_NAMES = None


def taxonomy_genre_names():
    """Every parent and child of the vendored hierarchy, normalised - the
    offline half of the genre-name set the engine classifies crowd tags
    against (the other half is MusicBrainz's genre whitelist)."""
    global _TAXONOMY_GENRE_NAMES
    if _TAXONOMY_GENRE_NAMES is None:
        names = set()
        for parent, children in GENRE_HIERARCHY.items():
            names.add(normalize_tag(parent))
            names.update(normalize_tag(child) for child in children)
        names.discard('')
        _TAXONOMY_GENRE_NAMES = frozenset(names)
    return _TAXONOMY_GENRE_NAMES


def split_profile(profile, genre_names):
    """(genres, moods): a tag is a genre iff its normalised name is in
    `genre_names`; everything else - moods, scenes, textures - is a mood.
    Weights are carried over untouched. With no name set given, the
    taxonomy's own names stand in, which is what the engine falls back to
    when MusicBrainz's list can't be fetched."""
    if genre_names is None:
        genre_names = taxonomy_genre_names()
    genres, moods = {}, {}
    for tag, weight in (profile or {}).items():
        if normalize_tag(tag) in genre_names:
            genres[tag] = weight
        else:
            moods[tag] = weight
    return genres, moods


def era_year(tag):
    """Year implied by a tag like '1997', '90s', '1980s', or None."""
    cleaned = normalize_tag(tag)
    match = re.fullmatch(r'(19|20)(\d{2})s?', cleaned)
    if match:
        return int(match.group(1) + match.group(2))
    match = re.fullmatch(r'(\d{2})s', cleaned)
    if match:
        decade = int(match.group(1))
        # A bare "90s" means the 1990s; "00s"/"10s"/"20s" the 2000s onward.
        return 1900 + decade if decade >= 30 else 2000 + decade
    return None


def is_descriptive(tag):
    """True if a tag says something about the music itself."""
    cleaned = normalize_tag(tag)
    if not cleaned or len(cleaned) < 2:
        return False
    if cleaned in config.TAG_STOPLIST:
        return False
    if era_year(cleaned) is not None:
        return False
    if cleaned.isdigit():
        return False
    # Personal collection tags come in endless variations ("albums i own on
    # vinyl and cd"); anything first-person is collection management.
    if re.search(r'\b(i|my|me)\b', cleaned):
        return False
    return True


def tag_profile(raw_tags, max_tags=25):
    """[{name, count}] -> {normalized tag: weight in 0..1}, strongest first.

    Sorted by count before anything else, because `max_tags` truncates and
    the sources don't all return tags in vote order — an unsorted pass can
    throw away the defining tag and keep a stray one.
    """
    def _count_of(entry):
        if not isinstance(entry, dict):
            return 0.0
        try:
            return float(entry.get('count') or 0)
        except (TypeError, ValueError):
            return 0.0

    ordered = sorted(raw_tags or [], key=_count_of, reverse=True)
    profile = {}
    for entry in ordered:
        name = entry.get('name') if isinstance(entry, dict) else entry
        if not is_descriptive(name):
            continue
        count = _count_of(entry)
        cleaned = normalize_tag(name)
        weight = min(max(count, 1.0) / 100.0, 1.0)
        # An alias collision keeps the stronger of the two.
        profile[cleaned] = max(profile.get(cleaned, 0.0), weight)
        if len(profile) >= max_tags:
            break
    return profile


def era_hint(raw_tags):
    """Best-guess year from decade/year tags, used only when MusicBrainz has
    no release year for the album."""
    years = []
    for entry in raw_tags or []:
        name = entry.get('name') if isinstance(entry, dict) else entry
        year = era_year(name)
        if year is None:
            continue
        count = 0.0
        if isinstance(entry, dict):
            try:
                count = float(entry.get('count') or 0)
            except (TypeError, ValueError):
                count = 0.0
        years.append((count, year))
    if not years:
        return None
    return max(years)[1]


def specificity(tag):
    """Hierarchy-derived multiplier: known subgenres out-weigh known roots.

    Tags the taxonomy has never heard of (moods, scenes, "winter") sit
    between the two — they're descriptive but unverified.
    """
    entry = hierarchy_index().get(tag)
    if entry is None:
        return 1.0
    return 1.6 if entry[1] == 1 else 0.7


def root_genres(profile):
    """Top-level genres implied by a tag profile, strongest first."""
    scores = Counter()
    for tag, weight in profile.items():
        entry = hierarchy_index().get(tag)
        if entry is not None:
            scores[entry[0]] += weight
    return [genre for genre, _ in scores.most_common()]


def subgenre_tags(profile):
    """The tags in a profile that the hierarchy knows to be subgenres."""
    index = hierarchy_index()
    return {tag for tag in profile if (index.get(tag) or (None, 0))[1] == 1}


def build_idf(profiles):
    """Inverse document frequency across a pool of tag profiles.

    A tag on every album in the pool lands near the floor; a rare one keeps
    close to its full weight. The floor stays positive so shared broad genre
    is still mild evidence of similarity rather than none.
    """
    total = len(profiles)
    if total == 0:
        return {}
    document_frequency = Counter()
    for profile in profiles:
        document_frequency.update(profile.keys())
    return {
        tag: max(math.log((total + 1) / (count + 0.5)), 0.15)
        for tag, count in document_frequency.items()
    }


def weighted_vector(profile, idf):
    """Combine crowd prominence, corpus rarity and hierarchy depth."""
    return {
        tag: weight * idf.get(tag, 1.0) * specificity(tag)
        for tag, weight in profile.items()
    }


def cosine(vector_a, vector_b):
    if not vector_a or not vector_b:
        return 0.0
    small, large = (vector_a, vector_b) if len(vector_a) <= len(vector_b) else (vector_b, vector_a)
    dot = sum(value * large.get(tag, 0.0) for tag, value in small.items())
    if dot == 0.0:
        return 0.0
    norm_a = math.sqrt(sum(v * v for v in vector_a.values()))
    norm_b = math.sqrt(sum(v * v for v in vector_b.values()))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def shared_tags(profile_a, profile_b, limit=6):
    """Tags both albums carry, strongest-in-common first — the human-readable
    reason a recommendation showed up."""
    common = set(profile_a) & set(profile_b)
    ranked = sorted(common, key=lambda tag: min(profile_a[tag], profile_b[tag]), reverse=True)
    return ranked[:limit]
