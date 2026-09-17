"""The album fingerprint, and how one gets built.

Deliberately no critic score anywhere. What a listening corpus and a
catalogue can tell you instead:

* genre       where the record sits in the vendored genre taxonomy
* mood        the descriptive tags the taxonomy has never heard of — the
              "melancholic / hypnagogic / mysterious" vocabulary that carries
              the intangibles genre names can't
* lineage     the *artist's* tag vector: a scene and a pedigree, which is a
              different thing from one record's sound
* neighbours  ListenBrainz's collaborative similar-artist set, compared as an
              overlap. Listener behaviour rather than vocabulary, so it finds
              kinship no tag agrees on
* prose       bag-of-words over the Wikipedia article: where it was made,
              what it was reacting to, who produced it
* reach       log10 distinct listeners
* devotion    listens per listener: how hard the people who found it hold on.
              Cult records run high on devotion and low on reach
* canonicity  this album's share of its artist's audience — the difference
              between a calling card and a deep cut
* era         release year
* scale       runtime and track count — a 78-minute double LP is not the same
              object as a 31-minute one
* pacing      mean track length and how uneven it is
* definition  how concentrated the tag distribution is: everyone agreeing on
              one label is a different kind of record from one drawing forty
              scattered ones, and "hard to place" is itself worth matching on
* origin      where the artist is from, and whether they're a band or a person
* career      years into the artist's career when the record landed: a
              restless debut and a late masterwork are different animals
* titling     mean words per track title, a real stylistic tell

Almost all of it arrives in two bulk requests per batch of albums, because
ListenBrainz serves metadata and popularity for many mbids at a time.
"""

import math
import re
from dataclasses import dataclass, field

from . import tags as tagmod
from . import text as textmod

# Titles that are usually not the studio album you meant to compare against.
# The catalogue's own release-group type is the better signal; this catches
# the many release groups that carry no secondary type at all.
_NON_STUDIO = re.compile(
    r'\b(live|unplugged|greatest hits|best of|anthology|collection|'
    r'compilation|b-sides|bsides|rarities|remix(?:es|ed)?|demos?|'
    r'instrumentals?|karaoke|tribute|soundtrack|session(?:s)?)\b'
    r'|\(live\b|\blive at\b|\blive in\b',
    re.IGNORECASE,
)
_EDITION_NOISE = re.compile(
    r'\s*[\(\[][^\)\]]*\b(deluxe|expanded|remaster(?:ed)?|anniversary|'
    r'edition|reissue|bonus|explicit|special|legacy|version)\b[^\)\]]*[\)\]]'
    r'|\s*[-–—:]\s*(deluxe|expanded|remastered|anniversary)\b.*$',
    re.IGNORECASE,
)
NON_STUDIO_TYPES = {
    'live', 'compilation', 'remix', 'dj-mix', 'mixtape/street', 'soundtrack',
    'interview', 'spokenword', 'audiobook', 'audio drama', 'demo',
}


def canonical_title(title):
    cleaned = _EDITION_NOISE.sub('', title or '').strip()
    return cleaned or (title or '').strip()


def album_key(artist, title):
    return f'{(artist or "").strip().lower()}␟{canonical_title(title).lower()}'


def looks_non_studio(title):
    return bool(_NON_STUDIO.search(title or ''))


def jaccard(set_a, set_b):
    if not set_a or not set_b:
        return None
    union = set_a | set_b
    return (len(set_a & set_b) / len(union)) if union else None


