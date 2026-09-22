"""The album fingerprint, and how one gets built.

One record, everything we can know about it, laid out so that two of them
can be compared axis by axis and so that every statistic can be shown side
by side. Roughly, in the order the pipeline fills it in:

* the descriptive vector: `profile` (every tag), split into `genres` (what
  ListenBrainz flags as a genre, or what the genre-name list recognises) and
  `moods` (the rest - "melancholic / hypnagogic / mysterious", the vocabulary
  genre names can't carry); `artist_profile` is the artist's own vector, a
  scene and a pedigree rather than one record's sound
* reception: listeners and listens from ListenBrainz, fans from Deezer,
  scrobbles from Last.fm, critic scores from Wikidata, want/have from Discogs
* the connection graph: `personnel` (members, side projects, aliases - the
  people, keyed by mbid), the production `circle` (producers, engineers,
  performers, studios, labels - keyed by a name key so MusicBrainz, Wikidata
  and Discogs credits can meet), and the collaborative `artist_neighbours`
* shape: runtime, track count, pacing, BPM and loudness
* provenance: where the artist is from, band or person, years into a career

Everything is optional. A field that is missing stays at its empty default,
and the similarity axes drop what they cannot measure rather than guessing.
`as_row()` flattens the whole thing into one JSON-serialisable dict for the
table and the CSV.

The first fill (`from_metadata`) arrives in two bulk requests per batch of
albums, because ListenBrainz serves metadata and popularity for many mbids at
a time. The `apply_*` functions each take one parsed payload (see
`credits.py`) and copy it onto the features without ever dropping what an
earlier stage put there.
"""

import math
import re
import unicodedata
from dataclasses import dataclass, field, fields
from urllib.parse import quote

from . import tags as tagmod

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

_PERSON_PUNCT = re.compile(r'[^\w\s]')


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


_LABEL_SUFFIX = re.compile(r'\s+(?:records|recordings|record co|record company|music)$')


