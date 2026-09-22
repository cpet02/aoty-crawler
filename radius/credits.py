"""Pure functions over raw API payloads: who made a record, and where.

The "connection" axes in DESIGN.md (personnel, circle) need the people
around an album, not just its tags: members and side projects from a
MusicBrainz artist lookup, producers, engineers, guests and studios from a
release lookup, and whatever Wikidata, Deezer, Discogs and Last.fm add on
top. Every function here takes one raw client payload and returns a plain
dict in the shape INTERFACES.md fixes, so the parsing can be tested against
saved responses (tests/fixtures) without a client in sight, and so the
engine never has to know a MusicBrainz field name.

Two decisions worth knowing about:

* People are keyed by `person_key(name)`, not by mbid. MusicBrainz, Wikidata
  and Discogs each have their own ids and none of them link to the others
  for a producer, so the only key that lets "Steve Albini" from one source
  match "Steve Albini" from another is a normalised name. Mbids are kept
  alongside for display links.
* Nothing here raises on missing data. A `{}`, a `None`, a missing key or a
  null value all produce the documented shape with empty defaults, because
  the engine calls these on whatever the wild returns.
"""

import re
import statistics
import unicodedata
from collections import Counter

# ---------------------------------------------------------------------------
# Small tolerant accessors
# ---------------------------------------------------------------------------

def _dict(value):
    return value if isinstance(value, dict) else {}


def _list(value):
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    # Last.fm-style "one item is a dict, none is ''" lists.
    if isinstance(value, dict):
        return [value]
    return []


def _int(value, default=0):
    try:
        if value is None or value == '':
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _float(value):
    try:
        if value is None or value == '' or isinstance(value, bool):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _text(value):
    return value if isinstance(value, str) else ''


def _mean(values):
    return sum(values) / len(values) if values else None


def _spread(values):
    return statistics.pstdev(values) if len(values) >= 2 else (0.0 if values else None)


# ---------------------------------------------------------------------------
# Names
# ---------------------------------------------------------------------------

_PUNCTUATION = re.compile(r'[^\w\s]')
_SPACES = re.compile(r'\s+')
# 'Polydor' and 'Polydor Records' are one label; so are 'Touch and Go' and
# 'Touch and Go Records'. Nobody is called 'X Records', so the suffix can go
# from every key without harming a person's name.
_LABEL_SUFFIX = re.compile(r'\s+(?:records|recordings|record co|record company|music)$')


def person_key(name):
    """Casefold, strip diacritics (NFKD), turn punctuation into spaces,
    collapse spaces, drop a leading 'the ' and a trailing ' records'.
    albums.py carries the same recipe as _person_key because it must not
    import this module; keep the two identical."""
    if not name:
        return ''
    text = unicodedata.normalize('NFKD', str(name))
    text = ''.join(ch for ch in text if not unicodedata.combining(ch))
    text = _PUNCTUATION.sub(' ', text.casefold())
    text = _SPACES.sub(' ', text).strip()
    if text.startswith('the '):
        text = text[4:]
    stripped = _LABEL_SUFFIX.sub('', text)
    return stripped or text


# ---------------------------------------------------------------------------
# Dates, ratings, url relations (shared by the MusicBrainz parsers)
# ---------------------------------------------------------------------------

_DATE_WORST = (9999, 99, 99)


def _date_tuple(value):
    """'1991' -> (1991, 0, 0); '1991-03-15' -> (1991, 3, 15); missing or
    unparseable -> a tuple that sorts after every real date."""
    if not isinstance(value, str) or not value.strip():
        return _DATE_WORST
    parts = []
    for piece in value.strip().split('-')[:3]:
        if not piece.isdigit():
            break
        parts.append(int(piece))
    if not parts:
        return _DATE_WORST
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts)


def _year_of(value):
    parsed = _date_tuple(value)
    return parsed[0] if parsed != _DATE_WORST else None


def _rating_value(rating):
    return _float(_dict(rating).get('value'))


