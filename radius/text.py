"""Bag-of-words vectors over the prose Last.fm already hands us.

`album.getInfo` carries a wiki summary and `artist.getInfo` a bio, both in
the payloads this project fetches anyway. That text is where the genuinely
unnameable things live — who produced it, where it was recorded, what it was
reacting against, the fact that it was written in one week in a borrowed
house. No tag vocabulary captures that, and two records described in similar
words are often alike in ways no genre label would predict.

Cheap and deliberately shallow: strip markup, drop stopwords, count stems.
Idf across the candidate pool does the discriminating, same as for tags.
"""

import re

_TAG_RE = re.compile(r'<[^>]+>')
_WORD_RE = re.compile(r"[a-z][a-z'\-]{2,}")

# Last.fm appends a licence notice to every wiki and bio; it would otherwise
# be the single most "shared" phrase in the entire corpus.
_BOILERPLATE = re.compile(
    r'user-contributed text is available under.*$'
    r'|read more on last\.?fm.*$'
    r'|do not edit this field.*$',
    re.IGNORECASE | re.DOTALL,
)

STOPWORDS = {
    'the', 'and', 'was', 'were', 'has', 'have', 'had', 'his', 'her', 'its',
    'their', 'they', 'them', 'this', 'that', 'these', 'those', 'with', 'from',
    'for', 'are', 'but', 'not', 'you', 'all', 'can', 'been', 'which', 'who',
    'whom', 'what', 'when', 'where', 'how', 'why', 'would', 'could', 'should',
    'also', 'after', 'before', 'during', 'into', 'out', 'over', 'under',
    'more', 'most', 'other', 'some', 'such', 'only', 'own', 'same', 'than',
    'then', 'there', 'here', 'about', 'above', 'again', 'between', 'both',
    'each', 'few', 'once', 'said', 'says', 'one', 'two', 'three', 'first',
    'second', 'third', 'new', 'released', 'release', 'album', 'albums',
    'record', 'records', 'song', 'songs', 'track', 'tracks', 'band', 'group',
    'music', 'musical', 'studio', 'label', 'lastfm', 'wikipedia',
    'featuring', 'feat', 'via', 'http', 'https', 'www', 'com',
    # Release and chart boilerplate. Every album article says an album was
    # released on a date by a label and charted at a number; none of it
    # distinguishes one record from another.
    'fourth', 'fifth', 'sixth', 'seventh', 'eighth', 'ninth', 'tenth',
    'debut', 'follow', 'followed', 'following', 'chart', 'charts', 'charted',
    'number', 'peaked', 'position', 'sales', 'sold', 'copies', 'certified',
    'platinum', 'gold', 'billboard', 'week', 'weeks', 'year', 'years',
    'january', 'february', 'march', 'april', 'june', 'july', 'august',
    'september', 'october', 'november', 'december',
    'critics', 'critical', 'reviews', 'review', 'reviewer', 'acclaim',
    'rated', 'rating', 'score', 'metacritic', 'pitchfork', 'rolling',
    'magazine', 'named', 'list', 'ranked', 'placed', 'awarded', 'award',
    'released', 'release', 'releases', 'reissued', 'recording', 'records',
    'track', 'tracks', 'single', 'singles', 'title', 'titled', 'called',
    'includes', 'including', 'consists', 'features', 'contains',
}


def name_tokens(*names):
    """Words from an album or artist's own name.

    A record's title and its artist are perfectly unique to it, so idf hands
    them the highest possible weight while they carry no information at all
    about what a record is *like*. They have to go.
    """
    tokens = set()
    for name in names:
        for word in _WORD_RE.findall((name or '').lower()):
            tokens.add(word)
            # Possessives show up constantly in these articles.
            tokens.add(word + "'s")
    return tokens


def clean_prose(*chunks):
    """Markup-free, boilerplate-free lowercase text from one or more sources."""
    parts = []
    for chunk in chunks:
        if not chunk:
            continue
        text = _TAG_RE.sub(' ', str(chunk))
        text = _BOILERPLATE.sub(' ', text)
        parts.append(text.lower())
    return ' '.join(parts)


def prose_profile(text, max_terms=60, exclude=()):
    """{term: sublinear term frequency} — damped so a word repeated ten times
    doesn't outweigh ten distinct words."""
    if not text:
        return {}
    excluded = set(exclude)
    counts = {}
    for word in _WORD_RE.findall(text):
        if word in STOPWORDS or word in excluded or len(word) < 4:
            continue
        counts[word] = counts.get(word, 0) + 1
    if not counts:
        return {}
    ranked = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)[:max_terms]
    peak = ranked[0][1]
    # Sublinear scaling, normalised against the document's own top term so
    # long bios don't dominate short ones purely by length.
    return {term: (1.0 + (count - 1) / peak) / 2.0 for term, count in ranked}
