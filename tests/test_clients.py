"""Offline tests for the API clients.

A fake session stands in for requests.Session, so every test exercises the
real request plumbing — caching, retries, rate headers, the body-problem
hook, param shapes — without touching the network or needing a key.
"""

import importlib
import json
import os
import sys
import types

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def _leaf(name):
    """Import radius.<name> even while radius/__init__.py cannot load.

    The package root imports the whole engine; these tests only need the
    leaf modules (clients, cache, config). When the root fails — as it does
    while sibling modules are mid-rewrite — register a bare package and load
    the leaf through it. A healthy package never reaches the fallback.
    """
    try:
        return importlib.import_module(f'radius.{name}')
    except ImportError:
        if 'radius' in sys.modules:
            raise
        package = types.ModuleType('radius')
        package.__path__ = [os.path.join(ROOT, 'radius')]
        sys.modules['radius'] = package
        return importlib.import_module(f'radius.{name}')


clients = _leaf('clients')
config = _leaf('config')
Cache = _leaf('cache').Cache
ApiError, RateLimited, _as_list = clients.ApiError, clients.RateLimited, clients._as_list
DeezerClient, DiscogsClient = clients.DeezerClient, clients.DiscogsClient
LastFmClient, ListenBrainzClient = clients.LastFmClient, clients.ListenBrainzClient
MusicBrainzClient, WikidataClient = clients.MusicBrainzClient, clients.WikidataClient


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------

class FakeResponse:
    def __init__(self, body=None, status=200, headers=None, text=None):
        self.status_code = status
        self.headers = headers or {}
        self._body = body
        self.text = text if text is not None else (
            json.dumps(body) if body is not None else '')

    def json(self):
        if self._body is None:
            raise ValueError('not json')
        return self._body


class FakeSession:
    """Answers from a scripted list (the last response repeats) or a handler
    callable(method, url, params, json, headers) -> FakeResponse."""

    def __init__(self, responses=None, handler=None):
        self.responses = list(responses or [])
        self.handler = handler
        self.calls = []

    def request(self, method, url, params=None, json=None, timeout=None, headers=None):
        self.calls.append({'method': method, 'url': url, 'params': params,
                           'json': json, 'headers': headers})
        if self.handler is not None:
            return self.handler(method, url, params, json, headers)
        if len(self.responses) > 1:
            return self.responses.pop(0)
        return self.responses[0]


@pytest.fixture
def cache(tmp_path):
    return Cache(path=str(tmp_path / 'c.sqlite'))


@pytest.fixture
def sleeps(monkeypatch):
    """Record every sleep instead of waiting (limiter and backoff both)."""
    calls = []
    monkeypatch.setattr(clients.time, 'sleep', lambda seconds: calls.append(seconds))
    return calls


def make(client_cls, cache, session, **kwargs):
    return client_cls(cache=cache, session=session, rate=1000, **kwargs)


# ---------------------------------------------------------------------------
# Shared plumbing
# ---------------------------------------------------------------------------

def test_cache_hit_makes_no_second_request(cache, sleeps):
    session = FakeSession([FakeResponse({'id': 'rg-1', 'title': 'Spiderland'})])
    mb = make(MusicBrainzClient, cache, session)
    assert mb.release_group('rg-1')['title'] == 'Spiderland'
    assert mb.release_group('rg-1')['title'] == 'Spiderland'
    assert len(session.calls) == 1
    assert mb.calls_made == 1 and mb.cache_hits == 1
    assert session.calls[0]['params']['inc'].startswith('releases+media')


def test_user_agent_and_accept_are_sent(cache, sleeps):
    session = FakeSession([FakeResponse({})])
    make(WikidataClient, cache, session).entities(['Q1'])
    headers = session.calls[0]['headers']
    assert headers['User-Agent'] == config.USER_AGENT
    assert headers['Accept'] == 'application/json'


def test_non_json_200_raises_with_the_text(cache, sleeps):
    session = FakeSession([FakeResponse(text='<html>oops</html>')])
    mb = make(MusicBrainzClient, cache, session)
    with pytest.raises(ApiError) as info:
        mb.release_group('rg-1')
    assert '<html>oops</html>' in str(info.value)


