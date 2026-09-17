"""Tunables and the tag stoplist.

No credentials live here, because none of the services Radius uses need one.
Everything network-facing is deliberately conservative — this project already
got one IP blocked by hammering a site, and the fix was not to sneak around
more carefully but to stop scraping and start asking APIs politely.
"""

import os

PROJECT_ROOT_GUESS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_dotenv(path=None):
    """Read .env into the environment if present, without adding a dependency.

    Values already in the real environment win, so an exported setting always
    beats a stale one in the file. Nothing here is required — .env is only
    useful for overriding rate limits or the contact address.
    """
    path = path or os.path.join(PROJECT_ROOT_GUESS, '.env')
    if not os.path.exists(path):
        return
    try:
        with open(path, encoding='utf-8') as handle:
            for line in handle:
                line = line.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                key, _, value = line.partition('=')
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = value
    except OSError:
        pass


load_dotenv()

PROJECT_ROOT = PROJECT_ROOT_GUESS
DATA_ROOT = os.path.join(PROJECT_ROOT, 'data')
CACHE_PATH = os.path.join(DATA_ROOT, 'cache', 'radius.sqlite')

MUSICBRAINZ_API_ROOT = 'https://musicbrainz.org/ws/2/'
LISTENBRAINZ_API_ROOT = 'https://api.listenbrainz.org/'
LISTENBRAINZ_LABS_ROOT = 'https://labs.api.listenbrainz.org/'
WIKIPEDIA_API_ROOT = 'https://en.wikipedia.org/w/api.php'
WIKIDATA_API_ROOT = 'https://www.wikidata.org/w/api.php'
LASTFM_API_ROOT = 'https://ws.audioscrobbler.com/2.0/'

# MusicBrainz publish a hard limit of one request per second for anonymous
# clients. ListenBrainz and Wikipedia are more generous, but there is no
# reason to crowd them either.
MUSICBRAINZ_REQUESTS_PER_SECOND = float(os.getenv('RADIUS_MB_RPS', '1'))
LISTENBRAINZ_REQUESTS_PER_SECOND = float(os.getenv('RADIUS_LB_RPS', '4'))
WIKIPEDIA_REQUESTS_PER_SECOND = float(os.getenv('RADIUS_WIKI_RPS', '4'))

# Last.fm is the one optional service, and the only one wanting a key. It is
# a tag enricher and nothing more: MusicBrainz tags are accurate but sparse —
# four votes on a record Last.fm has eighty tags for — and the thin end of
# that is exactly the mood vocabulary the fingerprint most wants. With no key
# set, every path here is skipped and the rest of Radius is unchanged.
LASTFM_API_KEY = os.getenv('LASTFM_API_KEY', '')
# Their terms allow roughly 5 requests/second; we sit under that.
LASTFM_REQUESTS_PER_SECOND = float(os.getenv('RADIUS_LASTFM_RPS', '4'))

# How many mbids to put in one ListenBrainz metadata/popularity request.
LB_BATCH_SIZE = int(os.getenv('RADIUS_LB_BATCH', '25'))

# ListenBrainz's collaborative similar-artist model. Their labs endpoint
# names the algorithm explicitly rather than versioning the URL.
LB_SIMILAR_ARTIST_ALGORITHM = os.getenv(
    'RADIUS_LB_SIMILAR_ALGORITHM',
    'session_based_days_7500_session_300_contribution_5_threshold_10_'
    'limit_100_filter_True_skip_30',
)

# Every one of these services asks to be told who is calling. Set
# RADIUS_CONTACT to your own address or repo so an operator can reach you if
# a run ever misbehaves — it is the courtesy that keeps these APIs open.
_CONTACT = os.getenv('RADIUS_CONTACT', 'https://github.com/cpet02/aoty-crawler')
USER_AGENT = os.getenv(
    'RADIUS_USER_AGENT', f'radius-album-similarity/0.2 ( {_CONTACT} )'
)

REQUEST_TIMEOUT = 25
MAX_RETRIES = 3

