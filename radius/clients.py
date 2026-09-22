"""Rate-limited, cached clients for the six JSON services Radius reads.

Four of them are keyless — MusicBrainz, ListenBrainz, Wikidata and Deezer
serve this data to anyone who sends an honest User-Agent — and the other two
only add on top: a Last.fm key unlocks its crowd tags and charts, a Discogs
token merely raises Discogs' keyless rate. No scraping anywhere.

* MusicBrainzClient  the canonical catalogue: resolving an album to an mbid,
                     searching release groups by tag, and the deep lookups
                     (release group, release, artist) that carry credits and
                     personnel. One request per second, their hard limit, so
                     this is the expensive client and is used sparingly.
* ListenBrainzClient listening data and MusicBrainz metadata in bulk, plus
                     the labs similarity endpoints (artists, recordings).
* WikidataClient     entity claims in batches of 50: review scores, ids,
                     producers and labels as Q-ids, and their labels.
* DeezerClient       fans, explicit flag, per-track BPM and loudness.
* DiscogsClient      styles, have/want counts, community rating.
* LastFmClient       tags, similar artists, tag charts, album listeners.

Every response goes through the disk cache first, so a repeated query costs
nothing and the network is touched once per fact — including "no such
thing" answers, which are cached as an empty body so a miss is never asked
twice.

Threading: each client keeps its own requests.Session and is safe to call
from several threads at once. The spacing limiter holds a lock, the cache
holds a lock, and nothing else here is shared mutable state (the counters
are informational). The engine runs one worker thread per service, which is
what keeps MusicBrainz serial at 1 rps while the others proceed in parallel.
"""

import os
import threading
import time

import requests

from . import config
from .cache import Cache


class ApiError(RuntimeError):
    pass


class RateLimited(ApiError):
    """The service asked us to slow down and kept asking."""


class KeyRejected(ApiError):
    """The service refused our API key; nothing about the request itself is
    at fault, so the answer must never be cached against it."""


class _RateLimiter:
    """Simple spacing limiter: never issue two requests closer together than
    1/rps. Shared across threads because Streamlit reruns are threaded."""

    def __init__(self, requests_per_second):
        self.min_interval = 1.0 / max(requests_per_second, 0.01)
        self._lock = threading.Lock()
        self._last = 0.0

    def wait(self):
        with self._lock:
            elapsed = time.monotonic() - self._last
            if elapsed < self.min_interval:
                time.sleep(self.min_interval - elapsed)
            self._last = time.monotonic()


def _header(response, name):
    """A response header by name, tolerant of plain-dict headers (tests) as
    well as requests' case-insensitive ones."""
    headers = getattr(response, 'headers', None) or {}
    value = headers.get(name)
    if value is None:
        wanted = name.lower()
        for key, candidate in headers.items():
            if str(key).lower() == wanted:
                return candidate
    return value


# The longest we will sleep because a service's rate headers say the window
# is exhausted. ListenBrainz windows are ~10 s; anything longer than this
# means the headers are wrong and we would rather retry than hang.
_RATE_HEADER_SLEEP_CAP = 15.0


