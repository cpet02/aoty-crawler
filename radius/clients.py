"""Rate-limited, cached clients for the three keyless services Radius uses.

No API keys anywhere. MusicBrainz, ListenBrainz and Wikipedia all serve this
data to anyone who sends an honest User-Agent, which is the whole reason the
project moved off Last.fm: no application process, no key to leak, and no
scraping.

* MusicBrainzClient  the canonical catalogue — resolving an album to an mbid,
                     finding release groups by tag, reading a tracklist. One
                     request per second, which is their published limit, so
                     this is the expensive client and gets used sparingly.
* ListenBrainzClient listening data and MusicBrainz metadata in bulk. Its
                     metadata and popularity endpoints take many mbids per
                     request, so a whole candidate pool costs a handful of
                     calls rather than hundreds.
* WikipediaClient    article intros, up to 20 titles per request, for the
                     prose axis.

Every response goes through the disk cache first, so a repeated query costs
nothing and the network is touched once per fact.
"""

import threading
import time

import requests

from . import config
from .cache import Cache


class ApiError(RuntimeError):
    pass


class RateLimited(ApiError):
    """The service asked us to slow down and kept asking."""


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


class _HttpClient:
    """Shared request plumbing: identify ourselves, respect the limiter, back
    off on throttling instead of hammering through it."""

    rate = 1.0

    def __init__(self, cache=None, session=None, rate=None):
        self.cache = cache or Cache()
        self.session = session or requests.Session()
        self.limiter = _RateLimiter(rate or self.rate)
        self.calls_made = 0
        self.cache_hits = 0

    def _request(self, method, url, params=None, json_body=None):
        last_error = None
        for attempt in range(config.MAX_RETRIES):
            self.limiter.wait()
            try:
                response = self.session.request(
                    method, url, params=params, json=json_body,
                    timeout=config.REQUEST_TIMEOUT,
                    headers={'User-Agent': config.USER_AGENT,
                             'Accept': 'application/json'},
                )
            except requests.RequestException as exc:
                last_error = exc
                time.sleep(2 ** attempt)
                continue

            if response.status_code == 200:
                try:
                    return response.json()
                except ValueError as exc:
                    raise ApiError(f'non-JSON response from {url}') from exc

            if response.status_code in (429, 500, 502, 503, 504):
                # Honour Retry-After when offered; otherwise back off. Being
                # asked to slow down is a reason to slow down, not to retry
                # harder — that is how an IP ends up blocked.
                wait = response.headers.get('Retry-After')
                try:
                    delay = float(wait) if wait else 2 ** (attempt + 1)
                except ValueError:
                    delay = 2 ** (attempt + 1)
                last_error = RateLimited(f'HTTP {response.status_code} from {url}')
                time.sleep(min(delay, 30))
                continue

            raise ApiError(
                f'HTTP {response.status_code} from {url}: {response.text[:200]}'
            )
        raise (last_error if isinstance(last_error, ApiError)
               else ApiError(f'giving up on {url}: {last_error}'))

    def _cached(self, namespace, key_params, method, url,
                params=None, json_body=None):
        key = Cache.make_key(namespace, key_params)
        ttl = config.TTL_DAYS.get(namespace, config.DEFAULT_TTL_DAYS)
        cached = self.cache.get(key, ttl)
        if cached is not None:
            self.cache_hits += 1
            return cached
        body = self._request(method, url, params=params, json_body=json_body)
        self.calls_made += 1
        self.cache.put(key, body)
        return body


def _chunked(items, size):
    items = list(items)
    for start in range(0, len(items), size):
        yield items[start:start + size]


