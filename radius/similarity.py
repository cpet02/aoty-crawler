"""Fingerprint distance: how far one album sits from the seed, and why.

Nineteen axes in five groups (docs/DESIGN.md "Axes"), each normalised to
roughly 0..1 and combined as a weighted mean over whatever could be measured
for BOTH albums. An axis with no data on either side is dropped from the
mean rather than scored: the difference between "we don't know" and
"different".

Two kinds of axis, because there are two kinds of evidence:

* Symmetric axes measure a distance whenever both sides have the data: tag
  vectors, audience size, year, runtime, BPM, country. Not matching is
  informative in itself - a 1971 record is genuinely far from a 2019 one.
* Evidence axes (personnel, circle, co_listening) fire only on overlap. Not
  sharing a producer says nothing, since most pairs of records share nobody,
  but sharing one is strong evidence of closeness. So an evidence axis
  enters the mean at distance 0 with weight w * strength when there is
  overlap and is absent otherwise, which pulls a connected record closer
  without pushing every unconnected one away.

`coverage` is the share of the requested weight that was actually measured,
counting evidence axes at full weight, so a low coverage reads as "thin data
or no connections", never as "far away".

`explain` turns a match into the reasons a listener would give ("David Pajo
is in both", "both produced by Steve Albini", "12 similar artists in
common"), strongest first.
"""

import math
from dataclasses import asdict, dataclass, field, fields

from . import tags as tagmod
from .albums import jaccard

# The delta on each axis that counts as "completely different": two orders
# of magnitude of audience, 4x the replay rate, a quarter century, an hour of
# runtime, and so on. These set what a distance actually means.
REACH_SPAN = 2.0                    # log10 listeners / fans
DEVOTION_SPAN = 2.0                 # log2 listens per listener
CANONICITY_SPAN = 2.0               # log2 share of the artist's audience
ACCLAIM_SPAN = 0.5                  # of the 0..1 critic scale
ERA_SPAN = 25.0                     # years
RUNTIME_SPAN_SECONDS = 3600.0
TRACK_COUNT_SPAN = 14.0
TRACK_LENGTH_SPAN_SECONDS = 240.0
SPREAD_SPAN = 0.8                   # coefficient of variation of track length
BPM_SPAN = 60.0
GAIN_SPAN_DB = 12.0
CAREER_SPAN = 15.0                  # years into the career
# Similar-artist sets are 100 names wide, so even a strong match rarely
# exceeds ~0.3 Jaccard; scale so real overlap registers as closeness.
KINSHIP_JACCARD_SPAN = 0.3

# Evidence strength: two shared people, or three co-listened tracks, is as
# connected as the axis gets.
PERSONNEL_FULL_STRENGTH = 2.0
CO_LISTENING_FULL_STRENGTH = 3.0
CO_LISTENING_ARTIST_WEIGHT = 0.4
CIRCLE_PERSON_WEIGHT = 1.0
CIRCLE_STUDIO_WEIGHT = 0.7
CIRCLE_LABEL_WEIGHT = 0.5

EVIDENCE_AXES = ('personnel', 'circle', 'co_listening')


@dataclass
class SimilarityWeights:
    """Relative pull of each axis. Zero switches an axis off entirely.

    The defaults lead with what the album sounds like and who made it, keep
    reception as a real but secondary pull, and treat shape and provenance
    as tiebreakers. `acclaim` ships off: Wikidata review scores are sparse
    and most records have none, so it is shown as a statistic and ranked on
    only by choice.
    """

    genre: float = 1.0
    mood: float = 0.8
    definition: float = 0.1
    personnel: float = 0.9
    circle: float = 0.6
    co_listening: float = 0.5
    kinship: float = 0.7
    lineage: float = 0.45
    convergence: float = 0.3
    reach: float = 0.3
    devotion: float = 0.3
    canonicity: float = 0.15
    acclaim: float = 0.0
    era: float = 0.2
    scale: float = 0.15
    pacing: float = 0.15
    energy: float = 0.2
    origin: float = 0.15
    career: float = 0.15

    def as_dict(self):
        return asdict(self)

    def active(self):
        return {name: w for name, w in self.as_dict().items() if w > 0}

    @classmethod
    def axis_names(cls):
        return [f.name for f in fields(cls)]

    @classmethod
    def only(cls, *axes, **weights):
        """A weight set with everything off except the named axes."""
        zeroed = {name: 0.0 for name in cls.axis_names()}
        zeroed.update({axis: 1.0 for axis in axes})
        zeroed.update(weights)
        return cls(**zeroed)


