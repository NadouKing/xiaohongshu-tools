"""Explicit network acceptance. Prints metrics only; no login/token dumps."""

import argparse
import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

from xiaohongshu_tools import XiaohongshuClient, XiaohongshuError


async def run(args):
    report = {
        "checkedAt": datetime.now(UTC).isoformat(),
        "runtime": "Python native CDP, installed Chrome, no Go service",
        "keyword": args.keyword,
        "details": [],
    }
    async with XiaohongshuClient(
        cookies_file=args.cookies_file, profile_dir=args.profile_dir, headless=True
    ) as client:
        report["session"] = (await client.check_session())["data"]
        search = await client.search(args.keyword, limit=8)
        report["search"] = {
            "count": search["data"]["count"],
            "elapsedMs": search["elapsedMs"],
            "method": search["method"],
        }
        for item in search["data"]["items"][:5]:
            try:
                detail = await client.detail(item["id"], comment_limit=10)
                data = detail["data"]
                report["details"].append(
                    {
                        "id": data["id"],
                        "title": data["title"],
                        "bodyCharacters": len(data["body"]),
                        "commentSampleCount": data["commentSampleCount"],
                        "commentsHasMore": data["commentsHasMore"],
                        "commentScope": data["commentScope"],
                        "commentMethod": data["commentMethod"],
                        "elapsedMs": detail["elapsedMs"],
                    }
                )
            except XiaohongshuError as error:
                report.setdefault("unavailable", []).append({"id": item["id"], "code": error.code})
            if len(report["details"]) >= 2:
                break
    report["passed"] = report["search"]["count"] > 0 and len(report["details"]) >= 2
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--keyword", default="广州 文冲 幸福里")
    parser.add_argument("--cookies-file")
    parser.add_argument("--profile-dir")
    parser.add_argument("--output")
    raise SystemExit(asyncio.run(run(parser.parse_args())))