@dataclass
class AlbumFeatures:
    artist: str
    title: str
    mbid: str = ''                 # release-group mbid
    artist_mbid: str = ''
    url: str = ''
    image_url: str = ''
    listeners: int = 0             # distinct listeners
    listen_count: int = 0          # total listens
    profile: dict = field(default_factory=dict)
    artist_profile: dict = field(default_factory=dict)
    artist_neighbours: frozenset = frozenset()
    prose: dict = field(default_factory=dict)
    year: int = None
    release_type: str = ''
    secondary_types: tuple = ()
    artist_area: str = ''
    artist_type: str = ''
    artist_debut_year: int = None
    artist_listeners: int = 0
    track_count: int = 0
    runtime_seconds: int = 0
    mean_track_seconds: float = 0.0
    track_length_spread: float = 0.0
    mean_title_words: float = 0.0

    @property
    def key(self):
        return album_key(self.artist, self.title)

    @property
    def reach(self):
        """log10 listeners — linear over orders of magnitude."""
        return math.log10(self.listeners + 1)

    @property
    def devotion(self):
        """Listens per listener. 1.0 means nobody came back to it."""
        if self.listeners <= 0:
            return 0.0
        return self.listen_count / self.listeners

    @property
    def canonicity(self):
        """Share of the artist's audience that reached this record."""
        if not self.artist_listeners or not self.listeners:
            return None
        return min(self.listeners / self.artist_listeners, 1.0)

    @property
    def definition(self):
        """Normalised entropy of the tag profile: 0 = one label everyone
        agrees on, 1 = tagged in every direction at once."""
        weights = [w for w in self.profile.values() if w > 0]
        if len(weights) < 2:
            return 0.0
        total = sum(weights)
        entropy = -sum((w / total) * math.log(w / total) for w in weights)
        return entropy / math.log(len(weights))

    @property
    def career_stage(self):
        """Years into the artist's career, or None."""
        if not self.year or not self.artist_debut_year:
            return None
        return max(self.year - self.artist_debut_year, 0)

    @property
    def has_tracklist(self):
        return self.track_count > 0 and self.runtime_seconds > 0

    @property
    def is_studio(self):
        """False for live albums, compilations and the like."""
        if self.release_type and self.release_type.lower() in NON_STUDIO_TYPES:
            return False
        if any((t or '').lower() in NON_STUDIO_TYPES for t in self.secondary_types):
            return False
        return not looks_non_studio(self.title)

    @property
    def root_genres(self):
        return tagmod.root_genres(self.profile)

    @property
    def subgenres(self):
        return tagmod.subgenre_tags(self.profile)

    @property
    def genre_profile(self):
        """Only the tags the taxonomy recognises as genre."""
        index = tagmod.hierarchy_index()
        return {t: w for t, w in self.profile.items() if t in index}

    @property
    def mood_profile(self):
        """Everything else — moods, scenes, textures, sonic adjectives."""
        index = tagmod.hierarchy_index()
        return {t: w for t, w in self.profile.items() if t not in index}

    @property
    def top_tags(self):
        return sorted(self.profile, key=self.profile.get, reverse=True)

    def as_row(self):
        canon = self.canonicity
        return {
            'artist': self.artist,
            'album': self.title,
            'year': self.year,
            'listeners': self.listeners or None,
            'listens': self.listen_count or None,
            'listens_each': round(self.devotion, 2) if self.listeners else None,
            'tracks': self.track_count or None,
            'runtime_min': round(self.runtime_seconds / 60.0, 1) if self.runtime_seconds else None,
            'canonicity': round(canon, 3) if canon is not None else None,
            'definition': round(self.definition, 3),
            'career_stage': self.career_stage,
            'from': self.artist_area or None,
            'artist_type': self.artist_type or None,
            'release_type': self.release_type or None,
            'genre_tags': ', '.join(t for t in self.top_tags if t in self.genre_profile)[:120],
            'mood_tags': ', '.join(t for t in self.top_tags if t in self.mood_profile)[:120],
            'lineage_tags': ', '.join(
                sorted(self.artist_profile, key=self.artist_profile.get, reverse=True)[:5]),
            'url': self.url,
            'image_url': self.image_url,
            'mbid': self.mbid,
        }


