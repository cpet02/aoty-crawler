"""Tunables and the tag stoplist.

No credentials are required here: every service Radius depends on serves its
data keyless. The two optional keys (Last.fm, Discogs) are purely additive.
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
WIKIDATA_API_ROOT = 'https://www.wikidata.org/w/api.php'
DEEZER_API_ROOT = 'https://api.deezer.com/'
DISCOGS_API_ROOT = 'https://api.discogs.com/'
LASTFM_API_ROOT = 'https://ws.audioscrobbler.com/2.0/'

# MusicBrainz publish a hard limit of one request per second for anonymous
# clients (a 503 is how they say "too fast"). ListenBrainz's API docs ask
# the same of every client application: never more than one call per
# second. Their rate headers allow bursts of 30 per 10-second window, but
# that is the ceiling, not the pace; since their fight with AI scrapers the
# gateway sometimes answers with a "Verifying your browser" page instead of
# data (seen Sep 2026). Wikidata and Deezer are more generous, but there is
# no reason to crowd them either.
MUSICBRAINZ_REQUESTS_PER_SECOND = float(os.getenv('RADIUS_MB_RPS', '1'))
LISTENBRAINZ_REQUESTS_PER_SECOND = float(os.getenv('RADIUS_LB_RPS', '1'))
WIKIDATA_REQUESTS_PER_SECOND = float(os.getenv('RADIUS_WIKIDATA_RPS', '4'))
# Deezer's documented limit is 50 requests per 5 seconds per IP.
DEEZER_REQUESTS_PER_SECOND = float(os.getenv('RADIUS_DEEZER_RPS', '5'))

# Discogs works keyless at 25 requests/minute. Credentials only raise that to
# 60/minute (and switch Discogs enrichment on by default); they unlock no
# extra data. Either a personal access token or a registered app's consumer
# key and secret will do. The database is public, so the full OAuth flow,
# which acts as a particular Discogs user, is never needed.
DISCOGS_TOKEN = os.getenv('DISCOGS_TOKEN', '')
DISCOGS_CONSUMER_KEY = os.getenv('DISCOGS_CONSUMER_KEY', '')
DISCOGS_CONSUMER_SECRET = os.getenv('DISCOGS_CONSUMER_SECRET', '')
DISCOGS_AUTHENTICATED = bool(DISCOGS_TOKEN or (DISCOGS_CONSUMER_KEY and DISCOGS_CONSUMER_SECRET))
DISCOGS_REQUESTS_PER_MINUTE = float(
    os.getenv('RADIUS_DISCOGS_RPM', '60' if DISCOGS_AUTHENTICATED else '25')
)

# Last.fm is the other optional service, and the only one wanting a key. It
# thickens tag vectors (MusicBrainz tags are accurate but sparse — four votes
# on a record Last.fm has eighty tags for — and the thin end of that is the
# mood vocabulary the fingerprint most wants), and adds similar artists, tag
# charts and listener counts as extra signals. With no key set, every path
# is skipped and the rest of Radius is unchanged.
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

# The similar-recordings endpoint rejects any algorithm name outside this
# set (the list is echoed in its 400 body). The days_9000 one is the broadest:
# 174 hits for one Slint track against 83 for the listener-capped variants.
LB_SIMILAR_RECORDING_ALGORITHMS = (
    'session_based_days_9000_session_300_contribution_5_threshold_15_limit_50_skip_30',
    'session_based_days_7500_session_300_contribution_5_threshold_15_limit_50_skip_30_top_n_listeners_1000',
    'session_based_days_7500_session_300_contribution_5_threshold_15_limit_50_skip_30',
    'session_based_days_180_session_300_contribution_5_threshold_15_limit_50_skip_30',
    'session_based_days_1500_session_300_contribution_5_threshold_15_limit_50_skip_30_top_n_listeners_1000',
    'session_based_days_7500_session_300_contribution_sqrt_threshold_15_limit_50_skip_30_top_n_listeners_1000',
    'session_based_listens_session_300_contribution_5_threshold_15_limit_50_skip_30',
)
LB_SIMILAR_RECORDING_ALGORITHM = os.getenv(
    'RADIUS_LB_SIMILAR_RECORDING_ALGORITHM', LB_SIMILAR_RECORDING_ALGORITHMS[0]
)

# Every one of these services asks to be told who is calling. Set
# RADIUS_CONTACT to your own address or repo so an operator can reach you if
# a run ever misbehaves — it is the courtesy that keeps these APIs open.
_CONTACT = os.getenv('RADIUS_CONTACT', 'https://github.com/cpet02/aoty-crawler')
USER_AGENT = os.getenv(
    'RADIUS_USER_AGENT', f'radius-album-similarity/0.3 ( {_CONTACT} )'
)

REQUEST_TIMEOUT = 25
MAX_RETRIES = 3

# Cache lifetimes, in days. Catalogue facts barely move; listening counts
# drift slowly enough that a month is plenty.
TTL_DAYS = {
    'mb.rg.search': 60,
    'mb.rg.full': 120,
    'mb.rg.browse': 60,
    'mb.release.full': 365,
    'mb.artist.full': 120,
    'mb.genres': 365,
    'lb.metadata': 60,
    'lb.metadata.recording': 120,
    'lb.popularity.rg': 30,
    'lb.popularity.artist': 30,
    'lb.top.rg': 60,
    'lb.similar.artist': 60,
    'lb.similar.recording': 60,
    'wikidata.entities': 120,
    'wikidata.labels': 365,
    'deezer.search': 120,
    'deezer.album': 60,
    'deezer.track': 365,
    'discogs.master': 180,
    'discogs.release': 60,
    'lastfm.album.tags': 90,
    'lastfm.artist.tags': 90,
    'lastfm.artist.similar': 90,
    'lastfm.album.info': 30,
    'lastfm.tag.albums': 30,
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
    'this album is exceptionally important', 'exceptionally important',
    'overrated', 'underrated', 'albums to hear before you die',
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
