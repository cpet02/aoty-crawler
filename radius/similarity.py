"""Fingerprint distance.

Sixteen axes, each derived from payloads the fetcher already pulls. Every
axis is normalised to roughly 0..1, and the overall distance is a weighted
mean over the axes that are *computable for both albums* — an axis with no
data on one side is dropped from the mean rather than silently scored as a
perfect match, which is the difference between "we don't know" and "identical".

    texture-ish, from tags and prose
      genre       the taxonomy-recognised part of the album's tag vector
      mood        the rest of it: moods, scenes, textures, adjectives
      lineage     the artist's tag vector — scene and pedigree, not one record
      neighbours  overlap of Last.fm similar-artist sets: pure listener
                  behaviour, so it finds kinship no vocabulary agrees on
      prose       bag-of-words over the album's Wikipedia article. Off by
                  default — see SimilarityWeights for why it underperforms
      co_tagging  how strongly the crowd already files this next to the seed,
                  measured by how many of the seed's own tag and artist
                  neighbourhoods coughed it up

    reception, with no critics in it
      reach       log10 distinct listeners
      devotion    listens per listener
      canonicity  this album's share of its artist's audience

    shape
      era         release year
      scale       runtime and track count
      pacing      mean track length and how uneven it is
      titling     mean words per track title
      definition  entropy of the tag distribution: how easy to place it is
      origin      where the artist is from, and band vs solo
      career      years into the artist's career when the record landed
"""

import math
from dataclasses import dataclass, asdict, fields

from . import tags as tagmod
from .albums import jaccard

# The delta on each axis that counts as "completely different": two orders of
# magnitude of audience, 4x the replay rate, a quarter century, an hour of
# runtime, and so on. These set what a radius actually means.
REACH_SPAN = 2.0
DEVOTION_SPAN = 2.0
ERA_SPAN = 25.0
RUNTIME_SPAN_SECONDS = 3600.0
TRACK_COUNT_SPAN = 14.0
TRACK_LENGTH_SPAN_SECONDS = 240.0
SPREAD_SPAN = 0.8
TITLE_WORDS_SPAN = 4.0
CAREER_SPAN = 15.0
# Bag-of-words overlap between two album articles is tiny even when they are
# plainly about similar records — a few shared words out of sixty. Raw cosine
# would therefore report "completely different" for every pair alike, so the
# axis is scaled to the range it actually operates in, the same way the
# similar-artist Jaccard is.
PROSE_SCALE = 0.12


@dataclass
class SimilarityWeights:
    """Relative pull of each axis. Zero switches an axis off entirely.

    The defaults lead with what the album sounds like, keep reception as a
    real but secondary pull, and treat shape as a tiebreaker.

    Two axes ship switched off. `titling` is more curiosity than signal. And
    `prose` measured badly in practice: Wikipedia album ledes are boilerplate
    ("the fourth studio album by..."), so two records that sound nothing alike
    share more wording than two that do — on one check, Lemonade scored closer
    to Spiderland than Mogwai did. The plumbing is kept because the idea is
    sound and a better text source would redeem it, but it is not switched on
    by default while it ranks worse than nothing.
    """

    genre: float = 1.0
    mood: float = 0.8
    lineage: float = 0.45
    neighbours: float = 0.6
    prose: float = 0.0
    co_tagging: float = 0.35
    reach: float = 0.35
    devotion: float = 0.35
    canonicity: float = 0.2
    era: float = 0.2
    scale: float = 0.15
    pacing: float = 0.15
    definition: float = 0.1
    origin: float = 0.15
    career: float = 0.15
    titling: float = 0.0

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
    'lineage': 'artist lineage',
    'neighbours': 'listener kinship',
    'prose': 'how it gets written about',
    'co_tagging': 'crowd co-tagging',
    'reach': 'audience size',
    'devotion': 'listener devotion',
    'canonicity': 'standing in discography',
    'era': 'era',
    'scale': 'runtime & length',
    'pacing': 'track pacing',
    'definition': 'how easy to place',
    'origin': 'where it comes from',
    'career': 'career stage',
    'titling': 'track titling',
}

