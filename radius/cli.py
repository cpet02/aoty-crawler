"""Command line entry point: `python -m radius "Bon Iver - For Emma, Forever Ago"`."""

import argparse
import csv
import json
import sys

from .clients import ApiError
from .engine import SeedNotFound, Services, find_similar
from .similarity import AXIS_GROUPS, AXIS_LABELS, SimilarityWeights, describe_axes


def build_parser():
    parser = argparse.ArgumentParser(
        prog='radius',
        description='Find albums whose fingerprint sits near one you already like.',
    )
    parser.add_argument(
        'seed', nargs='?',
        help='Seed album as "Artist - Album", or any search text with --search.',
    )
    parser.add_argument('--artist', help='Seed artist (instead of the "A - B" form).')
    parser.add_argument('--album', help='Seed album (instead of the "A - B" form).')
    parser.add_argument('--search', action='store_true',
                        help='Treat the seed as free text and let MusicBrainz resolve it.')

    parser.add_argument('--radius', type=float, default=0.55,
                        help='Max fingerprint distance, 0..1. 0.3 tight, 0.7 loose.')
    parser.add_argument('-n', '--top', type=int, default=25, help='How many results.')
    parser.add_argument('--pool', type=int, default=120,
                        help='Candidates to fully fingerprint. Higher is better and slower.')

    parser.add_argument('--weight', action='append', default=[], metavar='AXIS=VALUE',
                        help='Override one axis weight, e.g. --weight mood=1.5. Repeatable.')
    parser.add_argument('--only', nargs='+', metavar='AXIS',
                        help='Score on these axes alone.')
    parser.add_argument('--list-axes', action='store_true',
                        help='Print the fingerprint axes and their default weights.')

    parser.add_argument('--obscurity', choices=('any', 'more_obscure', 'better_known'),
                        default='any', help='Restrict by audience size relative to the seed.')
    parser.add_argument('--lateral', action='store_true',
                        help='Prefer the same broad genre but subgenres the seed lacks.')
    parser.add_argument('--include-same-artist', action='store_true',
                        help='Allow other albums by the seed artist.')
    parser.add_argument('--per-artist', type=int, default=2, metavar='N',
                        help='Max albums per artist in the results (0 = no cap).')
    parser.add_argument('--include-non-studio', action='store_true',
                        help='Allow live albums, compilations, remix sets.')
    parser.add_argument('--no-enrich', action='store_true',
                        help='Skip tracklist lookups, dropping the shape axes (faster).')
    parser.add_argument('--no-prose', action='store_true',
                        help='Skip Wikipedia lookups, dropping the prose axis (faster).')
    parser.add_argument('--no-crowd-tags', action='store_true',
                        help='Skip Last.fm tag enrichment even if a key is set.')

    parser.add_argument('--json', dest='json_out', metavar='PATH',
                        help='Write full results to a JSON file.')
    parser.add_argument('--csv', dest='csv_out', metavar='PATH',
                        help='Write full results to a CSV file.')
    parser.add_argument('--quiet', action='store_true', help='No progress output.')
    return parser


def parse_weights(args):
    if args.only:
        weights = SimilarityWeights.only(*args.only)
    else:
        weights = SimilarityWeights()
    known = SimilarityWeights.axis_names()
    for override in args.weight:
        axis, _, value = override.partition('=')
        axis = axis.strip()
        if axis not in known:
            raise SystemExit(f'Unknown axis "{axis}". Try --list-axes.')
        try:
            setattr(weights, axis, float(value))
        except ValueError:
            raise SystemExit(f'Weight for {axis} must be a number, got "{value}".')
    return weights


def print_axes():
    defaults = SimilarityWeights()
    for group, axes in AXIS_GROUPS.items():
        print(f'\n{group}')
        for axis in axes:
            weight = getattr(defaults, axis)
            state = f'{weight:.2f}' if weight else 'off'
            print(f'  {axis:<12} {state:>5}  {AXIS_LABELS[axis]}')
    print('\nOverride with --weight axis=value, or isolate with --only axis [axis ...].')