class _HttpClient:
    """Shared request plumbing: identify ourselves, respect the limiter, back
    off on throttling instead of hammering through it.

    Subclasses set `rate` and may set `extra_headers` (merged into every
    request), `json_error_statuses` (HTTP statuses whose JSON body carries
    the service's own error code and should be inspected rather than raised)
    and override `_body_problem` for services that signal errors inside
    otherwise-successful responses.
    """

    rate = 1.0
    extra_headers = {}
    json_error_statuses = ()

    def __init__(self, cache=None, session=None, rate=None, extra_headers=None):
        self.cache = cache or Cache()
        self.session = session or requests.Session()
        self.limiter = _RateLimiter(rate or self.rate)
        self.extra_headers = dict(self.extra_headers, **(extra_headers or {}))
        self.calls_made = 0
        self.cache_hits = 0

    def _body_problem(self, body):
        """Classify a parsed body: None when it is a real answer, 'retry' when
        the service is asking us to back off (counts against MAX_RETRIES,
        RateLimited when exhausted), 'empty' when the service says there is
        no such thing (the caller gets {} and the miss is cached). May raise
        ApiError for a body that must not be cached at all."""
        return None

    def _honour_rate_headers(self, response):
        if str(_header(response, 'X-RateLimit-Remaining') or '').strip() != '0':
            return
        try:
            reset_in = float(_header(response, 'X-RateLimit-Reset-In'))
        except (TypeError, ValueError):
            reset_in = 1.0
        time.sleep(max(0.0, min(reset_in, _RATE_HEADER_SLEEP_CAP)))

    def _request(self, method, url, params=None, json_body=None, expect_json=True):
        """One logical request with retries. Returns the parsed JSON body, or
        the raw text when expect_json is False. `params` may be a dict or a
        list of (key, value) tuples when a key has to repeat."""
        headers = {'User-Agent': config.USER_AGENT,
                   'Accept': 'application/json' if expect_json else 'text/plain'}
        headers.update(self.extra_headers)
        last_error = None
        for attempt in range(config.MAX_RETRIES):
            self.limiter.wait()
            try:
                response = self.session.request(
                    method, url, params=params, json=json_body,
                    timeout=config.REQUEST_TIMEOUT, headers=headers,
                )
            except requests.RequestException as exc:
                last_error = exc
                time.sleep(2 ** attempt)
                continue

            self._honour_rate_headers(response)
            status = response.status_code

            if status == 200 or status in self.json_error_statuses:
                if not expect_json and status == 200:
                    return response.text
                try:
                    body = response.json()
                except ValueError as exc:
                    raise ApiError(
                        f'non-JSON response from {url}: {response.text[:200]}'
                    ) from exc
                problem = self._body_problem(body)
                if problem == 'retry':
                    last_error = RateLimited(f'{url} asked us to back off: {body}')
                    time.sleep(min(2 ** (attempt + 1), 30))
                    continue
                if problem == 'empty':
                    return {}
                if status == 200:
                    return body
                raise ApiError(f'HTTP {status} from {url}: {response.text[:200]}')

            if status in (429, 500, 502, 503, 504):
                # Honour Retry-After when offered; otherwise back off. Being
                # asked to slow down is a reason to slow down, not to retry
                # harder — that is how an IP ends up blocked.
                wait = response.headers.get('Retry-After')
                try:
                    delay = float(wait) if wait else 2 ** (attempt + 1)
                except ValueError:
                    delay = 2 ** (attempt + 1)
                last_error = RateLimited(f'HTTP {status} from {url}')
                time.sleep(min(delay, 30))
                continue

            raise ApiError(f'HTTP {status} from {url}: {response.text[:200]}')
        raise (last_error if isinstance(last_error, ApiError)
               else ApiError(f'giving up on {url}: {last_error}'))

    def _cached(self, namespace, key_params, method, url,
                params=None, json_body=None, expect_json=True):
        """Serve from the cache or fetch and store. The key is built from
        `key_params`, never from the wire `params`, so a request whose params
        are an unordered list of tuples still keys canonically. Text bodies
        round-trip through the cache as JSON strings without any special
        handling."""
        key = Cache.make_key(namespace, key_params)
        ttl = config.TTL_DAYS.get(namespace, config.DEFAULT_TTL_DAYS)
        cached = self.cache.get(key, ttl)
        if cached is not None:
            self.cache_hits += 1
            return cached
        body = self._request(method, url, params=params, json_body=json_body,
                             expect_json=expect_json)
        self.calls_made += 1
        self.cache.put(key, body)
        return body


def _chunked(items, size):
    items = list(items)
    for start in range(0, len(items), size):
        yield items[start:start + size]


