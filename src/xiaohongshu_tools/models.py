import re
from datetime import UTC, datetime
from urllib.parse import urlsplit

from .errors import XiaohongshuError

NOTE_ID = re.compile(r"^[0-9a-fA-F]{24}$")


def note_id(value: str) -> str:
    if NOTE_ID.fullmatch(value):
        return value.lower()
    raise XiaohongshuError("invalid_note_id", "笔记 ID 必须是 24 位十六进制字符。")


def canonical_url(ident: str) -> str:
    return f"https://www.xiaohongshu.com/explore/{note_id(ident)}"


def iso_time(value):
    if value is None or value == "":
        return None
    try:
        timestamp = float(value)
        if timestamp > 100_000_000_000:
            timestamp /= 1000
        return datetime.fromtimestamp(timestamp, UTC).isoformat()
    except TypeError, ValueError, OverflowError, OSError:
        return None


def search_items(raw: list, limit: int) -> list[dict]:
    result, seen = [], set()
    for item in raw:
        card = item.get("noteCard") or item.get("note_card")
        ident = item.get("id", "")
        if not card or item.get("modelType", "note") != "note":
            continue
        if not NOTE_ID.fullmatch(ident) or ident in seen:
            continue
        seen.add(ident)
        result.append(
            {
                "id": ident,
                "title": card.get("displayTitle") or card.get("title") or "",
                "url": canonical_url(ident),
                "type": card.get("type"),
                "author": (card.get("user") or {}).get("nickname")
                or (card.get("user") or {}).get("nickName"),
                "xsecToken": item.get("xsecToken") or item.get("xsec_token"),
            }
        )
        if len(result) >= limit:
            break
    return result


def normalize_comments(comments: list, limit: int) -> list[dict]:
    result, seen = [], set()
    for item in comments:
        content = item.get("content") or ""
        if not content.strip():
            continue
        ident = str(item.get("id") or "")
        key = ident or content.strip()
        if key in seen:
            continue
        seen.add(key)
        result.append(
            {
                "id": ident or None,
                "content": content.strip(),
                "author": (item.get("userInfo") or {}).get("nickname"),
                "publishedAt": iso_time(item.get("createTime")),
                "publishedLabel": item.get("publishedLabel"),
                "likeCount": item.get("likeCount"),
            }
        )
        if len(result) >= limit:
            break
    return result if limit else []


def public_result(value, *, field=None):
    """Recursively remove private values before any CLI serialization."""
    if isinstance(value, dict):
        return {
            key: public_result(item, field=key)
            for key, item in value.items()
            if key.lower().replace("_", "")
            not in {"xsectoken", "cookie", "cookies", "authorization", "headers", "seed"}
        }
    if isinstance(value, list):
        return [public_result(item, field=field) for item in value]
    if (
        isinstance(value, str)
        and value.startswith(("http://", "https://"))
        and field
        and field.lower().endswith("url")
    ):
        parsed = urlsplit(value)
        # Our public URLs are canonical note URLs. Do not serialize signed query strings.
        return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
    return value