AXIS_LABELS = {
    'genre': 'genre',
    'mood': 'mood & texture',
    'definition': 'how easy to place',
    'personnel': 'people in common',
    'circle': 'production circle',
    'co_listening': 'co-listening',
    'kinship': 'listener kinship',
    'lineage': 'artist lineage',
    'convergence': 'candidate convergence',
    'reach': 'audience size',
    'devotion': 'listener devotion',
    'canonicity': 'standing in discography',
    'acclaim': 'critical acclaim',
    'era': 'era',
    'scale': 'runtime & length',
    'pacing': 'track pacing',
    'energy': 'tempo & loudness',
    'origin': 'where it comes from',
    'career': 'career stage',
}

AXIS_GROUPS = {
    'Sound': ['genre', 'mood', 'definition'],
    'Connection': ['personnel', 'circle', 'co_listening', 'kinship', 'lineage', 'convergence'],
    'Reception': ['reach', 'devotion', 'canonicity', 'acclaim'],
    'Shape': ['era', 'scale', 'pacing', 'energy'],
    'Provenance': ['origin', 'career'],
}

# One plain line per axis: what a match on it means.
AXIS_HELP = {
    'genre': 'Shares its genres.',
    'mood': 'Has the same mood and texture.',
    'definition': 'Just as easy, or as hard, to pin to one genre.',
    'personnel': 'The same musicians play on it.',
    'circle': 'Same producers, engineers, studios or label.',
    'co_listening': 'People play it alongside the seed.',
    'kinship': "Its artist's similar artists are the seed's too.",
    'lineage': 'Its artist comes from the same scene.',
    'convergence': 'Several different routes led to it.',
    'reach': 'About as many listeners.',
    'devotion': 'Its listeners replay it about as often.',
    'canonicity': "Same standing in its artist's catalogue: classic or deep cut.",
    'acclaim': 'Similar critic scores. Off by default: few albums have any.',
    'era': 'Released around the same time.',
    'scale': 'About the same length.',
    'pacing': 'Tracks of a similar length.',
    'energy': 'Similar tempo and loudness.',
    'origin': 'Artist from the same country.',
    'career': "Made at the same point in the artist's career.",
}

# One-click starting points for the weights: name -> (what it favours,
# weights). Each is a clean slate - an axis it does not name is off - so a
# preset gives the same result whatever the sliders said before.
PRESETS = {
    'Sound': ('Only how it sounds.',
              {'genre': 1.2, 'mood': 1.2, 'definition': 0.2, 'energy': 0.4, 'lineage': 0.3}),
    'People': ('Who made it: musicians, producers, studios, labels.',
               {'personnel': 1.5, 'circle': 1.2, 'lineage': 0.4, 'genre': 0.4, 'mood': 0.2}),
    'Listeners': ('What the same listeners play.',
                  {'co_listening': 1.5, 'kinship': 1.2, 'convergence': 0.6, 'genre': 0.4, 'mood': 0.2}),
    'Era & place': ('Same time, same place, same scene.',
                    {'era': 1.2, 'origin': 1.0, 'lineage': 0.6, 'career': 0.4, 'genre': 0.5}),
    'Stature': ('Same size of audience and standing.',
                {'reach': 1.2, 'devotion': 0.8, 'canonicity': 0.8, 'acclaim': 0.4, 'genre': 0.4}),
}


@dataclass
class Evidence:
    """What the candidate stage learned about one album that the features
    themselves don't carry: how many independent sources coughed it up, and
    how often the seed's recordings are played alongside its tracks (or its
    artist's)."""

    convergence: float = None       # prefilter_score / max prefilter in pool
    album_hits: float = 0.0         # co-listening hits on this album
    artist_hits: float = 0.0        # co-listening hits by this artist
    neighbour_idf: dict = None      # similar-artist name -> rarity across the pool
    known_personnel: float = 0.0    # personnel strength known before the deep lookups: a candidate
                                    # found through the seed's own people graph shares one by construction