def _distinct(values):
    """Truthy values, deduplicated, first occurrence wins."""
    seen = set()
    out = []
    for value in values or ():
        if value and value not in seen:
            seen.add(value)
            out.append(value)
    return out


def _escape(value):
    """Escape the Lucene syntax MusicBrainz search would otherwise choke on."""
    out = []
    for char in str(value or ''):
        if char in '+-&|!(){}[]^"~*?:\\/':
            out.append(' ')
        else:
            out.append(char)
    return ' '.join(''.join(out).split())


def _as_list(value):
    """Last.fm's list quirk: one item arrives as a bare dict, none as ''."""
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        return [value]
    return []


class MusicBrainzClient(_HttpClient):
    """The catalogue. Held to one request per second, as they ask.

    The lookups raise ApiError on failure (a 404 for an unknown mbid
    included) rather than caching a miss, because a failed lookup is far
    more often a transient than a fact.
    """

    rate = config.MUSICBRAINZ_REQUESTS_PER_SECOND

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._genre_names = None

    def search_release_groups(self, query, limit=25, offset=0):
        body = self._cached(
            'mb.rg.search', {'q': query, 'limit': limit, 'offset': offset},
            'GET', config.MUSICBRAINZ_API_ROOT + 'release-group',
            params={'query': query, 'fmt': 'json', 'limit': limit, 'offset': offset},
        )
        return (body or {}).get('release-groups') or []

    def find_album(self, artist=None, album=None, query=None, limit=10):
        """Resolve typed-in text to candidate release groups, best first."""
        if artist and album:
            lucene = f'releasegroup:"{_escape(album)}" AND artist:"{_escape(artist)}"'
        else:
            lucene = _escape(query or '')
        results = self.search_release_groups(lucene, limit=limit)
        if not results and artist and album:
            # Fall back to loose matching when the strict field query finds
            # nothing — punctuation and subtitles trip it up constantly.
            results = self.search_release_groups(
                _escape(f'{artist} {album}'), limit=limit
            )
        return results

    def release_groups_by_tags(self, tags, limit=100, primary_type='album'):
        """Release groups carrying EVERY one of `tags` (one tag is fine).

        Conjunctions are far more on-topic than any single tag: "post-rock"
        alone is thousands of records, "post-rock" AND "slowcore" is a scene.
        """
        if isinstance(tags, str):
            tags = [tags]
        clauses = [f'tag:"{escaped}"' for escaped in (_escape(t) for t in tags) if escaped]
        if not clauses:
            return []
        if primary_type:
            clauses.append(f'primarytype:{primary_type}')
        return self.search_release_groups(' AND '.join(clauses), limit=limit)

    def _lookup(self, namespace, entity, mbid, inc):
        # `inc` is part of the key: it is what the answer answers. Widen a
        # lookup later and the old, thinner body must not be served for a
        # year in place of the one the new parser needs.
        body = self._cached(
            namespace, {'mbid': mbid, 'inc': inc},
            'GET', config.MUSICBRAINZ_API_ROOT + f'{entity}/{mbid}',
            params={'fmt': 'json', 'inc': inc},
        )
        return body if isinstance(body, dict) else {}

    def release_group(self, mbid):
        """Editions, url-rels (Wikidata / Discogs ids), genres, tags, rating."""
        return self._lookup(
            'mb.rg.full', 'release-group', mbid,
            'releases+media+url-rels+genres+tags+ratings+artist-credits',
        )

    def release(self, mbid):
        """One edition in full: tracklist with recording-level credits, labels,
        places. This is where producers, engineers and studios live."""
        return self._lookup(
            'mb.release.full', 'release', mbid,
            'recordings+artist-credits+labels+artist-rels+recording-level-rels'
            '+place-rels+media+release-groups',
        )

    def artist(self, mbid):
        """Members, side projects, collaborations, links, genres, tags."""
        return self._lookup(
            'mb.artist.full', 'artist', mbid,
            'artist-rels+url-rels+genres+tags+ratings',
        )

    def release_groups_by_artist(self, artist_mbid, limit=100):
        """An artist's release groups, as the browse endpoint serves them
        (id, title, primary-type, secondary-types, first-release-date). The
        keyless replacement for ListenBrainz's top-release-groups endpoint,
        which went auth-only in 2026; ListenBrainz's bulk popularity call
        then ranks what this returns."""
        body = self._cached(
            'mb.rg.browse', {'artist': artist_mbid, 'limit': limit},
            'GET', config.MUSICBRAINZ_API_ROOT + 'release-group',
            params={'artist': artist_mbid, 'fmt': 'json', 'limit': limit},
        )
        if not isinstance(body, dict):
            return []
        return [g for g in (body.get('release-groups') or []) if isinstance(g, dict)]

    def genre_names(self):
        """Every MusicBrainz genre name, lower-cased — the whitelist that
        decides whether a tag is a genre or a mood. Memoised per instance on
        top of the year-long cache entry; frozenset() if the fetch fails so
        callers fall back to the vendored taxonomy."""
        if self._genre_names is not None:
            return self._genre_names
        try:
            body = self._cached(
                'mb.genres', {'fmt': 'txt'},
                'GET', config.MUSICBRAINZ_API_ROOT + 'genre/all',
                params={'fmt': 'txt'}, expect_json=False,
            )
        except ApiError:
            return frozenset()
        if not isinstance(body, str):
            return frozenset()
        self._genre_names = frozenset(
            line.strip().lower() for line in body.splitlines() if line.strip()
        )
        return self._genre_names