def _ranked_names(entries):
    """[{name, count}] -> names by count descending, ties alphabetical."""
    counted = {}
    for entry in _list(entries):
        entry = _dict(entry)
        name = _text(entry.get('name')).strip()
        if not name:
            continue
        counted[name] = max(counted.get(name, 0), _int(entry.get('count')))
    return [name for name, _ in sorted(counted.items(), key=lambda item: (-item[1], item[0]))]


def _url_relations(relations):
    """[(type, url)] for every url-rel in a MusicBrainz relations list."""
    found = []
    for relation in _list(relations):
        relation = _dict(relation)
        if relation.get('target-type') not in (None, 'url'):
            continue
        url = _text(_dict(relation.get('url')).get('resource'))
        rtype = _text(relation.get('type'))
        if url and rtype:
            found.append((rtype, url))
    return found


def _links(url_relations):
    links = {}
    for rtype, url in url_relations:
        links.setdefault(rtype, url)
    return links


_WIKIDATA_ID = re.compile(r'/(?:wiki|entity)/(Q\d+)')
_DISCOGS_MASTER_ID = re.compile(r'/master/(\d+)')


def _first_match(pattern, urls):
    for url in urls:
        match = pattern.search(url)
        if match:
            return match.group(1)
    return ''


# ---------------------------------------------------------------------------
# Release groups
# ---------------------------------------------------------------------------

_HOME_COUNTRIES = frozenset({'US', 'GB', 'XW', 'XE'})


def _format_rank(fmt):
    text = _text(fmt).casefold()
    if not text:
        return 2
    if 'cd' in text:
        return 0
    if text == 'digital media':
        return 1
    if 'vinyl' in text or 'flexi' in text or 'shellac' in text:
        return 3
    return 2


def _release_media(release):
    return [medium for medium in _list(_dict(release).get('media')) if isinstance(medium, dict)]


def _release_track_count(release):
    return sum(_int(medium.get('track-count')) for medium in _release_media(release))


def _release_format_rank(release):
    ranks = [_format_rank(medium.get('format')) for medium in _release_media(release)]
    return min(ranks) if ranks else 2


def canonical_release_order(rg_payload):
    """Release ids, best first, for picking the edition whose tracklist and
    credits stand for the album.

    Official beats everything else; then the track count closest to what
    most official editions have (so a box set with 41 tracks never stands
    for a 6-track record); then CD, digital, other, vinyl (CD tracklists are
    the cleanest in MusicBrainz); then the earliest date; then a release in
    a major market. Dates are compared as (y, m, d) tuples with missing
    parts as 0 and a missing date sorting last.
    """
    releases = [
        release for release in _list(_dict(rg_payload).get('releases'))
        if isinstance(release, dict) and _text(release.get('id'))
    ]
    if not releases:
        return []
    official = [release for release in releases if release.get('status') == 'Official']
    counts = Counter(
        count for count in (_release_track_count(r) for r in (official or releases)) if count > 0
    )
    modal = counts.most_common(1)[0][0] if counts else 0

    def rank(release):
        return (
            release.get('status') != 'Official',
            abs(_release_track_count(release) - modal),
            _release_format_rank(release),
            _date_tuple(release.get('date')),
            _text(release.get('country')) not in _HOME_COUNTRIES,
        )

    ordered, seen = [], set()
    for release in sorted(releases, key=rank):
        if release['id'] not in seen:
            seen.add(release['id'])
            ordered.append(release['id'])
    return ordered


