"""Async helpers for extracting culture signals from Qloo.

Callers may pass any async HTTP client implementing :class:`AsyncQlooClient`.

Use :func:`create_qloo_async_client` to create an authenticated ``httpx`` client
from the repository's existing settings.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from typing import Protocol, TypedDict

import httpx

from backend.settings import QLOO_BASE_URL, get_settings

SEARCH_TYPES: tuple[str, ...] = (
    "urn:entity:artist",
    "urn:entity:book",
    "urn:entity:brand",
    "urn:entity:destination",
    "urn:entity:movie",
    "urn:entity:person",
    "urn:entity:place",
    "urn:entity:podcast",
    "urn:entity:tv_show",
)
"""Entity types searched when resolving a free-text Qloo entity name."""

_INSIGHTS_TAKE = 50
_TAG_TYPE = "urn:tag"


class AsyncQlooClient(Protocol):
    """Minimal async HTTP interface accepted by the extractor functions."""

    async def get(
        self, url: str, *, params: Mapping[str, str | int]
    ) -> httpx.Response: ...


class TasteSignal(TypedDict):
    """Normalized Qloo tag returned by a taste extraction request."""

    id: str
    name: str


class BrandCultureComparison(TypedDict):
    """Tag overlap and differences between two brands' culture signals."""

    shared: list[TasteSignal]
    first_only: list[TasteSignal]
    second_only: list[TasteSignal]


class ExpandedPersonaAndTAMSignals(TypedDict):
    """Deduplicated tag expansions for persona and TAM entity identifiers."""

    persona: list[TasteSignal]
    tam: list[TasteSignal]


def create_qloo_async_client(**kwargs: object) -> httpx.AsyncClient:
    """Create an authenticated ``httpx.AsyncClient`` from existing settings.

    The API key is read from ``get_settings()`` and is never embedded here.
    ``kwargs`` are forwarded to ``httpx.AsyncClient`` (for example a test
    transport or timeout).
    """

    api_key = get_settings().qloo_api_key
    if not api_key:
        raise ValueError("QLOO_API_KEY is required to create a Qloo client")
    return httpx.AsyncClient(
        base_url=QLOO_BASE_URL,
        headers={"X-Api-Key": api_key, "Accept": "application/json"},
        **kwargs,
    )


