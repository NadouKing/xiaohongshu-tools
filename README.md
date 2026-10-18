# xiaohongshu-tools

Python 3.14 的小红书只读采集库与 `xhs` CLI。通过本机 Chrome 的原生 CDP 读取已登录网页，供出行研究、脚本和 AI 编排使用。

当前支持：登录状态、可见浏览器扫码登录、有界搜索、笔记正文、有上限的一级评论样本。无需 Go 服务、Node、Playwright 或独立大模型 API。**它不是小红书官方 API。**

## 安装

需要 Python 3.14、[uv](https://docs.astral.sh/uv/) 和已安装的 Google Chrome。开发者从仓库运行：

```sh
uv sync --locked
uv run xhs --version
uv run xhs login
uv run xhs search "广州 文冲 幸福里" --limit 8
uv run xhs search "广州 黄埔 周末" --limit 30
uv run xhs detail 682415b0000000002001f472 --comment-limit 10
```

系统安装 Chrome 后自动发现；自定义路径用全局参数 `--chrome-path`，专用数据目录用 `--profile-dir`。全局参数放在子命令之前，例如 `xhs --visible search "广州 周末"`。Linux/macOS 的路径发现已实现，真实浏览器验收目前仅覆盖 Windows。

这是三个独立 Python 包之一。接入 `lazy-trip` 后，由主仓的一套 `.venv` 安装并直接 import 本包，无需再执行本仓 `uv sync`。本仓 `uv.lock` 用于独立开发；它不要求用户运行额外常驻服务。

## Python 接口

```python
import asyncio
from xiaohongshu_tools import XiaohongshuClient


async def main():
    async with XiaohongshuClient(headless=True, timeout=30) as client:
        session = await client.check_session()
        if session["data"]["state"] != "ready":
            raise RuntimeError("先运行 xhs login")
        result = await client.search("广州 文冲 幸福里", limit=8, sort="综合")
        first = result["data"]["items"][0]
        detail = await client.detail(
            first["id"], xsec_token=first.get("xsecToken"), comment_limit=10
        )
        print(detail["data"]["title"], detail["data"]["commentSampleCount"])


asyncio.run(main())
```

构造参数：`profile_dir=None, chrome_path=None, headless=True, timeout=30.0, cookies_file=None`。
已有本地 cookie 文件可**显式**通过 `cookies_file` 或 `--cookies-file` 导入独立 profile。支持裸数组和 `{ "version": 2, "cookies": [...] }`。来源文件只读，不自动查找其他工具的凭据、不覆盖来源文件。

统一结果：

```json
{
  "schemaVersion": 1,
  "status": "ok",
  "source": "xiaohongshu",
  "fetchedAt": "2026-10-18T12:45:31+00:00",
  "method": "cdp.page_state",
  "elapsedMs": 1942,
  "data": {"items": [], "count": 0, "hasMore": null}
}
```

- `check_session().data`：`state=ready|login_required|verification_required` 和 `authenticated`。
- `search().data.items`：`id,title,url,type,author,xsecToken`。访问 token 仅供库调用方在私有内存中衔接详情；公开输出必须过滤。
- `search(limit=1..50)`：默认 `20` 保留首屏行为；大于 `20` 时最多滚动 `8` 轮，追加加载预算最多 `18` 秒，连续 `3` 轮无新增就停止。返回 `requestedLimit/loadedCount/scrolls/stopReason/hasMore`；达到时间或滚动边界可能少于请求量，未知是否到底时 `hasMore=null`。
- `detail().data`：`id,title,body,url,publishedAt,comments,commentSampleCount,commentsHasMore,commentScope`，另有评论获取路径与上限。
- `commentsHasMore=null` 表示无法判断；`false` 也不表示所有楼中楼均已读取。`commentScope` 始终明确为有界一级评论样本，`comment_limit=0` 时是 `not_requested`。
- 失败抛出 `XiaohongshuError` 子类，其 `code` 稳定且消息经过简化。CLI 输出 JSON 错误、非零退出，不打印网页、CDP 原始错误或凭据。

## 实现与边界

原生 WebSocket CDP → Chrome 页面导航 → 应用 `__INITIAL_STATE__`；评论状态缺失时读取已渲染的评论元素，并做有界滚动。搜索默认首屏 20 条，主动请求可有界加载至 50 条；评论最多 100 条，默认 20。排序通过现有页面控件应用，刷新未完成会显式报错。官方 `/website-login/captcha` 跳转会明确返回 `verification_required`，不当作空结果或仅等待超时；仍需人工完成验证。

没有重写签名算法、验证码绕过或通用 HTTP 抓取代理。没有发帖、点赞、评论、关注等账号写入。站点验证、登录失效、笔记删除和页面改版会影响可用性；工具显式报告错误，不伪造结果。

CLI 的 stdout 过滤 token 和 URL 查询串；详情衔接 token 只缓存到专用 profile 同级 `private/`，12 小时过期。Chrome profile 与该缓存都是敏感本地数据，不应进入 Git、日志和分享文件。使用专用目录，不使用日常 Chrome 用户目录。每个 profile 同时只允许一个本工具进程；退出会关闭本次启动的 Chrome，保留本地登录。

## 开发与验收

```sh
uv run ruff check .
uv run ruff format --check .
uv run pytest
uv build
uv run python scripts/smoke_installed_wheel.py dist/xiaohongshu_tools-0.1.1-py3-none-any.whl
# 仅主动需要真实平台验收时运行：
uv run python scripts/live_acceptance.py --output private/live-acceptance.json
```

目录外 wheel 烟测会创建临时测试环境，验证安装产物而非借用源码。生产环境由主应用统一管理，不为每个平台常驻一套环境。真实验收记录仅保留计数、耗时、公开笔记 ID/标题，不保存正文、评论用户或访问参数：[2026-10-18 实测](docs/live-acceptance-2026-10-18.json)。这些耗时不构成相对 Playwright 或 Go 服务的性能比较。

参考了 [xpzouying/xiaohongshu-mcp](https://github.com/xpzouying/xiaohongshu-mcp) 的站点状态读取思路（Apache-2.0），本包独立实现 Python CDP；工程分层与安装产物验收借鉴 [seller-ops-automation](https://github.com/DouNineGo/seller-ops-automation)，不依赖该项目。

更多见 [架构](docs/architecture.md)、[部署](docs/deployment.md)、[环境](docs/environment.md)。

每次改动按[开发与 PR 交付](docs/development-delivery.md)建分支、验证并提交草稿 PR；审查见[处理规则](docs/review.md)。本轮借鉴范围、上游状态与暂缓项见[上游维护检查](docs/upstream-review-2026-10-18.md)。