# ---------------------------------------------------------------------------
# Distance helpers
# ---------------------------------------------------------------------------

def _clamp01(value):
    return 0.0 if value < 0 else (1.0 if value > 1 else value)


def _vector_distance(vector_a, vector_b):
    """None when either side is empty - unknown, not dissimilar."""
    if not vector_a or not vector_b:
        return None
    return 1.0 - _clamp01(tagmod.cosine(vector_a, vector_b))


def _log_distance(value_a, value_b, span, log=math.log10):
    """Distance in log space, for quantities where a multiple is the unit
    of change rather than a sum. Needs a positive value on both sides."""
    if not value_a or not value_b or value_a <= 0 or value_b <= 0:
        return None
    return _clamp01(abs(log(value_a) - log(value_b)) / span)


def _linear_distance(value_a, value_b, span):
    if value_a is None or value_b is None:
        return None
    return _clamp01(abs(value_a - value_b) / span)


def _mean(values):
    present = [v for v in values if v is not None]
    if not present:
        return None
    return sum(present) / len(present)


def _keys(mapping):
    return set(mapping or ())


def _weighted_jaccard(names_a, names_b, idf):
    """Overlap of two similar-artist sets, each name weighted by how rare it
    is across the pool. ListenBrainz's lists are popularity-biased - the same
    twenty famous acts turn up as "similar" to everything - so without the
    weighting two unrelated records look kin through Aphex Twin and Beck.
    None when either side is empty."""
    names_a, names_b = set(names_a or ()), set(names_b or ())
    if not names_a or not names_b:
        return None
    if not idf:
        return jaccard(names_a, names_b)
    shared = sum(idf.get(name, 1.0) for name in names_a & names_b)
    union = sum(idf.get(name, 1.0) for name in names_a | names_b)
    return shared / union if union else None


def _shared_neighbour_names(seed, other, idf, limit=8):
    """Shared similar artists for display: rarest first, original casing."""
    shared = set(seed.artist_neighbours) & set(other.artist_neighbours)
    if not shared:
        return []
    display = {}
    for name in tuple(seed.artist_neighbours_ranked or ()) + tuple(other.artist_neighbours_ranked or ()):
        display.setdefault(name.strip().lower(), name)
    ordered = sorted(shared, key=lambda name: (-(idf or {}).get(name, 1.0), name))
    return [display.get(name, name) for name in ordered[:limit]]


# ---------------------------------------------------------------------------
# Axes
# ---------------------------------------------------------------------------

