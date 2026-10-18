import asyncio
import json

import pytest

from xiaohongshu_tools import VerificationRequired, XiaohongshuClient, XiaohongshuError, scripts
from xiaohongshu_tools.browser import Browser, find_chrome


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