class ListenBrainzClient(_HttpClient):
    """Listening data plus MusicBrainz metadata, in batches.

    This is where the work happens. Its metadata and popularity endpoints
    accept many mbids per request, so fingerprinting a 120-album pool costs
    single-digit requests instead of hundreds. The labs endpoints supply
    collaborative similarity for artists and recordings.
    """

    rate = config.LISTENBRAINZ_REQUESTS_PER_SECOND

    # The recording metadata endpoint caps a call at 25 mbids regardless of
    # what LB_BATCH_SIZE says; similar-recordings is capped at 10 seeds.
    RECORDING_METADATA_BATCH = 25
    SIMILAR_RECORDINGS_BATCH = 10

    def metadata(self, release_group_mbids, inc='tag artist release'):
        """{mbid: metadata} for many release groups at once.

        Tags come back at both release-group and artist level, which is what
        feeds the genre/mood vectors and the separate lineage vector.
        """
        collected = {}
        for batch in _chunked(_distinct(release_group_mbids), config.LB_BATCH_SIZE):
            body = self._cached(
                'lb.metadata', {'mbids': sorted(batch), 'inc': inc},
                'GET', config.LISTENBRAINZ_API_ROOT + '1/metadata/release_group/',
                params={'release_group_mbids': ','.join(batch), 'inc': inc},
            )
            if isinstance(body, dict):
                collected.update(body)
        return collected

    def popularity(self, release_group_mbids):
        """{mbid: {total_listen_count, total_user_count}} for many at once."""
        collected = {}
        for batch in _chunked(_distinct(release_group_mbids), config.LB_BATCH_SIZE):
            body = self._cached(
                'lb.popularity.rg', {'mbids': sorted(batch)},
                'POST', config.LISTENBRAINZ_API_ROOT + '1/popularity/release-group',
                json_body={'release_group_mbids': list(batch)},
            )
            for entry in body or []:
                if isinstance(entry, dict) and entry.get('release_group_mbid'):
                    collected[entry['release_group_mbid']] = entry
        return collected

    def artist_popularity(self, artist_mbids):
        """{mbid: counts} — the denominator for canonicity."""
        collected = {}
        for batch in _chunked(_distinct(artist_mbids), config.LB_BATCH_SIZE):
            body = self._cached(
                'lb.popularity.artist', {'mbids': sorted(batch)},
                'POST', config.LISTENBRAINZ_API_ROOT + '1/popularity/artist',
                json_body={'artist_mbids': list(batch)},
            )
            for entry in body or []:
                if isinstance(entry, dict) and entry.get('artist_mbid'):
                    collected[entry['artist_mbid']] = entry
        return collected

    def top_release_groups(self, artist_mbid):
        """An artist's most-listened albums — the candidate source that
        follows listener behaviour rather than vocabulary."""
        try:
            body = self._cached(
                'lb.top.rg', {'artist': artist_mbid},
                'GET', config.LISTENBRAINZ_API_ROOT
                + f'1/popularity/top-release-groups-for-artist/{artist_mbid}',
            )
        except ApiError:
            return []
        return body if isinstance(body, list) else []

    @staticmethod
    def _labs_entries(body):
        # The labs endpoints have returned both a bare list and a list of
        # result sets over time; take the last list of dicts either way.
        if isinstance(body, list) and body and isinstance(body[0], list):
            body = body[-1]
        return [entry for entry in (body or []) if isinstance(entry, dict)]

    def similar_artists(self, artist_mbid, algorithm=None):
        """[{artist_mbid, name, score}] — ListenBrainz's own collaborative
        similarity, computed from what people actually listen to together."""
        algorithm = algorithm or config.LB_SIMILAR_ARTIST_ALGORITHM
        try:
            body = self._cached(
                'lb.similar.artist', {'artist': artist_mbid, 'algo': algorithm},
                'GET', config.LISTENBRAINZ_LABS_ROOT + 'similar-artists/json',
                params={'artist_mbids': artist_mbid, 'algorithm': algorithm},
            )
        except ApiError:
            return []
        return self._labs_entries(body)

    def similar_recordings(self, recording_mbids, algorithm=None):
        """Recordings people play alongside the given ones, as the flat list
        of raw entries ({recording_mbid, release_mbid, score, reference_mbid,
        ...}). Seeds go 10 per call, the query key repeated per seed — the
        endpoint 400s (with an HTML body) on a comma-joined list. A chunk
        that fails is skipped, so a single bad call never empties the rest."""
        algorithm = algorithm or config.LB_SIMILAR_RECORDING_ALGORITHM
        collected = []
        for chunk in _chunked(_distinct(recording_mbids), self.SIMILAR_RECORDINGS_BATCH):
            params = [('recording_mbids', mbid) for mbid in chunk]
            params.append(('algorithm', algorithm))
            try:
                body = self._cached(
                    'lb.similar.recording', {'mbids': sorted(chunk), 'algo': algorithm},
                    'GET', config.LISTENBRAINZ_LABS_ROOT + 'similar-recordings/json',
                    params=params,
                )
            except ApiError:
                continue
            collected.extend(self._labs_entries(body))
        return collected

    def recording_metadata(self, recording_mbids, inc='artist release'):
        """{recording_mbid: raw entry} with the release (and so release group)
        each recording belongs to — how similar recordings become candidate
        albums. Missing mbids are simply absent."""
        collected = {}
        for batch in _chunked(_distinct(recording_mbids), self.RECORDING_METADATA_BATCH):
            body = self._cached(
                'lb.metadata.recording', {'mbids': sorted(batch), 'inc': inc},
                'GET', config.LISTENBRAINZ_API_ROOT + '1/metadata/recording/',
                params={'recording_mbids': ','.join(batch), 'inc': inc},
            )
            if isinstance(body, dict):
                collected.update(body)
        return collected