def _symmetric_distances(seed, other, seed_vectors, other_vectors, evidence):
    distances = {}

    for axis in ('genre', 'mood', 'lineage'):
        distances[axis] = _vector_distance(seed_vectors.get(axis), other_vectors.get(axis))

    if seed.profile and other.profile:
        distances['definition'] = _clamp01(abs(seed.definition - other.definition))

    overlap = _weighted_jaccard(seed.artist_neighbours, other.artist_neighbours,
                                evidence.neighbour_idf if evidence is not None else None)
    if overlap is not None:
        distances['kinship'] = _clamp01(1.0 - min(overlap / KINSHIP_JACCARD_SPAN, 1.0))

    if evidence is not None and evidence.convergence is not None:
        distances['convergence'] = _clamp01(1.0 - evidence.convergence)

    # Three readings of audience size, each only where both sides have it.
    distances['reach'] = _mean([
        _log_distance(seed.listeners, other.listeners, REACH_SPAN),
        _log_distance(seed.fans, other.fans, REACH_SPAN),
        _log_distance(seed.lastfm_listeners, other.lastfm_listeners, REACH_SPAN),
    ])
    distances['devotion'] = _log_distance(seed.devotion, other.devotion, DEVOTION_SPAN, math.log2)
    distances['canonicity'] = _log_distance(seed.canonicity, other.canonicity, CANONICITY_SPAN, math.log2)
    distances['acclaim'] = _linear_distance(seed.acclaim, other.acclaim, ACCLAIM_SPAN)

    distances['era'] = _linear_distance(seed.year, other.year, ERA_SPAN)

    if seed.has_tracklist and other.has_tracklist:
        # Runtime and track count are two readings of the same thing, so they
        # average into one axis rather than double-counting size.
        distances['scale'] = _mean([
            _linear_distance(seed.runtime_seconds, other.runtime_seconds, RUNTIME_SPAN_SECONDS),
            _linear_distance(seed.track_count, other.track_count, TRACK_COUNT_SPAN),
        ])
        if seed.mean_track_seconds and other.mean_track_seconds:
            distances['pacing'] = _mean([
                _linear_distance(seed.mean_track_seconds, other.mean_track_seconds,
                                 TRACK_LENGTH_SPAN_SECONDS),
                _linear_distance(seed.track_length_spread, other.track_length_spread, SPREAD_SPAN),
            ])

    # A bpm of 0 is Deezer's "not analysed"; a gain of 0 dB is a real value.
    distances['energy'] = _mean([
        _linear_distance(seed.bpm_mean or None, other.bpm_mean or None, BPM_SPAN),
        _linear_distance(seed.gain_mean, other.gain_mean, GAIN_SPAN_DB),
    ])

    if seed.artist_area and other.artist_area:
        # Same country is the signal worth having; scene geography is coarse
        # and anything finer would be false precision. Being the same kind of
        # act - band or solo - rides along on the same axis at a third of it.
        same_place = seed.artist_area.strip().lower() == other.artist_area.strip().lower()
        distance = 0.0 if same_place else 1.0
        if seed.artist_type and other.artist_type:
            same_kind = seed.artist_type.strip().lower() == other.artist_type.strip().lower()
            distance = (distance * 2 + (0.0 if same_kind else 1.0)) / 3.0
        distances['origin'] = distance

    distances['career'] = _linear_distance(seed.career_stage, other.career_stage, CAREER_SPAN)

    return {axis: d for axis, d in distances.items() if d is not None}


def _shared_personnel_mbids(seed, other):
    return _keys(seed.personnel) & _keys(other.personnel)


def _circle_overlap(seed, other):
    """Shared circle keys by role. A person counts once whether credited as
    producer or engineer on either side; those who are producers on both
    records are reported as producers, the rest as engineers."""
    people = (_keys(seed.producers) | _keys(seed.engineers)) & (_keys(other.producers) | _keys(other.engineers))
    producers = _keys(seed.producers) & _keys(other.producers)
    return {
        'producers': producers,
        'engineers': people - producers,
        'studios': _keys(seed.studios) & _keys(other.studios),
        'labels': _keys(seed.labels) & _keys(other.labels),
    }


def _evidence_strengths(seed, other, evidence):
    strengths = {}
    shared_people = _shared_personnel_mbids(seed, other)
    personnel = len(shared_people) / PERSONNEL_FULL_STRENGTH
    if evidence is not None and evidence.known_personnel:
        personnel = max(personnel, evidence.known_personnel)
    if personnel > 0:
        strengths['personnel'] = min(1.0, personnel)

    circle = _circle_overlap(seed, other)
    score = (
        CIRCLE_PERSON_WEIGHT * (len(circle['producers']) + len(circle['engineers']))
        + CIRCLE_STUDIO_WEIGHT * len(circle['studios'])
        + CIRCLE_LABEL_WEIGHT * len(circle['labels'])
    )
    if score > 0:
        strengths['circle'] = min(1.0, score)

    if evidence is not None:
        hits = (evidence.album_hits or 0.0) + CO_LISTENING_ARTIST_WEIGHT * (evidence.artist_hits or 0.0)
        if hits > 0:
            strengths['co_listening'] = min(1.0, hits / CO_LISTENING_FULL_STRENGTH)
    return strengths


def axis_distances(seed, other, seed_vectors, other_vectors, evidence=None):
    """(distances, strengths) per axis.

    Symmetric axes appear in `distances` when both sides have the data.
    Evidence axes appear in both dicts - distance 0.0, strength in (0, 1] -
    when there is overlap, and in neither when there is none.
    """
    distances = _symmetric_distances(seed, other, seed_vectors or {}, other_vectors or {}, evidence)
    strengths = _evidence_strengths(seed, other, evidence)
    for axis in strengths:
        distances[axis] = 0.0
    return distances, strengths


