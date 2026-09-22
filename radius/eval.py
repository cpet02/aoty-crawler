"""Golden-set evaluation: does the engine surface the artists you'd expect?

Tuning a similarity engine by eye doesn't work. Every weight change makes one
seed look better and another worse, and memory of the previous run is short.
So this module keeps a small curated set of seeds, each paired with the
artists any listener of that record would expect to find nearby, and scores
a run by how many of them appear in the top N and how early the first one
shows up (mean reciprocal rank).

The set is opinionated rather than exhaustive: a missing artist is not proof
of a bad result, but the aggregate moving down after a change is a reason to
look before keeping it. `python -m radius.eval` runs the live engine (cached
after the first pass), prints a table, and can save a baseline or diff
against one.

Matching is by artist name, folded so that punctuation, diacritics and a
leading "The" never cost a hit -- the point is to measure the engine, not the
spelling conventions of three different databases.

The engine is imported inside `evaluate()`, not at the top, so this module
imports (and its pure scoring functions test) regardless of the state of
`engine.py`; a `runner` callable can replace the engine call entirely.
"""

import argparse
import json
import re
import sys
import unicodedata

GOLDEN = [
    {'seed': 'Slint - Spiderland', 'expect': [
        'Rodan', 'June of 44', 'Codeine', 'Bedhead', 'Tortoise', 'Papa M',
        'The For Carnation', 'Talk Talk', 'Bark Psychosis', 'Shellac',
        'Gastr del Sol', 'Duster', 'Low', 'Shipping News', "Rachel's",
        'Bitch Magnet', 'Squirrel Bait', 'Mogwai', 'Unwound', 'Polvo',
        'Godspeed You! Black Emperor', 'Fugazi', 'Swans', 'Sonic Youth',
    ]},
    {'seed': 'Bon Iver - For Emma, Forever Ago', 'expect': [
        'Fleet Foxes', 'Iron & Wine', 'Sufjan Stevens', 'The Tallest Man on Earth',
        'Volcano Choir', 'Big Red Machine', 'Elliott Smith', 'José González',
        'S. Carey', 'Phosphorescent', 'Damien Rice', 'Ray LaMontagne',
        'Nick Drake', 'Bright Eyes', 'The Antlers', 'Grizzly Bear',
        'Band of Horses', 'Great Lake Swimmers', 'DeYarmond Edison', 'Gayngs',
        'Sharon Van Etten', 'The Shins',
    ]},
    {'seed': 'Portishead - Dummy', 'expect': [
        'Massive Attack', 'Tricky', 'Morcheeba', 'Lamb', 'Sneaker Pimps',
        'Beth Gibbons', 'Hooverphonic', 'Zero 7', 'Air', 'Björk', 'Goldfrapp',
        'DJ Shadow', 'UNKLE', 'Thievery Corporation', 'Esthero', 'Smoke City',
        'Bowery Electric', 'Alpha', 'Red Snapper', 'Rustin Man',
    ]},
    {'seed': 'Radiohead - Kid A', 'expect': [
        'Thom Yorke', 'Atoms for Peace', 'Boards of Canada', 'Aphex Twin',
        'Autechre', 'Björk', 'Sigur Rós', 'Talk Talk', 'Portishead',
        'Massive Attack', 'Broadcast', 'Four Tet', 'Flying Lotus', 'Burial',
        'Jonny Greenwood', 'Blonde Redhead', 'The Smile', 'Mogwai',
        'Godspeed You! Black Emperor', 'Spiritualized', 'Grizzly Bear', 'Beck',
    ]},
    {'seed': 'Talk Talk - Laughing Stock', 'expect': [
        'Mark Hollis', 'Bark Psychosis', 'Slint', 'Disco Inferno', 'The Blue Nile',
        'David Sylvian', 'Japan', 'Sigur Rós', 'Robert Wyatt', "Rachel's",
        'Mogwai', 'Godspeed You! Black Emperor', 'Low', 'The Durutti Column',
        'Elbow', 'Doves', 'Bill Fay', 'Nick Drake', 'Scott Walker', 'Radiohead',
        'Portishead', 'Bowery Electric', '.O.rang', 'Rustin Man',
    ]},
    {'seed': 'My Bloody Valentine - Loveless', 'expect': [
        'Slowdive', 'Ride', 'Lush', 'Swervedriver', 'Cocteau Twins',
        'The Jesus and Mary Chain', 'Chapterhouse', 'Pale Saints', 'Medicine',
        'Catherine Wheel', 'Curve', 'Sonic Youth', 'Dinosaur Jr.',
        'The Boo Radleys', 'Drop Nineteens', 'Seefeel', 'Bowery Electric',
        'Galaxie 500', 'Alcest', 'Deerhunter', 'Beach House', 'DIIV',
        'A Place to Bury Strangers', 'Primal Scream', 'Flying Saucer Attack',
    ]},
    {'seed': 'Kendrick Lamar - To Pimp a Butterfly', 'expect': [
        'Kamasi Washington', 'Thundercat', 'Flying Lotus', 'Terrace Martin',
        'Robert Glasper', 'Anderson .Paak', 'Vince Staples', 'ScHoolboy Q',
        'Ab-Soul', 'Jay Rock', 'Isaiah Rashad', 'J. Cole', 'Childish Gambino',
        'Frank Ocean', "D'Angelo", 'Erykah Badu', 'The Roots', 'Common',
        'Mos Def', 'Outkast', 'Denzel Curry', 'JID', 'Danny Brown', 'Little Simz',
        'Saba', 'Noname', 'Funkadelic',
    ]},
    {'seed': 'Joni Mitchell - Blue', 'expect': [
        'Carole King', 'James Taylor', 'Neil Young', 'Crosby, Stills, Nash & Young',
        'Judee Sill', 'Laura Nyro', 'Nick Drake', 'Leonard Cohen', 'Bob Dylan',
        'Joan Baez', 'Cat Stevens', 'Carly Simon', 'Jackson Browne',
        'Van Morrison', 'Joan Armatrading', 'Karen Dalton', 'Linda Perhacs',
        'Vashti Bunyan', 'Weyes Blood', 'Rickie Lee Jones', 'Sandy Denny',
        'Fairport Convention', 'Buffy Sainte-Marie', 'Judy Collins',
        'Tim Buckley', 'Jeff Buckley', 'Emmylou Harris', 'Gram Parsons',
    ]},
    {'seed': 'Burial - Untrue', 'expect': [
        'Four Tet', 'Boards of Canada', 'Actress', 'Zomby', 'Kode9', 'Joy Orbison',
        'James Blake', 'Mount Kimbie', 'Andy Stott', 'Massive Attack',
        'Portishead', 'Aphex Twin', 'Autechre', 'Flying Lotus', 'The Caretaker',
        'Tim Hecker', 'William Basinski', 'Blawan', 'Pinch', 'Shackleton',
        'Skream', 'Benga', 'Digital Mystikz', 'Darkstar', 'Jamie xx', 'The xx',
        'Fever Ray', 'Oneohtrix Point Never', 'Vessel', 'Lorn',
    ]},
    {'seed': 'Miles Davis - Kind of Blue', 'expect': [
        'John Coltrane', 'Bill Evans', 'Cannonball Adderley', 'Thelonious Monk',
        'Charles Mingus', 'Herbie Hancock', 'Wayne Shorter', 'Dave Brubeck',
        'Chet Baker', 'Sonny Rollins', 'Art Blakey', 'Duke Ellington',
        'Charlie Parker', 'Dizzy Gillespie', 'Horace Silver', 'Wynton Kelly',
        'Lee Morgan', 'Stan Getz', 'McCoy Tyner', 'Oliver Nelson', 'Ahmad Jamal',
        'Grant Green', 'Kenny Burrell', 'Gil Evans',
    ]},
    {'seed': 'Weyes Blood - Titanic Rising', 'expect': [
        'Father John Misty', 'Angel Olsen', 'Aldous Harding', 'Julia Holter',
        'Natalie Prass', 'Cate Le Bon', 'Lana Del Rey', 'Mitski',
        'Sharon Van Etten', 'Joanna Newsom', 'Perfume Genius', 'Big Thief',
        'Adrianne Lenker', 'Jessica Pratt', 'Judee Sill', 'Harry Nilsson',
        'Carpenters', 'Joni Mitchell', 'Ariel Pink', 'Drugdealer', 'Kevin Morby',
        'Hand Habits', 'Molly Burch', 'The Weather Station', 'Fleetwood Mac',
        'Beach House', 'Cass McCombs', 'Andy Shauf',
    ]},
    {'seed': 'Duster - Stratosphere', 'expect': [
        'Slint', 'Bedhead', 'Codeine', 'Low', 'Red House Painters', 'Galaxie 500',
        'Sparklehorse', 'Grandaddy', 'Helvetia', 'Eiafuawn', 'Elliott Smith',
        'Alex G', "Carissa's Wierd", 'Idaho', 'Early Day Miners', 'Seam',
        'Movietone', 'Flying Saucer Attack', 'Yo La Tengo', 'Pavement',
        'Built to Spill', 'Modest Mouse', 'Songs: Ohia', 'Mazzy Star',
        'American Football', 'Have a Nice Life', 'Karate', 'The Microphones',
        'Mount Eerie', 'Neutral Milk Hotel', 'Pinback', 'Unwound',
    ]},
]