def _clean_string(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _extract_entity_id(item: object) -> str | None:
    if not isinstance(item, Mapping):
        return None

    candidates: list[object] = [item.get("entity_id"), item.get("id")]
    nested = item.get("entity")
    if isinstance(nested, Mapping):
        candidates.extend((nested.get("entity_id"), nested.get("id")))
    return next((value for raw in candidates if (value := _clean_string(raw))), None)


async def resolve_qloo_entity_id(
    client: AsyncQlooClient,
    entity_name: str,
    types: Sequence[str] = SEARCH_TYPES,
) -> str | None:
    """Resolve a name via Qloo ``/search`` and return its first entity ID.

    ``types`` is sent as a comma-separated list of entity URNs. Returns ``None``
    when Qloo has no usable result; HTTP status errors are propagated unchanged.
    """

    query = _clean_string(entity_name)
    if query is None:
        raise ValueError("entity_name must be a non-empty string")

    normalized_types = tuple(
        sorted({cleaned for value in types if (cleaned := _clean_string(value))})
    )
    if not normalized_types:
        raise ValueError("types must contain at least one non-empty entity type")

    response = await client.get(
        f"{QLOO_BASE_URL}/search",
        params={"query": query, "types": ",".join(normalized_types)},
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, Mapping):
        raise ValueError("Qloo search response must be a JSON object")

    results = payload.get("results", [])
    if not isinstance(results, list):
        raise ValueError("Qloo search results must be a JSON array")

    return next((entity_id for item in results if (entity_id := _extract_entity_id(item))), None)


def _normalized_tastes(payload: object) -> list[TasteSignal]:
    if not isinstance(payload, Mapping):
        raise ValueError("Qloo insights response must be a JSON object")

    results = payload.get("results", [])
    if not isinstance(results, list):
        raise ValueError("Qloo insights results must be a JSON array")

    by_id: dict[str, str] = {}
    for item in results:
        if not isinstance(item, Mapping):
            continue

        nested = item.get("entity")
        entity = nested if isinstance(nested, Mapping) else item
        entity_id = _clean_string(entity.get("id")) or _clean_string(entity.get("entity_id"))
        name = _clean_string(entity.get("name"))
        if entity_id is None:
            entity_id = name
        if entity_id is None:
            continue
        name = name or entity_id

        # If a malformed response repeats an id with different labels, choose
        # deterministically rather than depending on response ordering.
        by_id[entity_id] = min(by_id.get(entity_id, name), name)

    return [{"id": entity_id, "name": by_id[entity_id]} for entity_id in sorted(by_id)]


async def fetch_entity_tastes(
    client: AsyncQlooClient, entity_id: str
) -> list[TasteSignal]:
    """Fetch up to 50 normalized taste-tag signals for one Qloo entity ID.

    The insights request uses ``signal.interests.entities``, ``filter.type``
    set to ``urn:tag``, and ``take=50``. Returns tags sorted and deduplicated by
    ID; HTTP status errors propagate to the caller.
    """

    clean_id = _clean_string(entity_id)
    if clean_id is None:
        raise ValueError("entity_id must be a non-empty string")

    response = await client.get(
        f"{QLOO_BASE_URL}/v2/insights",
        params={
            "signal.interests.entities": clean_id,
            "filter.type": _TAG_TYPE,
            "take": _INSIGHTS_TAKE,
        },
    )
    response.raise_for_status()
    return _normalized_tastes(response.json())


async def fetch_term_tastes(
    client: AsyncQlooClient,
    term: str,
    types: Sequence[str] = SEARCH_TYPES,
) -> list[TasteSignal]:
    """Resolve a free-text term and fetch its taste tags.

    Returns an empty list when the term cannot be resolved; otherwise returns
    the normalized, deterministic tag list from :func:`fetch_entity_tastes`.
    """

    entity_id = await resolve_qloo_entity_id(client, term, types=types)
    if entity_id is None:
        return []
    return await fetch_entity_tastes(client, entity_id)


def _taste_index(tastes: Sequence[TasteSignal]) -> dict[str, TasteSignal]:
    return {taste["id"]: taste for taste in tastes}


async def compare_brand_cultures(
    client: AsyncQlooClient,
    first_brand_id: str,
    second_brand_id: str,
) -> BrandCultureComparison:
    """Compare two brands' tag signals, returning shared and unique tags.

    The result contains sorted ``shared``, ``first_only``, and ``second_only``
    lists of normalized tag objects. Both insights requests are issued
    concurrently; HTTP errors are propagated.
    """

    first, second = await asyncio.gather(
        fetch_entity_tastes(client, first_brand_id),
        fetch_entity_tastes(client, second_brand_id),
    )
    first_by_id, second_by_id = _taste_index(first), _taste_index(second)
    first_ids, second_ids = set(first_by_id), set(second_by_id)

    return {
        "shared": [first_by_id[key] for key in sorted(first_ids & second_ids)],
        "first_only": [first_by_id[key] for key in sorted(first_ids - second_ids)],
        "second_only": [second_by_id[key] for key in sorted(second_ids - first_ids)],
    }


async def expand_persona_and_tam_signals(
    client: AsyncQlooClient,
    persona_entity_ids: Sequence[str],
    tam_entity_ids: Sequence[str],
) -> ExpandedPersonaAndTAMSignals:
    """Expand persona and TAM entity IDs into deduplicated taste-tag lists.

    Each group is fetched concurrently. Tags are unioned by ID and sorted, so
    output does not depend on request completion or input order.
    """

    async def expand(entity_ids: Sequence[str]) -> list[TasteSignal]:
        groups = await asyncio.gather(
            *(fetch_entity_tastes(client, entity_id) for entity_id in entity_ids)
        )
        merged: dict[str, TasteSignal] = {}
        for group in groups:
            for taste in group:
                merged[taste["id"]] = taste
        return [merged[key] for key in sorted(merged)]

    persona, tam = await asyncio.gather(
        expand(persona_entity_ids), expand(tam_entity_ids)
    )
    return {"persona": persona, "tam": tam}