# ---------------------------------------------------------------------------
# The match
# ---------------------------------------------------------------------------

@dataclass
class Match:
    features: object
    distance: float
    axes: dict
    strengths: dict = field(default_factory=dict)
    shared_tags: list = field(default_factory=list)
    distinct_tags: list = field(default_factory=list)
    shared_neighbours: list = field(default_factory=list)
    shared_personnel: list = field(default_factory=list)
    shared_circle: dict = field(default_factory=dict)      # role -> display names
    co_listening: tuple = (0.0, 0.0)                        # (album hits, artist hits)
    sources: tuple = ()
    coverage: float = 1.0
    reasons: list = field(default_factory=list)

    @property
    def similarity(self):
        return 1.0 - self.distance

    @property
    def connected(self):
        """True when at least one evidence axis fired."""
        return bool(self.strengths)

    def as_row(self):
        row = self.features.as_row()
        circle = self.shared_circle or {}
        album_hits, artist_hits = (tuple(self.co_listening) + (0.0, 0.0))[:2]
        row.update({
            'similarity': round(self.similarity, 3),
            'distance': round(self.distance, 3),
            'coverage': round(self.coverage, 3),
            'axes_measured': len(self.axes),
            'connected': self.connected,
            'reasons': ' | '.join(self.reasons),
            'shared_tags': ', '.join(self.shared_tags),
            'new_tags': ', '.join(self.distinct_tags),
            'shared_similar_artists': ', '.join(self.shared_neighbours),
            'shared_personnel': ', '.join(self.shared_personnel),
            'shared_producers': ', '.join(circle.get('producers', ())),
            'shared_engineers': ', '.join(circle.get('engineers', ())),
            'shared_studios': ', '.join(circle.get('studios', ())),
            'shared_labels': ', '.join(circle.get('labels', ())),
            'co_listening_album_hits': round(float(album_hits), 2),
            'co_listening_artist_hits': round(float(artist_hits), 2),
            'found_via': ', '.join(sorted(self.sources)[:4]),
        })
        for axis, value in self.axes.items():
            row[f'd_{axis}'] = round(value, 3)
        for axis, value in self.strengths.items():
            row[f's_{axis}'] = round(value, 3)
        return row


def _display_name(key, *mappings):
    for mapping in mappings:
        name = (mapping or {}).get(key)
        if name:
            return name
    return key


def _shared_personnel_names(seed, other):
    return sorted(
        _display_name(mbid, seed.personnel, other.personnel)
        for mbid in _shared_personnel_mbids(seed, other)
    )


def _shared_circle_names(seed, other):
    overlap = _circle_overlap(seed, other)
    lookups = {
        'producers': (seed.producers, other.producers),
        'engineers': (seed.engineers, other.engineers, seed.producers, other.producers),
        'studios': (seed.studios, other.studios),
        'labels': (seed.labels, other.labels),
    }
    shared = {}
    for role, keys in overlap.items():
        if keys:
            shared[role] = sorted(_display_name(key, *lookups[role]) for key in keys)
    return shared