class WikidataClient(_HttpClient):
    """Entity claims in bulk: review scores, external ids, producer and label
    Q-ids for albums whose MusicBrainz url-rels point at Wikidata. Fifty ids
    per call is the API's own ceiling."""

    rate = config.WIKIDATA_REQUESTS_PER_SECOND
    BATCH = 50
    # MediaWiki reports its own failures inside an HTTP 200 body. Caching
    # one as "these entities do not exist" would blank the critic scores
    # and producer credits of every album in the batch for four months.
    TRANSIENT_PREFIXES = ('internal_api_error', 'readonly')
    TRANSIENT_CODES = frozenset({'maxlag', 'ratelimited', 'timeout', 'busy'})

    def _body_problem(self, body):
        if not isinstance(body, dict):
            return None
        error = body.get('error')
        if not isinstance(error, dict):
            return None
        code = str(error.get('code') or '')
        if code in self.TRANSIENT_CODES or code.startswith(self.TRANSIENT_PREFIXES):
            return 'retry'
        raise ApiError(f"Wikidata rejected the request ({code}): {error.get('info')}")

    def _entities(self, namespace, qids, props):
        collected = {}
        for batch in _chunked(_distinct(qids), self.BATCH):
            try:
                body = self._cached(
                    namespace, {'ids': sorted(batch), 'props': props},
                    'GET', config.WIKIDATA_API_ROOT,
                    params={'action': 'wbgetentities', 'ids': '|'.join(batch),
                            'props': props, 'languages': 'en',
                            'sitefilter': 'enwiki', 'format': 'json'},
                )
            except ApiError:
                continue
            for qid, entity in ((body or {}).get('entities') or {}).items():
                if isinstance(entity, dict) and 'missing' not in entity:
                    collected[qid] = entity
        return collected

    def entities(self, qids, props='claims|labels|sitelinks'):
        """{qid: raw entity}; unknown ids (which come back flagged 'missing')
        are dropped."""
        return self._entities('wikidata.entities', qids, props)

    def labels(self, qids):
        """{qid: English label} for the Q-ids that have one — how producer,
        label and reviewer ids become names."""
        collected = {}
        for qid, entity in self._entities('wikidata.labels', qids, 'labels').items():
            label = ((entity.get('labels') or {}).get('en') or {}).get('value')
            if label:
                collected[qid] = label
        return collected


