"""Command line entry point: `python -m radius "Slint - Spiderland"`."""

import argparse
import csv
import json
import sys

from .clients import ApiError
from .engine import MODES, SeedNotFound, Services, find_similar
from .similarity import AXIS_GROUPS, AXIS_LABELS, SimilarityWeights, describe_axes


def build_parser():
    parser = argparse.ArgumentParser(
        prog='radius',
        description='Find the albums most deeply connected to one you already like.',
    )
    parser.add_argument(
        'seeds', nargs='*',
        help='Seed album(s) as "Artist - Album", "mbid:<release-group id>" or free text. '
             'Several seeds are blended into one fingerprint.',
    )
    parser.add_argument('--mode', choices=sorted(MODES), default='closest',
                        help='closest: nearest fingerprints. sideways: same broad genre, '
                             'corners the seed is not in. deep_cuts: less heard than the seed.')
    parser.add_argument('-n', '--top', type=int, default=25, help='How many results.')
    parser.add_argument('--pool', type=int, default=150,
                        help='Candidates to bulk-fingerprint. Higher is better and slower.')
    parser.add_argument('--shortlist', type=int, default=None,
                        help='How many get the deep MusicBrainz lookups (default 1.5x --top, min 30).')
    parser.add_argument('--per-artist', type=int, default=1, metavar='N',
                        help='Max albums per artist in the results (0 = no cap).')
    parser.add_argument('--radius', type=float, default=None,
                        help='Optional cap on fingerprint distance, 0..1.')

    parser.add_argument('--weight', action='append', default=[], metavar='AXIS=VALUE',
                        help='Override one axis weight, e.g. --weight mood=1.5. Repeatable.')
    parser.add_argument('--only', nargs='+', metavar='AXIS',
                        help='Score on these axes alone.')
    parser.add_argument('--list-axes', action='store_true',
                        help='Print the fingerprint axes and their default weights.')

    parser.add_argument('--include-same-artist', action='store_true',
                        help='Allow other albums by the seed artist.')
    parser.add_argument('--include-non-studio', action='store_true',
                        help='Allow live albums, compilations, remix sets.')
    parser.add_argument('--no-crowd-tags', action='store_true',
                        help='Skip Last.fm even if a key is set.')
    parser.add_argument('--discogs', action='store_true',
                        help='Fetch Discogs stats even without a token (25 requests/minute, slow).')
    parser.add_argument('--no-deep', action='store_true',
                        help='Skip the deep lookups: a fast, shallow run on bulk data only.')

    parser.add_argument('--explain', action='store_true',
                        help='Print every axis and every statistic per result.')
    parser.add_argument('--json', dest='json_out', metavar='PATH',
                        help='Write full results to a JSON file.')
    parser.add_argument('--csv', dest='csv_out', metavar='PATH',
                        help='Write full results to a CSV file.')
    parser.add_argument('--quiet', action='store_true', help='No progress output.')
    return parser


def parse_weights(args):
    known = SimilarityWeights.axis_names()
    for axis in args.only or ():
        if axis not in known:
            raise SystemExit(f'Unknown axis "{axis}". Try --list-axes.')
    if args.only:
        weights = SimilarityWeights.only(*args.only)
    else:
        weights = SimilarityWeights()
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
            print(f'  {axis:<13} {state:>5}  {AXIS_LABELS[axis]}')
    print('\nOverride with --weight axis=value, or isolate with --only axis [axis ...].')


def _progress(stage, done, total, label):
    bar = f'[{stage}] {done}/{total}'
    sys.stderr.write(f'\r{bar:<26} {label[:60]:<60}')
    sys.stderr.flush()
    if total and done >= total:
        sys.stderr.write('\n')