def test_rate_headers_at_zero_trigger_a_capped_sleep(cache, sleeps):
    session = FakeSession([
        FakeResponse({}, headers={'X-RateLimit-Remaining': '0',
                                  'X-RateLimit-Reset-In': '3'}),
        FakeResponse({}, headers={'X-RateLimit-Remaining': '0',
                                  'X-RateLimit-Reset-In': '40'}),
        FakeResponse({}, headers={'X-RateLimit-Remaining': '7',
                                  'X-RateLimit-Reset-In': '40'}),
    ])
    lb = make(ListenBrainzClient, cache, session)
    lb.metadata(['a'])
    assert 3.0 in sleeps
    lb.metadata(['b'])
    assert 15.0 in sleeps          # capped, never the full 40
    sleeps.clear()
    lb.metadata(['c'])
    assert not [s for s in sleeps if s >= 1]


def test_503_honours_retry_after_then_gives_up(cache, sleeps):
    session = FakeSession([FakeResponse(status=503, headers={'Retry-After': '2'},
                                        text='rate limit')])
    mb = make(MusicBrainzClient, cache, session)
    with pytest.raises(RateLimited):
        mb.release_group('rg-1')
    assert len(session.calls) == config.MAX_RETRIES
    # Between attempts only: sleeping after the last one would just delay
    # the exception the caller is already getting.
    assert sleeps.count(2.0) == config.MAX_RETRIES - 1


def test_extra_headers_reach_every_request(cache, sleeps):
    session = FakeSession([FakeResponse({'entities': {}})])
    client = make(WikidataClient, cache, session, extra_headers={'X-Test': 'yes'})
    client.entities(['Q1'])
    assert session.calls[0]['headers']['X-Test'] == 'yes'


# ---------------------------------------------------------------------------
# MusicBrainz
# ---------------------------------------------------------------------------

def test_genre_names_parses_the_text_body_and_memoises(cache, sleeps):
    session = FakeSession([FakeResponse(text='Ambient\nzydeco\n\n2-step\n')])
    mb = make(MusicBrainzClient, cache, session)
    names = mb.genre_names()
    assert names == frozenset({'ambient', 'zydeco', '2-step'})
    assert session.calls[0]['params'] == {'fmt': 'txt'}
    assert session.calls[0]['headers']['Accept'] == 'text/plain'
    # The text body lives in the cache as a JSON string, transparently.
    assert cache.get(Cache.make_key('mb.genres', {'fmt': 'txt'}), None) == 'Ambient\nzydeco\n\n2-step\n'
    assert mb.genre_names() is names
    assert len(session.calls) == 1


def test_genre_names_is_empty_when_the_fetch_fails(cache, sleeps):
    session = FakeSession([FakeResponse(status=404, text='no')])
    assert make(MusicBrainzClient, cache, session).genre_names() == frozenset()


def test_release_groups_by_tags_builds_an_and_query(cache, sleeps):
    session = FakeSession([FakeResponse({'release-groups': [{'id': 'x'}]})])
    mb = make(MusicBrainzClient, cache, session)
    hits = mb.release_groups_by_tags(['post-rock', 'slowcore'])
    assert hits == [{'id': 'x'}]
    params = session.calls[0]['params']
    assert params['query'] == 'tag:"post rock" AND tag:"slowcore" AND primarytype:album'
    assert params['limit'] == 100
    mb.release_groups_by_tags('shoegaze', primary_type='')
    assert session.calls[1]['params']['query'] == 'tag:"shoegaze"'
    assert mb.release_groups_by_tags([]) == []


def test_lookups_hit_the_documented_endpoints(cache, sleeps):
    session = FakeSession([FakeResponse({'id': 'any'})])
    mb = make(MusicBrainzClient, cache, session)
    mb.release('r1')
    mb.artist('a1')
    assert session.calls[0]['url'].endswith('release/r1')
    assert 'recording-level-rels' in session.calls[0]['params']['inc']
    assert session.calls[1]['url'].endswith('artist/a1')
    assert 'artist-rels' in session.calls[1]['params']['inc']


# ---------------------------------------------------------------------------
# ListenBrainz
# ---------------------------------------------------------------------------

def test_similar_recordings_repeats_the_seed_param_and_names_the_algorithm(cache, sleeps):
    session = FakeSession([FakeResponse([{'recording_mbid': 'z', 'score': 3}])])
    lb = make(ListenBrainzClient, cache, session)
    hits = lb.similar_recordings(['b', 'a'], algorithm='algo-x')
    assert hits == [{'recording_mbid': 'z', 'score': 3}]
    params = session.calls[0]['params']
    assert isinstance(params, list)
    assert params.count(('recording_mbids', 'a')) == 1
    assert params.count(('recording_mbids', 'b')) == 1
    assert ('algorithm', 'algo-x') in params
    assert 'labs.api.listenbrainz.org' in session.calls[0]['url']
    # Same seeds in another order is the same question: canonical key.
    lb.similar_recordings(['a', 'b'], algorithm='algo-x')
    assert len(session.calls) == 1