def release_group_facts(rg_payload):
    rg = _dict(rg_payload)
    releases = [r for r in _list(rg.get('releases')) if isinstance(r, dict)]
    first = _text(rg.get('first-release-date'))
    url_rels = _url_relations(rg.get('relations'))
    urls = [url for _, url in url_rels]
    rating = _dict(rg.get('rating'))
    return {
        'first_release_date': first,
        'year': _year_of(first),
        'primary_type': _text(rg.get('primary-type')),
        'secondary_types': [t for t in _list(rg.get('secondary-types')) if isinstance(t, str)],
        'editions': len(releases),
        'release_countries': sorted({_text(r.get('country')) for r in releases} - {''}),
        'mb_genres': _ranked_names(rg.get('genres')),
        'mb_rating': _rating_value(rating),
        'mb_rating_votes': _int(rating.get('votes-count')),
        'wikidata_id': _first_match(_WIKIDATA_ID, urls),
        'discogs_master_id': _first_match(_DISCOGS_MASTER_ID, urls),
        'links': _links(url_rels),
    }


# ---------------------------------------------------------------------------
# Releases: tracklist shape and the production circle
# ---------------------------------------------------------------------------

def _release_tracks(release):
    """(medium, track, recording) for every track, in order."""
    for medium in _release_media(release):
        for track in _list(medium.get('tracks')):
            if isinstance(track, dict):
                yield medium, track, _dict(track.get('recording'))


def release_shape(release_payload):
    release = _dict(release_payload)
    media = _release_media(release)
    titles, lengths, recording_mbids, formats = [], [], [], []
    for medium in media:
        fmt = _text(medium.get('format'))
        if fmt and fmt not in formats:
            formats.append(fmt)
    for _, track, recording in _release_tracks(release):
        titles.append(_text(track.get('title')) or _text(recording.get('title')))
        lengths.append(_int(track.get('length')) or _int(recording.get('length')))
        # Tracks without a recording id are useless downstream (they are what
        # the co-listening lookup is keyed on), so they are skipped rather
        # than left as blanks.
        if _text(recording.get('id')):
            recording_mbids.append(recording['id'])
    positive = [length for length in lengths if length > 0]
    runtime_ms = sum(positive)
    mean_ms = runtime_ms / len(positive) if positive else 0.0
    spread = statistics.pstdev(positive) / mean_ms if len(positive) >= 2 and mean_ms > 0 else 0.0
    return {
        'release_mbid': _text(release.get('id')),
        'status': _text(release.get('status')),
        'date': _text(release.get('date')),
        'country': _text(release.get('country')),
        'barcode': _text(release.get('barcode')),
        'packaging': _text(release.get('packaging')),
        'formats': formats,
        'disc_count': len(media),
        'track_count': len(titles),
        'titles': titles,
        'lengths_ms': lengths,
        'recording_mbids': recording_mbids,
        'runtime_seconds': int(round(runtime_ms / 1000.0)),
        'mean_track_seconds': mean_ms / 1000.0,
        'track_length_spread': spread,
    }


_ENGINEER_TYPES = frozenset({
    'engineer', 'recording', 'mix', 'mastering', 'sound', 'audio',
    'programming', 'remixer',
})
_PERFORMER_TYPES = frozenset({
    'performer', 'instrument', 'vocal', 'orchestra', 'performing orchestra',
    'conductor', 'chorus master', 'concertmaster',
})
# Place relations that describe manufacturing rather than making the record.
_MANUFACTURING_PLACE_TYPES = frozenset({
    'manufactured at', 'pressed at', 'printed at', 'glass mastered at',
})


def _credited_artists(release):
    """(ids, types) of every artist in the release and track artist credits."""
    ids, types = set(), []
    credits = list(_list(release.get('artist-credit')))
    for _, track, _ in _release_tracks(release):
        credits.extend(_list(track.get('artist-credit')))
    for entry in credits:
        artist = _dict(_dict(entry).get('artist'))
        if _text(artist.get('id')):
            ids.add(artist['id'])
            types.append(_text(artist.get('type')))
    return ids, types


