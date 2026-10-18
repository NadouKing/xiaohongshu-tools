import asyncio
import json
from contextlib import asynccontextmanager
from urllib.parse import parse_qs, urlsplit

import pytest

from xiaohongshu_tools import (
    AuthenticationRequired,
    VerificationRequired,
    XiaohongshuClient,
    XiaohongshuError,
    scripts,
)
from xiaohongshu_tools.browser import Browser, find_chrome


@pytest.mark.parametrize("keyword", ["广州 文冲 幸福里", "C++ & coffee", "a/b #周末"])
def test_search_url_preserves_keyword_without_form_style_spaces(keyword):
    """Literal +/&/# must remain keyword data rather than extra query/fragment fields."""

    async def run():
        client = XiaohongshuClient()
        client._session_bootstrapped = True
        captured = []

        @asynccontextmanager
        async def page(url):
            captured.append(url)
            yield "fixture"

        async def wait(*args, **kwargs):
            return []

        client._page = page
        client._wait = wait
        result = await client.search(keyword, limit=5)
        url = urlsplit(captured[0])
        assert url.hostname == "www.xiaohongshu.com" and url.path == "/search_result"
        assert url.fragment == "" and "+" not in url.query and "%20" in url.query
        assert parse_qs(url.query) == {"keyword": [keyword], "source": ["web_explore_feed"]}
        assert result["data"]["count"] == 0

    asyncio.run(run())


def test_cold_search_probes_homepage_before_deep_link_and_only_once():
    async def run():
        client = XiaohongshuClient()
        events = []

        async def probe():
            events.append("homepage")
            return {"data": {"state": "ready"}}

        @asynccontextmanager
        async def page(url):
            events.append("search")
            yield "fixture"

        async def wait(*args, **kwargs):
            return []

        client.check_session = probe
        client._page = page
        client._wait = wait
        await asyncio.gather(client._ensure_session(), client._ensure_session())
        await client.search("first")
        await client.search("second")
        assert events == ["homepage", "search", "search"]
        await client.close()
        await client.search("after close")
        assert events[-2:] == ["homepage", "search"]

    asyncio.run(run())


@pytest.mark.parametrize("state", ["login_required", "verification_required"])
def test_bootstrap_gate_is_not_cached_or_followed_by_search(state):
    async def run():
        client = XiaohongshuClient()

        async def probe():
            return {"data": {"state": state}}

        client.check_session = probe
        expected = AuthenticationRequired if state == "login_required" else VerificationRequired
        with pytest.raises(expected):
            await client.search("test")
        assert client._session_bootstrapped is False and client.browser is None

    asyncio.run(run())


def notes(start, stop):
    return [
        {
            "id": f"{n:024x}",
            "modelType": "note",
            "xsecToken": "fixture-private",
            "noteCard": {"displayTitle": f"note {n}"},
        }
        for n in range(start, stop)
    ]


class SearchPage:
    def __init__(self, batch=None, *, ended=False, blocked=False):
        self.batch = batch if batch is not None else notes(0, 20)
        self.ended = ended
        self.blocked = blocked
        self.scrolls = 0

    async def evaluate(self, expression, session):
        if expression == scripts.SEARCH_END:
            return self.ended
        if expression == scripts.SCROLL_SEARCH:
            self.scrolls += 1
            return True
        if expression == scripts.PAGE_STATUS:
            return {"verificationRequired": self.blocked}
        if expression == scripts.SEARCH_DATA:
            return self.batch
        raise AssertionError("Unexpected probe")


def test_default_first_batch_does_not_scroll():
    async def run():
        client = XiaohongshuClient()
        client.browser = SearchPage()
        items, meta = await client._search_pages("fixture", notes(0, 20), 20)
        assert len(items) == 20 and client.browser.scrolls == 0
        assert meta["hasMore"] is None

    asyncio.run(run())


def test_pagination_merges_overlapping_batches_and_reports_clipped_results():
    async def run():
        client = XiaohongshuClient()
        client.browser = SearchPage(notes(15, 40))
        items, meta = await client._search_pages("fixture", notes(0, 20), 30)
        assert len(items) == len({item["id"] for item in items}) == 30
        assert meta["loadedCount"] == 40 and meta["scrolls"] == 1
        assert meta["hasMore"] is True and meta["stopReason"] == "requested_limit"

    asyncio.run(run())


def test_explicit_end_and_confirmed_empty_do_not_scroll():
    async def run():
        client = XiaohongshuClient()
        client.browser = SearchPage(ended=True)
        items, meta = await client._search_pages("fixture", notes(0, 5), 30)
        assert len(items) == 5 and meta["hasMore"] is False
        empty, meta = await client._search_pages("fixture", [], 30)
        assert not empty and meta["hasMore"] is False
        assert client.browser.scrolls == 0

    asyncio.run(run())


def test_deadline_returns_partial_and_keeps_exhaustion_unknown():
    async def run():
        client = XiaohongshuClient(timeout=0.01)
        client.browser = SearchPage(notes(0, 20))
        items, meta = await client._search_pages("fixture", notes(0, 20), 30)
        assert len(items) == 20 and meta["hasMore"] is None
        assert meta["stopReason"] == "deadline" and meta["scrolls"] == 1

    asyncio.run(run())


@pytest.mark.parametrize("slow_probe", [scripts.SEARCH_END, scripts.SCROLL_SEARCH])
def test_deadline_cancels_inflight_probe_and_preserves_loaded_notes(slow_probe):
    class SlowPage(SearchPage):
        cancelled = False

        async def evaluate(self, expression, session):
            if expression == slow_probe:
                try:
                    await asyncio.sleep(1)
                except asyncio.CancelledError:
                    self.cancelled = True
                    raise
            return await super().evaluate(expression, session)

    async def run():
        client = XiaohongshuClient(timeout=0.02)
        client.browser = SlowPage()
        items, meta = await client._search_pages("fixture", notes(0, 20), 30)
        assert client.browser.cancelled is True
        assert len(items) == 20
        assert meta["stopReason"] == "deadline" and meta["hasMore"] is None

    asyncio.run(run())


def test_gate_during_pagination_is_not_reported_as_empty_or_exhausted():
    async def run():
        client = XiaohongshuClient()
        client.browser = SearchPage(blocked=True)
        with pytest.raises(VerificationRequired):
            await client._search_pages("fixture", notes(0, 20), 30)

    asyncio.run(run())


def test_reported_gate_paths_in_real_chrome_fixture(tmp_path):
    """Real Chrome runs the probe with a synthetic URL, without accessing accounts."""
    try:
        executable = find_chrome()
    except XiaohongshuError:
        pytest.skip("Chrome not installed; live fixture is not counted as passed")

    async def run():
        browser = Browser(tmp_path / "synthetic-profile", executable, True, 10)
        await browser.start()
        try:
            _, session = await browser.new_page()
            for host, path, verify, login in [
                ("www.xiaohongshu.com", "/website-login/captcha", True, False),
                ("www.xiaohongshu.com", "/website-login/", False, True),
                ("www.xiaohongshu.com", "/search_result", False, False),
                ("www.xiaohongshu.com", "/explore/website-login", False, False),
                ("unrelated.invalid", "/website-login/captcha", False, False),
            ]:
                location = json.dumps({"hostname": host, "pathname": path})
                expression = f"(function(location) {{ return {scripts.PAGE_STATUS}; }})({location})"
                status = await browser.evaluate(expression, session)
                assert status["verificationRequired"] is verify
                assert status["loginRequired"] is login
        finally:
            await browser.close()

    asyncio.run(run())
