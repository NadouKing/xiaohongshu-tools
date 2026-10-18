import asyncio
import json
import socket
import time
from contextlib import asynccontextmanager

import pytest

from xiaohongshu_tools import (
    AuthenticationRequired,
    VerificationRequired,
    XiaohongshuClient,
    XiaohongshuError,
    scripts,
)
from xiaohongshu_tools.browser import Browser, ProfileLock
from xiaohongshu_tools.cli import load_cache, main, save_cache
from xiaohongshu_tools.client import importable_cookies
from xiaohongshu_tools.models import normalize_comments, public_result, search_items

NOTE = "682415b0000000002001f472"


def test_search_ignores_ads_and_duplicates_and_does_not_put_token_in_url():
    raw = [
        {"id": NOTE, "modelType": "live_v2", "noteCard": {"displayTitle": "ad"}},
        {"id": "not-a-note", "noteCard": {"displayTitle": "hot search"}},
        {
            "id": NOTE,
            "modelType": "note",
            "xsecToken": "private-token",
            "noteCard": {"displayTitle": "真实笔记"},
        },
        {"id": NOTE, "modelType": "note", "noteCard": {"displayTitle": "duplicate"}},
    ]
    items = search_items(raw, 20)
    assert len(items) == 1
    assert items[0]["title"] == "真实笔记"
    assert items[0]["xsecToken"] == "private-token"
    assert "?" not in items[0]["url"]


def test_cli_redaction_recursive():
    original = {
        "data": {
            "items": [
                {
                    "xsecToken": "secret",
                    "url": "https://www.xiaohongshu.com/explore/x?xsec_token=secret",
                }
            ]
        },
        "cookies": ["secret"],
        "headers": {"Authorization": "secret"},
    }
    assert "secret" not in json.dumps(public_result(original))
    assert original["data"]["items"][0]["xsecToken"] == "secret"
    body = "https://example.com/story?chapter=1\n这是一段笔记正文。"
    assert public_result({"body": body})["body"] == body


def test_cookie_import_is_explicit_scoped_unexpired_and_read_only(tmp_path):
    path = tmp_path / "fixture.json"
    cookies = {
        "version": 2,
        "seed": 123,
        "cookies": [
            {
                "name": "allowed",
                "value": "fixture",
                "domain": ".xiaohongshu.com",
                "path": "/",
                "expires": time.time() + 3600,
                "size": 123,
                "session": False,
            },
            {"name": "wrong", "value": "fixture", "domain": "evil-xiaohongshu.com"},
            {"name": "expired", "value": "fixture", "domain": ".xiaohongshu.com", "expires": 1},
        ],
    }
    path.write_text(json.dumps(cookies), encoding="utf-8")
    before = path.read_bytes()
    result = importable_cookies(path)
    assert [item["name"] for item in result] == ["allowed"]
    assert "seed" not in result[0] and "size" not in result[0]
    assert path.read_bytes() == before


def test_cookie_errors_do_not_echo_content_or_paths(tmp_path):
    path = tmp_path / "private-name.json"
    path.write_text("private-secret", encoding="utf-8")
    with pytest.raises(XiaohongshuError) as error:
        importable_cookies(path)
    assert error.value.code == "invalid_cookies_file"
    assert "private" not in str(error.value)


def test_profile_lock_excludes_second_owner_and_releases(tmp_path):
    first, second = ProfileLock(tmp_path), ProfileLock(tmp_path)
    first.acquire()
    try:
        with pytest.raises(XiaohongshuError) as error:
            second.acquire()
        assert error.value.code == "profile_busy"
    finally:
        first.release()
    second.acquire()
    second.release()


def test_comments_are_bounded_deduplicated_and_no_empty_samples():
    data = [
        {"id": "a", "content": "one"},
        {"id": "a", "content": "duplicate"},
        {"id": "b", "content": " "},
        {"id": "c", "content": "two"},
    ]
    assert len(normalize_comments(data, 10)) == 2
    assert len(normalize_comments(data, 1)) == 1
    assert normalize_comments(data, 0) == []


def test_invalid_inputs_fail_before_browser_launch():
    async def run():
        client = XiaohongshuClient(chrome_path="missing")
        for invocation in (
            client.search("", limit=20),
            client.search("coffee", limit=51),
            client.search("coffee", sort="incorrect"),
            client.detail("../../file"),
            client.detail(NOTE, comment_limit=101),
        ):
            with pytest.raises(XiaohongshuError):
                await invocation
        assert client.browser is None
        await client.close()
        await client.close()

    asyncio.run(run())


class ProbeBrowser:
    def __init__(self, status=None, raws=None):
        self.status = status or {}
        self.raws = iter(raws or [])
        self.scrolls = 0

    async def evaluate(self, expression, session):
        if expression == scripts.PAGE_STATUS:
            return self.status
        if expression == scripts.SCROLL_COMMENTS:
            self.scrolls += 1
            return True
        if expression == scripts.COMMENT_DOM:
            return {"items": [], "ended": False}
        return next(self.raws, None)