AXIS_HELP = {
    'genre': "Increase to demand closer genre-tag overlap, decrease to let other "
             "axes carry more of the match. E.g. raise it to keep results "
             "strictly within post-rock; lower it to let mood matter more than "
             "the genre label.",
    'mood': "Increase to weight shared mood/texture tags more, decrease to "
            "ignore them. E.g. raise it to surface other 'melancholic, "
            "hypnagogic' records even in a different genre.",
    'lineage': "Increase to favour artists from a similar scene or pedigree, "
               "decrease to judge the album on its own. E.g. raise it to stay "
               "inside the same underground scene rather than just the same "
               "sound.",
    'neighbours': "Increase to weight overlap in who else's fans listen to "
                  "both artists, decrease to ignore listener behaviour. E.g. "
                  "raise it to find albums real listeners already pair "
                  "together, even if the tags don't obviously match.",
    'prose': "Increase to weight shared wording in each album's Wikipedia "
             "article, decrease to ignore it. Off by default — it measured "
             "worse than nothing, since album write-ups are mostly "
             "boilerplate. Leave at 0 unless you're experimenting.",
    'co_tagging': "Increase to favour albums the crowd already files next to "
                  "your seed, decrease to explore further from it. E.g. raise "
                  "it for safer, more obviously-related picks; lower it to "
                  "range wider.",
    'reach': "Increase to match similar listener counts, decrease to ignore "
             "popularity entirely. E.g. raise it to avoid pairing a niche cult "
             "record with a mainstream hit.",
    'devotion': "Increase to match how obsessively each album's fans replay "
                "it, decrease to ignore that. E.g. raise it to find other "
                "records with an equally devoted cult following.",
    'canonicity': "Increase to match how central each album is to its own "
                  "artist's catalogue, decrease to ignore it. E.g. raise it to "
                  "compare a landmark record to other landmark records rather "
                  "than to deep cuts.",
    'era': "Increase to favour albums released around the same time, decrease "
           "to range freely across eras. E.g. raise it to stay within a few "
           "years of the seed; lower it to ignore release date completely.",
    'scale': "Increase to match total runtime, decrease to ignore album "
             "length. E.g. raise it to avoid pairing a 25-minute record with "
             "a 90-minute one.",
    'pacing': "Increase to match average track length, decrease to ignore it. "
              "E.g. raise it to keep both albums built from similarly long "
              "(or short) tracks.",
    'definition': "Increase to match how easily each album sits in one genre "
                  "vs. spreads across several, decrease to ignore it. E.g. "
                  "raise it to keep a genre-fluid record paired with other "
                  "genre-fluid ones rather than one narrowly-tagged record.",
    'origin': "Increase to favour artists from the same country or region, "
              "decrease to ignore geography. E.g. raise it to stay within the "
              "same national scene.",
    'career': "Increase to match how far into their career each artist was at "
              "release, decrease to ignore it. E.g. raise it to pair debut "
              "albums with other debuts rather than late-career records.",
    'titling': "Increase to match how the tracks are named, decrease to "
               "ignore it. Off by default — curiosity more than signal. "
               "E.g. leave at 0 unless you're curious whether titling style "
               "tracks with sound.",
}

AXIS_GROUPS = {
    'Sound & association': ['genre', 'mood', 'lineage', 'neighbours', 'prose', 'co_tagging'],
    'Reception (no critics)': ['reach', 'devotion', 'canonicity'],
    'Shape': ['era', 'scale', 'pacing', 'definition', 'titling'],
    'Provenance': ['origin', 'career'],
}


def _clamp01(value):
    return 0.0 if value < 0 else (1.0 if value > 1 else value)


def _vector_distance(vector_a, vector_b):
    """None when either side is empty — unknown, not dissimilar."""
    if not vector_a or not vector_b:
        return None
    return 1.0 - _clamp01(tagmod.cosine(vector_a, vector_b))


def _ratio_distance(value_a, value_b, span):
    """Distance in log2 space, for quantities where doubling is the unit of
    change rather than adding."""
    if not value_a or not value_b or value_a <= 0 or value_b <= 0:
        return None
    return _clamp01(abs(math.log2(value_a) - math.log2(value_b)) / span)


def _linear_distance(value_a, value_b, span):
    if value_a is None or value_b is None:
        return None
    return _clamp01(abs(value_a - value_b) / span)


def _mean(values):
    present = [v for v in values if v is not None]
    if not present:
        return None
    return sum(present) / len(present)


