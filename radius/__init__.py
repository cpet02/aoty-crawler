"""Radius — find albums similar to one you already like.

Seeded by a single album rather than by a filter form: the seed's own
weighted tag profile, popularity and listener devotion define a point, and
everything else is ranked by distance from it inside a tunable radius.

Data comes from three keyless JSON APIs — ListenBrainz for tags, listening
counts and collaborative similarity, MusicBrainz for the catalogue, Wikipedia
for prose — read through a disk cache at a rate below what each service asks
for. No API key, no HTML parsing, no crawling: one cached request per fact.
"""

from .engine import Services, find_similar  # noqa: F401
from .similarity import SimilarityWeights  # noqa: F401
