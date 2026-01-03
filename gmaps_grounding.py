from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import requests


def _get_json(url: str, params: Dict[str, Any]) -> Dict[str, Any]:
    resp = requests.get(url, params=params, timeout=20)
    resp.raise_for_status()
    return resp.json()


def ground_location(
    *,
    query: str,
    api_key: Optional[str] = None,
    include_details: bool = True,
    details_fields: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Resolve a location query using Google Maps/Places APIs."""
    key = api_key or os.getenv("GMAPS_API_KEY", "")
    if not key:
        return {"status": "error", "error": "GMAPS_API_KEY not set and no api_key provided."}

    search = _get_json(
        "https://maps.googleapis.com/maps/api/place/textsearch/json",
        {"query": query, "key": key},
    )
    if search.get("status") != "OK" or not search.get("results"):
        return {
            "status": "error",
            "error": "No results found for query.",
            "api_status": search.get("status"),
            "api_error": search.get("error_message"),
        }

    top = search["results"][0]
    place_id = top.get("place_id")
    summary = {
        "name": top.get("name"),
        "formatted_address": top.get("formatted_address"),
        "place_id": place_id,
        "types": top.get("types") or [],
        "location": (top.get("geometry") or {}).get("location") or {},
        "viewport": (top.get("geometry") or {}).get("viewport") or {},
        "rating": top.get("rating"),
        "user_ratings_total": top.get("user_ratings_total"),
    }

    details = None
    if include_details and place_id:
        fields = details_fields or [
            "name",
            "formatted_address",
            "geometry",
            "international_phone_number",
            "website",
            "opening_hours",
            "rating",
            "user_ratings_total",
            "types",
            "business_status",
        ]
        details_resp = _get_json(
            "https://maps.googleapis.com/maps/api/place/details/json",
            {"place_id": place_id, "fields": ",".join(fields), "key": key},
        )
        if details_resp.get("status") == "OK":
            details = details_resp.get("result")
        else:
            details = {
                "error": "Place details lookup failed.",
                "api_status": details_resp.get("status"),
                "api_error": details_resp.get("error_message"),
            }

    return {"status": "success", "summary": summary, "details": details}