# ---------------------------------------------------------------------------
# Name matching
# ---------------------------------------------------------------------------

def normalise_name(name):
    """Fold an artist name down to what two databases would agree on.

    Casefolded, diacritics stripped, apostrophes removed, every other run of
    punctuation or whitespace collapsed to one space, and a leading "the"
    dropped -- so "Godspeed You! Black Emperor" and "Godspeed You Black
    Emperor!" are the same act, and so are "Rachel's" and "Rachels".
    Apostrophes are dropped rather than split on because they sit inside a
    word (D'Angelo); a hyphen or dot marks a boundary (Ab-Soul, Ab Soul).
    """
    text = unicodedata.normalize('NFKD', name or '')
    text = ''.join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"['’ʼ]", '', text.casefold())
    text = re.sub(r'[\W_]+', ' ', text).strip()
    if text.startswith('the '):
        text = text[4:]
    return text


def name_matches(expected, artist):
    """True when a normalised expected name is the result artist, or sits
    whole inside it -- "Bon Iver" inside "Bon Iver & Friends".

    Containment is word-bounded on purpose: the golden set has "Low", "Air",
    "Lamb", "Curve" and "Alpha", which a bare substring test would find in
    Lowell George, Airborne, Lambchop, and Alphaville.
    """
    if not expected or not artist:
        return False
    return expected == artist or f' {expected} ' in f' {artist} '


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def score_seed(expected, result_artists):
    """Metrics for one ranked list of result artist names.

    Each expected artist counts once, at the rank it first appears; `mrr` is
    1/rank of the earliest hit of any expected artist.
    """
    ranked = [normalise_name(artist) for artist in result_artists]
    first_rank = {}
    for name in expected:
        key = normalise_name(name)
        for rank, artist in enumerate(ranked, 1):
            if name_matches(key, artist):
                first_rank[name] = rank
                break
    # sorted() is stable, so artists tied on rank keep the golden order.
    found = sorted(first_rank, key=first_rank.get)
    return {
        'hits': len(found),
        'expected': len(expected),
        'hit_rate': len(found) / len(expected) if expected else 0.0,
        'found': found,
        'missing': [name for name in expected if name not in first_rank],
        'mrr': 1.0 / min(first_rank.values()) if first_rank else 0.0,
    }