class MusicBrainzClient(_HttpClient):
    """The catalogue. Held to one request per second, as they ask."""

    rate = config.MUSICBRAINZ_REQUESTS_PER_SECOND

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

    def release_groups_by_tag(self, tag, limit=100, primary_type='album'):
        query = f'tag:"{_escape(tag)}"'
        if primary_type:
            query += f' AND primarytype:{primary_type}'
        return self.search_release_groups(query, limit=limit)

    def tracklist(self, release_group_mbid):
        """([track titles], [track lengths in ms]) for one release of the group.

        Individual lengths, not just the total, because the pacing axis needs
        how uneven the tracks are and not only how long the record is.

        Costs a full second of the MusicBrainz budget, so callers keep it for
        albums that actually made the result list.
        """
        body = self._cached(
            'mb.release.tracks', {'rg': release_group_mbid},
            'GET', config.MUSICBRAINZ_API_ROOT + 'release',
            params={'release-group': release_group_mbid, 'fmt': 'json',
                    'inc': 'recordings', 'limit': 1},
        )
        releases = (body or {}).get('releases') or []
        if not releases:
            return [], []
        lengths, titles = [], []
        for medium in releases[0].get('media') or []:
            for track in medium.get('tracks') or []:
                titles.append(track.get('title') or '')
                length = track.get('length')
                if isinstance(length, (int, float)) and length > 0:
                    lengths.append(int(length))
        return titles, lengths

    def release_group_relations(self, release_group_mbid):
        """One release-group lookup, shared by article_ref and reception so
        asking for both costs one request instead of two: MusicBrainz
        returns url relationships and the community rating off the same
        `inc`.
        """
        body = self._cached(
            'mb.rg.relations', {'mbid': release_group_mbid},
            'GET', config.MUSICBRAINZ_API_ROOT + f'release-group/{release_group_mbid}',
            params={'fmt': 'json', 'inc': 'url-rels ratings'},
        )
        return body or {}

    def article_ref(self, release_group_mbid):
        """Where to find this album's write-up, as ('wikipedia', title) or
        ('wikidata', 'Q123'), or None.

        MusicBrainz has largely migrated from direct Wikipedia links to
        Wikidata ones, so most release groups only offer a Q-id. Returning
        both shapes lets the caller resolve the Q-ids in bulk afterwards
        instead of one lookup per album.
        """
        body = self.release_group_relations(release_group_mbid)
        wikidata_id = None
        for relation in body.get('relations') or []:
            url = ((relation or {}).get('url') or {}).get('resource') or ''
            if 'wikipedia.org/wiki/' in url:
                return 'wikipedia', url.rsplit('/wiki/', 1)[-1].replace('_', ' ')
            if 'wikidata.org/wiki/Q' in url:
                wikidata_id = url.rsplit('/wiki/', 1)[-1]
        return ('wikidata', wikidata_id) if wikidata_id else None

    def reception(self, release_group_mbid):
        """{'rating': 0..5 or None, 'rating_votes': int}.

        The rating is MusicBrainz's own crowd rating, not a popularity proxy
        — it is people saying "this is good," independent of how many
        listened. A vote count of 0 means nobody has rated it, not that it
        was rated zero.
        """
        body = self.release_group_relations(release_group_mbid)
        rating_info = body.get('rating') or {}
        return {
            'rating': rating_info.get('value'),
            'rating_votes': rating_info.get('votes-count') or 0,
        }


def _escape(value):
    """Escape the Lucene syntax MusicBrainz search would otherwise choke on."""
    out = []
    for char in str(value or ''):
        if char in '+-&|!(){}[]^"~*?:\\/':
            out.append(' ')
        else:
            out.append(char)
    return ' '.join(''.join(out).split())


class ListenBrainzClient(_HttpClient):
    """Listening data plus MusicBrainz metadata, in batches.

    This is where the work happens. Its metadata and popularity endpoints
    accept many mbids per request, so fingerprinting a 120-album pool costs
    single-digit requests instead of hundreds.
    """

    rate = config.LISTENBRAINZ_REQUESTS_PER_SECOND

    def metadata(self, release_group_mbids, inc='tag artist release'):
        """{mbid: metadata} for many release groups at once.

        Tags come back at both release-group and artist level, which is what
        feeds the genre/mood vectors and the separate lineage vector.
        """
        collected = {}
        for batch in _chunked(release_group_mbids, config.LB_BATCH_SIZE):
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
        for batch in _chunked(release_group_mbids, config.LB_BATCH_SIZE):
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
        for batch in _chunked(artist_mbids, config.LB_BATCH_SIZE):
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
        # The labs endpoints have returned both a bare list and a list of
        # result sets over time; take the last list of dicts either way.
        if isinstance(body, list) and body and isinstance(body[0], list):
            body = body[-1]
        return [entry for entry in (body or []) if isinstance(entry, dict)]