def release_circle(release_payload):
    """Labels, producers, engineers, guest performers and studios.

    Credits live on the recordings, so the same (type, artist) shows up once
    per track; they are aggregated by artist id. Guests are the hard part:
    a record credited to a band lists its members' instruments the same way
    as a guest's, and the release payload does not know who the members
    are. MusicBrainz flags guests with a 'guest' attribute, so on a
    band-credited release only those count; on a release credited to
    people, everyone not in the credit is a guest.
    """
    release = _dict(release_payload)
    credited_ids, credited_types = _credited_artists(release)
    solo_credit = bool(credited_ids) and all(t == 'Person' for t in credited_types)

    labels, catalog_numbers = {}, []
    for info in _list(release.get('label-info')):
        info = _dict(info)
        name = _text(_dict(info.get('label')).get('name')).strip()
        if name:
            labels.setdefault(person_key(name), name)
        catno = _text(info.get('catalog-number')).strip()
        if catno and catno not in catalog_numbers:
            catalog_numbers.append(catno)

    producers, engineers, performers, studios = {}, {}, {}, {}
    credits = {}

    def take(relation, level):
        relation = _dict(relation)
        target = relation.get('target-type')
        rtype = _text(relation.get('type'))
        if not rtype or target not in ('artist', 'place'):
            return
        entity = _dict(relation.get(target))
        name = _text(entity.get('name')).strip()
        if not name:
            return
        mbid = _text(entity.get('id'))
        attributes = [a for a in _list(relation.get('attributes')) if isinstance(a, str)]
        entry = credits.setdefault((level, rtype, mbid or name), {
            'role': rtype, 'name': name, 'mbid': mbid, 'level': level,
            'source': 'musicbrainz', 'attributes': [],
        })
        for attribute in attributes:
            if attribute not in entry['attributes']:
                entry['attributes'].append(attribute)
        key = person_key(name)
        if target == 'place':
            if rtype not in _MANUFACTURING_PLACE_TYPES:
                studios.setdefault(key, name)
        elif rtype == 'producer':
            producers.setdefault(key, name)
        elif rtype in _ENGINEER_TYPES:
            engineers.setdefault(key, name)
        elif rtype in _PERFORMER_TYPES:
            if mbid not in credited_ids and ('guest' in attributes or solo_credit):
                performers.setdefault(key, name)

    for relation in _list(release.get('relations')):
        take(relation, 'release')
    for _, _, recording in _release_tracks(release):
        for relation in _list(recording.get('relations')):
            take(relation, 'recording')

    return {
        'labels': labels,
        'catalog_numbers': catalog_numbers,
        'producers': producers,
        'engineers': engineers,
        'performers': performers,
        'studios': studios,
        'credits': list(credits.values()),
    }


# ---------------------------------------------------------------------------
# Artists: the personnel graph
# ---------------------------------------------------------------------------

# When the same artist appears under several relation types, keep the one
# that says the most about shared identity.
_PEOPLE_RELATION_PRIORITY = {
    'is person': 0, 'member of band': 1, 'founder': 2, 'subgroup': 3,
    'collaboration': 4, 'supporting musician': 5,
    'instrumental supporting musician': 6, 'vocal supporting musician': 7,
}


def artist_personnel(artist_payload):
    artist = _dict(artist_payload)
    life = _dict(artist.get('life-span'))
    people, links = {}, {}
    for relation in _list(artist.get('relations')):
        relation = _dict(relation)
        target = relation.get('target-type')
        rtype = _text(relation.get('type'))
        if target == 'url':
            url = _text(_dict(relation.get('url')).get('resource'))
            if rtype and url:
                links.setdefault(rtype, url)
            continue
        if target != 'artist' or rtype not in _PEOPLE_RELATION_PRIORITY:
            continue
        other = _dict(relation.get('artist'))
        mbid = _text(other.get('id'))
        if not mbid:
            continue
        current = people.get(mbid)
        if current is not None and (
            _PEOPLE_RELATION_PRIORITY[current['relation']] <= _PEOPLE_RELATION_PRIORITY[rtype]
        ):
            continue
        people[mbid] = {
            'name': _text(other.get('name')),
            'relation': rtype,
            'type': _text(other.get('type')),
        }
    tags = []
    for entry in _list(artist.get('tags')):
        entry = _dict(entry)
        if _text(entry.get('name')):
            tags.append({'name': entry['name'], 'count': _int(entry.get('count'))})
    tags.sort(key=lambda entry: (-entry['count'], entry['name']))
    return {
        'mbid': _text(artist.get('id')),
        'name': _text(artist.get('name')),
        'type': _text(artist.get('type')),
        'gender': _text(artist.get('gender')),
        'area': _text(_dict(artist.get('area')).get('name')),
        'begin_year': _year_of(life.get('begin')),
        'end_year': _year_of(life.get('end')),
        'people': people,
        'links': links,
        'mb_genres': _ranked_names(artist.get('genres')),
        'tags': tags,
    }