class DeezerClient(_HttpClient):
    """Fans, explicit flag and per-track BPM / gain. Keyless.

    Deezer reports errors inside HTTP 200 bodies: {'error': {'code', ...}}.
    Code 4 is the quota and is retried with backoff; anything else (800 'no
    data' for a bad id, and the rest) means there is nothing there, so the
    method returns None / [] and the miss is cached like any other answer.
    """

    rate = config.DEEZER_REQUESTS_PER_SECOND
    SEARCH_LIMIT = 10

    # 4 is the quota and 700 is "service busy": both mean try again. Every
    # other code describes the request (800 no data, 500/501/600 bad
    # parameters), so the empty answer is the answer and is worth caching.
    TRANSIENT_CODES = frozenset({'4', '700'})

    def _body_problem(self, body):
        if not isinstance(body, dict) or not isinstance(body.get('error'), dict):
            return None
        return 'retry' if str(body['error'].get('code')) in self.TRANSIENT_CODES else 'empty'

    def _search(self, query):
        body = self._cached(
            'deezer.search', {'q': query, 'limit': self.SEARCH_LIMIT},
            'GET', config.DEEZER_API_ROOT + 'search/album',
            params={'q': query, 'limit': self.SEARCH_LIMIT},
        )
        data = (body or {}).get('data') if isinstance(body, dict) else None
        return [hit for hit in (data or []) if isinstance(hit, dict)]

    def search_album(self, artist, title):
        """Raw search hits for an album: the fielded query first, then plain
        text when that finds nothing (Deezer's field matching is strict about
        punctuation). Order is unreliable — the caller picks the edition."""
        artist = ' '.join(str(artist or '').replace('"', ' ').split())
        title = ' '.join(str(title or '').replace('"', ' ').split())
        if not artist and not title:
            return []
        hits = self._search(f'artist:"{artist}" album:"{title}"') if artist and title else []
        if not hits:
            hits = self._search(' '.join(part for part in (artist, title) if part))
        return hits

    def _lookup(self, namespace, entity, deezer_id):
        body = self._cached(
            namespace, {'id': str(deezer_id)},
            'GET', config.DEEZER_API_ROOT + f'{entity}/{deezer_id}',
        )
        return body if isinstance(body, dict) and body.get('id') else None

    def album(self, deezer_id):
        """The album with fans, label, genres and its track ids; None when
        Deezer has no such album."""
        return self._lookup('deezer.album', 'album', deezer_id)

    def track(self, track_id):
        """One track with bpm (0 = not analysed) and gain; None when unknown."""
        return self._lookup('deezer.track', 'track', track_id)


