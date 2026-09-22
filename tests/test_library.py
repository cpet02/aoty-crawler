"""Offline tests for the library: bookmarks and ratings on disk.

Everything runs against a temporary directory. The clock is stubbed where
ordering matters, because Windows hands out identical timestamps to writes
that land within the same few milliseconds.
"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from radius import library
from radius.library import Library, clamp_rating, manual_key


SPIDERLAND = {
    'mbid': 'rg-slint', 'artist': 'Slint', 'album': 'Spiderland', 'year': 1991,
    'image_url': 'https://img/spiderland.jpg', 'url': 'https://mb/rg-slint',
    'listeners': 12000,      # extra as_row() columns are ignored
}
LAUGHING_STOCK = {
    'mbid': 'rg-talktalk', 'artist': 'Talk Talk', 'album': 'Laughing Stock',
    'year': 1991, 'image_url': '', 'url': 'https://mb/rg-talktalk',
}
TITANIC_RISING = {
    'mbid': 'rg-weyes', 'artist': 'Weyes Blood', 'album': 'Titanic Rising',
    'year': 2019, 'image_url': 'https://img/tr.jpg', 'url': 'https://mb/rg-weyes',
}

LEGACY_RATINGS = {
    '139513-weyes-blood-titanic-rising': {
        'rating': 10.0, 'title': 'Titanic Rising', 'artist_name': 'Weyes Blood',
        'genres': ['Baroque Pop', 'Art Pop'], 'rated_at': '2026-08-24T00:05:24.413817',
    },
}
LEGACY_BOOKMARKS = {
    '3030-true-widow-as-high': {
        'title': 'As High As the Highest Heavens', 'artist_name': 'True Widow',
        'genres': ['Slowcore', 'Shoegaze'],
        'url': 'https://www.albumoftheyear.org/album/3030.php',
        'bookmarked_at': '2026-08-24T00:02:39.704212',
    },
}

WEYES_KEY = 'manual:weyes-blood-titanic-rising'
WIDOW_KEY = 'manual:true-widow-as-high-as-the-highest-heavens'


@pytest.fixture
def ticking_clock(monkeypatch):
    """Strictly increasing timestamps, one per call."""
    tick = {'n': 0}

    def fake_now():
        tick['n'] += 1
        return f'2026-09-21T12:00:{tick["n"]:02d}+00:00'
    monkeypatch.setattr(library, '_now', fake_now)
    return tick


def write_legacy(data_dir, ratings=None, bookmarks=None):
    os.makedirs(data_dir, exist_ok=True)
    if ratings is not None:
        with open(os.path.join(data_dir, 'ratings.json'), 'w', encoding='utf-8') as handle:
            json.dump(ratings, handle)
    if bookmarks is not None:
        with open(os.path.join(data_dir, 'bookmarks.json'), 'w', encoding='utf-8') as handle:
            json.dump(bookmarks, handle)


# ---------------------------------------------------------------------------
# Keys and ratings
# ---------------------------------------------------------------------------

def test_manual_key_matches_the_old_slug_recipe():
    assert manual_key('Weyes Blood', 'Titanic Rising') == WEYES_KEY
    assert manual_key('Sigur R\u00f3s', '( )') == 'manual:sigur-r-s'
    assert manual_key('', '') == 'manual:'


def test_ratings_clamp_to_ten_and_round_to_half_steps():
    assert clamp_rating(7.3) == 7.5
    assert clamp_rating(7.2) == 7.0
    assert clamp_rating(4.25) == 4.5
    assert clamp_rating(11) == 10.0
    assert clamp_rating(-3) == 0.0
    assert clamp_rating('8.6') == 8.5
    assert clamp_rating('ten') is None
    assert clamp_rating(None) is None
    assert clamp_rating(float('nan')) is None


# ---------------------------------------------------------------------------
# Save / unsave / rate / unrate / note / remove
# ---------------------------------------------------------------------------

def test_save_album_stores_the_row_under_its_mbid(tmp_path):
    lib = Library(str(tmp_path))
    entry = lib.save_album(SPIDERLAND, from_seed='Talk Talk - Laughing Stock')

    assert entry['key'] == 'rg-slint'
    assert entry['mbid'] == 'rg-slint'
    assert entry['title'] == 'Spiderland'          # as_row() said 'album'
    assert entry['artist'] == 'Slint'
    assert entry['year'] == 1991
    assert entry['image_url'] == SPIDERLAND['image_url']
    assert entry['url'] == SPIDERLAND['url']
    assert entry['saved'] is True
    assert entry['saved_at']
    assert entry['rating'] is None
    assert entry['from_seed'] == 'Talk Talk - Laughing Stock'
    assert entry['source'] == 'radius'
    assert 'listeners' not in entry

    assert lib.is_saved('rg-slint')
    assert lib.get('rg-slint')['title'] == 'Spiderland'
    assert [e['key'] for e in lib.saved()] == ['rg-slint']
    assert lib.rated() == []
    assert lib.get('nope') is None
    assert not lib.is_saved('nope')
    assert lib.rating_of('nope') is None


def test_file_shape_is_versioned_and_left_without_a_temp_file(tmp_path):
    lib = Library(str(tmp_path / 'nested' / 'data'))
    lib.save_album(SPIDERLAND)

    with open(lib.path, encoding='utf-8') as handle:
        on_disk = json.load(handle)
    assert on_disk['version'] == 1
    assert on_disk['legacy_imported'] is False
    assert set(on_disk['entries']) == {'rg-slint'}
    assert set(on_disk['entries']['rg-slint']) == set(library.ENTRY_FIELDS)
    assert not os.path.exists(lib.path + '.tmp')


def test_unsave_drops_an_entry_that_has_nothing_else(tmp_path):
    lib = Library(str(tmp_path))
    lib.save_album(SPIDERLAND)
    lib.unsave('rg-slint')
    assert lib.get('rg-slint') is None
    assert lib.all() == []
    lib.unsave('rg-slint')                          # harmless twice


def test_unsave_keeps_an_entry_that_still_carries_a_rating(tmp_path):
    lib = Library(str(tmp_path))
    lib.save_album(SPIDERLAND)
    lib.rate('rg-slint', 9)
    lib.unsave('rg-slint')
    entry = lib.get('rg-slint')
    assert entry['saved'] is False
    assert entry['saved_at'] is None
    assert entry['rating'] == 9.0


def test_rate_rounds_clamps_and_creates_from_a_row(tmp_path):
    lib = Library(str(tmp_path))
    entry = lib.rate('rg-slint', 7.3, row=SPIDERLAND)
    assert entry['rating'] == 7.5
    assert entry['rated_at']
    assert entry['saved'] is False                  # rating is not bookmarking
    assert entry['title'] == 'Spiderland'
    assert lib.rating_of('rg-slint') == 7.5
    assert [e['key'] for e in lib.rated()] == ['rg-slint']
    assert lib.saved() == []

    assert lib.rate('rg-slint', 11)['rating'] == 10.0
    assert lib.rate('rg-slint', -1)['rating'] == 0.0
    assert lib.rate('rg-slint', '8.6')['rating'] == 8.5
    assert lib.rating_of('rg-slint') == 8.5


def test_rate_needs_a_row_to_create_an_entry(tmp_path):
    lib = Library(str(tmp_path))
    assert lib.rate('rg-slint', 8) is None
    assert lib.get('rg-slint') is None


def test_unrate_and_notes(tmp_path):
    lib = Library(str(tmp_path))
    lib.save_album(SPIDERLAND)
    lib.set_note('rg-slint', '  the one with the boat  ')
    assert lib.get('rg-slint')['note'] == 'the one with the boat'

    lib.rate('rg-slint', 8.5)
    lib.unsave('rg-slint')
    lib.unrate('rg-slint')
    entry = lib.get('rg-slint')                     # the note keeps it alive
    assert entry['rating'] is None
    assert entry['rated_at'] is None
    assert entry['note'] == 'the one with the boat'

    lib.set_note('rg-slint', '')
    assert lib.get('rg-slint') is None              # nothing left to say

    lib.set_note('missing', 'x')                    # no entry, no error
    assert lib.get('missing') is None


def test_remove(tmp_path):
    lib = Library(str(tmp_path))
    lib.save_album(SPIDERLAND)
    lib.rate('rg-talktalk', 9, row=LAUGHING_STOCK)
    lib.remove('rg-slint')
    lib.remove('never-there')
    assert [e['key'] for e in lib.all()] == ['rg-talktalk']


def test_all_is_ordered_newest_first(tmp_path, ticking_clock):
    lib = Library(str(tmp_path))
    lib.save_album(SPIDERLAND)
    lib.save_album(LAUGHING_STOCK)
    lib.rate('rg-weyes', 10, row=TITANIC_RISING)
    assert [e['key'] for e in lib.all()] == ['rg-weyes', 'rg-talktalk', 'rg-slint']

    lib.save_album(SPIDERLAND)                      # touching it moves it up
    assert [e['key'] for e in lib.all()] == ['rg-slint', 'rg-weyes', 'rg-talktalk']


def test_a_row_without_mbid_is_keyed_manually(tmp_path):
    lib = Library(str(tmp_path))
    entry = lib.save_album({'mbid': '', 'artist': 'Weyes Blood', 'album': 'Titanic Rising'})
    assert entry['key'] == WEYES_KEY
    assert entry['mbid'] is None
    assert [e['key'] for e in lib.unresolved()] == [WEYES_KEY]


def test_saving_with_an_mbid_absorbs_the_manual_twin(tmp_path):
    lib = Library(str(tmp_path))
    lib.rate('', 9.5, row={'mbid': '', 'artist': 'Weyes Blood', 'album': 'Titanic Rising'})
    assert lib.get(WEYES_KEY)['rating'] == 9.5

    entry = lib.save_album(TITANIC_RISING)
    assert entry['key'] == 'rg-weyes'
    assert entry['rating'] == 9.5                   # followed the record
    assert entry['saved'] is True
    assert entry['year'] == 2019
    assert lib.get(WEYES_KEY) is None
    assert len(lib.all()) == 1


def test_two_instances_share_one_file(tmp_path):
    Library(str(tmp_path)).save_album(SPIDERLAND)
    other = Library(str(tmp_path))
    assert other.is_saved('rg-slint')
    other.rate('rg-slint', 8)
    assert Library(str(tmp_path)).rating_of('rg-slint') == 8.0


# ---------------------------------------------------------------------------
# Robustness of the file
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('garbage', ['{not json', '[]', '{"entries": 3}', '', '"str"'])
def test_a_corrupt_file_is_an_empty_library(tmp_path, garbage):
    with open(tmp_path / 'library.json', 'w', encoding='utf-8') as handle:
        handle.write(garbage)
    lib = Library(str(tmp_path))
    assert lib.all() == []
    assert lib.get('rg-slint') is None
    assert lib.legacy_imported is False
    lib.save_album(SPIDERLAND)                      # and it recovers on write
    assert Library(str(tmp_path)).is_saved('rg-slint')


def test_odd_entries_on_disk_are_normalised(tmp_path):
    with open(tmp_path / 'library.json', 'w', encoding='utf-8') as handle:
        json.dump({'version': 1, 'entries': {
            'rg-x': {'artist': 'X', 'title': 'Y', 'rating': 7.3, 'saved': 1, 'year': '1999'},
            'rg-bad': 'not an entry',
        }}, handle)
    lib = Library(str(tmp_path))
    entry = lib.get('rg-x')
    assert entry['rating'] == 7.5
    assert entry['saved'] is True
    assert entry['year'] == 1999
    assert entry['note'] == ''
    assert entry['mbid'] is None
    assert lib.get('rg-bad') is None


# ---------------------------------------------------------------------------
# Legacy import and resolution
# ---------------------------------------------------------------------------

def test_legacy_import_reads_both_files_once(tmp_path):
    write_legacy(tmp_path, LEGACY_RATINGS, LEGACY_BOOKMARKS)
    lib = Library(str(tmp_path))
    assert lib.legacy_imported is False
    assert lib.import_legacy() == 2

    rated = lib.get(WEYES_KEY)
    assert rated['mbid'] is None
    assert rated['artist'] == 'Weyes Blood'
    assert rated['title'] == 'Titanic Rising'
    assert rated['rating'] == 10.0
    assert rated['rated_at'] == '2026-08-24T00:05:24.413817'
    assert rated['saved'] is False
    assert rated['source'] == 'legacy_ratings'

    saved = lib.get(WIDOW_KEY)
    assert saved['mbid'] is None
    assert saved['saved'] is True
    assert saved['saved_at'] == '2026-08-24T00:02:39.704212'
    assert saved['rating'] is None
    assert saved['url'] == LEGACY_BOOKMARKS['3030-true-widow-as-high']['url']
    assert saved['source'] == 'legacy_bookmarks'

    assert {e['key'] for e in lib.unresolved()} == {WEYES_KEY, WIDOW_KEY}
    assert lib.legacy_imported is True

    # Idempotent: a second call imports nothing and duplicates nothing, even
    # after the user has removed one of the entries.
    lib.remove(WIDOW_KEY)
    assert lib.import_legacy() == 0
    assert Library(str(tmp_path)).import_legacy() == 0
    assert [e['key'] for e in lib.all()] == [WEYES_KEY]


def test_legacy_import_copes_with_one_file_or_none(tmp_path):
    lib = Library(str(tmp_path))
    assert lib.import_legacy() == 0
    assert lib.all() == []

    write_legacy(tmp_path / 'ratings_only', ratings=LEGACY_RATINGS)
    lib = Library(str(tmp_path / 'ratings_only'))
    assert lib.import_legacy() == 1
    assert lib.get(WEYES_KEY)['rating'] == 10.0


def test_legacy_import_merges_a_rated_and_bookmarked_album(tmp_path):
    bookmarks = {'139513-weyes-blood-titanic-rising': {
        'title': 'Titanic Rising', 'artist_name': 'Weyes Blood', 'genres': [],
        'url': 'https://www.albumoftheyear.org/album/139513.php',
        'bookmarked_at': '2026-08-24T00:03:00',
    }}
    write_legacy(tmp_path, LEGACY_RATINGS, bookmarks)
    lib = Library(str(tmp_path))
    assert lib.import_legacy() == 1
    entry = lib.get(WEYES_KEY)
    assert entry['rating'] == 10.0
    assert entry['saved'] is True
    assert entry['saved_at'] == '2026-08-24T00:03:00'
    assert entry['url'] == bookmarks['139513-weyes-blood-titanic-rising']['url']
    assert len(lib.all()) == 1


def test_legacy_import_skips_junk_records(tmp_path):
    write_legacy(tmp_path, ratings={
        'no-title': {'rating': 8, 'artist_name': 'Someone'},
        'no-number': {'rating': 'n/a', 'artist_name': 'Someone', 'title': 'Thing'},
        'not-a-dict': 'x',
        'ok': {'rating': 7.3, 'artist_name': 'Someone', 'title': 'Else'},
    }, bookmarks='not a dict at all')
    lib = Library(str(tmp_path))
    assert lib.import_legacy() == 1
    assert [e['key'] for e in lib.all()] == ['manual:someone-else']
    assert lib.get('manual:someone-else')['rating'] == 7.5


def test_legacy_import_folds_into_an_album_already_saved_by_mbid(tmp_path):
    write_legacy(tmp_path, LEGACY_RATINGS, None)
    lib = Library(str(tmp_path))
    lib.save_album(TITANIC_RISING)
    assert lib.import_legacy() == 1
    assert lib.get(WEYES_KEY) is None
    entry = lib.get('rg-weyes')
    assert entry['rating'] == 10.0
    assert entry['saved'] is True
    assert entry['year'] == 2019                    # the library's details win
    assert entry['source'] == 'radius'
    assert lib.unresolved() == []


def test_resolve_rekeys_an_imported_entry(tmp_path):
    write_legacy(tmp_path, LEGACY_RATINGS, LEGACY_BOOKMARKS)
    lib = Library(str(tmp_path))
    lib.import_legacy()
    lib.set_note(WEYES_KEY, 'side one')

    entry = lib.resolve(WEYES_KEY, 'rg-weyes', year=2019, album='Titanic Rising',
                        image_url='https://img/tr.jpg', url='https://mb/rg-weyes')
    assert entry['key'] == 'rg-weyes'
    assert entry['mbid'] == 'rg-weyes'
    assert entry['rating'] == 10.0
    assert entry['rated_at'] == '2026-08-24T00:05:24.413817'
    assert entry['note'] == 'side one'
    assert entry['year'] == 2019
    assert entry['image_url'] == 'https://img/tr.jpg'
    assert entry['source'] == 'radius'

    assert lib.get(WEYES_KEY) is None
    assert lib.get('rg-weyes')['artist'] == 'Weyes Blood'
    assert [e['key'] for e in lib.unresolved()] == [WIDOW_KEY]
    assert lib.rating_of('rg-weyes') == 10.0
    assert lib.import_legacy() == 0                 # still no duplicates
    assert len(lib.all()) == 2


def test_resolve_merges_into_an_existing_mbid_entry(tmp_path):
    lib = Library(str(tmp_path))
    lib.save_album(TITANIC_RISING, from_seed='Slint - Spiderland')
    lib.set_note('rg-weyes', 'from radius')
    lib.rate('', 9.5, row={'mbid': '', 'artist': 'Weyes Blood', 'album': 'Titanic Rising (Remaster)'})
    manual = 'manual:weyes-blood-titanic-rising-remaster'
    lib.set_note(manual, 'from the old list')

    entry = lib.resolve(manual, 'rg-weyes')
    assert entry['saved'] is True
    assert entry['rating'] == 9.5
    assert entry['title'] == 'Titanic Rising'       # the existing entry's details win
    assert entry['from_seed'] == 'Slint - Spiderland'
    assert entry['note'] == 'from radius\nfrom the old list'
    assert lib.get(manual) is None
    assert len(lib.all()) == 1


def test_resolve_unknown_key_or_empty_mbid(tmp_path):
    lib = Library(str(tmp_path))
    assert lib.resolve('manual:nothing', 'rg-x') is None
    lib.save_album({'mbid': '', 'artist': 'A', 'album': 'B'})
    entry = lib.resolve('manual:a-b', '', year=2001)  # no mbid: details only
    assert entry['key'] == 'manual:a-b'
    assert entry['mbid'] is None
    assert entry['year'] == 2001