def _person_key(name):
    """Name key for matching credits across sources.

    This is deliberately the same recipe as credits.person_key (casefold,
    strip diacritics via NFKD, drop punctuation, collapse whitespace, drop a
    leading 'the ' and a trailing ' records'), defined locally because
    albums.py must not import credits.py. Keep the two identical.
    """
    text = unicodedata.normalize('NFKD', str(name or ''))
    text = ''.join(ch for ch in text if not unicodedata.combining(ch))
    text = _PERSON_PUNCT.sub(' ', text.casefold())
    text = re.sub(r'\s+', ' ', text).strip()
    if text.startswith('the '):
        text = text[4:]
    stripped = _LABEL_SUFFIX.sub('', text)
    return stripped or text


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
    # --- v2 additions, in pipeline order ---
    artist_end_year: int = None
    artist_gender: str = ''
    artist_links: dict = field(default_factory=dict)        # {relation type: url}
    genres: dict = field(default_factory=dict)              # the split of `profile`
    moods: dict = field(default_factory=dict)
    artist_neighbour_mbids: frozenset = frozenset()
    artist_neighbours_ranked: tuple = ()                    # display names, strongest first
    personnel: dict = field(default_factory=dict)           # {mbid: name}, the artist included
    personnel_relations: dict = field(default_factory=dict)  # {mbid: relation label}
    editions: int = 0
    release_countries: frozenset = frozenset()
    first_release_date: str = ''
    mb_genres: list = field(default_factory=list)
    mb_rating: float = None
    mb_rating_votes: int = 0
    wikidata_id: str = ''
    discogs_master_id: str = ''
    links: dict = field(default_factory=dict)               # {relation type: url}
    canonical_release_mbid: str = ''
    track_titles: list = field(default_factory=list)
    recording_mbids: list = field(default_factory=list)
    formats: list = field(default_factory=list)
    labels: dict = field(default_factory=dict)              # {person key: name}
    catalog_numbers: list = field(default_factory=list)
    release_country: str = ''
    release_date: str = ''
    barcode: str = ''
    producers: dict = field(default_factory=dict)           # {person key: name}
    engineers: dict = field(default_factory=dict)
    performers: dict = field(default_factory=dict)
    studios: dict = field(default_factory=dict)
    credits: list = field(default_factory=list)             # [{'role','name','mbid','level','source'}]
    artist_rg_listeners: int = 0                            # summed over the artist's release groups
    artist_top_listeners: int = 0                           # the artist's most-listened release group
    artist_first_release_year: int = None                   # earliest release in that catalogue
    deezer_id: int = None
    fans: int = 0
    explicit: bool = None
    deezer_label: str = ''
    deezer_genres: list = field(default_factory=list)
    deezer_release_date: str = ''
    deezer_url: str = ''
    bpm_mean: float = None
    bpm_spread: float = None
    gain_mean: float = None
    gain_spread: float = None
    tracks_with_bpm: int = 0
    lastfm_listeners: int = 0
    lastfm_playcount: int = 0
    critic_scores: dict = field(default_factory=dict)       # {reviewer: 0..1}
    acclaim: float = None
    spotify_id: str = ''
    styles: list = field(default_factory=list)
    have: int = 0
    want: int = 0
    discogs_rating: float = None
    discogs_votes: int = 0
    num_for_sale: int = 0
    lowest_price: float = None
    discogs_url: str = ''
    enriched: set = field(default_factory=set)              # stage tags applied
    seed_mbids: tuple = ()                                  # only on a blend
    seed_artist_mbids: tuple = ()

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
        """This record's audience as a share of the artist's most-listened
        record's: 1.0 for the calling card, small for a deep cut.

        Measured against the biggest single release group rather than the
        artist's total because ListenBrainz maps listens to release groups
        far less completely than to artists, so a share of the artist total
        reads every record as a deep cut. None until the artist's catalogue
        has been fetched.
        """
        if not self.artist_top_listeners or not self.listeners:
            return None
        return min(self.listeners / self.artist_top_listeners, 1.0)

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
        """Years between the artist's first record and this one, or None.

        The catalogue's earliest release is the honest start. MusicBrainz's
        begin year only stands in until that is known, and for a solo artist
        it is their date of birth, which would read a debut album as thirty
        years into a career.
        """
        start = self.artist_first_release_year or self.artist_debut_year
        if not self.year or not start:
            return None
        return max(self.year - start, 0)

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

    def _split(self):
        # A features object built by hand (or before any split ran) still
        # gets a usable split, from the taxonomy's names alone.
        if self.genres or self.moods or not self.profile:
            return self.genres, self.moods
        return tagmod.split_profile(self.profile, None)

    @property
    def genre_profile(self):
        """The tags the sources call genres."""
        return self._split()[0]

    @property
    def mood_profile(self):
        """Everything else — moods, scenes, textures, sonic adjectives."""
        return self._split()[1]

    @property
    def top_tags(self):
        return sorted(self.profile, key=self.profile.get, reverse=True)

    @property
    def want_ratio(self):
        """Discogs want / have: how much more sought-after than owned."""
        if not self.have or not self.want:
            return None
        return self.want / self.have

    @property
    def label(self):
        if self.labels:
            return next(iter(self.labels.values()))
        return self.deezer_label or ''

    @property
    def producer_names(self):
        return sorted(self.producers.values())

    @property
    def studio_names(self):
        return sorted(self.studios.values())

    def as_row(self):
        """One flat, JSON-serialisable dict per album, every field included.

        Key order is fixed by construction so a CSV of many rows lines up.
        Dicts of {key: name} become their sorted names; sets and lists are
        joined; floats are rounded to three places.
        """
        canon = self.canonicity
        want_ratio = self.want_ratio
        return {
            # identity
            'artist': self.artist,
            'album': self.title,
            'year': self.year,
            'mbid': self.mbid,
            'artist_mbid': self.artist_mbid,
            'url': self.url,
            'image_url': self.image_url,
            'release_type': self.release_type or None,
            'secondary_types': _join(self.secondary_types),
            'is_studio': bool(self.is_studio),
            # provenance
            'from': self.artist_area or None,
            'artist_type': self.artist_type or None,
            'artist_gender': self.artist_gender or None,
            'artist_debut_year': self.artist_debut_year,
            'artist_end_year': self.artist_end_year,
            'artist_first_release_year': self.artist_first_release_year,
            'career_stage': self.career_stage,
            'artist_links': _join_pairs(self.artist_links),
            # reception
            'listeners': self.listeners or None,
            'listens': self.listen_count or None,
            'listens_each': round(self.devotion, 2) if self.listeners else None,
            'reach': _round(self.reach) if self.listeners else None,
            'canonicity': _round(canon),
            'artist_listeners': self.artist_listeners or None,
            'artist_rg_listeners': self.artist_rg_listeners or None,
            'artist_top_listeners': self.artist_top_listeners or None,
            'fans': self.fans or None,
            'lastfm_listeners': self.lastfm_listeners or None,
            'lastfm_playcount': self.lastfm_playcount or None,
            'acclaim': _round(self.acclaim),
            'critic_scores': _join_scores(self.critic_scores),
            'mb_rating': _round(self.mb_rating),
            'mb_rating_votes': self.mb_rating_votes or None,
            'discogs_rating': _round(self.discogs_rating),
            'discogs_votes': self.discogs_votes or None,
            'have': self.have or None,
            'want': self.want or None,
            'want_ratio': _round(want_ratio),
            # shape
            'tracks': self.track_count or None,
            'runtime_min': round(self.runtime_seconds / 60.0, 1) if self.runtime_seconds else None,
            'mean_track_seconds': _round(self.mean_track_seconds) if self.mean_track_seconds else None,
            'track_length_spread': _round(self.track_length_spread) if self.mean_track_seconds else None,
            'bpm_mean': _round(self.bpm_mean),
            'bpm_spread': _round(self.bpm_spread),
            'gain_mean': _round(self.gain_mean),
            'gain_spread': _round(self.gain_spread),
            'tracks_with_bpm': self.tracks_with_bpm or None,
            'explicit': self.explicit,
            # sound
            'definition': _round(self.definition),
            'tags': _join(self.top_tags),
            'genre_tags': _join(_by_weight(self.genre_profile)),
            'mood_tags': _join(_by_weight(self.mood_profile)),
            'lineage_tags': _join(_by_weight(self.artist_profile)),
            'root_genres': _join(self.root_genres),
            'subgenres': _join(sorted(self.subgenres)),
            'mb_genres': _join(self.mb_genres),
            'styles': _join(self.styles),
            'deezer_genres': _join(self.deezer_genres),
            # connection
            'personnel_count': len(self.personnel),
            'personnel': _join_names(self.personnel),
            'personnel_relations': _join_pairs(
                {self.personnel.get(mbid, mbid): rel for mbid, rel in self.personnel_relations.items()}),
            'producers': _join_names(self.producers),
            'engineers': _join_names(self.engineers),
            'performers': _join_names(self.performers),
            'studios': _join_names(self.studios),
            'label': self.label or None,
            'labels': _join_names(self.labels),
            'neighbours_count': len(self.artist_neighbours),
            'neighbours': _join(sorted(self.artist_neighbours)),
            # catalogue
            'canonical_release_mbid': self.canonical_release_mbid,
            'editions': self.editions or None,
            'release_countries': _join(sorted(self.release_countries)),
            'first_release_date': self.first_release_date,
            'release_date': self.release_date,
            'release_country': self.release_country,
            'barcode': self.barcode,
            'formats': _join(self.formats),
            'catalog_numbers': _join(self.catalog_numbers),
            'track_titles': _join(self.track_titles),
            'recording_mbids': _join(self.recording_mbids),
            'credits_count': len(self.credits),
            'credits': _join(f'{c.get("role", "")}: {c.get("name", "")}' for c in self.credits),
            'wikidata_id': self.wikidata_id,
            'discogs_master_id': self.discogs_master_id,
            'spotify_id': self.spotify_id,
            'deezer_id': self.deezer_id,
            'deezer_label': self.deezer_label,
            'deezer_release_date': self.deezer_release_date,
            'deezer_url': self.deezer_url,
            'discogs_url': self.discogs_url,
            'num_for_sale': self.num_for_sale or None,
            'lowest_price': _round(self.lowest_price),
            'links': _join_pairs(self.links),
            # bookkeeping
            'enriched': _join(sorted(self.enriched)),
            'seed_mbids': _join(self.seed_mbids),
            'seed_artist_mbids': _join(self.seed_artist_mbids),
        }


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def _as_int(value):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _as_float(value):
    if value is None or value == '':
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _round(value, places=3):
    return None if value is None else round(float(value), places)


