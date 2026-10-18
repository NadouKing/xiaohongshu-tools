import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path

from . import XiaohongshuClient, XiaohongshuError, __version__
from .models import public_result


class JsonArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        raise XiaohongshuError("invalid_arguments", "参数错误，请使用 --help 查看用法。")


def parser():
    result = JsonArgumentParser(description="Read-only Xiaohongshu tools via local Chrome CDP")
    result.add_argument("--version", action="version", version=__version__)
    result.add_argument("--profile-dir", help="专用 Chrome 用户目录（不要使用日常浏览器目录）")
    result.add_argument("--chrome-path", help="Chrome 可执行文件")
    result.add_argument("--cookies-file", help="显式导入本地 Cookie 文件（文件只读）")
    result.add_argument("--visible", action="store_true", help="显示专用 Chrome 窗口")
    result.add_argument("--timeout", type=float, default=30)
    commands = result.add_subparsers(dest="command", required=True)
    commands.add_parser("session", help="检查登录状态")
    login = commands.add_parser("login", help="在可见浏览器扫码登录")
    login.add_argument("--wait-seconds", type=int, default=180)
    search = commands.add_parser("search", help="搜索笔记；limit>20时有界滚动，stdout 不输出 token")
    search.add_argument("keyword")
    search.add_argument("--limit", type=int, default=20)
    search.add_argument("--sort", default="综合")
    detail = commands.add_parser("detail", help="读取正文和有界评论样本")
    detail.add_argument("item_id")
    detail.add_argument("--comment-limit", type=int, default=20)
    return result


def cache_path(client):
    return client.profile_dir.parent / "private" / "search-tokens.json"


def save_cache(path: Path, result):
    path.parent.mkdir(parents=True, exist_ok=True)
    records = load_cache(path)
    for item in result["data"]["items"]:
        if item.get("xsecToken"):
            records[item["id"]] = {"token": item["xsecToken"], "savedAt": time.time()}
    temporary = path.with_suffix(".lock.tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        json.dump(records, handle)
    os.replace(temporary, path)


def load_cache(path: Path):
    try:
        records = json.loads(path.read_text(encoding="utf-8"))
        return {
            key: value
            for key, value in records.items()
            if isinstance(value, dict)
            and isinstance(value.get("token"), str)
            and isinstance(value.get("savedAt"), (int, float))
            and time.time() - value["savedAt"] < 12 * 3600
        }
    except OSError, ValueError, AttributeError, TypeError:
        return {}


async def run(args):
    async with XiaohongshuClient(
        profile_dir=args.profile_dir,
        chrome_path=args.chrome_path,
        headless=not (args.visible or args.command == "login"),
        timeout=args.timeout,
        cookies_file=args.cookies_file,
    ) as client:
        if args.command == "session":
            return await client.check_session()
        if args.command == "login":
            return await client.login(wait_seconds=args.wait_seconds)
        if args.command == "search":
            result = await client.search(args.keyword, limit=args.limit, sort=args.sort)
            save_cache(cache_path(client), result)
            return result
        cached = load_cache(cache_path(client)).get(args.item_id, {})
        return await client.detail(
            args.item_id, xsec_token=cached.get("token"), comment_limit=args.comment_limit
        )


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    try:
        args = parser().parse_args(argv)
        result = asyncio.run(run(args))
        print(json.dumps(public_result(result), ensure_ascii=False))
        return 0
    except XiaohongshuError as error:
        result = {
            "schemaVersion": 1,
            "status": "error",
            "source": "xiaohongshu",
            "error": {"code": error.code, "message": str(error)},
        }
    except KeyboardInterrupt:
        result = {
            "schemaVersion": 1,
            "status": "error",
            "source": "xiaohongshu",
            "error": {"code": "cancelled", "message": "操作已取消。"},
        }
    except Exception:
        # Do not dump raw CDP/page errors, paths or credentials on stdout or stderr.
        result = {
            "schemaVersion": 1,
            "status": "error",
            "source": "xiaohongshu",
            "error": {"code": "unexpected_error", "message": "运行失败；请检查浏览器和配置。"},
        }
    print(json.dumps(result, ensure_ascii=False))
    return 1


if __name__ == "__main__":
    sys.exit(main())