# ---------------------------------------------------------------------------
# Deezer
# ---------------------------------------------------------------------------

_EDITION_WORDS = r'(?:remaster(?:ed)?|deluxe|expanded|anniversary|edition|reissue|bonus|special|legacy|version)'
_EDITION_NOISE = re.compile(r'\b' + _EDITION_WORDS + r'\b', re.IGNORECASE)
_EDITION_PARENTHETICAL = re.compile(
    r'\s*[\(\[][^\)\]]*\b' + _EDITION_WORDS + r'\b[^\)\]]*[\)\]]', re.IGNORECASE)
_EDITION_SUFFIX = re.compile(
    r'\s*[-\u2013\u2014:]\s*(?:deluxe|expanded|remaster(?:ed)?|anniversary)\b.*$', re.IGNORECASE)


def _album_title_key(title):
    text = _EDITION_PARENTHETICAL.sub(' ', _text(title))
    text = _EDITION_SUFFIX.sub('', text)
    return person_key(text)


def match_deezer_album(hits, artist, title, track_count=None):
    """The search hit that is this album: same artist (normalised), same
    title once edition noise is stripped, not a remaster/deluxe unless the
    seed title is one, and by preference the edition with the canonical
    track count and record_type 'album'. Order in the response is not
    trusted because Deezer ranked a 20-track remaster above the original.
    """
    if isinstance(hits, dict):
        hits = hits.get('data')
    want_artist = person_key(artist)
    want_title = _album_title_key(title)
    seed_is_edition = bool(_EDITION_NOISE.search(_text(title)))
    best, best_rank = None, None
    for hit in _list(hits):
        hit = _dict(hit)
        hit_artist = person_key(_dict(hit.get('artist')).get('name'))
        if want_artist and hit_artist != want_artist:
            continue
        hit_title = _text(hit.get('title'))
        if want_title and _album_title_key(hit_title) != want_title:
            continue
        if _EDITION_NOISE.search(hit_title) and not seed_is_edition:
            continue
        tracks = _int(hit.get('nb_tracks'))
        hit_is_edition = bool(_EDITION_NOISE.search(hit_title))
        rank = (
            0 if not track_count or tracks == track_count else 1,
            abs(tracks - track_count) if track_count else 0,
            hit_is_edition != seed_is_edition,
            0 if _text(hit.get('record_type')).casefold() == 'album' else 1,
        )
        if best_rank is None or rank < best_rank:
            best, best_rank = hit, rank
    return best


def deezer_facts(album_payload, track_payloads=()):
    album = _dict(album_payload)
    genres = []
    for genre in _list(_dict(album.get('genres')).get('data')):
        name = _text(_dict(genre).get('name'))
        if name and name not in genres:
            genres.append(name)
    bpms, gains = [], []
    for track in _list(track_payloads):
        track = _dict(track)
        bpm = _float(track.get('bpm'))
        gain = _float(track.get('gain'))
        analysed = bpm is not None and bpm > 0
        if analysed:
            bpms.append(bpm)
        # An unanalysed track reports 0 for both; a 0 dB gain next to a real
        # bpm is a genuine measurement.
        if gain is not None and (gain != 0 or analysed):
            gains.append(gain)
    explicit = album.get('explicit_lyrics')
    return {
        'deezer_id': _int(album.get('id')) or None,
        'fans': _int(album.get('fans')),
        'explicit': explicit if isinstance(explicit, bool) else None,
        'label': _text(album.get('label')),
        'release_date': _text(album.get('release_date')),
        'genres': genres,
        'nb_tracks': _int(album.get('nb_tracks')),
        'duration': _int(album.get('duration')),
        'url': _text(album.get('link')),
        'bpm_mean': _mean(bpms),
        'bpm_spread': _spread(bpms),
        'gain_mean': _mean(gains),
        'gain_spread': _spread(gains),
        'tracks_with_bpm': len(bpms),
    }


