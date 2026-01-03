from __future__ import annotations

import base64
import datetime as dt
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests


def _get_json(url: str, headers: Dict[str, str], params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    resp = requests.get(url, headers=headers, params=params, timeout=20)
    resp.raise_for_status()
    return resp.json()


def _extract_headers(payload: Dict[str, Any]) -> Dict[str, str]:
    headers = payload.get("headers") or []
    out: Dict[str, str] = {}
    for item in headers:
        name = item.get("name")
        value = item.get("value")
        if name and value:
            out[name] = value
    return out


def _walk_parts(parts: List[Dict[str, Any]], mime_type: str) -> Optional[str]:
    for part in parts:
        if part.get("mimeType") == mime_type and part.get("body", {}).get("data"):
            data = part["body"]["data"]
            return base64.urlsafe_b64decode(data.encode("utf-8")).decode("utf-8", errors="replace")
        child_parts = part.get("parts") or []
        if child_parts:
            found = _walk_parts(child_parts, mime_type)
            if found:
                return found
    return None


def _extract_body(payload: Dict[str, Any]) -> Optional[str]:
    body = payload.get("body", {}).get("data")
    if body:
        return base64.urlsafe_b64decode(body.encode("utf-8")).decode("utf-8", errors="replace")
    parts = payload.get("parts") or []
    text = _walk_parts(parts, "text/plain")
    if text:
        return text
    return _walk_parts(parts, "text/html")


def _refresh_access_token(
    *, client_id: str, client_secret: str, refresh_token: str
) -> Optional[str]:
    token_resp = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        },
        timeout=20,
    )
    token_resp.raise_for_status()
    payload = token_resp.json()
    return payload.get("access_token")


def _load_refresh_token() -> str:
    path = os.getenv("GMAIL_TOKEN_STORE_PATH", ".gmail_tokens.json")
    try:
        data = json.loads(Path(path).read_text())
    except Exception:
        return ""
    token = data.get("refresh_token")
    return token if isinstance(token, str) else ""


def read_today_emails(
    *,
    access_token: Optional[str] = None,
    client_id: Optional[str] = None,
    client_secret: Optional[str] = None,
    refresh_token: Optional[str] = None,
    user_id: str = "me",
    max_results: int = 10,
    query: Optional[str] = None,
    include_body: bool = False,
) -> Dict[str, Any]:
    """Read today's emails using the Gmail API."""
    token = access_token or os.getenv("GMAIL_ACCESS_TOKEN", "")
    if not token:
        client_id = client_id or os.getenv("GMAIL_CLIENT_ID", "")
        client_secret = client_secret or os.getenv("GMAIL_CLIENT_SECRET", "")
        refresh_token = refresh_token or os.getenv("GMAIL_REFRESH_TOKEN", "")
        if not refresh_token:
            refresh_token = _load_refresh_token()
        if not client_id or not client_secret or not refresh_token:
            return {
                "status": "error",
                "error": "access_token or (client_id, client_secret, refresh_token) is required.",
            }
        try:
            token = _refresh_access_token(
                client_id=client_id,
                client_secret=client_secret,
                refresh_token=refresh_token,
            )
        except Exception as exc:
            return {"status": "error", "error": f"token refresh failed: {exc}"}
        if not token:
            return {"status": "error", "error": "token refresh failed: no access_token returned."}

    today = dt.datetime.now().date()
    default_query = f"after:{today.strftime('%Y/%m/%d')}"
    q = query or default_query
    headers = {"Authorization": f"Bearer {token}"}

    list_resp = _get_json(
        f"https://gmail.googleapis.com/gmail/v1/users/{user_id}/messages",
        headers,
        params={"maxResults": max_results, "q": q},
    )
    message_refs = list_resp.get("messages") or []
    if not message_refs:
        return {"status": "success", "messages": [], "query": q}

    messages = []
    for ref in message_refs:
        msg_id = ref.get("id")
        if not msg_id:
            continue
        fmt = "full" if include_body else "metadata"
        msg = _get_json(
            f"https://gmail.googleapis.com/gmail/v1/users/{user_id}/messages/{msg_id}",
            headers,
            params={"format": fmt, "metadataHeaders": ["From", "To", "Subject", "Date"]},
        )
        payload = msg.get("payload") or {}
        headers_map = _extract_headers(payload)
        item = {
            "id": msg.get("id"),
            "thread_id": msg.get("threadId"),
            "snippet": msg.get("snippet"),
            "internal_date": msg.get("internalDate"),
            "from": headers_map.get("From"),
            "to": headers_map.get("To"),
            "subject": headers_map.get("Subject"),
            "date": headers_map.get("Date"),
        }
        if include_body:
            item["body"] = _extract_body(payload)
        messages.append(item)

    return {"status": "success", "messages": messages, "query": q}
