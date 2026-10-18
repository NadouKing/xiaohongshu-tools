import asyncio
import json
import os
import time
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlencode

from . import scripts
from .browser import Browser, default_profile, find_chrome
from .errors import AuthenticationRequired, VerificationRequired, XiaohongshuError
from .models import canonical_url, iso_time, normalize_comments, note_id, search_items


def importable_cookies(path: Path) -> list[dict]:
    """Read only an explicitly supplied file; never modify or display it."""
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
        cookies = value.get("cookies") if isinstance(value, dict) else value
        if not isinstance(cookies, list):
            raise ValueError
        result = []
        for cookie in cookies:
            domain = str(cookie.get("domain", ""))
            if domain.lstrip(".") not in {"xiaohongshu.com", "www.xiaohongshu.com"}:
                continue
            filtered = {
                key: cookie[key]
                for key in ("name", "value", "domain", "path", "httpOnly", "secure")
                if key in cookie
            }
            if not filtered.get("name") or not isinstance(filtered.get("value"), str):
                continue
            expiry = cookie.get("expires")
            if isinstance(expiry, (float, int)) and expiry > 0:
                if expiry <= time.time():
                    continue
                filtered["expires"] = expiry
            if cookie.get("sameSite") in {"Strict", "Lax", "None"}:
                filtered["sameSite"] = cookie["sameSite"]
            result.append(filtered)
        if not result:
            raise ValueError
        return result
    except OSError, ValueError, TypeError, AttributeError:
        raise XiaohongshuError(
            "invalid_cookies_file", "无法读取有效的小红书 Cookie 文件。"
        ) from None


