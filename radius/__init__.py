"""Radius: find the albums most deeply connected to one you already like.

Seeded by an album (or a blend of a few) rather than by a filter form: the
seed's tag vectors, the people who made it, its production circle, the
listeners who pair it with other records, its audience and its shape define
a point, and everything in its neighbourhood is ranked by distance from it.

Data comes from keyless JSON APIs - MusicBrainz, ListenBrainz, Wikidata,
Deezer, Discogs - plus Last.fm when a key is configured, all read through a
disk cache at a rate below what each service asks for. No API key required,
no HTML parsing, no crawling: one cached request per fact.
"""

from .engine import Services, SeedNotFound, find_similar, search_albums  # noqa: F401
from .similarity import SimilarityWeights  # noqa: F401