def _as_int(value):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def tag_entries(raw):
    """ListenBrainz tag dicts -> the {name, count} shape tag_profile wants.

    MusicBrainz tag counts are small integers — a handful of votes — rather
    than Last.fm's 0-100 scale, so they get rescaled against the strongest tag
    on the record. Prominence ordering is what actually matters here, since
    the broad genre almost always outvotes its own subgenre, and that ordering
    survives rescaling untouched.
    """
    entries = [t for t in (raw or []) if isinstance(t, dict) and t.get('tag')]
    if not entries:
        return []
    peak = max(max(_as_int(t.get('count')), 1) for t in entries)
    return [
        {'name': t['tag'], 'count': 100.0 * max(_as_int(t.get('count')), 1) / peak}
        for t in entries
    ]


def _year_from(block):
    """Release year out of a 'date' field that may be a bare year, a
    year-month, or a full date."""
    if block.get('year'):
        return _as_int(block['year']) or None
    date = str(block.get('date') or '')
    return int(date[:4]) if len(date) >= 4 and date[:4].isdigit() else None


def _cover_art(block):
    """Cover art comes free with the metadata, as an archive.org id pair."""
    caa_id = block.get('caa_id')
    release_mbid = block.get('caa_release_mbid')
    if not caa_id or not release_mbid:
        return ''
    return (f'https://archive.org/download/mbid-{release_mbid}/'
            f'mbid-{release_mbid}-{caa_id}_thumb250.jpg')


def _title_verbosity(titles):
    """Mean word count of the track titles. Long, sentence-like titles are a
    genuine signature (post-rock, emo, folk), and so are one-word ones."""
    words = [len((t or '').split()) for t in titles if t]
    return (sum(words) / len(words)) if words else 0.0


def from_metadata(mbid, metadata, popularity=None):
    """Build an AlbumFeatures from one ListenBrainz metadata entry.

    Returns None when the record carries no descriptive tags at all — an
    album with no tag profile can't be placed in the space, so it can't be
    honestly compared to anything.
    """
    metadata = metadata or {}
    tag_block = metadata.get('tag') or {}
    # The release_group block is the canonical one; the release block is the
    # specific edition ListenBrainz happened to pick and can disagree on date.
    release_block = metadata.get('release_group') or metadata.get('release') or {}
    artist_block = metadata.get('artist') or {}
    artists = artist_block.get('artists') or []
    primary_artist = artists[0] if artists and isinstance(artists[0], dict) else {}

    profile = tagmod.tag_profile(tag_entries(tag_block.get('release_group')))
    artist_profile = tagmod.tag_profile(tag_entries(tag_block.get('artist')), max_tags=12)
    if not profile:
        # An untagged record can still be placed using its artist's tags, but
        # that is weaker evidence, so it comes in at reduced weight.
        profile = {tag: weight * 0.6 for tag, weight in artist_profile.items()}
    if not profile:
        return None

    counts = popularity or {}
    features = AlbumFeatures(
        artist=artist_block.get('name') or primary_artist.get('name') or '',
        title=release_block.get('name') or '',
        mbid=mbid,
        artist_mbid=primary_artist.get('artist_mbid') or '',
        url=f'https://musicbrainz.org/release-group/{mbid}',
        listeners=_as_int(counts.get('total_user_count')),
        listen_count=_as_int(counts.get('total_listen_count')),
        profile=profile,
        artist_profile=artist_profile,
        year=_year_from(release_block),
        image_url=_cover_art(release_block),
        release_type=release_block.get('type') or '',
        artist_area=primary_artist.get('area') or '',
        artist_type=primary_artist.get('type') or '',
        artist_debut_year=primary_artist.get('begin_year') or None,
    )
    if not features.title or not features.artist:
        return None
    return features