def summarise(per_seed, top_n):
    count = len(per_seed)
    return {
        'top_n': top_n,
        'per_seed': per_seed,
        'hits_at_n': sum(s['hit_rate'] for s in per_seed) / count if count else 0.0,
        'mrr': sum(s['mrr'] for s in per_seed) / count if count else 0.0,
        'requests': sum(s['requests'] for s in per_seed),
    }


def select_seeds(filters=None, golden=None):
    """Golden entries whose seed text contains any filter, case-insensitively.
    No filters means the whole set."""
    golden = GOLDEN if golden is None else golden
    if not filters:
        return list(golden)
    wanted = [text.casefold() for text in filters]
    return [entry for entry in golden
            if any(text in entry['seed'].casefold() for text in wanted)]


def _entries(seeds):
    """`seeds` may be filter strings or ready-made golden-style entries."""
    if seeds and all(isinstance(item, dict) for item in seeds):
        return list(seeds)
    return select_seeds(seeds)


def _result_artists(result):
    artists = []
    for match in getattr(result, 'matches', None) or []:
        features = getattr(match, 'features', None)
        artists.append(getattr(features, 'artist', '') or '')
    return artists


def _requests_spent(result, services, before):
    """Requests this one seed cost.

    The live Services counter is cumulative across the process, so its
    difference is the honest per-seed figure; a result with no counter
    behind it (a fake runner) reports its own count.
    """
    after = getattr(services, 'requests_made', None)
    if isinstance(before, int) and isinstance(after, int):
        return after - before
    return int(getattr(result, 'requests_made', 0) or 0)


