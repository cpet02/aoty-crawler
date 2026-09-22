# Verified API facts (live-probed 2026-09-22)

Exact shapes the clients and parsers rely on. Every item here was observed
in a live response, not read from documentation. Send
`User-Agent: radius-album-similarity/0.3 ( <contact> )` and
`Accept: application/json` on every request.

## MusicBrainz — https://musicbrainz.org/ws/2/ (fmt=json)

Rate: 1 request/second per IP, hard. Exceeding it returns 503 "exceeding the
allowable rate limit". No rate headers. Search (`?query=`) and lookups are
served by different backends; search omits empty keys, lookups return empty
lists.

**Release-group lookup** `release-group/{mbid}?inc=releases+media+url-rels+genres+tags+ratings+artist-credits`
— accepted as-is.
- `first-release-date` ('1991-03-15'), `primary-type`, `secondary-types` (list, may be empty)
- `releases[]`: `id`, `status` ('Official'…), `date` (variable precision: '1991' or '1991-03-15', may be absent), `country` ('US', 'XW' worldwide, 'XE' Europe, may be absent), `title`, `disambiguation`, `packaging`, `barcode`
- `releases[].media[]`: `format` ('CD', 'Digital Media', '12" Vinyl'…), `track-count`, `position`. No tracks here.
- `genres[]` `{name, count}` — MB's whitelisted genres; `tags[]` `{name, count}` — includes folksonomy
- `rating.value` (0–5 float or null), `rating.votes-count`
- `relations[]` (url-rels): `type` ∈ allmusic, discogs, wikidata, review, 'other databases', 'discography entry', …; `url.resource`. Discogs master id = `/master/(\d+)`, Wikidata id = `/wiki/(Q\d+)`, AllMusic = `/album/(mw\d+)`.
- Dates must be normalised before ordering ('1991' vs '1991-03-15').

**Release lookup** `release/{mbid}?inc=recordings+artist-credits+labels+artist-rels+recording-level-rels+place-rels+media+release-groups`
— accepted as-is.
- `status`, `date`, `country`, `barcode`, `packaging`, `label-info[]` → `label.id`, `label.name`, `catalog-number` (may be null)
- `artist-credit[].artist.id` (the album artists — used to tell guests from members)
- `media[]`: `format`, `track-count`, `tracks[]` → `title`, `length` (ms int, may be null), `number` (string), `position`, `recording.id`, `recording.length`, `recording.relations[]`, `artist-credit[]`
- **Credits live at recording level**: `media[].tracks[].recording.relations[]` with `type` ∈ instrument, vocal, recording, engineer, mix, mastering, producer, programming, … (`target-type` 'artist', `direction` 'backward', `artist.id`, `artist.name`, `artist.type`, `attributes` list like ['electric bass guitar'] or ['additional']) and `type` 'recorded at' / 'mixed at' … with `target-type` 'place', `place.id`, `place.name`.
- Release-level `relations[]` is often empty; when present it is place rels ('mastered at', 'manufactured at' — ignore 'manufactured at').
- Same (type, artist.id) appears on every track: aggregate by artist id.

**Artist lookup** `artist/{mbid}?inc=artist-rels+url-rels+genres+tags+ratings` — accepted.
- `type` ('Group'/'Person'), `gender`, `country`, `area.name`, `begin-area.name`, `life-span.begin/end/ended`, `genres[]`, `tags[]`, `rating`
- `relations[]` with `target-type` 'artist': `type` ∈ 'member of band' (group side: direction 'backward', the member is `artist`; person side: direction 'forward', the band is `artist`), 'is person' (solo aliases, Person↔Person), 'instrumental supporting musician', 'vocal supporting musician', 'supporting musician', 'collaboration', 'founder', 'subgroup'; `artist.id/name/type`, `begin`, `end`, `ended`, `attributes` (instruments, 'original'). Same pair can repeat with different attributes — dedupe by artist id.
- url-rels: allmusic, bandcamp, discogs (artist id), 'free streaming', last.fm, 'official homepage', wikidata, youtube music, streaming, 'social network', songkick…
- A group lookup gives its members but NOT the members' other bands: one more lookup per member.

**Search** `release-group?query=<lucene>&limit=100&offset=0`
- Conjunctions work: `tag:"post-rock" AND tag:"slowcore" AND primarytype:album` (152 hits). All scores 100 for AND queries; ordering is not meaningful.
- Results: `id`, `title`, `score`, `primary-type`, `secondary-types` (ONLY present when non-empty), `first-release-date` (may be absent), `count` (releases in group), `tags[] {name,count}`, `artist-credit[].artist.id/name`, `artist-credit[].name`, `releases[].id/status`.
- Escape Lucene specials as the existing `_escape` does.

**Genre whitelist** `genre/all?fmt=txt` → `text/plain`, one lowercase name per line, 2206 lines (2-step, … zydeco). Cache 365 days.

## ListenBrainz — https://api.listenbrainz.org/1/ and https://labs.api.listenbrainz.org/