def test_similar_recordings_uses_the_configured_default_and_chunks_by_ten(cache, sleeps):
    session = FakeSession([FakeResponse([])])
    lb = make(ListenBrainzClient, cache, session)
    lb.similar_recordings([f'r{i}' for i in range(23)])
    assert len(session.calls) == 3
    first = session.calls[0]['params']
    assert sum(1 for k, _ in first if k == 'recording_mbids') == 10
    assert ('algorithm', config.LB_SIMILAR_RECORDING_ALGORITHM) in first
    assert config.LB_SIMILAR_RECORDING_ALGORITHM in config.LB_SIMILAR_RECORDING_ALGORITHMS


def test_similar_recordings_is_empty_on_an_html_400(cache, sleeps):
    session = FakeSession([FakeResponse(status=400, text='<!doctype html><title>400</title>')])
    lb = make(ListenBrainzClient, cache, session)
    assert lb.similar_recordings(['a']) == []
    assert lb.similar_recordings(['a']) == []
    assert len(session.calls) == 2          # an error is never cached


def test_recording_metadata_comma_joins_at_most_25_per_call(cache, sleeps):
    def handler(method, url, params, body, headers):
        ids = params['recording_mbids'].split(',')
        assert len(ids) <= 25
        return FakeResponse({m: {'recording': {'name': m}} for m in ids})

    session = FakeSession(handler=handler)
    lb = make(ListenBrainzClient, cache, session)
    ids = [f'rec-{i}' for i in range(30)]
    result = lb.recording_metadata(ids)
    assert len(session.calls) == 2
    assert len(session.calls[0]['params']['recording_mbids'].split(',')) == 25
    assert session.calls[0]['params']['inc'] == 'artist release'
    assert set(result) == set(ids)


# ---------------------------------------------------------------------------
# Wikidata
# ---------------------------------------------------------------------------

def test_entities_batches_fifty_and_drops_missing(cache, sleeps):
    def handler(method, url, params, body, headers):
        ids = params['ids'].split('|')
        assert len(ids) <= 50
        assert params['props'] == 'claims|labels|sitelinks'
        assert params['languages'] == 'en' and params['sitefilter'] == 'enwiki'
        entities = {q: {'id': q, 'claims': {}} for q in ids}
        if 'Q7' in entities:
            entities['Q7'] = {'id': 'Q7', 'missing': ''}
        return FakeResponse({'entities': entities})

    session = FakeSession(handler=handler)
    wd = make(WikidataClient, cache, session)
    qids = [f'Q{i}' for i in range(60)]
    result = wd.entities(qids)
    assert len(session.calls) == 2
    assert 'Q7' not in result
    assert len(result) == 59


def test_labels_returns_only_english_labels(cache, sleeps):
    session = FakeSession([FakeResponse({'entities': {
        'Q1': {'id': 'Q1', 'labels': {'en': {'language': 'en', 'value': 'Steve Albini'}}},
        'Q2': {'id': 'Q2', 'labels': {'fr': {'language': 'fr', 'value': 'Rien'}}},
        'Q3': {'id': 'Q3', 'missing': ''},
    }})])
    wd = make(WikidataClient, cache, session)
    assert wd.labels(['Q1', 'Q2', 'Q3']) == {'Q1': 'Steve Albini'}
    assert session.calls[0]['params']['props'] == 'labels'


# ---------------------------------------------------------------------------
# Deezer
# ---------------------------------------------------------------------------

def test_deezer_no_data_error_is_cached_as_a_miss(cache, sleeps):
    session = FakeSession([FakeResponse(
        {'error': {'type': 'DataException', 'message': 'no data', 'code': 800}})])
    dz = make(DeezerClient, cache, session)
    assert dz.album(123) is None
    assert cache.get(Cache.make_key('deezer.album', {'id': '123'}), None) == {}
    assert dz.album(123) is None
    assert len(session.calls) == 1


def test_deezer_quota_is_retried_then_raises(cache, sleeps):
    session = FakeSession([FakeResponse(
        {'error': {'type': 'Exception', 'message': 'Quota limit exceeded', 'code': 4}})])
    dz = make(DeezerClient, cache, session)
    with pytest.raises(RateLimited):
        dz.track(9)
    assert len(session.calls) == config.MAX_RETRIES
    assert [s for s in sleeps if s >= 2]
    assert cache.get(Cache.make_key('deezer.track', {'id': '9'}), None) is Cache.MISS