def _progress(stage, done, total, label):
    bar = f'[{stage}] {done}/{total}'
    sys.stderr.write(f'\r{bar:<24} {label[:52]:<52}')
    sys.stderr.flush()
    if total and done >= total:
        sys.stderr.write('\n')


def _use_utf8_output():
    """Stop a Windows console from killing a finished run.

    The default console encoding here is cp1252, which cannot represent a
    good share of the album titles this tool prints — one '♯' in a track
    title and the whole result set dies with a UnicodeEncodeError after every
    request has already been paid for.
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding='utf-8', errors='replace')
        except (AttributeError, ValueError):
            pass


def main(argv=None):
    _use_utf8_output()
    args = build_parser().parse_args(argv)

    if args.list_axes:
        print_axes()
        return 0

    artist, album, query = args.artist, args.album, None
    if args.seed:
        if args.search or ' - ' not in args.seed:
            query = args.seed
        else:
            artist, _, album = (part.strip() for part in args.seed.partition(' - '))
    if not (query or (artist and album)):
        raise SystemExit(
            'Give a seed: radius "Artist - Album", or --artist X --album Y, '
            'or --search "some text".'
        )

    services = Services.create()
    try:
        result = find_similar(
            artist=artist, album=album, query=query,
            weights=parse_weights(args),
            radius=args.radius, top_n=args.top, pool_size=args.pool,
            exclude_same_artist=not args.include_same_artist,
            studio_only=not args.include_non_studio,
            max_per_artist=args.per_artist,
            obscurity=args.obscurity, lateral=args.lateral,
            enrich_results=not args.no_enrich,
            with_prose=not args.no_prose,
            enrich_tags_with_lastfm=not args.no_crowd_tags,
            services=services,
            progress=None if args.quiet else _progress,
        )
    except ApiError as exc:
        raise SystemExit(f'\n{exc}')
    except SeedNotFound as exc:
        message = str(exc)
        if exc.suggestions:
            options = '\n  '.join(
                f"{s['artist']} - {s['album']}" for s in exc.suggestions[:5]
            )
            message += f'\n\nDid you mean:\n  {options}'
        raise SystemExit(f'\n{message}')

    if services.tag_enrichment and not args.no_crowd_tags:
        source = 'MusicBrainz + Last.fm crowd tags'
    else:
        source = 'MusicBrainz only (no LASTFM_API_KEY set)'
    print(f'\nTags: {source}', file=sys.stderr)

    seed = result.seed
    year = f' ({seed.year})' if seed.year else ''
    print(f'\nSeed: {seed.artist} - {seed.title}{year}')
    print(f'  tags      {", ".join(seed.top_tags[:8])}')
    print(f'  listeners {seed.listeners:,} · {seed.devotion:.1f} listens each')
    if seed.artist_area:
        print(f'  from      {seed.artist_area}'
              + (f' · {seed.career_stage} yrs into career' if seed.career_stage is not None else ''))
    print(f'\n{result.fingerprinted} of {result.considered} candidates fingerprinted '
          f'· {result.requests_made} requests · {result.cache_hits} cache hits')

    for note in result.notes:
        print(f'\n! {note}')

    if result.matches:
        print(f'\nInside radius {args.radius:.2f}:\n')
        for rank, match in enumerate(result.matches, 1):
            features = match.features
            year = features.year or '????'
            print(f'{rank:>3}. {features.artist} - {features.title} ({year})'
                  f'   sim {match.similarity:.3f}')
            print(f'     {describe_axes(match)}')
            if match.shared_tags:
                print(f'     shared: {", ".join(match.shared_tags)}')
            if match.distinct_tags:
                print(f'     new:    {", ".join(match.distinct_tags)}')

    rows = result.rows()
    if args.json_out:
        with open(args.json_out, 'w', encoding='utf-8') as handle:
            json.dump({'seed': seed.as_row(), 'results': rows}, handle, indent=2)
        print(f'\nWrote {args.json_out}')
    if args.csv_out and rows:
        columns = sorted({key for row in rows for key in row})
        with open(args.csv_out, 'w', encoding='utf-8', newline='') as handle:
            writer = csv.DictWriter(handle, fieldnames=columns)
            writer.writeheader()
            writer.writerows(rows)
        print(f'Wrote {args.csv_out}')

    return 0