def compare(seed, other, seed_vectors, other_vectors, weights,
            evidence=None, lateral_bonus=0.0, sources=()):
    """Fingerprint distance between the seed and one candidate, or None when
    nothing that is switched on could be measured.

    `lateral_bonus` nudges toward records that share the seed's broad genre
    while bringing subgenres it doesn't have - the "same neighbourhood, room
    I haven't been in" case, which is usually what you actually want from a
    recommendation rather than a near-duplicate.
    """
    distances, strengths = axis_distances(seed, other, seed_vectors, other_vectors, evidence)
    active = weights.as_dict()

    numerator = 0.0
    denominator = 0.0
    for axis, distance in distances.items():
        weight = active.get(axis, 0.0)
        if weight <= 0:
            continue
        effective = weight * strengths.get(axis, 1.0)
        numerator += effective * distance
        denominator += effective

    if denominator <= 0:
        return None

    distance = numerator / denominator
    requested = sum(w for w in active.values() if w > 0)
    coverage = min(denominator / requested, 1.0) if requested else 1.0

    if lateral_bonus:
        new_subgenres = other.subgenres - seed.subgenres
        if new_subgenres and set(other.root_genres) & set(seed.root_genres):
            distance = max(0.0, distance - lateral_bonus)

    shared_neighbours = _shared_neighbour_names(
        seed, other, evidence.neighbour_idf if evidence is not None else None)
    shared_personnel = _shared_personnel_names(seed, other)
    shared_circle = _shared_circle_names(seed, other)
    co_listening = (
        (float(evidence.album_hits or 0.0), float(evidence.artist_hits or 0.0))
        if evidence is not None else (0.0, 0.0)
    )
    return Match(
        features=other,
        distance=distance,
        axes=distances,
        strengths=strengths,
        shared_tags=tagmod.shared_tags(seed.profile, other.profile),
        distinct_tags=sorted(
            set(other.profile) - set(seed.profile),
            key=other.profile.get, reverse=True,
        )[:4],
        shared_neighbours=shared_neighbours,
        shared_personnel=shared_personnel,
        shared_circle=shared_circle,
        co_listening=co_listening,
        sources=tuple(sources),
        coverage=coverage,
        reasons=explain(seed, other, distances, strengths, shared_neighbours,
                        shared_personnel, shared_circle, co_listening),
    )


# ---------------------------------------------------------------------------
# Reasons
# ---------------------------------------------------------------------------

MAX_REASONS = 8
# How close a symmetric axis must be before it is worth saying out loud:
# the descriptive axes are noisy enough that 0.35 is already a real match,
# the scalar ones need to be nearly equal to mean anything.
_REASON_THRESHOLDS = {
    'genre': 0.35, 'mood': 0.35, 'lineage': 0.35, 'kinship': 0.35,
    'era': 0.2, 'origin': 0.2, 'career': 0.2, 'reach': 0.2, 'devotion': 0.2,
}
# Tie-break order when two reasons are equally strong.
_REASON_ORDER = (
    'personnel', 'circle', 'co_listening', 'kinship', 'genre', 'mood',
    'lineage', 'era', 'origin', 'career', 'reach', 'devotion',
)


def _names_phrase(names):
    names = [n for n in names if n]
    if not names:
        return ''
    if len(names) == 1:
        return names[0]
    if len(names) <= 3:
        return ', '.join(names[:-1]) + ' and ' + names[-1]
    return ', '.join(names[:3]) + f' and {len(names) - 3} more'


def _personnel_reason(seed, other, names):
    if not names:
        # Known through the seed's people graph, but the candidate's own
        # personnel has not been fetched yet (or names nobody the seed lists).
        return "made by someone from the seed's circle"
    # A shared person who IS the artist on either side (a member's solo
    # record, a side project) connects the two; a member in both bands is
    # simply in both.
    connectors = set()
    for mbid in _shared_personnel_mbids(seed, other):
        relations = ((seed.personnel_relations or {}).get(mbid), (other.personnel_relations or {}).get(mbid))
        if 'artist' in relations:
            connectors.add(_display_name(mbid, seed.personnel, other.personnel))
    single = len(names) == 1
    if all(name in connectors for name in names):
        verb = 'connects them' if single else 'connect them'
    else:
        verb = 'is in both' if single else 'are in both'
    return f'{_names_phrase(names)} {verb}'


def _engineer_reason(seed, other, names):
    if not names:
        return ''
    on_both = all(
        name in (seed.engineers or {}).values() and name in (other.engineers or {}).values()
        for name in names
    )
    if on_both:
        return f'both engineered by {_names_phrase(names)}'
    return f'{_names_phrase(names)} worked on both'


def _prefixed(prefix, names):
    phrase = _names_phrase(names or ())
    return f'{prefix} {phrase}' if phrase else ''