# ---------------------------------------------------------------------------
# Wikidata
# ---------------------------------------------------------------------------

# Reviewer Q-id -> the scale a bare number is out of. AllMusic, Album of the
# Year, Metacritic, Pitchfork, Rolling Stone, NME, The Guardian.
REVIEWER_SCALES = {
    'Q31181': 5, 'Q48989591': 100, 'Q150248': 100, 'Q1097006': 10,
    'Q33511': 5, 'Q1044417': 10, 'Q11148': 5,
}

_LETTER_GRADES = {
    'a+': 1.0, 'a': 0.95, 'a-': 0.9, 'b+': 0.85, 'b': 0.8, 'b-': 0.75,
    'c+': 0.7, 'c': 0.65, 'c-': 0.6, 'd+': 0.55, 'd': 0.5, 'd-': 0.45,
    'f': 0.1,
}
_NUMBER = r'(\d+(?:[.,]\d+)?)'
_FRACTION = re.compile(r'^' + _NUMBER + r'\s*(?:/|out of|of)\s*' + _NUMBER + r'(?:\s*stars?)?$')
_PERCENT = re.compile(r'^' + _NUMBER + r'\s*%$')
_STAR_COUNT = re.compile(r'^' + _NUMBER + r'\s*(\u00bd)?\s*stars?$')
_BARE_NUMBER = re.compile(r'^' + _NUMBER + r'$')
_LETTER = re.compile(r'^([a-f])\s*([+\-\u2212])?$')
_BLACK_STARS = '\u2605\u2b50'
_STAR_GLYPHS = _BLACK_STARS + '\u2606'
_HALF_STAR = '\u00bd'


def _number(text):
    return float(text.replace(',', '.'))


def _unit(value):
    return max(0.0, min(1.0, round(value, 4)))


def parse_review_score(text, reviewer_qid=None):
    """A Wikidata review score string as a 0..1 fraction, or None when the
    text is a verdict ('favorable') rather than a number. A bare number is
    read against the reviewer's known scale, else the smallest of /5, /10,
    /100 that fits."""
    if text is None or isinstance(text, bool):
        return None
    raw = str(text).strip()
    if not raw:
        return None
    lowered = raw.casefold().replace('\u2044', '/')
    if any(star in raw for star in _STAR_GLYPHS):
        # Filled stars count, hollow ones are the unfilled remainder.
        stars = sum(raw.count(star) for star in _BLACK_STARS) + 0.5 * raw.count(_HALF_STAR)
        return _unit(stars / 5.0) if stars > 0 else None
    match = _FRACTION.match(lowered)
    if match:
        denominator = _number(match.group(2))
        return _unit(_number(match.group(1)) / denominator) if denominator > 0 else None
    match = _PERCENT.match(lowered)
    if match:
        return _unit(_number(match.group(1)) / 100.0)
    match = _STAR_COUNT.match(lowered)
    if match:
        stars = _number(match.group(1)) + (0.5 if match.group(2) else 0.0)
        return _unit(stars / 5.0)
    match = _LETTER.match(lowered)
    if match:
        grade = match.group(1) + (match.group(2) or '').replace('\u2212', '-')
        return _LETTER_GRADES.get(grade)
    match = _BARE_NUMBER.match(lowered)
    if match:
        value = _number(match.group(1))
        scale = REVIEWER_SCALES.get(reviewer_qid)
        if scale and value <= scale:
            return _unit(value / scale)
        for scale in (5, 10, 100):
            if value <= scale:
                return _unit(value / scale)
    return None


