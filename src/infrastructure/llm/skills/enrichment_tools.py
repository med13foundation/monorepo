"""Skill builders for Tier-2 content acquisition and enrichment decisions."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import urlopen

from src.type_definitions.json_utils import to_json_value

if TYPE_CHECKING:
    from collections.abc import Callable

    from src.type_definitions.common import JSONObject


def _normalize_identifier(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _normalize_pmcid(pmcid: str) -> str:
    candidate = pmcid.strip().upper()
    if candidate.startswith("PMC"):
        return candidate
    return f"PMC{candidate}"


def _http_get_text(url: str, *, timeout_seconds: int) -> str:
    with urlopen(url, timeout=timeout_seconds) as response:  # noqa: S310
        payload = response.read()
    if not isinstance(payload, bytes | bytearray):
        msg = "Expected HTTP response payload to be bytes"
        raise TypeError(msg)
    return bytes(payload).decode("utf-8", errors="replace")


def make_fetch_pmc_oa_tool(
    *,
    http_timeout_seconds: int = 20,
    **_: object,
) -> Callable[[str], JSONObject]:
    """Build a tool callable for fetching PMC OA XML metadata."""

    def fetch_pmc_oa(pmcid: str) -> JSONObject:
        normalized = _normalize_pmcid(pmcid)
        encoded = quote(normalized, safe="")
        url = f"https://www.ncbi.nlm.nih.gov/pmc/utils/oa/oa.fcgi?id={encoded}"
        try:
            content_text = _http_get_text(url, timeout_seconds=http_timeout_seconds)
        except (HTTPError, URLError, OSError, UnicodeDecodeError) as exc:
            return {
                "found": False,
                "acquisition_method": "pmc_oa",
                "content_format": "xml",
                "content_text": None,
                "content_length_chars": 0,
                "warning": f"PMC OA fetch failed: {exc!s}",
                "source_url": url,
            }

        return {
            "found": True,
            "acquisition_method": "pmc_oa",
            "content_format": "xml",
            "content_text": content_text,
            "content_length_chars": len(content_text),
            "source_url": url,
        }

    return fetch_pmc_oa


def make_fetch_europe_pmc_tool(
    *,
    http_timeout_seconds: int = 20,
    **_: object,
) -> Callable[[str], JSONObject]:
    """Build a tool callable for fetching Europe PMC full-text XML."""

    def fetch_europe_pmc(identifier: str) -> JSONObject:
        normalized = _normalize_identifier(identifier)
        if normalized is None:
            return {
                "found": False,
                "acquisition_method": "europe_pmc",
                "content_format": "xml",
                "content_text": None,
                "content_length_chars": 0,
                "warning": "Identifier is required for Europe PMC fetch",
            }

        encoded = quote(normalized, safe="")
        url = f"https://www.ebi.ac.uk/europepmc/webservices/rest/{encoded}/fullTextXML"
        try:
            content_text = _http_get_text(url, timeout_seconds=http_timeout_seconds)
        except (HTTPError, URLError, OSError, UnicodeDecodeError) as exc:
            return {
                "found": False,
                "acquisition_method": "europe_pmc",
                "content_format": "xml",
                "content_text": None,
                "content_length_chars": 0,
                "warning": f"Europe PMC fetch failed: {exc!s}",
                "source_url": url,
            }

        return {
            "found": True,
            "acquisition_method": "europe_pmc",
            "content_format": "xml",
            "content_text": content_text,
            "content_length_chars": len(content_text),
            "source_url": url,
        }

    return fetch_europe_pmc


def make_check_open_access_tool(
    **_: object,
) -> Callable[[str | None, str | None], JSONObject]:
    """Build a tool callable for coarse open-access eligibility checks."""

    def check_open_access(
        pmcid: str | None = None,
        doi: str | None = None,
    ) -> JSONObject:
        normalized_pmcid = _normalize_identifier(pmcid)
        normalized_doi = _normalize_identifier(doi)
        if normalized_pmcid is not None:
            return {
                "is_open_access": True,
                "reason": "pmcid_present",
                "pmcid": _normalize_pmcid(normalized_pmcid),
                "doi": normalized_doi,
            }
        return {
            "is_open_access": False,
            "reason": "pmcid_missing",
            "pmcid": None,
            "doi": normalized_doi,
        }

    return check_open_access


def make_pass_through_tool(
    **_: object,
) -> Callable[[JSONObject | None, str | None], JSONObject]:
    """Build a tool callable for deterministic structured-data pass-through."""

    def pass_through(
        payload: JSONObject | None = None,
        content_text: str | None = None,
    ) -> JSONObject:
        if isinstance(payload, dict):
            normalized_payload = {
                str(key): to_json_value(value) for key, value in payload.items()
            }
            serialized = json.dumps(normalized_payload, default=str)
            return {
                "decision": "enriched",
                "acquisition_method": "pass_through",
                "content_format": "structured_json",
                "content_payload": normalized_payload,
                "content_text": None,
                "content_length_chars": len(serialized),
            }
        if isinstance(content_text, str) and content_text.strip():
            normalized_text = content_text.strip()
            return {
                "decision": "enriched",
                "acquisition_method": "pass_through",
                "content_format": "text",
                "content_payload": None,
                "content_text": normalized_text,
                "content_length_chars": len(normalized_text),
            }
        return {
            "decision": "skipped",
            "acquisition_method": "skipped",
            "content_format": "text",
            "content_payload": None,
            "content_text": None,
            "content_length_chars": 0,
            "warning": "No pass-through payload available",
        }

    return pass_through


__all__ = [
    "make_check_open_access_tool",
    "make_fetch_europe_pmc_tool",
    "make_fetch_pmc_oa_tool",
    "make_pass_through_tool",
]
