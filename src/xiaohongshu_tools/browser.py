"""Small sequential CDP transport. No Playwright, Selenium, Node or Go dependency."""

import asyncio
import json
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

import websockets

from .errors import XiaohongshuError


def default_profile() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local"))
    else:
        base = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state"))
    return base / "xiaohongshu-tools" / "browser-profile"


def find_chrome(explicit: str | Path | None = None) -> str:
    candidates = [explicit, os.environ.get("XHS_CHROME_PATH")]
    if sys.platform == "win32":
        for name in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
            if os.environ.get(name):
                candidates.append(Path(os.environ[name]) / "Google/Chrome/Application/chrome.exe")
    elif sys.platform == "darwin":
        candidates.append("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
    candidates.extend(shutil.which(n) for n in ("google-chrome", "chromium", "chromium-browser"))
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return str(candidate)
    raise XiaohongshuError("chrome_not_found", "没有找到 Chrome；请设置 --chrome-path。")


class ProfileLock:
    """OS lock releases even if Python crashes; do not delete another Chrome's locks."""

    def __init__(self, profile: Path):
        self.path = profile / "xiaohongshu-tools.owner"
        self.handle = None

    def acquire(self):
        self.handle = self.path.open("a+b")
        self.handle.seek(0)
        if self.path.stat().st_size == 0:
            self.handle.write(b"0")
            self.handle.flush()
        self.handle.seek(0)
        try:
            if sys.platform == "win32":
                import msvcrt

                msvcrt.locking(self.handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.handle.close()
            self.handle = None
            raise XiaohongshuError("profile_busy", "小红书专用浏览器目录正在使用中。") from None

    def release(self):
        if self.handle:
            self.handle.close()
            self.handle = None


class Browser:
    def __init__(self, profile: Path, executable: str, headless: bool, timeout: float):
        self.profile = profile
        self.executable = executable
        self.headless = headless
        self.timeout = timeout
        self.process = None
        self.ws = None
        self.lock = ProfileLock(profile)
        self._sequence = 0
        self._send_lock = asyncio.Lock()

    async def start(self):
        self.profile.mkdir(parents=True, exist_ok=True)
        self.lock.acquire()
        active = self.profile / "DevToolsActivePort"
        arguments = [
            self.executable,
            "--remote-debugging-port=0",
            "--remote-debugging-address=127.0.0.1",
            f"--user-data-dir={self.profile}",
            "--no-first-run",
            "--no-default-browser-check",
            "--lang=zh-CN",
            "--window-size=1440,960",
            *(["--headless=new"] if self.headless else []),
            "about:blank",
        ]
        try:
            # A manually launched Chrome does not hold our own lock. Preserve it.
            if active.is_file():
                try:
                    old_port = active.read_text().splitlines()[0]
                    if old_port.isdigit() and 0 < int(old_port) < 65536:
                        try:
                            connection = await asyncio.to_thread(
                                socket.create_connection, ("127.0.0.1", int(old_port)), 0.3
                            )
                        except OSError:
                            pass
                        else:
                            connection.close()
                            raise XiaohongshuError(
                                "profile_busy", "该专用目录已有 Chrome 运行，请先关闭它。"
                            )
                except IndexError, ValueError, OSError:
                    pass
                active.unlink(missing_ok=True)
            self.process = subprocess.Popen(
                arguments,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=(subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0),
            )
            deadline = time.monotonic() + self.timeout
            while time.monotonic() < deadline:
                if self.process.poll() is not None:
                    raise XiaohongshuError(
                        "browser_start_failed", "Chrome 启动失败；请检查路径和专用目录是否被占用。"
                    )
                try:
                    port, endpoint = active.read_text().strip().splitlines()[:2]
                    if port.isdigit() and endpoint.startswith("/devtools/browser/"):
                        self.ws = await websockets.connect(
                            f"ws://127.0.0.1:{port}{endpoint}",
                            open_timeout=self.timeout,
                            max_size=16 * 1024 * 1024,
                            proxy=None,
                        )
                        return
                except OSError, ValueError:
                    pass
                await asyncio.sleep(0.1)
            raise XiaohongshuError("browser_timeout", "等待 Chrome CDP 端口超时。")
        except BaseException as error:
            await self.close()
            if not isinstance(error, Exception) or isinstance(error, XiaohongshuError):
                raise
            raise XiaohongshuError("browser_start_failed", "无法连接专用 Chrome。") from None

    async def send(self, method: str, params: dict | None = None, session: str | None = None):
        async with self._send_lock:
            if not self.ws:
                raise XiaohongshuError("browser_closed", "浏览器尚未连接或已关闭。")
            self._sequence += 1
            ident = self._sequence
            message = {"id": ident, "method": method, "params": params or {}}
            if session:
                message["sessionId"] = session
            try:
                async with asyncio.timeout(self.timeout):
                    await self.ws.send(json.dumps(message))
                    while True:
                        response = json.loads(await self.ws.recv())
                        if response.get("id") != ident:
                            continue
                        if "error" in response:
                            raise XiaohongshuError("cdp_error", f"浏览器操作 {method} 失败。")
                        return response.get("result", {})
            except TimeoutError:
                raise XiaohongshuError("cdp_timeout", f"浏览器操作 {method} 超时。") from None
            except websockets.exceptions.ConnectionClosed:
                raise XiaohongshuError("browser_closed", "浏览器连接已关闭。") from None

    async def evaluate(self, expression: str, session: str):
        response = await self.send(
            "Runtime.evaluate",
            {"expression": expression, "returnByValue": True, "awaitPromise": True},
            session,
        )
        if response.get("exceptionDetails"):
            raise XiaohongshuError("page_evaluation_failed", "页面脚本执行失败。")
        return response.get("result", {}).get("value")

    async def new_page(self):
        target = (await self.send("Target.createTarget", {"url": "about:blank"}))["targetId"]
        session = (await self.send("Target.attachToTarget", {"targetId": target, "flatten": True}))[
            "sessionId"
        ]
        await self.send("Page.enable", session=session)
        return target, session

    async def close(self):
        try:
            if self.ws:
                try:
                    await self.send("Browser.close")
                except Exception:
                    pass
                finally:
                    try:
                        await self.ws.close()
                    except Exception:
                        pass
                    self.ws = None
            if self.process:
                try:
                    await asyncio.to_thread(self.process.wait, timeout=4)
                except Exception:
                    try:
                        self.process.terminate()
                        await asyncio.to_thread(self.process.wait, timeout=4)
                    except Exception:
                        try:
                            self.process.kill()
                            await asyncio.to_thread(self.process.wait, timeout=4)
                        except Exception:
                            pass
                finally:
                    self.process = None
        finally:
            self.lock.release()