def evaluate(services=None, top_n=25, seeds=None, progress=None, runner=None,
             **engine_kwargs):
    """Run every chosen seed through the engine and score it.

    seeds       None for the whole golden set, a list of case-insensitive
                substrings to filter it by, or a list of golden-style entries.
    progress    progress(seed_index, total_seeds, seed_text), before each run.
    runner      runner(seed_text, top_n, services, **engine_kwargs) returning
                an object with .matches (each with .features.artist) and
                .requests_made. The default wraps engine.find_similar.

    A seed whose run raises is scored as zero hits with an 'error' entry
    rather than sinking the other eleven: an evaluation costs minutes of
    API time and one unresolvable seed shouldn't throw that away.
    """
    entries = _entries(seeds)
    if runner is None:
        from .engine import Services, find_similar
        if services is None:
            services = Services.create()

        def runner(seed_text, top_n, services, **kwargs):
            return find_similar(seeds=[seed_text], services=services,
                                top_n=top_n, **kwargs)

    per_seed = []
    for index, entry in enumerate(entries):
        if progress:
            progress(index, len(entries), entry['seed'])
        before = getattr(services, 'requests_made', None)
        error = ''
        try:
            result = runner(entry['seed'], top_n, services, **engine_kwargs)
        except Exception as exc:  # noqa: BLE001 - see docstring
            result, error = None, f'{type(exc).__name__}: {exc}'
        scored = score_seed(entry['expect'], _result_artists(result)[:top_n])
        scored['seed'] = entry['seed']
        scored['requests'] = _requests_spent(result, services, before)
        if error:
            scored['error'] = error
        per_seed.append(scored)
    return summarise(per_seed, top_n)


# ---------------------------------------------------------------------------
# Baselines
# ---------------------------------------------------------------------------

def save_report(report, path):
    with open(path, 'w', encoding='utf-8') as handle:
        json.dump(report, handle, indent=2, ensure_ascii=False)


def load_report(path):
    with open(path, encoding='utf-8') as handle:
        return json.load(handle)


def compare_reports(current, baseline):
    """How this run moved against a saved one, per seed and in aggregate.

    Seeds present on only one side get a None on the other and no delta.
    """
    old = {row['seed']: row for row in baseline.get('per_seed', [])}
    new = {row['seed']: row for row in current.get('per_seed', [])}
    rows = []
    for seed in list(new) + [seed for seed in old if seed not in new]:
        before = old.get(seed, {}).get('hits')
        after = new.get(seed, {}).get('hits')
        delta = after - before if before is not None and after is not None else None
        rows.append({'seed': seed, 'before': before, 'after': after, 'delta': delta})

    def aggregate(key):
        before = float(baseline.get(key) or 0.0)
        after = float(current.get(key) or 0.0)
        return {'before': before, 'after': after, 'delta': after - before}

    return {
        'per_seed': rows,
        'hits_at_n': aggregate('hits_at_n'),
        'mrr': aggregate('mrr'),
        'top_n': {'before': baseline.get('top_n'), 'after': current.get('top_n')},
    }