def test_deezer_search_tries_fielded_then_plain(cache, sleeps):
    session = FakeSession([
        FakeResponse({'data': [], 'total': 0}),
        FakeResponse({'data': [{'id': 1, 'title': 'Spiderland'}], 'total': 1}),
    ])
    dz = make(DeezerClient, cache, session)
    assert dz.search_album('Slint', 'Spiderland') == [{'id': 1, 'title': 'Spiderland'}]
    assert session.calls[0]['params']['q'] == 'artist:"Slint" album:"Spiderland"'
    assert session.calls[1]['params']['q'] == 'Slint Spiderland'
    # Both queries are cached under their own keys.
    dz.search_album('Slint', 'Spiderland')
    assert len(session.calls) == 2


def test_deezer_album_and_track_need_an_id(cache, sleeps):
    session = FakeSession([FakeResponse({'id': 5, 'fans': 12}), FakeResponse({'bpm': 0})])
    dz = make(DeezerClient, cache, session)
    assert dz.album(5) == {'id': 5, 'fans': 12}
    assert dz.track(6) is None


# ---------------------------------------------------------------------------
# Discogs
# ---------------------------------------------------------------------------

def test_discogs_sends_authorization_only_with_a_token(cache, sleeps, monkeypatch):
    monkeypatch.delenv('RADIUS_DISCOGS_RPM', raising=False)
    with_token = FakeSession([FakeResponse({'id': 1, 'styles': ['Post Rock']})])
    client = make(DiscogsClient, cache, with_token, token='abc')
    assert client.master(1)['styles'] == ['Post Rock']
    assert with_token.calls[0]['headers']['Authorization'] == 'Discogs token=abc'
    assert with_token.calls[0]['params'] == {'curr_abbr': 'USD'}
    assert client.configured is True

    keyless = FakeSession([FakeResponse({'id': 2})])
    client = make(DiscogsClient, cache, keyless, token='')
    assert client.release(2) == {'id': 2}
    assert 'Authorization' not in keyless.calls[0]['headers']
    assert client.configured is True


def test_discogs_returns_none_on_errors(cache, sleeps):
    session = FakeSession([FakeResponse(status=404, text='{"message": "not found"}')])
    assert make(DiscogsClient, cache, session, token='').master(1) is None


# ---------------------------------------------------------------------------
# Last.fm
# ---------------------------------------------------------------------------

def test_as_list_normalises_lastfm_quirks():
    assert _as_list([{'a': 1}]) == [{'a': 1}]
    assert _as_list({'a': 1}) == [{'a': 1}]
    assert _as_list('') == []
    assert _as_list(None) == []


def test_lastfm_similar_artists_parses_match_to_float(cache, sleeps):
    session = FakeSession([FakeResponse({'similarartists': {'artist': [
        {'name': 'Rodan', 'mbid': 'm1', 'match': '1'},
        {'name': 'Bedhead', 'mbid': '', 'match': '0.835862'},
        {'name': 'Nobody', 'match': 'n/a'},
    ]}})])
    lfm = make(LastFmClient, cache, session, api_key='k')
    hits = lfm.similar_artists('Slint', limit=3)
    assert hits[0] == {'name': 'Rodan', 'mbid': 'm1', 'match': 1.0}
    assert hits[1]['match'] == pytest.approx(0.835862)
    assert hits[2]['match'] == 0.0 and hits[2]['mbid'] == ''
    assert session.calls[0]['params']['method'] == 'artist.getSimilar'
    assert session.calls[0]['params']['limit'] == '3'


def test_lastfm_single_item_dict_is_a_list(cache, sleeps):
    session = FakeSession([FakeResponse({'similarartists': {'artist':
        {'name': 'Rodan', 'mbid': 'm1', 'match': '0.5'}}})])
    lfm = make(LastFmClient, cache, session, api_key='k')
    assert lfm.similar_artists('Slint') == [{'name': 'Rodan', 'mbid': 'm1', 'match': 0.5}]


def test_lastfm_tag_top_albums_reads_rank_and_artist(cache, sleeps):
    session = FakeSession([FakeResponse({'albums': {'album': [
        {'name': 'Spiderland', 'mbid': 'rel-1',
         'artist': {'name': 'Slint', 'mbid': 'art-1'}, '@attr': {'rank': '1'}},
        {'name': 'Rusty', 'mbid': '', 'artist': {'name': 'Rodan', 'mbid': 'art-2'}},
    ], '@attr': {'tag': 'post-rock', 'total': '1000'}}})])
    lfm = make(LastFmClient, cache, session, api_key='k')
    albums = lfm.tag_top_albums('post-rock', limit=2)
    assert albums == [
        {'name': 'Spiderland', 'mbid': 'rel-1', 'artist': 'Slint',
         'artist_mbid': 'art-1', 'rank': 1},
        {'name': 'Rusty', 'mbid': '', 'artist': 'Rodan', 'artist_mbid': 'art-2', 'rank': 2},
    ]


