# xiaohongshu-tools

Python 3.14 的小红书只读采集库与 `xhs` CLI。通过本机 Chrome 的原生 CDP 读取已登录网页，供脚本、Python 应用和 AI 编排使用。

当前支持：登录状态、可见浏览器扫码登录、有界搜索、笔记正文、有上限的一级评论样本。无需 Go 服务、Node、Playwright 或独立大模型 API。**它不是小红书官方 API。**

## 安装

需要 Python 3.14、[uv](https://docs.astral.sh/uv/) 和已安装的 Google Chrome。开发者从仓库运行：

```sh
git clone https://github.com/NadouKing/xiaohongshu-tools.git
cd xiaohongshu-tools
uv sync --locked
uv run xhs --version
uv run xhs login
uv run xhs search "广州 文冲 幸福里" --limit 8
uv run xhs search "广州 黄埔 周末" --limit 30
uv run xhs detail 682415b0000000002001f472 --comment-limit 10
```

系统安装 Chrome 后自动发现；自定义路径用全局参数 `--chrome-path`，专用数据目录用 `--profile-dir`。全局参数放在子命令之前，例如 `xhs --visible search "广州 周末"`。Linux/macOS 的路径发现已实现，真实浏览器验收目前仅覆盖 Windows。

只克隆本仓就能安装和使用，不需要 Trip、大众点评工具或其他仓库。本仓 `uv.lock` 管理自己的依赖；运行无需额外常驻服务。也可在现有 Python 3.14 环境中安装 `uv build` 生成的 wheel，再直接使用 `xhs` 或下面的 Python 接口。

## 独立工具与集成关系

Python 库和 CLI 都是正式使用入口，调用同一个客户端。其他应用可以按需选择，不必先安装出行规划器。工具只负责平台会话、搜索、笔记与评论样本，参数和数据合同由本仓维护。

[`lazy-trip`](https://github.com/NadouKing/lazy-trip) 是一个可选调用方：它直接 import 本包，在自己的 `research` 模块把笔记转成出行证据、过滤不相关结果、衔接地点与路线。本包不读取 Trip 配置，也不接收预算、路线或出行需求。Trip 可将工具包装入自己的一套 `.venv`，这是一种部署方式，不是本工具的运行前提。

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

本包的结果外壳：

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

与其他工具采用相似的异步调用、结果外壳和错误码，便于调用方处理生命周期和失败；没有强制统一平台数据。`sort`、`xsec_token`、`comment_limit`、笔记和评论字段仍属于小红书合同，调用方负责适配自己的业务模型。

## 实现与边界

原生 WebSocket CDP → Chrome 页面导航 → 应用 `__INITIAL_STATE__`；评论状态缺失时读取已渲染的评论元素，并做有界滚动。搜索默认首屏 20 条，主动请求可有界加载至 50 条；评论最多 100 条，默认 20。排序通过现有页面控件应用，刷新未完成会显式报错。官方 `/website-login/captcha` 跳转会明确返回 `verification_required`，不当作空结果或仅等待超时；仍需人工完成验证。

搜索和详情在每次浏览器冷启动后先访问首页确认会话，再打开深链接；同一客户端随后复用初始化结果。当前实测中，冷启动直接打开搜索深链接会导航超时，先完成首页初始化后可以正常读取。每个页面仍检查登录/验证，不以缓存状态代替当前检查。关键词采用 URI 百分号编码，保留空格、加号及其他特殊字符的原意。

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

目录外 wheel 烟测创建临时测试环境，只安装本包及声明依赖，检查库、CLI 和未安装任何集成应用或其他平台工具；CI 同样执行。日常可独立安装，也可共用调用方环境。真实验收记录仅保留计数、耗时、公开笔记 ID/标题，不保存正文、评论用户或访问参数：[2026-10-18 实测](docs/live-acceptance-2026-10-18.json)。这些耗时不构成相对 Playwright 或 Go 服务的性能比较。

参考了 [xpzouying/xiaohongshu-mcp](https://github.com/xpzouying/xiaohongshu-mcp) 的站点状态读取思路（Apache-2.0），本包独立实现 Python CDP。

更多见 [架构](docs/architecture.md)、[部署](docs/deployment.md)、[环境](docs/environment.md)。

每次改动按[开发与 PR 交付](docs/development-delivery.md)建分支、验证并提交草稿 PR；审查见[处理规则](docs/review.md)。本轮借鉴范围、上游状态与暂缓项见[上游维护检查](docs/upstream-review-2026-10-18.md)。