# ---------------------------------------------------------------------------
# Printing
# ---------------------------------------------------------------------------

def _names(items, limit):
    if not items:
        return '-'
    text = ', '.join(items[:limit])
    if len(items) > limit:
        text += f' (+{len(items) - limit})'
    return text


def format_table(report, names=4):
    lines = [f"{'seed':<40} {'hits':>6} {'mrr':>5}"]
    for row in report['per_seed']:
        hits = f"{row['hits']}/{row['expected']}"
        lines.append(f"{row['seed']:<40} {hits:>6} {row['mrr']:>5.2f}")
        if row.get('error'):
            lines.append(f"    ! {row['error']}")
        lines.append(f"    found:   {_names(row['found'], names)}")
        lines.append(f"    missing: {_names(row['missing'], names)}")
    count = len(report['per_seed'])
    lines.append('')
    lines.append(f"{count} seeds, hits@{report['top_n']} {report['hits_at_n']:.3f}, "
                 f"mrr {report['mrr']:.3f}, {report['requests']} requests")
    return '\n'.join(lines)


def format_comparison(diff, label='baseline'):
    lines = [f"vs {label}", f"{'seed':<40} {'before':>6} {'after':>6} {'delta':>6}"]
    for row in diff['per_seed']:
        before = '-' if row['before'] is None else str(row['before'])
        after = '-' if row['after'] is None else str(row['after'])
        delta = 'new' if row['delta'] is None else f"{row['delta']:+d}"
        lines.append(f"{row['seed']:<40} {before:>6} {after:>6} {delta:>6}")
    for key, name in (('hits_at_n', 'hits@N'), ('mrr', 'mrr')):
        entry = diff[key]
        lines.append(f"{name:<8} {entry['before']:.3f} -> {entry['after']:.3f} "
                     f"({entry['delta']:+.3f})")
    top = diff['top_n']
    if top['before'] is not None and top['before'] != top['after']:
        lines.append(f"! baseline used top {top['before']}, this run top {top['after']}")
    return '\n'.join(lines)


# ---------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------

def _seed_progress(index, total, seed_text):
    sys.stderr.write(f'[{index + 1}/{total}] {seed_text}\n')
    sys.stderr.flush()


def _use_utf8_output():
    """Same fix as cli.py: a cp1252 console cannot print half these names."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding='utf-8', errors='replace')
        except (AttributeError, ValueError):
            pass


def build_parser():
    parser = argparse.ArgumentParser(
        prog='radius.eval',
        description='Score the engine against the golden set: hits@N and MRR per seed.',
    )
    parser.add_argument('-n', '--top', type=int, default=25, help='Results per seed.')
    parser.add_argument('--seed', action='append', metavar='TEXT',
                        help='Only seeds whose text contains this. Repeatable.')
    parser.add_argument('--save', metavar='PATH', help='Write the report as JSON.')
    parser.add_argument('--compare', metavar='PATH',
                        help='Diff this run against a report saved with --save.')
    parser.add_argument('--quiet', action='store_true', help='No progress output.')
    return parser


def main(argv=None):
    _use_utf8_output()
    parser = build_parser()
    args = parser.parse_args(argv)
    if not select_seeds(args.seed):
        parser.error(f"no golden seed matches {', '.join(args.seed)}")

    report = evaluate(top_n=args.top, seeds=args.seed,
                      progress=None if args.quiet else _seed_progress)
    print(format_table(report))

    if args.compare:
        print()
        print(format_comparison(compare_reports(report, load_report(args.compare)),
                                label=args.compare))
    if args.save:
        save_report(report, args.save)
        print(f'\nWrote {args.save}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