Rate: api.listenbrainz.org returns `X-RateLimit-Limit: 30`, `X-RateLimit-Remaining`, `X-RateLimit-Reset-In` (seconds) — **30 requests per ~10 s window**. Keep ≤ 2.5 rps and sleep `Reset-In` when Remaining hits 0. Labs has no headers; keep 0.5 s spacing.

**Similar recordings** `labs…/similar-recordings/json?recording_mbids=A&recording_mbids=B&algorithm=<name>`
- Multiple seeds by REPEATING `recording_mbids` (requests `params` as a list of tuples). Comma-joined → 400.
- `algorithm` is mandatory and must be one of: `session_based_days_9000_session_300_contribution_5_threshold_15_limit_50_skip_30` (broadest: 174 hits for one Slint track), `session_based_days_7500_session_300_contribution_5_threshold_15_limit_50_skip_30_top_n_listeners_1000` (83 hits, listener-capped), `session_based_days_7500_session_300_contribution_5_threshold_15_limit_50_skip_30`, `session_based_days_180_…`, `session_based_days_1500_…_top_n_listeners_1000`, `session_based_days_7500_session_300_contribution_sqrt_threshold_15_limit_50_skip_30_top_n_listeners_1000`, `session_based_listens_session_300_contribution_5_threshold_15_limit_50_skip_30`. Default to the days_9000 one.
- Response: FLAT list; entries `{recording_mbid, recording_name, artist_credit_name, artist_credit_mbids (null — do not rely on it), release_name, release_mbid, caa_id, caa_release_mbid, score (int co-listen count, descending), reference_mbid (which seed)}`. Total capped around 200 across seeds; partition by `reference_mbid`. No release_group_mbid.
- Errors are HTML with 400 — check content-type before `.json()`.

**Recording metadata** `1/metadata/recording/?recording_mbids=a,b,…&inc=artist release` (comma-separated OK, ≤25 per call)
- Dict keyed by recording mbid (missing ones absent). `.recording.name/length/first_release_date/isrcs/rels[]` (`{artist_mbid, artist_name, instrument?, type}` performer credits), `.artist.artists[].artist_mbid/name/type/area/begin_year/end_year/rels{}`, `.release.mbid/name/release_group_mbid/caa_id/caa_release_mbid/year/album_artist_name`.

**Similar artists** `labs…/similar-artists/json?artist_mbids=<mbid>&algorithm=session_based_days_7500_session_300_contribution_5_threshold_10_limit_100_filter_True_skip_30` — flat list of 100: `{artist_mbid, name, comment, type, gender, score (int), reference_mbid}`.

**Release-group metadata** `1/metadata/release_group/?release_group_mbids=…&inc=tag artist release` — dict keyed by mbid. `release_group.{name,type,date,caa_id,caa_release_mbid,rels[]}` (NO secondary_types), `artist.artists[].{artist_mbid,name,type,area,begin_year,end_year,join_phrase,rels{type: url}}`, `tag.release_group[]` / `tag.artist[]` entries `{tag, count, genre_mbid?}` — **`genre_mbid` present iff the tag is an MB genre**.

**Popularity** bulk endpoints (`1/popularity/release-group`, `1/popularity/artist`) work keyless as in v1.
`1/popularity/top-recordings-for-artist` and `1/popularity/top-release-groups-for-artist` **both return 401 without an
auth token** (verified 2026-09-22: "Due to bad actors and AI scrapers... you need to provide an Auth token"). The client
still tries top-release-groups (it returns [] on the 401), and `candidates.artist_albums` falls back to a MusicBrainz
release-group browse ranked by the keyless bulk popularity call.

**MusicBrainz release-group browse** `release-group?artist=<mbid>&fmt=json&limit=100` → `release-groups[] {id, title,
primary-type, secondary-types, first-release-date}` plus `release-group-count`. Slint: 12 groups, mostly Live bootlegs,
so filter on primary type Album/EP and drop non-studio secondary types.

## Deezer — https://api.deezer.com/ (keyless)

Rate: documented 50 requests / 5 s per IP; no headers. **Errors come back as HTTP 200 with `{"error": {"type", "message", "code"}}`** — code 800 'no data' (bad id), code 4 'Quota limit exceeded'. Empty search is `{"data": [], "total": 0}`.

- `search/album?q=artist:"Slint" album:"Spiderland"&limit=5` → `data[] {id, title, artist.{id,name}, nb_tracks, record_type ('album'…), explicit_lyrics, cover_medium, link}`. Order is unreliable (plain `q=` ranked the 20-track remaster first): match artist name exactly (casefold), skip titles with remaster/deluxe/expanded unless the seed title has them, prefer `nb_tracks` equal to the MusicBrainz canonical track count, prefer record_type 'album'.
- `album/{id}` → `fans`, `duration` (s), `nb_tracks`, `release_date`, `label`, `upc` (= MB barcode), `genres.data[].name` (may be empty), `explicit_lyrics` (bool), `explicit_content_lyrics` (int 0/1/2), `record_type`, `link`, `tracks.data[] {id, title, duration, rank, explicit_lyrics}`. No bpm/gain at album level.
- `track/{id}` → `bpm` (float; 0 = not analysed → missing), `gain` (dB float), `rank`, `duration`, `isrc`, `release_date`, `track_position`. BPM was present even for a 1991 track.
- No MusicBrainz ids anywhere; bridge on upc/isrc or name matching.