def _statements(claims, prop):
    """Non-deprecated statements for a property, preferred rank first."""
    statements = [
        statement for statement in _list(_dict(claims).get(prop))
        if isinstance(statement, dict) and statement.get('rank') != 'deprecated'
    ]
    statements.sort(key=lambda statement: statement.get('rank') != 'preferred')
    return statements


def _snak_value(snak):
    snak = _dict(snak)
    if snak.get('snaktype', 'value') != 'value':
        return None
    return _dict(snak.get('datavalue')).get('value')


def _item_id(value):
    return _text(_dict(value).get('id'))


def _qualifier_values(statement, prop):
    return [_snak_value(snak) for snak in _list(_dict(_dict(statement).get('qualifiers')).get(prop))]


def _item_ids(claims, prop):
    found = []
    for statement in _statements(claims, prop):
        qid = _item_id(_snak_value(statement.get('mainsnak')))
        if qid and qid not in found:
            found.append(qid)
    return found


def _first_string(claims, prop):
    for statement in _statements(claims, prop):
        value = _snak_value(statement.get('mainsnak'))
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ''


def _time_text(value):
    """'+1991-03-27T00:00:00Z' at precision 11/10/9 -> '1991-03-27' /
    '1991-03' / '1991'."""
    value = _dict(value)
    match = re.match(r'^[+-]?(\d+)-(\d{2})-(\d{2})', _text(value.get('time')))
    if not match:
        return ''
    year, month, day = match.groups()
    precision = _int(value.get('precision'), 11)
    if precision >= 11:
        return '%s-%s-%s' % (year.zfill(4), month, day)
    if precision == 10:
        return '%s-%s' % (year.zfill(4), month)
    return year.zfill(4)


_DURATION_UNIT_SECONDS = {'Q11574': 1, 'Q7727': 60, 'Q25235': 3600}


def _duration_seconds(value):
    value = _dict(value)
    amount = _float(value.get('amount'))
    unit = _text(value.get('unit')).rstrip('/').rsplit('/', 1)[-1]
    factor = _DURATION_UNIT_SECONDS.get(unit)
    if amount is None or factor is None:
        return None
    return int(round(amount * factor))


def wikidata_facts(entity):
    entity = _dict(entity)
    claims = _dict(entity.get('claims'))
    critic_scores, for_mean = {}, []
    for statement in _statements(claims, 'P444'):
        text = _snak_value(statement.get('mainsnak'))
        reviewer = next((qid for qid in map(_item_id, _qualifier_values(statement, 'P447')) if qid), '')
        score = parse_review_score(text, reviewer or None) if isinstance(text, str) else None
        if score is None or not reviewer:
            continue
        critic_scores.setdefault(reviewer, score)
        # P7887 (number of reviews) marks an aggregate such as an Album of
        # the Year user average, which would swamp the individual verdicts.
        if not _qualifier_values(statement, 'P7887'):
            for_mean.append(score)
    publication = ''
    for statement in _statements(claims, 'P577'):
        publication = _time_text(_snak_value(statement.get('mainsnak')))
        if publication:
            break
    duration = None
    for statement in _statements(claims, 'P2047'):
        duration = _duration_seconds(_snak_value(statement.get('mainsnak')))
        if duration is not None:
            break
    return {
        'critic_scores': critic_scores,
        'acclaim': _mean(for_mean),
        'spotify_id': _first_string(claims, 'P2205'),
        'discogs_master_id': _first_string(claims, 'P1954'),
        'allmusic_id': _first_string(claims, 'P1729'),
        'aoty_id': _first_string(claims, 'P7067'),
        'lastfm_id': _first_string(claims, 'P3192'),
        'publication_date': publication,
        'duration_seconds': duration,
        'producer_qids': _item_ids(claims, 'P162'),
        'label_qids': _item_ids(claims, 'P264'),
        'genre_qids': _item_ids(claims, 'P136'),
        'performer_qids': _item_ids(claims, 'P175'),
        'enwiki_title': _text(_dict(_dict(entity.get('sitelinks')).get('enwiki')).get('title')),
    }