def test_verification_never_attempts_bypass():
    async def run():
        client = XiaohongshuClient(timeout=0.05)
        client.browser = ProbeBrowser({"verificationRequired": True})
        with pytest.raises(VerificationRequired):
            await client._wait("fake-session", "expression")

    asyncio.run(run())


def test_auth_required_is_typed_on_no_page_data():
    async def run():
        client = XiaohongshuClient(timeout=0.01)
        client.browser = ProbeBrowser({"loginRequired": True})
        with pytest.raises(AuthenticationRequired):
            await client._wait("fake-session", "expression")

    asyncio.run(run())


def test_comment_limit_does_not_claim_exhaustive_when_truncating_loaded_batch():
    async def run():
        client = XiaohongshuClient()
        client.browser = ProbeBrowser()
        raw = {
            "comments": {
                "list": [{"id": str(n), "content": f"comment {n}"} for n in range(5)],
                "hasMore": False,
            }
        }
        items, has_more, _ = await client._comments("fake-session", NOTE, raw, 2)
        assert len(items) == 2 and has_more is True
        assert client.browser.scrolls == 0

    asyncio.run(run())


def test_private_cli_cache_is_bounded_in_time_and_not_public_result(tmp_path):
    path = tmp_path / "private" / "search-tokens.json"
    save_cache(path, {"data": {"items": [{"id": NOTE, "xsecToken": "fixture-secret"}]}})
    assert load_cache(path)[NOTE]["token"] == "fixture-secret"
    value = json.loads(path.read_text(encoding="utf-8"))
    value[NOTE]["savedAt"] -= 13 * 3600
    path.write_text(json.dumps(value), encoding="utf-8")
    assert not load_cache(path)


def test_cli_error_nonzero_json_no_traceback(monkeypatch, capsys):
    async def fail(args):
        raise XiaohongshuError("fixture_failure", "safe error")

    monkeypatch.setattr("xiaohongshu_tools.cli.run", fail)
    assert main(["session"]) == 1
    captured = capsys.readouterr()
    result = json.loads(captured.out)
    assert result["error"]["code"] == "fixture_failure"
    assert captured.err == ""


def test_cli_invalid_arguments_are_safe_json(capsys):
    assert main(["detail", "--unknown-private-token=secret"]) == 1
    captured = capsys.readouterr()
    assert json.loads(captured.out)["error"]["code"] == "invalid_arguments"
    assert "secret" not in captured.out and captured.err == ""


def test_existing_live_debug_port_is_preserved_without_process_start(tmp_path):
    async def run():
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            listener.listen(1)
            path = tmp_path / "DevToolsActivePort"
            expected = f"{listener.getsockname()[1]}\n/devtools/browser/fixture\n"
            path.write_text(expected)
            browser = Browser(tmp_path, "must-not-be-started", True, 0.1)
            with pytest.raises(XiaohongshuError) as error:
                await browser.start()
            assert error.value.code == "profile_busy"
            assert path.read_text() == expected
            assert browser.process is None
            assert browser.lock.handle is None

    asyncio.run(run())


def test_cleanup_reaps_owned_process_even_when_websocket_close_fails(tmp_path):
    class FailingWebSocket:
        async def close(self):
            raise OSError("synthetic close failure")

    class OwnedProcess:
        reaped = False

        def wait(self, timeout):
            self.reaped = True

    async def run():
        browser = Browser(tmp_path, "unused", True, 0.1)
        browser.lock.acquire()
        process = OwnedProcess()
        browser.process = process
        browser.ws = FailingWebSocket()

        async def fail(*args):
            raise OSError("synthetic transport failure")

        browser.send = fail
        await browser.close()
        assert process.reaped
        assert browser.lock.handle is None and browser.process is None

    asyncio.run(run())


def test_session_unknown_does_not_report_logout(monkeypatch):
    @asynccontextmanager
    async def page(url):
        yield "fake-session"

    async def run():
        client = XiaohongshuClient(timeout=0.01)
        client.browser = ProbeBrowser({"ready": True})
        monkeypatch.setattr(client, "_page", page)
        with pytest.raises(XiaohongshuError) as error:
            await client.check_session()
        assert error.value.code == "session_unknown"

    asyncio.run(run())


def test_initial_empty_state_without_explicit_empty_ui_is_not_a_result():
    async def run():
        client = XiaohongshuClient(timeout=0.01)
        client.browser = ProbeBrowser({"ready": True}, raws=[[]])
        with pytest.raises(XiaohongshuError) as error:
            await client._wait("fake-session", "search-expression", allow_empty=True)
        assert error.value.code == "page_data_unavailable"
        client.browser = ProbeBrowser({"searchEmpty": True, "searchLoading": False}, raws=[[]])
        assert await client._wait("fake-session", "search-expression", allow_empty=True) == []

    asyncio.run(run())
