from __future__ import annotations

from dataclasses import asdict, dataclass
import re
from typing import Any
from urllib.parse import urlparse

from latka_jazn.version import schema_version


SCHEMA_VERSION = schema_version("host_media_resource_catalog")
_URL_RE = re.compile(r"(?:https?://|www\.)\S+", flags=re.IGNORECASE)


def _fold(value: str) -> str:
    return str(value or "").lower().translate(str.maketrans("ąćęłńóśźż", "acelnoszz"))


@dataclass(frozen=True)
class MediaResource:
    name: str
    domains: tuple[str, ...]
    resource_kinds: tuple[str, ...]
    lookup_role: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


MEDIA_RESOURCES: tuple[MediaResource, ...] = (
    MediaResource("youtube", ("youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"), ("video", "music", "playlist", "live"), "public_metadata_and_page_lookup"),
    MediaResource("youtube_music", ("music.youtube.com",), ("music", "album", "track", "playlist"), "public_metadata_and_page_lookup"),
    MediaResource("spotify", ("spotify.com", "open.spotify.com"), ("track", "album", "artist", "playlist", "podcast"), "public_catalog_or_page_lookup"),
    MediaResource("soundcloud", ("soundcloud.com",), ("track", "artist", "playlist"), "public_metadata_and_page_lookup"),
    MediaResource("bandcamp", ("bandcamp.com",), ("track", "album", "artist"), "public_metadata_and_page_lookup"),
    MediaResource("apple_music", ("music.apple.com",), ("track", "album", "artist", "playlist"), "public_catalog_or_page_lookup"),
    MediaResource("apple_podcasts", ("podcasts.apple.com",), ("podcast", "episode"), "public_catalog_or_page_lookup"),
    MediaResource("deezer", ("deezer.com", "www.deezer.com"), ("track", "album", "artist", "playlist"), "public_metadata_and_page_lookup"),
    MediaResource("tidal", ("tidal.com", "listen.tidal.com"), ("track", "album", "artist", "playlist"), "public_metadata_and_page_lookup"),
    MediaResource("mixcloud", ("mixcloud.com", "www.mixcloud.com"), ("mix", "radio", "dj_set", "podcast"), "public_metadata_and_page_lookup"),
    MediaResource("audiomack", ("audiomack.com",), ("track", "album", "artist", "playlist"), "public_metadata_and_page_lookup"),
    MediaResource("lastfm", ("last.fm", "www.last.fm"), ("track", "album", "artist", "scrobble_metadata"), "music_metadata_lookup"),
    MediaResource("musicbrainz", ("musicbrainz.org",), ("recording", "release", "artist", "work"), "structured_music_metadata_lookup"),
    MediaResource("discogs", ("discogs.com", "www.discogs.com"), ("release", "artist", "label", "credits"), "discography_metadata_lookup"),
    MediaResource("genius", ("genius.com",), ("lyrics_page", "artist", "song_metadata"), "lyrics_page_discovery"),
    MediaResource("musixmatch", ("musixmatch.com", "www.musixmatch.com"), ("lyrics_page", "artist", "song_metadata"), "lyrics_page_discovery"),
    MediaResource("vimeo", ("vimeo.com", "www.vimeo.com"), ("video", "music_video", "live"), "public_metadata_and_page_lookup"),
    MediaResource("dailymotion", ("dailymotion.com", "www.dailymotion.com"), ("video", "music_video", "live"), "public_metadata_and_page_lookup"),
)

MEDIA_LOOKUP_TOKENS: tuple[str, ...] = (
    "youtube",
    "youtu.be",
    "spotify",
    "soundcloud",
    "bandcamp",
    "apple music",
    "deezer",
    "tidal",
    "mixcloud",
    "audiomack",
    "last.fm",
    "musicbrainz",
    "discogs",
    "genius",
    "musixmatch",
    "muzyk",
    "piosenk",
    "utwor",
    "posluch",
    "sluchaj",
    "album",
    "artyst",
    "wykonawc",
    "singiel",
    "playlista",
    "tekst piosenk",
    "tekst utwor",
    "teledysk",
    "koncert",
    "remiks",
    "remix",
    "cover",
    "wersja live",
    "soundtrack",
    "audio",
    "podcast",
    "music",
    "song",
    "track",
    "lyrics",
    "artist",
    "playlist",
    "listen",
    "music video",
    "live session",
)

_DOMAIN_INDEX: dict[str, str] = {
    domain.casefold(): item.name
    for item in MEDIA_RESOURCES
    for domain in item.domains
}


def media_resource_catalog() -> list[dict[str, Any]]:
    return [item.to_dict() for item in MEDIA_RESOURCES]


def _domain_from_url(value: str) -> str | None:
    raw = value.strip().rstrip(",.;:!?)]}")
    if raw.startswith("www."):
        raw = "https://" + raw
    try:
        parsed = urlparse(raw)
    except ValueError:
        return None
    host = str(parsed.hostname or "").casefold().strip(".")
    return host or None


def _resource_for_domain(domain: str) -> str | None:
    direct = _DOMAIN_INDEX.get(domain)
    if direct:
        return direct
    for known, resource in _DOMAIN_INDEX.items():
        if domain.endswith("." + known):
            return resource
    return None


def detect_media_lookup(text: str) -> dict[str, Any]:
    raw = str(text or "")
    folded = _fold(raw)
    matched_tokens = [token for token in MEDIA_LOOKUP_TOKENS if token in folded]
    urls = _URL_RE.findall(raw)
    resources: list[str] = []
    domains: list[str] = []
    for url in urls:
        domain = _domain_from_url(url)
        if not domain:
            continue
        domains.append(domain)
        resource = _resource_for_domain(domain)
        if resource and resource not in resources:
            resources.append(resource)

    media_lookup = bool(matched_tokens or resources)
    return {
        "schema_version": SCHEMA_VERSION,
        "media_lookup": media_lookup,
        "matched_tokens": list(dict.fromkeys(matched_tokens)),
        "matched_resources": resources,
        "matched_domains": list(dict.fromkeys(domains)),
        "urls_present": bool(urls),
        "preferred_host_tool": "web.run" if media_lookup else None,
        "lookup_scope": (
            "public_metadata_page_search_and_source_grounding" if media_lookup else "not_media_lookup"
        ),
        "playback_or_hearing_claim_allowed": False,
        "copyrighted_content_full_reproduction_allowed": False,
        "truth_boundary": (
            "Rozpoznanie serwisu lub słów muzycznych oznacza potrzebę lookupu metadanych/stron, nie dowód, "
            "że runtime albo host odtworzył, usłyszał lub uzyskał pełną treść audio albo tekst chroniony prawem autorskim."
        ),
    }