# ---------------------------------------------------------------------------
# Discogs
# ---------------------------------------------------------------------------

# Discogs disambiguates duplicate names with a numeric suffix: 'Touch And Go
# Records (2)'. It is never part of the name.
_DISCOGS_SUFFIX = re.compile(r'\s*\(\d+\)\s*$')
_DISCOGS_BRACKETS = re.compile(r'\s*\[[^\]]*\]')
_PRODUCER_ROLE = re.compile(r'^(?:(?:co|additional|associate|vocal|vocals|music|recording)[ -]?)?producer$')
_ENGINEER_ROLES = frozenset({
    'mixed by', 'mastered by', 'recorded by', 'remix', 'remixed by',
    'mix', 'mixing', 'mastering', 'recording', 'programmed by',
})


def _discogs_name(value):
    return _DISCOGS_SUFFIX.sub('', _text(value)).strip()


def _discogs_roles(role_text):
    """'Drums [Uncredited], Vocals [Uncredited]' -> ['drums', 'vocals']."""
    text = _DISCOGS_BRACKETS.sub('', _text(role_text))
    return [piece.strip().casefold() for piece in text.split(',') if piece.strip()]


def _is_engineer_role(role):
    return role in _ENGINEER_ROLES or 'engineer' in role


def discogs_facts(master_payload, release_payload=None):
    master = _dict(master_payload)
    release = _dict(release_payload)
    community = _dict(release.get('community'))
    rating = _dict(community.get('rating'))
    producers, engineers = {}, {}
    for extra in _list(release.get('extraartists')):
        extra = _dict(extra)
        name = _discogs_name(extra.get('name'))
        if not name:
            continue
        key = person_key(name)
        for role in _discogs_roles(extra.get('role')):
            if _PRODUCER_ROLE.match(role):
                producers.setdefault(key, name)
            elif _is_engineer_role(role):
                engineers.setdefault(key, name)
    formats = []
    for fmt in _list(release.get('formats')):
        name = _text(_dict(fmt).get('name'))
        if name and name not in formats:
            formats.append(name)
    labels = [_discogs_name(_dict(label).get('name')) for label in _list(release.get('labels'))]
    labels = [label for label in labels if label]
    year = _int(master.get('year')) or _int(release.get('year')) or _year_of(_text(release.get('released')))
    lowest = _float(master.get('lowest_price'))
    if lowest is None:
        lowest = _float(release.get('lowest_price'))
    return {
        'styles': [s for s in _list(master.get('styles') or release.get('styles')) if isinstance(s, str)],
        'genres': [g for g in _list(master.get('genres') or release.get('genres')) if isinstance(g, str)],
        'year': year or None,
        'main_release_id': _int(master.get('main_release')) or _int(release.get('id')) or None,
        'have': _int(community.get('have')),
        'want': _int(community.get('want')),
        'rating': _float(rating.get('average')),
        'rating_votes': _int(rating.get('count')),
        'num_for_sale': _int(master.get('num_for_sale')) or _int(release.get('num_for_sale')),
        'lowest_price': lowest,
        'formats': formats,
        'label': labels[0] if labels else '',
        'country': _text(release.get('country')),
        'url': _text(master.get('uri')) or _text(release.get('uri')),
        'producers': producers,
        'engineers': engineers,
    }


# ---------------------------------------------------------------------------
# Last.fm
# ---------------------------------------------------------------------------

def lastfm_facts(album_payload):
    album = _dict(album_payload)
    # Accept the whole response body as well as the 'album' object inside.
    if isinstance(album.get('album'), dict):
        album = album['album']
    return {
        'lastfm_listeners': _int(album.get('listeners')),
        'lastfm_playcount': _int(album.get('playcount')),
        'lastfm_url': _text(album.get('url')),
    }