def _use_utf8_output():
    """Stop a Windows console from killing a finished run: the default
    encoding there cannot represent a good share of album titles."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding='utf-8', errors='replace')
        except (AttributeError, ValueError):
            pass


def _fmt_int(value):
    return f'{int(value):,}' if value else '-'


def _seed_card(seed):
    year = f' ({seed.year})' if seed.year else ''
    lines = [f'\nSeed: {seed.artist} - {seed.title}{year}']
    lines.append(f'  tags       {", ".join(seed.top_tags[:8])}')
    if seed.listeners:
        lines.append(f'  listeners  {seed.listeners:,} on ListenBrainz, {seed.devotion:.1f} listens each'
                     + (f'; {seed.fans:,} Deezer fans' if seed.fans else '')
                     + (f'; {seed.lastfm_listeners:,} on Last.fm' if seed.lastfm_listeners else ''))
    origin = []
    if seed.artist_area:
        origin.append(seed.artist_area)
    if seed.artist_type:
        origin.append(seed.artist_type.lower())
    if seed.career_stage is not None:
        origin.append(f'{seed.career_stage} yrs into career')
    if origin:
        lines.append(f'  from       {" / ".join(origin)}')
    if seed.has_tracklist:
        lines.append(f'  shape      {seed.track_count} tracks, {seed.runtime_seconds // 60} min'
                     + (f', {seed.bpm_mean:.0f} bpm' if seed.bpm_mean else '')
                     + (f', {seed.gain_mean:.1f} dB gain' if seed.gain_mean is not None else ''))
    if seed.label or seed.producer_names or seed.studio_names:
        parts = []
        if seed.label:
            parts.append(f'on {seed.label}')
        if seed.producer_names:
            parts.append('produced by ' + ', '.join(seed.producer_names[:3]))
        if seed.studio_names:
            parts.append('recorded at ' + ', '.join(seed.studio_names[:2]))
        lines.append(f'  circle     {"; ".join(parts)}')
    if seed.personnel:
        others = [name for mbid, name in seed.personnel.items() if mbid != seed.artist_mbid]
        lines.append(f'  people     {len(others)} connected: {", ".join(others[:6])}'
                     + (' ...' if len(others) > 6 else ''))
    if seed.critic_scores:
        lines.append('  critics    ' + ', '.join(f'{k} {v:.2f}' for k, v in seed.critic_scores.items()))
    if seed.have or seed.want:
        lines.append(f'  discogs    {seed.have:,} have / {seed.want:,} want'
                     + (f', rated {seed.discogs_rating:.2f}' if seed.discogs_rating else ''))
    return '\n'.join(lines)


def _stat_line(features):
    parts = [f'{_fmt_int(features.listeners)} listeners']
    if features.listeners:
        parts.append(f'{features.devotion:.1f} each')
    if features.runtime_seconds:
        parts.append(f'{features.runtime_seconds // 60} min')
    if features.track_count:
        parts.append(f'{features.track_count} tracks')
    if features.bpm_mean:
        parts.append(f'{features.bpm_mean:.0f} bpm')
    if features.label:
        parts.append(features.label)
    if features.artist_area:
        parts.append(features.artist_area)
    return ' | '.join(parts)


def _print_match(rank, match, explain):
    features = match.features
    year = features.year or '????'
    tag = ' [connected]' if match.connected else ''
    print(f'{rank:>3}. {features.artist} - {features.title} ({year})'
          f'   sim {match.similarity:.3f}{tag}')
    for reason in match.reasons[:3]:
        print(f'     - {reason}')
    print(f'     {_stat_line(features)}')
    if not explain:
        return
    for reason in match.reasons[3:]:
        print(f'     - {reason}')
    print('     axes:')
    for axis, distance in sorted(match.axes.items(), key=lambda kv: kv[1]):
        strength = match.strengths.get(axis)
        if strength is not None:
            print(f'       {axis:<13} shared  strength {strength:.2f}')
        else:
            print(f'       {axis:<13} {distance:.3f}')
    print('     stats:')
    row = features.as_row()
    for key, value in row.items():
        if value in (None, '', 0, False) or key in ('image_url', 'recording_mbids'):
            continue
        text = str(value)
        if len(text) > 140:
            text = text[:137] + '...'
        print(f'       {key:<22} {text}')


def main(argv=None):
    _use_utf8_output()
    args = build_parser().parse_args(argv)

    if args.list_axes:
        print_axes()
        return 0
    if not args.seeds:
        raise SystemExit('Give a seed: radius "Artist - Album" [another seed ...]')

    services = Services.create()
    try:
        result = find_similar(
            seeds=args.seeds,
            weights=parse_weights(args),
            mode=args.mode, radius=args.radius, top_n=args.top, pool_size=args.pool,
            shortlist_size=args.shortlist,
            exclude_same_artist=not args.include_same_artist,
            studio_only=not args.include_non_studio,
            max_per_artist=args.per_artist,
            deep=not args.no_deep,
            with_discogs=True if args.discogs else None,
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

    for seed in (result.seeds if len(result.seeds) > 1 else [result.seed]):
        print(_seed_card(seed))
    if len(result.seeds) > 1:
        print(f'\nBlend: {result.seed.artist}')

    sources = ', '.join(f'{kind} {count}' for kind, count in result.sources.items())
    print(f'\n{result.fingerprinted} of {result.considered} candidates fingerprinted, '
          f'{result.shortlisted} deep-checked; {result.requests_made} requests, '
          f'{result.cache_hits} cache hits')
    if sources:
        print(f'  candidate sources: {sources}')
    timings = ', '.join(f'{stage} {seconds}s' for stage, seconds in result.timings.items())
    if timings:
        print(f'  timings: {timings}')

    for note in result.notes:
        print(f'\n! {note}')

    if result.matches:
        print(f'\nMost connected ({args.mode}):\n')
        for rank, match in enumerate(result.matches, 1):
            _print_match(rank, match, args.explain)
            if args.explain:
                print()

    rows = result.rows()
    if args.json_out:
        with open(args.json_out, 'w', encoding='utf-8') as handle:
            json.dump({'seed': result.seed.as_row(),
                       'seeds': [s.as_row() for s in result.seeds],
                       'results': rows, 'notes': result.notes,
                       'timings': result.timings, 'sources': result.sources},
                      handle, indent=2)
        print(f'\nWrote {args.json_out}')
    if args.csv_out and rows:
        columns = list(rows[0].keys())
        for row in rows[1:]:
            for key in row:
                if key not in columns:
                    columns.append(key)
        with open(args.csv_out, 'w', encoding='utf-8', newline='') as handle:
            writer = csv.DictWriter(handle, fieldnames=columns)
            writer.writeheader()
            writer.writerows(rows)
        print(f'Wrote {args.csv_out}')

    return 0