def axis_distances(seed, other, seed_vectors, other_vectors, co_tagging=None):
    """Per-axis distance, omitting any axis that can't be computed for both."""
    distances = {}

    for axis in ('genre', 'mood', 'lineage'):
        distance = _vector_distance(seed_vectors.get(axis), other_vectors.get(axis))
        if distance is not None:
            distances[axis] = distance

    seed_prose, other_prose = seed_vectors.get('prose'), other_vectors.get('prose')
    if seed_prose and other_prose:
        overlap = _clamp01(tagmod.cosine(seed_prose, other_prose))
        distances['prose'] = _clamp01(1.0 - min(overlap / PROSE_SCALE, 1.0))

    overlap = jaccard(set(seed.artist_neighbours), set(other.artist_neighbours))
    if overlap is not None:
        # Similar-artist sets are 100 names wide at most, so even a strong
        # match rarely exceeds ~0.3 Jaccard; scale so real overlap registers.
        distances['neighbours'] = _clamp01(1.0 - min(overlap / 0.3, 1.0))

    if co_tagging is not None:
        distances['co_tagging'] = _clamp01(1.0 - co_tagging)

    if seed.listeners and other.listeners:
        distances['reach'] = _clamp01(abs(seed.reach - other.reach) / REACH_SPAN)
        devotion = _ratio_distance(
            max(seed.devotion, 1.0), max(other.devotion, 1.0), DEVOTION_SPAN
        )
        if devotion is not None:
            distances['devotion'] = devotion

    seed_canon, other_canon = seed.canonicity, other.canonicity
    if seed_canon is not None and other_canon is not None:
        canon = _ratio_distance(seed_canon, other_canon, 2.0)
        if canon is not None:
            distances['canonicity'] = canon

    era = _linear_distance(seed.year, other.year, ERA_SPAN)
    if era is not None:
        distances['era'] = era

    if seed.has_tracklist and other.has_tracklist:
        # Runtime and track count are two readings of the same thing, so they
        # average into one axis rather than double-counting size.
        distances['scale'] = _mean([
            _linear_distance(seed.runtime_seconds, other.runtime_seconds, RUNTIME_SPAN_SECONDS),
            _linear_distance(seed.track_count, other.track_count, TRACK_COUNT_SPAN),
        ])
        pacing = _mean([
            _linear_distance(
                seed.mean_track_seconds, other.mean_track_seconds,
                TRACK_LENGTH_SPAN_SECONDS,
            ),
            _linear_distance(
                seed.track_length_spread, other.track_length_spread, SPREAD_SPAN
            ),
        ])
        if pacing is not None:
            distances['pacing'] = pacing

    if seed.mean_title_words and other.mean_title_words:
        distances['titling'] = _linear_distance(
            seed.mean_title_words, other.mean_title_words, TITLE_WORDS_SPAN
        )

    if seed.profile and other.profile:
        distances['definition'] = _clamp01(abs(seed.definition - other.definition))

    if seed.artist_area and other.artist_area:
        # Same country is the signal worth having; scene geography is coarse
        # and anything finer would be false precision. Being the same kind of
        # act — band or solo — rides along on the same axis, at half weight.
        same_place = seed.artist_area.strip().lower() == other.artist_area.strip().lower()
        distance = 0.0 if same_place else 1.0
        if seed.artist_type and other.artist_type:
            same_kind = seed.artist_type.strip().lower() == other.artist_type.strip().lower()
            distance = (distance * 2 + (0.0 if same_kind else 1.0)) / 3.0
        distances['origin'] = distance

    career = _linear_distance(seed.career_stage, other.career_stage, CAREER_SPAN)
    if career is not None:
        distances['career'] = career

    return {axis: d for axis, d in distances.items() if d is not None}


@dataclass
class Match:
    features: object
    distance: float
    axes: dict
    shared_tags: list
    distinct_tags: list
    shared_neighbours: list
    sources: tuple = ()
    coverage: float = 1.0

    @property
    def similarity(self):
        return 1.0 - self.distance

    def as_row(self):
        row = self.features.as_row()
        row.update({
            'similarity': round(self.similarity, 3),
            'distance': round(self.distance, 3),
            'axes_measured': len(self.axes),
            'shared_tags': ', '.join(self.shared_tags),
            'new_tags': ', '.join(self.distinct_tags),
            'shared_similar_artists': ', '.join(self.shared_neighbours),
            'found_via': ', '.join(sorted(self.sources)[:4]),
        })
        for axis, value in self.axes.items():
            row[f'd_{axis}'] = round(value, 3)
        return row


def compare(seed, other, seed_vectors, other_vectors, weights,
            co_tagging=None, lateral_bonus=0.0, sources=()):
    """Fingerprint distance between the seed and one candidate.

    `lateral_bonus` nudges toward records that share the seed's broad genre
    while bringing subgenres it doesn't have — the "same neighbourhood, room I
    haven't been in" case, which is usually what you actually want from a
    recommendation rather than a near-duplicate.
    """
    distances = axis_distances(seed, other, seed_vectors, other_vectors, co_tagging)
    active = weights.as_dict()

    numerator = 0.0
    denominator = 0.0
    for axis, distance in distances.items():
        weight = active.get(axis, 0.0)
        if weight <= 0:
            continue
        numerator += weight * distance
        denominator += weight

    if denominator == 0:
        # Nothing enabled was measurable for this album.
        return None

    distance = numerator / denominator
    requested = sum(w for axis, w in active.items() if w > 0)
    coverage = denominator / requested if requested else 1.0

    if lateral_bonus:
        new_subgenres = other.subgenres - seed.subgenres
        if new_subgenres and set(other.root_genres) & set(seed.root_genres):
            distance = max(0.0, distance - lateral_bonus)

    shared_neighbours = sorted(set(seed.artist_neighbours) & set(other.artist_neighbours))
    return Match(
        features=other,
        distance=distance,
        axes=distances,
        shared_tags=tagmod.shared_tags(seed.profile, other.profile),
        distinct_tags=sorted(
            set(other.profile) - set(seed.profile),
            key=other.profile.get, reverse=True,
        )[:4],
        shared_neighbours=shared_neighbours[:5],
        sources=tuple(sources),
        coverage=coverage,
    )


def describe_axes(match, limit=4):
    """Human-readable read on which parts of the fingerprint lined up."""
    parts = []
    for axis, distance in sorted(match.axes.items(), key=lambda kv: kv[1])[:limit]:
        verdict = 'close' if distance < 0.2 else ('near' if distance < 0.45 else 'far')
        parts.append(f'{AXIS_LABELS.get(axis, axis)}: {verdict}')
    return ' · '.join(parts)