# Cache lifetimes, in days. Catalogue facts barely move; listening counts
# drift slowly enough that a month is plenty.
TTL_DAYS = {
    'mb.rg.search': 60,
    'mb.release.tracks': 365,
    'mb.rg.urls': 365,
    'lb.metadata': 60,
    'lb.popularity.rg': 30,
    'lb.popularity.artist': 30,
    'lb.top.rg': 60,
    'lb.similar.artist': 60,
    'wikipedia.extracts': 180,
    'wikidata.sitelinks': 365,
    'lastfm.album.tags': 90,
    'lastfm.artist.tags': 90,
}
DEFAULT_TTL_DAYS = 30

# Tags that say something about the person tagging rather than the record.
# MusicBrainz folksonomy tags are cleaner than Last.fm's were, but the same
# collection-management habits show up, so the filter stays.
TAG_STOPLIST = {
    'albums i own', 'albums i own on vinyl', 'own it on vinyl', 'vinyl',
    'cd', 'cassette', 'mp3', 'spotify', 'itunes', 'bandcamp', 'soundcloud',
    'seen live', 'favorite albums', 'favourite albums', 'favorites',
    'favourites', 'favorite', 'favourite', 'my favorite albums',
    'best albums', 'best album ever', 'best of', 'best albums ever',
    'masterpiece', 'masterpieces', 'perfect', 'perfect albums', '10 out of 10',
    'classic', 'classic albums', 'essential', 'essential albums',
    'albums i love', 'love', 'loved', 'amazing', 'awesome', 'beautiful',
    'brilliant', 'genius', 'epic', 'great', 'good', 'good stuff', 'nice',
    'music', 'albums', 'album', 'lp', 'ep', 'song', 'songs', 'tracks',
    'to listen', 'want to listen', 'to check out', 'wishlist', 'want',
    'listened', 'recently listened', 'currently listening', 'on repeat',
    'reviewed', 'rateyourmusic', 'rym', 'pitchfork', 'discogs',
    'male vocalists', 'female vocalists', 'male vocalist', 'female vocalist',
    'female vocals', 'male vocals', 'singer', 'vocal', 'vocals', 'band',
    'artists i have seen live', 'radio',
    # MusicBrainz-specific noise: release-format and housekeeping tags.
    'studio album', 'studio', 'live album', 'compilation', 'soundtrack',
    'stereo', 'mono', 'remaster', 'remastered', 'reissue', 'explicit',
    'other', 'misc', 'miscellaneous', 'unknown', 'none', 'various',
}

# Nationality tags are dropped from the descriptive vector because the artist
# area from ListenBrainz covers geography properly, on its own axis.
TAG_STOPLIST |= {
    'usa', 'american', 'british', 'uk', 'english', 'canadian', 'australian',
    'japanese', 'swedish', 'german', 'french', 'norwegian', 'finnish',
    'russian', 'italian', 'polish', 'brazilian', 'icelandic', 'irish',
    'scottish', 'dutch', 'spanish', 'danish', 'belgian', 'mexican',
    'new zealand', 'south korean', 'chinese', 'argentine', 'portuguese',
    # MusicBrainz carries plenty of non-English nationality tags too.
    'américain', 'americain', 'britannique', 'anglais', 'canadien',
    'australien', 'allemand', 'suédois', 'suedois', 'norvégien',
    'japonais', 'français', 'francais', 'irlandais', 'écossais',
    'estadounidense', 'britanico', 'británico', 'amerikanisch', 'britisch',
}

# Retailer and catalogue-shelf taxonomies. These describe a shop's browse
# tree rather than the record, and they are broad enough to make unrelated
# albums look alike, which is exactly the failure mode idf can't fix.
TAG_STOPLIST |= {
    'rock and indie', 'alternative and punk', 'pop and rock', 'pop and chart',
    'dance and electronic', 'jazz and blues', 'folk and country',
    'metal and hard rock', 'rap and hip-hop', 'soul and reggae',
    'easy listening', 'general', 'popular music', 'contemporary',
}