def _join(items):
    return ', '.join(str(item) for item in items if item not in (None, ''))


def _join_names(mapping):
    return ', '.join(sorted(str(name) for name in (mapping or {}).values() if name))


def _join_pairs(mapping):
    return ', '.join(f'{key}: {value}' for key, value in sorted((mapping or {}).items()))


def _join_scores(mapping):
    return ', '.join(f'{key}={round(float(value), 2)}' for key, value in sorted((mapping or {}).items())
                     if value is not None)


def _by_weight(profile):
    return sorted(profile, key=profile.get, reverse=True)


def _merge_dict(target, extra):
    """Add what is missing; an earlier stage's name for a key is kept."""
    for key, value in (extra or {}).items():
        if key and key not in target:
            target[key] = value
    return target


def _extend_unique(target, extra):
    seen = set(target)
    for item in extra or []:
        if item and item not in seen:
            target.append(item)
            seen.add(item)
    return target


def _links_from(rels):
    """ListenBrainz hands relation links as {type: url}; MusicBrainz-shaped
    parsers hand [{type, url}]. Either becomes {type: url}."""
    if isinstance(rels, dict):
        return {str(k): v for k, v in rels.items() if k and v}
    links = {}
    for entry in rels or []:
        if isinstance(entry, dict) and entry.get('type') and entry.get('url'):
            links.setdefault(str(entry['type']), entry['url'])
    return links