class WikipediaClient(_HttpClient):
    """Article intros for the prose axis, in batches.

    Two hops, both batched: Wikidata Q-ids resolve to English Wikipedia
    titles 50 at a time, then Wikipedia serves 20 article intros per request.
    """

    rate = config.WIKIPEDIA_REQUESTS_PER_SECOND

    def titles_for_wikidata(self, wikidata_ids):
        """{Q-id: English Wikipedia title} for many entities at once."""
        collected = {}
        for batch in _chunked([q for q in wikidata_ids if q], 50):
            try:
                body = self._cached(
                    'wikidata.sitelinks', {'ids': sorted(batch)},
                    'GET', config.WIKIDATA_API_ROOT,
                    params={'action': 'wbgetentities', 'format': 'json',
                            'props': 'sitelinks', 'sitefilter': 'enwiki',
                            'ids': '|'.join(batch)},
                )
            except ApiError:
                continue
            for qid, entity in ((body or {}).get('entities') or {}).items():
                sitelink = ((entity or {}).get('sitelinks') or {}).get('enwiki') or {}
                if sitelink.get('title'):
                    collected[qid] = sitelink['title']
        return collected

    def extracts(self, titles):
        """{title: intro text}. Redirects are followed and normalised titles
        mapped back, so the caller can look up what it asked for."""
        collected = {}
        for batch in _chunked([t for t in titles if t], 20):
            body = self._cached(
                # The shape of the request is part of the key: change what is
                # asked for (intro vs full text, batch limits) and last
                # week's cached answer is no longer an answer to this
                # question. Bump this when the params below change.
                'wikipedia.extracts', {'titles': sorted(batch), 'v': 2},
                'GET', config.WIKIPEDIA_API_ROOT,
                params={
                    'action': 'query', 'format': 'json', 'prop': 'extracts',
                    # exlimit is what makes a batch a batch: it defaults to 1,
                    # so without it only the first title in the request comes
                    # back with an extract and every other album silently has
                    # no prose. 20 is the maximum the extension allows, which
                    # is why batches are sized to 20 above.
                    'explaintext': 1, 'redirects': 1, 'exintro': 1,
                    'exlimit': 20,
                    'titles': '|'.join(batch),
                },
            )
            query = (body or {}).get('query') or {}
            pages = query.get('pages') or {}
            by_title = {
                page.get('title'): page.get('extract') or ''
                for page in pages.values() if isinstance(page, dict)
            }
            # Map the titles we asked for back through any redirects.
            aliases = {}
            for hop in (query.get('redirects') or []) + (query.get('normalized') or []):
                aliases[hop.get('from')] = hop.get('to')
            for title in batch:
                resolved = aliases.get(title, title)
                resolved = aliases.get(resolved, resolved)
                if by_title.get(resolved):
                    collected[title] = by_title[resolved]
        return collected


class LastFmClient(_HttpClient):
    """Optional tag enricher.

    Last.fm is the only service here that wants a key, and it is used for one
    narrow job: thickening tag vectors. MusicBrainz tags are trustworthy but
    sparse, and what goes missing first is the mood vocabulary — "melancholic",
    "hypnagogic", "winter" — which is precisely where the intangible qualities
    of a record live. Last.fm's crowd supplies that in volume, already weighted
    0-100 by how often each tag was applied.

    Everything degrades cleanly: with no key, `configured` is False, every
    method returns nothing, and the fingerprint is built from MusicBrainz
    alone exactly as before.
    """

    rate = config.LASTFM_REQUESTS_PER_SECOND

    def __init__(self, api_key=None, **kwargs):
        super().__init__(**kwargs)
        self.api_key = api_key if api_key is not None else config.LASTFM_API_KEY

    @property
    def configured(self):
        return bool(self.api_key)

    def _tags(self, namespace, method, **params):
        if not self.configured:
            return []
        clean = {k: str(v) for k, v in params.items() if v}
        try:
            body = self._cached(
                namespace, clean, 'GET', config.LASTFM_API_ROOT,
                params=dict(clean, method=method, api_key=self.api_key,
                            format='json', autocorrect=1),
            )
        except ApiError:
            return []
        if isinstance(body, dict) and 'error' in body:
            # A bad key must not masquerade as "this album has no tags", or
            # the enricher silently does nothing for an entire run.
            if body.get('error') in (4, 9, 10, 26):
                raise ApiError(
                    f"Last.fm rejected the API key (error {body['error']}: "
                    f"{body.get('message')}). Fix or remove LASTFM_API_KEY."
                )
            return []
        entries = ((body or {}).get('toptags') or {}).get('tag') or []
        if isinstance(entries, dict):
            entries = [entries]
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