def merge_profiles(base, extra):
    """Combine two tag profiles by taking the stronger claim for each tag.

    The two sources fail in opposite directions. MusicBrainz tags are
    curated and precise but thin, and a record with four votes gets four
    tags. Last.fm's are broad and noisy but plentiful, and they carry the
    mood vocabulary MusicBrainz taggers rarely bother with. Taking the max
    keeps MusicBrainz's confident genre calls at full strength while letting
    Last.fm fill in everything it never had a word for — and because both
    sides are already normalised to 0..1 by prominence, neither can drown
    the other out purely by having more tags.
    """
    if not extra:
        return dict(base)
    merged = dict(base)
    for tag, weight in extra.items():
        merged[tag] = max(merged.get(tag, 0.0), weight)
    return merged


def enrich_tags(features, lastfm, artist_cache=None):
    """Thicken an album's tag vectors with Last.fm's crowd tags.

    A no-op when no key is configured, so this is safe to call
    unconditionally. Returns True if anything was actually added.
    """
    if lastfm is None or not getattr(lastfm, 'configured', False):
        return False
    if not features.artist or not features.title:
        return False

    before = len(features.profile)
    album_tags = tagmod.tag_profile(lastfm.album_tags(features.artist, features.title))
    features.profile = merge_profiles(features.profile, album_tags)

    # One artist lookup serves every album by that artist in the pool.
    if artist_cache is None:
        artist_cache = {}
    artist_key = features.artist.strip().lower()
    if artist_key not in artist_cache:
        artist_cache[artist_key] = tagmod.tag_profile(
            lastfm.artist_tags(features.artist), max_tags=12
        )
    features.artist_profile = merge_profiles(
        features.artist_profile, artist_cache[artist_key]
    )
    return len(features.profile) > before


def attach_tracklist(features, musicbrainz):
    """Fill in the shape axes: runtime, pacing, titling.

    Costs a full second of the MusicBrainz budget per album, so callers save
    it for albums that actually made the result list.
    """
    if not features.mbid or musicbrainz is None or features.has_tracklist:
        return features
    try:
        titles, lengths = musicbrainz.tracklist(features.mbid)
    except Exception:
        return features
    if not titles:
        return features

    features.track_count = len(titles)
    features.mean_title_words = _title_verbosity(titles)
    if lengths:
        seconds = [ms / 1000.0 for ms in lengths]
        mean = sum(seconds) / len(seconds)
        variance = sum((s - mean) ** 2 for s in seconds) / len(seconds)
        features.runtime_seconds = int(sum(seconds))
        features.mean_track_seconds = mean
        # Coefficient of variation: what separates an even run of songs from a
        # record built out of a nine-minute centrepiece and four interludes.
        features.track_length_spread = (math.sqrt(variance) / mean) if mean else 0.0
    return features


def attach_prose(features_list, musicbrainz, wikipedia):
    """Fetch Wikipedia intros for a batch of albums and vectorise them.

    Three batched stages, because MusicBrainz mostly points at Wikidata now
    rather than at Wikipedia directly: collect each album's article reference,
    resolve any Q-ids to English titles fifty at a time, then pull twenty
    article intros per request.
    """
    if musicbrainz is None or wikipedia is None:
        return

    direct, by_qid = {}, {}
    for features in features_list:
        if not features.mbid:
            continue
        try:
            ref = musicbrainz.article_ref(features.mbid)
        except Exception:
            ref = None
        if not ref:
            continue
        kind, value = ref
        if kind == 'wikipedia':
            direct[features.key] = value
        else:
            by_qid[features.key] = value

    titles = dict(direct)
    if by_qid:
        try:
            resolved = wikipedia.titles_for_wikidata(set(by_qid.values()))
        except Exception:
            resolved = {}
        for key, qid in by_qid.items():
            if resolved.get(qid):
                titles[key] = resolved[qid]
    if not titles:
        return

    try:
        extracts = wikipedia.extracts(set(titles.values()))
    except Exception:
        return
    for features in features_list:
        title = titles.get(features.key)
        if title and extracts.get(title):
            features.prose = textmod.prose_profile(
                textmod.clean_prose(extracts[title]),
                exclude=textmod.name_tokens(features.title, features.artist),
            )