class DiscogsClient(_HttpClient):
    """Styles, have/want and the community rating. Keyless at 25 requests a
    minute; a personal token raises that to 60 and nothing else. Every method
    swallows ApiError and returns None, because Discogs is an optional extra
    that must never sink a run."""

    rate = config.DISCOGS_REQUESTS_PER_MINUTE / 60.0

    def __init__(self, token=None, **kwargs):
        self.token = token if token is not None else config.DISCOGS_TOKEN
        if kwargs.get('rate') is None and self.token and not os.getenv('RADIUS_DISCOGS_RPM'):
            # A token handed to the constructor rather than the environment
            # still earns the 60/minute the config default did not know about.
            kwargs['rate'] = 1.0
        super().__init__(**kwargs)
        if self.token:
            self.extra_headers['Authorization'] = f'Discogs token={self.token}'

    @property
    def configured(self):
        return True

    def _lookup(self, namespace, path, discogs_id, params=None):
        try:
            body = self._cached(
                namespace, {'id': str(discogs_id)},
                'GET', config.DISCOGS_API_ROOT + f'{path}/{discogs_id}',
                params=params,
            )
        except ApiError:
            return None
        return body if isinstance(body, dict) and body.get('id') else None

    def master(self, master_id):
        """Styles, genres, year, main_release id, marketplace stats."""
        return self._lookup('discogs.master', 'masters', master_id,
                            params={'curr_abbr': 'USD'})

    def release(self, release_id):
        """Community have/want/rating, labels, formats, country, extraartists."""
        return self._lookup('discogs.release', 'releases', release_id)


# Last.fm error codes that mean the key, not the request, is the problem.
_LASTFM_BAD_KEY = (4, 9, 10, 26)
# Codes that mean "try again", not "there is no such record": 8 operation
# failed, 11 service offline, 16 temporary error, 29 rate limit. Cached as a
# miss, any of them would hide an album's tags for the TTL's whole 90 days.
_LASTFM_TRANSIENT = frozenset({8, 11, 16, 29})