def tag_entries(raw):
    """ListenBrainz tag dicts -> the {name, count, genre} shape tag_profile wants.

    MusicBrainz tag counts are small integers — a handful of votes — rather
    than Last.fm's 0-100 scale, so they get rescaled against the strongest tag
    on the record. Prominence ordering is what actually matters here, since
    the broad genre almost always outvotes its own subgenre, and that ordering
    survives rescaling untouched. `genre` is True when ListenBrainz attached
    a genre_mbid, i.e. the tag is on MusicBrainz's genre whitelist.
    """
    entries = [t for t in (raw or []) if isinstance(t, dict) and t.get('tag')]
    if not entries:
        return []
    peak = max(max(_as_int(t.get('count')), 1) for t in entries)
    return [
        {
            'name': t['tag'],
            'count': 100.0 * max(_as_int(t.get('count')), 1) / peak,
            'genre': bool(t.get('genre_mbid')),
        }
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


def _genre_names(genre_names):
    return tagmod.taxonomy_genre_names() if genre_names is None else genre_names


def _split_with_flags(profile, entries, genre_names, known_genres=(), known_moods=()):
    """Split a profile into (genres, moods).

    Precedence: a tag ListenBrainz flagged with a genre_mbid is a genre; a
    tag an earlier split already classified keeps its class; anything else
    is a genre iff its name is in `genre_names`, otherwise a mood.
    """
    genre_names = _genre_names(genre_names)
    flagged = {tagmod.normalize_tag(e['name']) for e in entries or [] if e.get('genre')}
    genres, moods = {}, {}
    for tag, weight in profile.items():
        if tag in flagged or tag in known_genres:
            genres[tag] = weight
        elif tag in known_moods:
            moods[tag] = weight
        elif tagmod.normalize_tag(tag) in genre_names:
            genres[tag] = weight
        else:
            moods[tag] = weight
    return genres, moods


# ---------------------------------------------------------------------------
# Stage S3: the bulk fill from ListenBrainz
# ---------------------------------------------------------------------------

def from_metadata(mbid, metadata, popularity=None, genre_names=None):
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

    entries = tag_entries(tag_block.get('release_group'))
    artist_entries = tag_entries(tag_block.get('artist'))
    profile = tagmod.tag_profile(entries)
    artist_profile = tagmod.tag_profile(artist_entries, max_tags=12)
    if not profile:
        # An untagged record can still be placed using its artist's tags, but
        # that is weaker evidence, so it comes in at reduced weight.
        profile = {tag: weight * 0.6 for tag, weight in artist_profile.items()}
        entries = artist_entries
    if not profile:
        return None
    genres, moods = _split_with_flags(profile, entries, genre_names)

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
        genres=genres,
        moods=moods,
        year=_year_from(release_block),
        image_url=_cover_art(release_block),
        release_type=release_block.get('type') or '',
        artist_area=primary_artist.get('area') or '',
        artist_type=primary_artist.get('type') or '',
        artist_debut_year=primary_artist.get('begin_year') or None,
        artist_end_year=primary_artist.get('end_year') or None,
        artist_gender=primary_artist.get('gender') or '',
        artist_links=_links_from(primary_artist.get('rels')),
        links=_links_from(release_block.get('rels')),
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


def enrich_tags(features, lastfm, artist_cache=None, genre_names=None):
    """Thicken an album's tag vectors with Last.fm's crowd tags.

    A no-op when no key is configured, so this is safe to call
    unconditionally. Returns True if anything was actually added. The
    genre/mood split is redone afterwards: tags ListenBrainz already
    classified keep their class, and the new Last.fm tags are classified
    against `genre_names`.
    """
    if lastfm is None or not getattr(lastfm, 'configured', False):
        return False
    if not features.artist or not features.title:
        return False

    before = len(features.profile)
    known_genres = set(features.genres)
    known_moods = set(features.moods)
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
    features.genres, features.moods = _split_with_flags(
        features.profile, (), genre_names, known_genres, known_moods
    )
    return len(features.profile) > before


# ---------------------------------------------------------------------------
# Stages S4/S5: one parsed payload at a time
# ---------------------------------------------------------------------------

def apply_release_group(features, facts):
    """Editions, countries, MB genres and rating, external ids - from
    credits.release_group_facts."""
    if not facts:
        return features
    if features.year is None and facts.get('year'):
        features.year = _as_int(facts['year']) or None
    if not features.release_type and facts.get('primary_type'):
        features.release_type = facts['primary_type']
    if facts.get('secondary_types'):
        features.secondary_types = tuple(facts['secondary_types'])
    if facts.get('first_release_date'):
        features.first_release_date = str(facts['first_release_date'])
    if facts.get('editions'):
        features.editions = _as_int(facts['editions'])
    if facts.get('release_countries'):
        features.release_countries = features.release_countries | frozenset(
            c for c in facts['release_countries'] if c)
    if facts.get('mb_genres'):
        features.mb_genres = _extend_unique(list(features.mb_genres), facts['mb_genres'])
    if facts.get('mb_rating') is not None:
        features.mb_rating = _as_float(facts['mb_rating'])
        features.mb_rating_votes = _as_int(facts.get('mb_rating_votes'))
    if facts.get('wikidata_id') and not features.wikidata_id:
        features.wikidata_id = str(facts['wikidata_id'])
    if facts.get('discogs_master_id') and not features.discogs_master_id:
        features.discogs_master_id = str(facts['discogs_master_id'])
    _merge_dict(features.links, facts.get('links'))
    features.enriched.add('rg')
    return features


def apply_release(features, shape, circle):
    """The canonical edition's tracklist and its production circle - from
    credits.release_shape and credits.release_circle."""
    shape = shape or {}
    circle = circle or {}
    if not shape and not circle:
        return features
    if shape.get('release_mbid'):
        features.canonical_release_mbid = str(shape['release_mbid'])
    if shape.get('date'):
        features.release_date = str(shape['date'])
    if shape.get('country'):
        features.release_country = str(shape['country'])
    if shape.get('barcode'):
        features.barcode = str(shape['barcode'])
    if shape.get('formats'):
        features.formats = _extend_unique(list(features.formats), shape['formats'])
    if shape.get('titles'):
        features.track_titles = list(shape['titles'])
    if shape.get('recording_mbids'):
        features.recording_mbids = _extend_unique(list(features.recording_mbids), shape['recording_mbids'])
    # Shape numbers are only trusted from a release that actually has tracks;
    # an empty payload must not zero out what an earlier stage knew.
    if _as_int(shape.get('track_count')) > 0:
        features.track_count = _as_int(shape['track_count'])
        if shape.get('runtime_seconds'):
            features.runtime_seconds = _as_int(shape['runtime_seconds'])
            features.mean_track_seconds = float(shape.get('mean_track_seconds') or 0.0)
            features.track_length_spread = float(shape.get('track_length_spread') or 0.0)

    _merge_dict(features.labels, circle.get('labels'))
    _extend_unique(features.catalog_numbers, circle.get('catalog_numbers'))
    _merge_dict(features.producers, circle.get('producers'))
    _merge_dict(features.engineers, circle.get('engineers'))
    _merge_dict(features.performers, circle.get('performers'))
    _merge_dict(features.studios, circle.get('studios'))
    for credit in circle.get('credits') or []:
        if isinstance(credit, dict) and credit not in features.credits:
            features.credits.append(dict(credit))
    features.enriched.add('release')
    return features


def apply_artist(features, personnel):
    """The people graph around the artist - from credits.artist_personnel."""
    if not personnel:
        return features
    artist_mbid = personnel.get('mbid') or features.artist_mbid
    artist_name = personnel.get('name') or features.artist
    if artist_mbid:
        features.personnel.setdefault(artist_mbid, artist_name)
        features.personnel_relations.setdefault(artist_mbid, 'artist')
        if not features.artist_mbid:
            features.artist_mbid = artist_mbid
    for mbid, person in (personnel.get('people') or {}).items():
        if not mbid or not isinstance(person, dict):
            continue
        features.personnel.setdefault(mbid, person.get('name') or mbid)
        features.personnel_relations.setdefault(mbid, person.get('relation') or '')
    if not features.artist_area and personnel.get('area'):
        features.artist_area = personnel['area']
    if not features.artist_type and personnel.get('type'):
        features.artist_type = personnel['type']
    if not features.artist_gender and personnel.get('gender'):
        features.artist_gender = personnel['gender']
    if not features.artist_debut_year and personnel.get('begin_year'):
        features.artist_debut_year = _as_int(personnel['begin_year']) or None
    if not features.artist_end_year and personnel.get('end_year'):
        features.artist_end_year = _as_int(personnel['end_year']) or None
    _merge_dict(features.artist_links, personnel.get('links'))
    features.enriched.add('artist')
    return features


def apply_deezer(features, facts):
    """Fans, explicitness and the per-track BPM / loudness statistics - from
    credits.deezer_facts."""
    if not facts:
        return features
    if facts.get('deezer_id'):
        features.deezer_id = _as_int(facts['deezer_id']) or None
    if facts.get('fans'):
        features.fans = _as_int(facts['fans'])
    if facts.get('explicit') is not None:
        features.explicit = bool(facts['explicit'])
    if facts.get('label'):
        features.deezer_label = str(facts['label'])
    if facts.get('release_date'):
        features.deezer_release_date = str(facts['release_date'])
    if facts.get('genres'):
        features.deezer_genres = _extend_unique(list(features.deezer_genres), facts['genres'])
    if facts.get('url'):
        features.deezer_url = str(facts['url'])
        features.links.setdefault('deezer', features.deezer_url)
    for name in ('bpm_mean', 'bpm_spread', 'gain_mean', 'gain_spread'):
        value = _as_float(facts.get(name))
        if value is not None:
            setattr(features, name, value)
    if facts.get('tracks_with_bpm'):
        features.tracks_with_bpm = _as_int(facts['tracks_with_bpm'])
    features.enriched.add('deezer')
    return features


def apply_wikidata(features, facts, labels=None):
    """Critic scores, external ids and the Wikidata-side producer and label
    credits - from credits.wikidata_facts, with Q-ids resolved through
    `labels` ({qid: name})."""
    if not facts:
        return features
    labels = labels or {}
    for qid, score in (facts.get('critic_scores') or {}).items():
        if score is None:
            continue
        features.critic_scores.setdefault(labels.get(qid, qid), float(score))
    if facts.get('acclaim') is not None:
        features.acclaim = _as_float(facts['acclaim'])
    if facts.get('spotify_id'):
        features.spotify_id = str(facts['spotify_id'])
        features.links.setdefault('spotify', f'https://open.spotify.com/album/{features.spotify_id}')
    if facts.get('discogs_master_id') and not features.discogs_master_id:
        features.discogs_master_id = str(facts['discogs_master_id'])
    if facts.get('allmusic_id'):
        features.links.setdefault('allmusic', f'https://www.allmusic.com/album/{facts["allmusic_id"]}')
    if facts.get('aoty_id'):
        features.links.setdefault('aoty', f'https://www.albumoftheyear.org/album/{facts["aoty_id"]}.php')
    if facts.get('lastfm_id'):
        features.links.setdefault('lastfm', f'https://www.last.fm/music/{facts["lastfm_id"]}')
    if facts.get('enwiki_title'):
        features.links.setdefault(
            'wikipedia', 'https://en.wikipedia.org/wiki/' + quote(str(facts['enwiki_title']).replace(' ', '_')))
    if features.wikidata_id:
        features.links.setdefault('wikidata', f'https://www.wikidata.org/wiki/{features.wikidata_id}')
    if facts.get('publication_date'):
        if not features.first_release_date:
            features.first_release_date = str(facts['publication_date'])
        if features.year is None:
            features.year = _year_from({'date': facts['publication_date']})
    # A producer Wikidata knows about counts for the circle axis even when
    # MusicBrainz has no credit for it, so it lands in the same dict under
    # the same name key.
    for qid in facts.get('producer_qids') or []:
        name = labels.get(qid)
        if name:
            features.producers.setdefault(_person_key(name), name)
    for qid in facts.get('label_qids') or []:
        name = labels.get(qid)
        if name:
            features.labels.setdefault(_person_key(name), name)
    features.enriched.add('wikidata')
    return features


def apply_discogs(features, facts):
    """Styles, community want/have and rating, plus Discogs' own producer and
    engineer credits - from credits.discogs_facts."""
    if not facts:
        return features
    if facts.get('styles'):
        features.styles = _extend_unique(list(features.styles), facts['styles'])
    if facts.get('have'):
        features.have = _as_int(facts['have'])
    if facts.get('want'):
        features.want = _as_int(facts['want'])
    if facts.get('rating') is not None:
        features.discogs_rating = _as_float(facts['rating'])
        features.discogs_votes = _as_int(facts.get('rating_votes'))
    if facts.get('num_for_sale'):
        features.num_for_sale = _as_int(facts['num_for_sale'])
    if facts.get('lowest_price') is not None:
        features.lowest_price = _as_float(facts['lowest_price'])
    if facts.get('url'):
        features.discogs_url = str(facts['url'])
        features.links.setdefault('discogs', features.discogs_url)
    if facts.get('label'):
        features.labels.setdefault(_person_key(facts['label']), facts['label'])
    if facts.get('country') and not features.release_country:
        features.release_country = str(facts['country'])
    if facts.get('year') and features.year is None:
        features.year = _as_int(facts['year']) or None
    if facts.get('formats') and not features.formats:
        features.formats = _extend_unique([], facts['formats'])
    _merge_dict(features.producers, facts.get('producers'))
    _merge_dict(features.engineers, facts.get('engineers'))
    features.enriched.add('discogs')
    return features


def apply_lastfm_info(features, facts):
    """Scrobble counts - from credits.lastfm_facts."""
    if not facts:
        return features
    if facts.get('lastfm_listeners'):
        features.lastfm_listeners = _as_int(facts['lastfm_listeners'])
    if facts.get('lastfm_playcount'):
        features.lastfm_playcount = _as_int(facts['lastfm_playcount'])
    if facts.get('lastfm_url'):
        features.links.setdefault('lastfm', str(facts['lastfm_url']))
    features.enriched.add('lastfm_info')
    return features


def apply_artist_release_groups(features, top_release_groups):
    """What the artist's catalogue says about this record: the canonicity
    denominators (listeners summed over every release group, and the biggest
    single one) and the year the artist first released anything, which is
    what career stage is measured from."""
    total, top = 0, 0
    first_year = None
    for entry in top_release_groups or []:
        if not isinstance(entry, dict):
            continue
        count = _as_int(entry.get('total_user_count'))
        total += count
        top = max(top, count)
        year = _year_from(entry.get('release_group') or {})
        if year and (first_year is None or year < first_year):
            first_year = year
    features.artist_rg_listeners = total
    features.artist_top_listeners = max(top, features.listeners if total else 0)
    if first_year:
        # This record cannot predate its own artist's first release; when the
        # catalogue is thin enough to say otherwise, the record itself is the
        # earliest thing we know about.
        features.artist_first_release_year = min(first_year, features.year or first_year)
    features.enriched.add('canonicity')
    return features


# ---------------------------------------------------------------------------
# Multi-seed blend
# ---------------------------------------------------------------------------

# Mean over the seeds that have a value; None and 0 both mean "unknown".
_MEAN_INT_FIELDS = (
    'listeners', 'listen_count', 'artist_listeners', 'artist_rg_listeners', 'artist_top_listeners',
    'year', 'artist_debut_year', 'artist_end_year', 'artist_first_release_year', 'track_count',
    'runtime_seconds', 'editions', 'fans', 'lastfm_listeners',
    'lastfm_playcount', 'have', 'want', 'mb_rating_votes', 'discogs_votes',
    'tracks_with_bpm', 'num_for_sale',
)
_MEAN_FLOAT_FIELDS = (
    'mean_track_seconds', 'track_length_spread', 'bpm_mean', 'bpm_spread',
    'gain_mean', 'gain_spread', 'acclaim', 'mb_rating', 'discogs_rating',
    'lowest_price',
)
# {key: value} dicts: union, first seed's value wins for a shared key.
_UNION_DICT_FIELDS = (
    'personnel', 'personnel_relations', 'producers', 'engineers',
    'performers', 'studios', 'labels', 'links', 'artist_links',
    'critic_scores',
)
_UNION_SET_FIELDS = ('artist_neighbours', 'artist_neighbour_mbids', 'release_countries')
_UNION_LIST_FIELDS = (
    'recording_mbids', 'track_titles', 'mb_genres', 'styles',
    'deezer_genres', 'formats', 'catalog_numbers',
)
# Text facts that only make sense when every seed agrees.
_AGREE_FIELDS = ('artist_area', 'artist_type', 'artist_gender', 'release_type', 'release_country')


def _mean_profile(profiles):
    """Element-wise mean over the seeds, renormalised so the strongest tag
    sits at 1.0 - a tag only one seed carries is still there, just weaker."""
    if not profiles:
        return {}
    total = {}
    for profile in profiles:
        for tag, weight in (profile or {}).items():
            total[tag] = total.get(tag, 0.0) + float(weight)
    count = len(profiles)
    mean = {tag: weight / count for tag, weight in total.items()}
    peak = max(mean.values(), default=0.0)
    if peak <= 0:
        return {}
    return {tag: weight / peak for tag, weight in mean.items()}


def _mean_of(values):
    present = [float(v) for v in values if v is not None and v != 0]
    return (sum(present) / len(present)) if present else None


def blend(features_list):
    """A centroid AlbumFeatures for several seeds.

    Tag profiles are averaged and renormalised, numbers are averaged over
    the seeds that have them, sets and dicts are unioned, and every seed's
    artist mbid is remembered so all of them can be excluded from results.
    """
    seeds = [f for f in (features_list or []) if f is not None]
    if not seeds:
        return None
    blended = AlbumFeatures(
        artist=' + '.join(dict.fromkeys(f.artist for f in seeds if f.artist)),
        title=' + '.join(f.title for f in seeds if f.title),
        mbid='',
        artist_mbid='',
        profile=_mean_profile([f.profile for f in seeds]),
        artist_profile=_mean_profile([f.artist_profile for f in seeds]),
        genres=_mean_profile([f.genre_profile for f in seeds]),
        moods=_mean_profile([f.mood_profile for f in seeds]),
        seed_mbids=tuple(f.mbid for f in seeds),
        seed_artist_mbids=tuple(dict.fromkeys(f.artist_mbid for f in seeds if f.artist_mbid)),
    )
    for name in _MEAN_INT_FIELDS:
        mean = _mean_of(getattr(f, name) for f in seeds)
        if mean is not None:
            setattr(blended, name, int(round(mean)))
    for name in _MEAN_FLOAT_FIELDS:
        mean = _mean_of(getattr(f, name) for f in seeds)
        if mean is not None:
            setattr(blended, name, mean)
    for name in _UNION_DICT_FIELDS:
        merged = {}
        for f in seeds:
            _merge_dict(merged, getattr(f, name))
        setattr(blended, name, merged)
    for name in _UNION_SET_FIELDS:
        setattr(blended, name, frozenset().union(*(frozenset(getattr(f, name)) for f in seeds)))
    for name in _UNION_LIST_FIELDS:
        merged = []
        for f in seeds:
            _extend_unique(merged, getattr(f, name))
        setattr(blended, name, merged)
    for name in _AGREE_FIELDS:
        values = {getattr(f, name) for f in seeds}
        setattr(blended, name, values.pop() if len(values) == 1 else '')
    blended.secondary_types = tuple(dict.fromkeys(t for f in seeds for t in f.secondary_types))
    blended.artist_neighbours_ranked = tuple(
        dict.fromkeys(name for f in seeds for name in f.artist_neighbours_ranked))
    blended.credits = [c for f in seeds for c in f.credits]
    blended.enriched = set().union(*(f.enriched for f in seeds))
    explicit = {f.explicit for f in seeds if f.explicit is not None}
    blended.explicit = explicit.pop() if len(explicit) == 1 else None
    return blended


FIELD_NAMES = tuple(f.name for f in fields(AlbumFeatures))