def test_lastfm_album_info_is_empty_on_error_6_and_cached(cache, sleeps):
    session = FakeSession([FakeResponse({'error': 6, 'message': 'Album not found'}, status=404)])
    lfm = make(LastFmClient, cache, session, api_key='k')
    assert lfm.album_info('Nobody', 'Nothing') == {}
    assert lfm.album_info('Nobody', 'Nothing') == {}
    assert len(session.calls) == 1


def test_lastfm_album_info_returns_the_album_object(cache, sleeps):
    session = FakeSession([FakeResponse({'album': {'name': 'Spiderland', 'listeners': '12',
                                                   'tags': {'tag': ''}}})])
    lfm = make(LastFmClient, cache, session, api_key='k')
    assert lfm.album_info('Slint', 'Spiderland')['listeners'] == '12'


def test_lastfm_bad_key_raises_and_is_not_cached(cache, sleeps):
    session = FakeSession([FakeResponse({'error': 10, 'message': 'Invalid API key'}, status=403)])
    lfm = make(LastFmClient, cache, session, api_key='bad')
    with pytest.raises(ApiError):
        lfm.album_tags('Slint', 'Spiderland')
    with pytest.raises(ApiError):
        lfm.album_tags('Slint', 'Spiderland')
    assert len(session.calls) == 2


def test_lastfm_without_a_key_does_nothing(cache, sleeps):
    session = FakeSession([FakeResponse({})])
    lfm = make(LastFmClient, cache, session, api_key='')
    assert not lfm.configured
    assert lfm.similar_artists('Slint') == []
    assert lfm.tag_top_albums('post-rock') == []
    assert lfm.album_info('Slint', 'Spiderland') == {}
    assert lfm.album_tags('Slint', 'Spiderland') == []
    assert session.calls == []


def test_a_service_that_keeps_failing_is_given_up_on(cache, sleeps):
    """The engine calls these clients once per album. Without a circuit
    breaker a service-wide outage costs every album the full retry ladder,
    which is minutes of sleeping for an answer that is not coming."""
    session = FakeSession([FakeResponse(status=503, text='down')])
    client = make(MusicBrainzClient, cache, session)
    for _ in range(client.OUTAGE_THRESHOLD):
        with pytest.raises(RateLimited):
            client.release_group('rg-%d' % len(session.calls))
    assert client.unavailable
    calls_before = len(session.calls)
    sleeps_before = len(sleeps)
    # Now it fails immediately: no request, no sleeping.
    with pytest.raises(RateLimited):
        client.release_group('rg-later')
    assert len(session.calls) == calls_before
    assert len(sleeps) == sleeps_before


def test_one_success_clears_the_failure_run(cache, sleeps):
    session = FakeSession([
        FakeResponse(status=503, text='down'),
        FakeResponse(status=503, text='down'),
        FakeResponse(status=503, text='down'),
        FakeResponse({'id': 'rg-ok'}),
    ])
    client = make(MusicBrainzClient, cache, session)
    with pytest.raises(RateLimited):
        client.release_group('rg-1')          # burns MAX_RETRIES attempts
    assert client._consecutive_failures == 1
    assert client.release_group('rg-2') == {'id': 'rg-ok'}
    assert client._consecutive_failures == 0 and not client.unavailable


def test_a_cached_json_null_is_a_hit_not_a_miss(cache, sleeps):
    """A stored null read back as a miss would re-issue its request on every
    single call, forever."""
    class NullResponse(FakeResponse):
        """A 200 whose JSON body really is null (the base fake treats a None
        body as 'not JSON at all', which is a different thing)."""

        def json(self):
            return None

    session = FakeSession([NullResponse(status=200, text='null')])
    client = make(MusicBrainzClient, cache, session)
    assert client.release_group('rg-null') == {}      # _lookup coerces to {}
    assert len(session.calls) == 1
    inc = session.calls[0]['params']['inc']
    key = Cache.make_key('mb.rg.full', {'mbid': 'rg-null', 'inc': inc})
    assert cache.get(key, None) is None                # the null really is stored
    client.release_group('rg-null')
    assert len(session.calls) == 1, 'the null must be served from the cache'