## Wikidata — https://www.wikidata.org/w/api.php

Rate: no hard limit; keep ≤ 4 rps, descriptive User-Agent. `wbgetentities&ids=Q1|Q2|…&props=claims|labels|sitelinks&languages=en&sitefilter=enwiki&format=json`, up to 50 ids per call. Unknown ids come back as `entities.<id>.missing`.

- Item values: `claims.P162[i].mainsnak.datavalue.value.id`; external ids: `.datavalue.value` (string); time: `.datavalue.value.time` ('+1991-03-27T00:00:00Z', honour `.precision` 11 day / 10 month / 9 year); quantity: `.datavalue.value.amount` ('+3201') with `.unit` (Q11574 second, Q7727 minute).
- `qualifiers`, `qualifiers-order`, `references` keys are OMITTED when empty. Skip `rank == 'deprecated'`.
- Properties with good coverage: P175 performer, P136 genre (multi), P162 producer, P264 label (multi), P577 publication date, P436 MB release-group id, P1954 Discogs master id, P2205 Spotify album id, P1729 AllMusic album id, P7067 Album of the Year album id, P3192 Last.fm id, P2047 duration, P155/P156 follows/followed by.
- P444 review score is SPARSE (Spiderland has none; OK Computer has 2) and the value is a bare string whose scale is implied by the reviewer in qualifier P447: '5' with P447=Q31181 (AllMusic, /5), '94' with P447=Q48989591 (Album of the Year, /100). P7887 qualifier marks an aggregate (number of reviews). P459 never seen. Parse defensively; do not rank on it by default.
- P483 / P1071 (studio, location) were absent on both probed albums. P1902 is Spotify ARTIST id (absent on albums).
- Resolve any Q-id to a name with one `props=labels` call (`entities.Q.labels.en.value`; may be absent).
- Prefer MB url-rels → Q-id over `wbsearchentities` (ambiguous by title).

## Discogs — https://api.discogs.com/ (keyless; optional token)

Rate: 25 requests/minute keyless, 60/minute with `Authorization: Discogs token=<token>`; moving 60 s window; headers `x-discogs-ratelimit`, `x-discogs-ratelimit-used`, `x-discogs-ratelimit-remaining`; 429 with Retry-After when exceeded. User-Agent is required by policy.

- `masters/{id}` (id from MB url-rels) → `styles[]` ('Alternative Rock', 'Math Rock', 'Post Rock'), `genres[]`, `year`, `main_release` (id), `most_recent_release`, `num_for_sale`, `lowest_price` (float, default currency; pass `curr_abbr=USD`), `tracklist[] {position, title, duration 'm:ss'}`, `artists[]`, `images[]`, `uri`. No community stats, labels, country on the master.
- `releases/{main_release}` → `community.have`, `community.want`, `community.rating.average` (0–5), `community.rating.count`, `labels[] {name, catno, id}`, `formats[] {name, descriptions[], qty}`, `country`, `released` ('1991-03-27', '1991', or '1991-00-00'), `genres`, `styles`, `extraartists[] {name, role}` (roles like 'Producer', 'Engineer', 'Mixed By', 'Mastered By', 'Recorded By', 'Bass [Uncredited]'), `companies[] {name, entity_type_name}`, `notes`, `num_for_sale`, `lowest_price`, `master_id` (may be absent/0).
- `masters/{id}/versions?per_page=1` → `pagination.items` = version count; `filters.available.format/country` histograms. Not used by default.

## Last.fm — https://ws.audioscrobbler.com/2.0/ (key required)

Rate: ~5 requests/second per key; no headers. Errors are JSON `{error: int, message}`: 10 bad key, 6 not found (404), 29 rate limit. **List quirk: a single item comes back as a dict, none as ''** — normalise every list (`similarartists.artist`, `albums.album`, `tags.tag`, `tracks.track`, `toptags.tag`).

- `artist.getSimilar&artist=Slint&limit=30` → `similarartists.artist[] {name, mbid ('' when unknown; 28/30 had one), match (STRING '0.835862'; first is '1'), url}`.
- `tag.getTopAlbums&tag=post-rock&limit=50&page=1` → `albums.album[] {name, mbid (a RELEASE id, '' for 6%), artist.{name, mbid (100% present)}, url, @attr.rank}`; `albums.@attr.total` etc. are strings.
- `album.getInfo&artist=&album=` → `album.{name, artist (STRING), mbid, url, listeners (STRING), playcount (STRING), wiki.{summary, content} (omitted when none; summary ends with an HTML <a> link), tags.tag[] {name} (no weights), tracks.track[] {name, duration (int seconds or null), @attr.rank}}`. Unknown → 404 error 6.
- `album.getTopTags` and `artist.getTopTags` → `toptags.tag[] {name, count (int 0–100)}` as v1 assumes.