class LastFmClient(_HttpClient):
    """Optional crowd signals, all behind one key.

    Tags first: MusicBrainz tags are trustworthy but sparse, and what goes
    missing first is the mood vocabulary — "melancholic", "hypnagogic",
    "winter" — which is precisely where the intangible qualities of a record
    live. Last.fm's crowd supplies that in volume, already weighted 0-100.
    Then similar artists, tag charts and album listener counts, each a
    candidate source or a statistic of its own.

    Everything degrades cleanly: with no key, `configured` is False, every
    method returns nothing, and the fingerprint is built from MusicBrainz
    alone. A key the service rejects raises KeyRejected (an ApiError) so it
    can never masquerade as "this album has no tags".
    """

    rate = config.LASTFM_REQUESTS_PER_SECOND
    # Last.fm puts its own error code in a JSON body on these statuses (404
    # for "not found", 403 for a bad key); inspect the body instead of
    # raising on the status so a miss can be cached and a bad key reported.
    json_error_statuses = (400, 403, 404)

    def __init__(self, api_key=None, **kwargs):
        super().__init__(**kwargs)
        self.api_key = api_key if api_key is not None else config.LASTFM_API_KEY

    @property
    def configured(self):
        return bool(self.api_key)

    def _body_problem(self, body):
        if not isinstance(body, dict) or 'error' not in body:
            return None
        code = body.get('error')
        try:
            code = int(code)
        except (TypeError, ValueError):
            return 'empty'
        if code in _LASTFM_BAD_KEY:
            raise KeyRejected(
                f"Last.fm rejected the API key (error {code}: "
                f"{body.get('message')}). Fix or remove LASTFM_API_KEY."
            )
        if code in _LASTFM_TRANSIENT:
            return 'retry'
        return 'empty'

    def _get(self, namespace, method, **params):
        """The parsed body for one Last.fm method, {} when not configured, on
        a miss, or on any failure except a rejected key."""
        if not self.configured:
            return {}
        clean = {k: str(v) for k, v in params.items() if v}
        try:
            body = self._cached(
                namespace, clean, 'GET', config.LASTFM_API_ROOT,
                params=dict(clean, method=method, api_key=self.api_key,
                            format='json', autocorrect=1),
            )
        except KeyRejected:
            raise
        except ApiError:
            return {}
        if not isinstance(body, dict):
            return {}
        if 'error' in body:
            # A stale error body cached by an earlier version. It says
            # nothing about the key in use now — a rejected key today is
            # raised by _body_problem on the live response — so it is
            # treated as a miss rather than allowed to disable Last.fm.
            return {}
        return body

    def _tags(self, namespace, method, **params):
        body = self._get(namespace, method, **params)
        entries = _as_list((body.get('toptags') or {}).get('tag'))
        return [
            {'name': e.get('name'), 'count': e.get('count') or 0}
            for e in entries if isinstance(e, dict) and e.get('name')
        ]

    def album_tags(self, artist, album):
        """[{name, count 0-100}] for one album, strongest first."""
        return self._tags('lastfm.album.tags', 'album.getTopTags',
                          artist=artist, album=album)

    def artist_tags(self, artist):
        """[{name, count 0-100}] for one artist — feeds the lineage axis."""
        return self._tags('lastfm.artist.tags', 'artist.getTopTags',
                          artist=artist)

    def similar_artists(self, artist, limit=30):
        """[{name, mbid ('' when unknown), match (0..1)}], best first. The
        match comes down the wire as a string."""
        body = self._get('lastfm.artist.similar', 'artist.getSimilar',
                         artist=artist, limit=limit)
        entries = _as_list((body.get('similarartists') or {}).get('artist'))
        out = []
        for entry in entries:
            if not isinstance(entry, dict) or not entry.get('name'):
                continue
            try:
                match = float(entry.get('match') or 0.0)
            except (TypeError, ValueError):
                match = 0.0
            out.append({'name': entry['name'], 'mbid': entry.get('mbid') or '',
                        'match': match})
        return out

    def tag_top_albums(self, tag, limit=50):
        """[{name, mbid (a RELEASE id or ''), artist, artist_mbid, rank}] —
        the tag's chart by listeners."""
        body = self._get('lastfm.tag.albums', 'tag.getTopAlbums',
                         tag=tag, limit=limit)
        entries = _as_list((body.get('albums') or {}).get('album'))
        out = []
        for position, entry in enumerate(entries, 1):
            if not isinstance(entry, dict) or not entry.get('name'):
                continue
            artist = entry.get('artist')
            artist = artist if isinstance(artist, dict) else {'name': artist or ''}
            try:
                rank = int((entry.get('@attr') or {}).get('rank') or position)
            except (TypeError, ValueError):
                rank = position
            out.append({'name': entry['name'], 'mbid': entry.get('mbid') or '',
                        'artist': artist.get('name') or '',
                        'artist_mbid': artist.get('mbid') or '', 'rank': rank})
        return out

    def album_info(self, artist, album):
        """The raw 'album' object (listeners, playcount, wiki, tracks), {}
        when Last.fm does not know the record."""
        body = self._get('lastfm.album.info', 'album.getInfo',
                         artist=artist, album=album)
        album_body = body.get('album')
        return album_body if isinstance(album_body, dict) else {}
