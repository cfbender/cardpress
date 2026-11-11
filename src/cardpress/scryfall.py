"""Scryfall client: search the catalogue and flatten cards into printable faces."""

import threading
import time
from dataclasses import dataclass
from functools import lru_cache

import httpx

API = "https://api.scryfall.com"
# Scryfall rejects requests without an accurate User-Agent and an Accept header.
HEADERS = {"User-Agent": "cardpress/0.1", "Accept": "application/json;q=0.9,*/*;q=0.8"}
# Scryfall's hard limits: 2 searches per second, 10 other requests per second.
SEARCH_INTERVAL = 0.5
LOOKUP_INTERVAL = 0.1

# Emblems and dungeons are not "tokens" to Scryfall, but they are at the table.
KIND_FILTERS = {
    "tokens": "(is:token or layout:emblem or t:dungeon)",
    "cards": "",
    "all": "include:extras",
}


class ScryfallError(Exception):
    def __init__(self, status: int, details: str):
        super().__init__(details)
        self.status = status
        self.details = details


@dataclass(frozen=True)
class Face:
    """One printable side of a card."""

    card_id: str
    index: int
    name: str
    mana_cost: str
    type_line: str
    rules: str
    stats: str
    colors: tuple[str, ...]
    artist: str
    set_name: str
    art_url: str | None
    image_url: str | None


@dataclass(frozen=True)
class SearchResult:
    faces: tuple[Face, ...]
    total_cards: int
    has_more: bool


class _Throttle:
    """Spaces requests out so the service never exceeds Scryfall's rate limits."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._ready_at = 0.0

    def wait(self, interval: float) -> None:
        with self._lock:
            delay = self._ready_at - time.monotonic()
            if delay > 0:
                time.sleep(delay)
            self._ready_at = time.monotonic() + interval


_client = httpx.Client(headers=HEADERS, timeout=20, follow_redirects=True)
_throttle = _Throttle()


def _get(path: str, params: dict | None, interval: float) -> dict:
    _throttle.wait(interval)
    try:
        response = _client.get(API + path, params=params)
    except httpx.HTTPError as error:
        raise ScryfallError(502, f"Could not reach Scryfall: {error}") from error
    try:
        body = response.json()
    except ValueError:
        body = {}
    if response.is_error:
        raise ScryfallError(response.status_code, body.get("details") or f"Scryfall returned {response.status_code}")
    return body


def _stats(part: dict) -> str:
    if part.get("power") is not None:
        return f"{part['power']}/{part['toughness']}"
    return part.get("loyalty") or part.get("defense") or ""


def faces_of(card: dict) -> list[Face]:
    """Split a Scryfall card into the sides that print separately.

    Transform cards, modal double-faced cards, and double-faced tokens have a
    picture per face, so each face prints on its own. Split, adventure, and flip
    cards are one picture: they print once, with the other halves in the rules box.
    """
    parts = card.get("card_faces") or [card]
    if not parts[0].get("image_uris"):
        first, *others = parts
        halves = [
            f"{half['name']} {half.get('mana_cost', '')} ({half.get('type_line', '')})\n{half.get('oracle_text', '')}"
            for half in others
        ]
        rules = "\n".join([first.get("oracle_text", ""), *halves])
        parts = [{**card, **first, "oracle_text": rules, "image_uris": card.get("image_uris")}]

    faces = []
    for index, part in enumerate(parts):
        images = part.get("image_uris") or {}
        faces.append(
            Face(
                card_id=card["id"],
                index=index,
                name=part["name"],
                mana_cost=part.get("mana_cost", ""),
                type_line=part.get("type_line", ""),
                rules=part.get("oracle_text", ""),
                stats=_stats(part),
                colors=tuple(part.get("colors") or card.get("colors") or ()),
                artist=part.get("artist") or card.get("artist", ""),
                set_name=card.get("set_name", ""),
                art_url=images.get("art_crop"),
                image_url=images.get("normal"),
            )
        )
    return faces


def search(query: str, kind: str) -> SearchResult:
    """The first page of Scryfall matches for a search in Scryfall syntax."""
    try:
        page = _get("/cards/search", {"q": f"({query}) {KIND_FILTERS[kind]}"}, SEARCH_INTERVAL)
    except ScryfallError as error:
        if error.status == 404:  # Scryfall answers "no matches" with a 404.
            return SearchResult((), 0, False)
        raise
    faces = tuple(face for card in page["data"] for face in faces_of(card))
    return SearchResult(faces, page["total_cards"], page["has_more"])


@lru_cache(maxsize=256)
def card_faces(card_id: str) -> tuple[Face, ...]:
    return tuple(faces_of(_get(f"/cards/{card_id}", None, LOOKUP_INTERVAL)))


@lru_cache(maxsize=64)
def art(url: str) -> bytes:
    """Art crop bytes. The image CDN (*.scryfall.io) has no rate limit."""
    try:
        return _client.get(url).raise_for_status().content
    except httpx.HTTPError as error:
        raise ScryfallError(502, f"Could not download the card art: {error}") from error