def _co_listening_reason(co_listening):
    album_hits, artist_hits = (tuple(co_listening or ()) + (0.0, 0.0))[:2]
    album = int(round(album_hits or 0.0))
    artist = int(round(artist_hits or 0.0))
    if album >= 1:
        verb = 'is' if album == 1 else 'are'
        return f"{album} of its tracks {verb} played alongside the seed's"
    if artist >= 1:
        verb = 'is' if artist == 1 else 'are'
        return f"{artist} of its artist's tracks {verb} played alongside the seed's"
    return "listeners play its tracks alongside the seed's"


def _kinship_reason(seed, other, shared_neighbours):
    count = len(set(seed.artist_neighbours) & set(other.artist_neighbours))
    if not count:
        return ''
    text = f'{count} similar artist{"" if count == 1 else "s"} in common'
    names = list(shared_neighbours or ())[:3]
    if names:
        text += ': ' + ', '.join(names) + ('...' if count > len(names) else '')
    return text


def _symmetric_reason(axis, seed, other, shared_neighbours):
    if axis == 'kinship':
        return _kinship_reason(seed, other, shared_neighbours)
    if axis == 'genre':
        tags = tagmod.shared_tags(seed.genre_profile, other.genre_profile, limit=3)
        return 'shares ' + ', '.join(tags) if tags else ''
    if axis == 'mood':
        tags = tagmod.shared_tags(seed.mood_profile, other.mood_profile, limit=3)
        return 'same mood: ' + ', '.join(tags) if tags else ''
    if axis == 'lineage':
        tags = tagmod.shared_tags(seed.artist_profile, other.artist_profile, limit=2)
        return 'same scene: ' + ', '.join(tags) if tags else ''
    if axis == 'era':
        return 'same era'
    if axis == 'origin':
        return f'both from {seed.artist_area.strip()}' if seed.artist_area else ''
    if axis == 'career':
        return 'same career stage'
    if axis == 'reach':
        return 'similar-sized audience'
    if axis == 'devotion':
        return 'similarly devoted listeners'
    return ''


def explain(seed, other, axes, strengths, shared_neighbours, shared_personnel,
            shared_circle, co_listening):
    """Ordered, human-readable reasons, strongest first.

    Evidence axes always lead (ordered by strength): a shared person or
    producer is the kind of connection the whole engine exists to find. A
    symmetric axis earns a reason only when it is close enough to mean
    something, and is ranked by how hard it pulled - its closeness scaled by
    its default weight - so "shares post-rock" outranks "same era".
    """
    axes = axes or {}
    strengths = strengths or {}
    pulls = SimilarityWeights().as_dict()
    found = []

    def add(axis, text, sub=0):
        if not text:
            return
        if axis in strengths:
            score = 10.0 + strengths[axis]
        else:
            score = (1.0 - axes.get(axis, 1.0)) * pulls.get(axis, 0.0)
        found.append((-score, _REASON_ORDER.index(axis), sub, text))

    if 'personnel' in strengths:
        add('personnel', _personnel_reason(seed, other, shared_personnel))
    if 'circle' in strengths:
        circle = shared_circle or {}
        add('circle', _prefixed('both produced by', circle.get('producers')), 0)
        add('circle', _engineer_reason(seed, other, circle.get('engineers')), 1)
        add('circle', _prefixed('both recorded at', circle.get('studios')), 2)
        add('circle', _prefixed('both on', circle.get('labels')), 3)
    if 'co_listening' in strengths:
        add('co_listening', _co_listening_reason(co_listening))
    for axis, threshold in _REASON_THRESHOLDS.items():
        distance = axes.get(axis)
        if distance is None or distance >= threshold:
            continue
        add(axis, _symmetric_reason(axis, seed, other, shared_neighbours))

    found.sort()
    return [text for _, _, _, text in found[:MAX_REASONS]]


def describe_axes(match, limit=4):
    """Human-readable read on which parts of the fingerprint lined up."""
    parts = []
    ranked = sorted(match.axes.items(), key=lambda kv: (kv[1], -match.strengths.get(kv[0], 0.0)))
    for axis, distance in ranked[:limit]:
        if axis in match.strengths:
            verdict = 'shared'
        else:
            verdict = 'close' if distance < 0.2 else ('near' if distance < 0.45 else 'far')
        parts.append(f'{AXIS_LABELS.get(axis, axis)}: {verdict}')
    return ', '.join(parts)