class XiaohongshuClient:
    """Read-only, serialized native CDP client. Use one dedicated profile per process."""

    def __init__(
        self,
        *,
        profile_dir=None,
        chrome_path=None,
        headless=True,
        timeout=30.0,
        cookies_file=None,
    ):
        self.profile_dir = Path(
            profile_dir or os.environ.get("XHS_PROFILE_DIR") or default_profile()
        )
        self.chrome_path = chrome_path
        self.headless = headless
        self.timeout = float(timeout)
        if self.timeout <= 0:
            raise XiaohongshuError("invalid_argument", "timeout 必须大于 0。")
        self.cookies_file = Path(cookies_file) if cookies_file else None
        self.browser = None
        self._operation_lock = asyncio.Lock()
        self._tokens = {}

    async def __aenter__(self):
        await self._start()
        return self

    async def __aexit__(self, *_):
        await self.close()

    async def _start(self):
        if self.browser:
            return
        executable = find_chrome(self.chrome_path)
        browser = Browser(self.profile_dir.resolve(), executable, self.headless, self.timeout)
        await browser.start()
        try:
            if self.cookies_file:
                await browser.send(
                    "Storage.setCookies", {"cookies": importable_cookies(self.cookies_file)}
                )
        except BaseException:
            await browser.close()
            raise
        self.browser = browser

    @asynccontextmanager
    async def _page(self, url: str):
        await self._start()
        target, session = await self.browser.new_page()
        try:
            navigation = await self.browser.send("Page.navigate", {"url": url}, session)
            if navigation.get("errorText"):
                raise XiaohongshuError("navigation_failed", "无法打开小红书页面。")
            yield session
        finally:
            try:
                await self.browser.send("Target.closeTarget", {"targetId": target})
            except XiaohongshuError:
                pass

    def _envelope(self, data, started, method="cdp.page_state"):
        return {
            "schemaVersion": 1,
            "status": "ok",
            "source": "xiaohongshu",
            "fetchedAt": datetime.now(UTC).isoformat(),
            "method": method,
            "elapsedMs": round((time.monotonic() - started) * 1000),
            "data": data,
        }

    async def _wait(self, session, expression, *, allow_empty=False):
        deadline = time.monotonic() + self.timeout
        began = time.monotonic()
        status = {}
        while time.monotonic() < deadline:
            status = await self.browser.evaluate(scripts.PAGE_STATUS, session) or {}
            if status.get("verificationRequired"):
                raise VerificationRequired()
            if status.get("inaccessible"):
                raise XiaohongshuError("note_unavailable", "笔记已删除、私密或当前不可访问。")
            value = await self.browser.evaluate(expression, session)
            if status.get("loginRequired") and time.monotonic() - began > 2:
                raise AuthenticationRequired()
            if not status.get("loginRequired"):
                if value:
                    return value
                if (
                    allow_empty
                    and value == []
                    and status.get("searchEmpty")
                    and not status.get("searchLoading")
                ):
                    return value
            await asyncio.sleep(0.25)
        if status.get("loginRequired"):
            raise AuthenticationRequired()
        raise XiaohongshuError(
            "page_data_unavailable", "页面未返回预期数据，可能需要登录或适配页面。"
        )

    async def check_session(self):
        started = time.monotonic()
        async with self._operation_lock, self._page("https://www.xiaohongshu.com/explore") as s:
            deadline = time.monotonic() + min(self.timeout, 12)
            status = {}
            while time.monotonic() < deadline:
                status = await self.browser.evaluate(scripts.PAGE_STATUS, s) or {}
                if status.get("verificationRequired"):
                    return self._envelope(
                        {"state": "verification_required", "authenticated": False},
                        started,
                        "cdp.session_probe",
                    )
                if status.get("loggedIn") or status.get("loginRequired"):
                    break
                await asyncio.sleep(0.3)
            if not (status.get("loggedIn") or status.get("loginRequired")):
                raise XiaohongshuError(
                    "session_unknown", "页面未提供可确认的登录状态，请检查网络或页面适配。"
                )
            return self._envelope(
                {
                    "state": "ready" if status.get("loggedIn") else "login_required",
                    "authenticated": bool(status.get("loggedIn")),
                },
                started,
                "cdp.session_probe",
            )

    async def login(self, *, wait_seconds=180):
        if self.headless:
            raise XiaohongshuError("visible_browser_required", "登录需要 headless=False。")
        started = time.monotonic()
        async with self._operation_lock, self._page("https://www.xiaohongshu.com/explore") as s:
            deadline = time.monotonic() + wait_seconds
            while time.monotonic() < deadline:
                status = await self.browser.evaluate(scripts.PAGE_STATUS, s) or {}
                if status.get("loggedIn"):
                    return self._envelope({"loggedIn": True}, started, "cdp.interactive_login")
                await asyncio.sleep(1)
            raise XiaohongshuError("login_timeout", "登录等待超时；可重新运行 xhs login。")

    async def search(self, keyword: str, *, limit: int = 20, sort="综合", **platform_options):
        if not isinstance(keyword, str) or not keyword.strip() or len(keyword) > 100:
            raise XiaohongshuError("invalid_argument", "keyword 需要 1 到 100 个字符。")
        if type(limit) is not int or not 1 <= limit <= 20:
            raise XiaohongshuError("invalid_argument", "搜索 limit 范围为 1 到 20。")
        if platform_options:
            raise XiaohongshuError("unsupported_option", "当前版本不支持这些搜索选项。")
        if sort not in {"综合", "最新", "最多点赞", "最多评论", "最多收藏"}:
            raise XiaohongshuError("invalid_argument", "不支持该排序方式。")
        started = time.monotonic()
        query = urlencode({"keyword": keyword.strip(), "source": "web_explore_feed"})
        async with (
            self._operation_lock,
            self._page(f"https://www.xiaohongshu.com/search_result?{query}") as s,
        ):
            raw = await self._wait(s, scripts.SEARCH_DATA, allow_empty=True)
            if sort != "综合":
                await self._sort(s, sort)
                raw = await self._wait(s, scripts.SEARCH_DATA, allow_empty=True)
            items = search_items(raw, limit)
            self._tokens.update(
                {item["id"]: item["xsecToken"] for item in items if item["xsecToken"]}
            )
            return self._envelope(
                {"items": items, "count": len(items), "hasMore": None, "sort": sort}, started
            )

    async def _sort(self, session, sort):
        before = await self.browser.evaluate(scripts.SEARCH_DATA, session)
        coords = await self.browser.evaluate(scripts.FILTER_COORDINATES, session)
        if not coords:
            raise XiaohongshuError("sort_unavailable", "网页排序控件不可用。")
        await self.browser.send(
            "Input.dispatchMouseEvent", {"type": "mouseMoved", **coords}, session
        )
        await asyncio.sleep(0.4)
        if not await self.browser.evaluate(scripts.select_sort(sort), session):
            raise XiaohongshuError("sort_unavailable", "无法应用排序，未返回伪装成已排序的结果。")
        deadline = time.monotonic() + min(self.timeout, 12)
        while time.monotonic() < deadline:
            current = await self.browser.evaluate(scripts.SEARCH_DATA, session)
            if current and current != before:
                return
            await asyncio.sleep(0.3)
        raise XiaohongshuError("sort_refresh_timeout", "排序后数据刷新超时；请重新搜索。")

    async def detail(self, item_id: str, *, xsec_token=None, comment_limit=20, **platform_options):
        ident = note_id(item_id)
        if type(comment_limit) is not int or not 0 <= comment_limit <= 100:
            raise XiaohongshuError("invalid_argument", "comment_limit 范围为 0 到 100。")
        if platform_options:
            raise XiaohongshuError("unsupported_option", "当前版本不支持这些详情选项。")
        token = xsec_token or self._tokens.get(ident)
        if token is not None and (not isinstance(token, str) or len(token) > 2048):
            raise XiaohongshuError("invalid_argument", "无效的笔记访问参数。")
        query = urlencode({"xsec_token": token, "xsec_source": "pc_feed"}) if token else ""
        started = time.monotonic()
        async with (
            self._operation_lock,
            self._page(canonical_url(ident) + ("?" + query if query else "")) as s,
        ):
            raw = await self._wait(s, scripts.note_data(ident))
            comments, has_more, origin = await self._comments(s, ident, raw, comment_limit)
            note = raw["note"]
            return self._envelope(
                {
                    "id": ident,
                    "title": note.get("title") or "",
                    "body": note.get("desc") or "",
                    "url": canonical_url(ident),
                    "publishedAt": iso_time(note.get("time")),
                    "type": note.get("type"),
                    "author": (note.get("user") or {}).get("nickname"),
                    "comments": comments,
                    "commentSampleCount": len(comments),
                    "commentsHasMore": has_more,
                    "commentScope": "not_requested"
                    if not comment_limit
                    else "bounded_top_level_sample",
                    "commentMethod": origin,
                    "commentLimit": comment_limit,
                    "commentCountReported": (note.get("interactInfo") or {}).get("commentCount"),
                },
                started,
                "cdp.page_state+bounded_comment_scroll",
            )

    async def _comments(self, session, ident, raw, limit):
        if not limit:
            return [], None, "not_requested"
        deadline = time.monotonic() + min(self.timeout, 12)
        collected, seen, previous, stagnant = [], set(), -1, 0
        has_more = None
        method = "page_state"
        while time.monotonic() < deadline:
            state = raw.get("comments") or {}
            current = state.get("list") or []
            dom = await self.browser.evaluate(scripts.COMMENT_DOM, session) or {}
            for item in current or dom.get("items", []):
                key = str(item.get("id") or item.get("content") or "")
                if key and key not in seen:
                    collected.append(item)
                    seen.add(key)
            if not current and dom.get("items"):
                method = "dom"
            if "hasMore" in state:
                has_more = bool(state["hasMore"])
            if dom.get("ended"):
                has_more = False
            sample = normalize_comments(collected, limit)
            if len(sample) >= limit or has_more is False:
                # We may have truncated a loaded batch even when the page reached its end.
                if len(normalize_comments(collected, 101)) > limit:
                    has_more = True
                return sample, has_more, method
            stagnant = stagnant + 1 if len(sample) == previous else 0
            if stagnant >= 4:
                break
            previous = len(sample)
            await self.browser.evaluate(scripts.SCROLL_COMMENTS, session)
            await asyncio.sleep(0.65)
            raw = await self.browser.evaluate(scripts.note_data(ident), session) or raw
        return normalize_comments(collected, limit), has_more, method

    async def close(self):
        if self.browser:
            await self.browser.close()
            self.browser = None
        self._tokens.clear()
