# 上游维护检查：2026-10-18

上游 [xpzouying/xiaohongshu-mcp](https://github.com/xpzouying/xiaohongshu-mcp) 最近代码推送为 2026-10-12；仓库未归档，不能概括为停止维护。
本轮获取全部 437 个 PR、428 个非 PR Issue 的索引与说明，按只读范围筛选 144 个候选；18 个 PR 的文件补丁下载后进入重点核对。
这不是 437 个补丁均已移植或每个评论线程都已逐条复核的声明。原始远端材料只留本地工作目录，不作为运行依赖。

## 本次吸收

| 来源 | 当时状态 | Python 处理 |
|---|---|---|
| [#781](https://github.com/xpzouying/xiaohongshu-mcp/pull/781) 搜索加载更多 | open | 使用现有 CDP 做有界滚动、跨批去重；默认20保持首屏，显式请求最大50。返回停止原因与未知的 hasMore，不保证读完搜索结果 |
| [#872](https://github.com/xpzouying/xiaohongshu-mcp/pull/872) 验证/登录跳转识别 | open | 在现有页面探针中检查官方域名及路径；进入验证页时明确返回 verification_required，排序/翻页过程中也保留门禁 |

以上是根据需求重新实现的 Python 版本，没有把上游 Go 服务引为依赖。上游使用 Apache-2.0；本仓继续注明来源，未复制其发布、指纹或认证服务。

## 已有等价能力与不适用项

| 来源 | 核对结论 |
|---|---|
| [#839](https://github.com/xpzouying/xiaohongshu-mcp/pull/839)、[#841](https://github.com/xpzouying/xiaohongshu-mcp/pull/841) | 已等具体 search feeds / noteDetailMap 数据，不等全页或 DOM 静止；每次新页面避免沿用上一页结果 |
| [#840](https://github.com/xpzouying/xiaohongshu-mcp/pull/840)、[#826](https://github.com/xpzouying/xiaohongshu-mcp/pull/826) | 已在客户端上下文复用一个浏览器，串行操作、profile锁、结束清理；无需为本地库加入服务端常驻池 |
| [#827](https://github.com/xpzouying/xiaohongshu-mcp/pull/827) | 已输出带UTC时区的ISO时间，主仓报告转中国时间；不新增一套含糊裸时间 |
| [#816](https://github.com/xpzouying/xiaohongshu-mcp/pull/816)、[#763](https://github.com/xpzouying/xiaohongshu-mcp/pull/763)、[#776](https://github.com/xpzouying/xiaohongshu-mcp/pull/776) | 已跳过默认综合筛选、按可见文本选项、等刷新、仅返回note卡片；保留没有标题的真实笔记 |
| [#858](https://github.com/xpzouying/xiaohongshu-mcp/pull/858) | 上游鼠标轨迹/面板点击路径与本仓页面函数选择路径不同；不照搬整套交互框架 |
| [#748](https://github.com/xpzouying/xiaohongshu-mcp/pull/748) | 已从结构化字段单独返回平台评论总数，并与实际样本数分开 |
| [#755](https://github.com/xpzouying/xiaohongshu-mcp/pull/755)、[#624](https://github.com/xpzouying/xiaohongshu-mcp/pull/624) | 原cookie只读导入、profile持久化、私有缓存原子替换及typed错误已经存在；不移植Go panic/随机画像逻辑 |

## 本轮未移植

- [#589](https://github.com/xpzouying/xiaohongshu-mcp/pull/589)：分享短链解析值得加入，但需要单独核对跳转域、私有访问参数、失效链接和真实短链样本；本轮仍用ID及私有搜索缓存衔接详情。
- [#824](https://github.com/xpzouying/xiaohongshu-mcp/pull/824)：拦截图片/音视频/字体需要资源与返回完整性的对照测量；本轮没有这项测量，不声称节省内存。
- [#825](https://github.com/xpzouying/xiaohongshu-mcp/pull/825)：字幕正文列入媒体证据扩展，需要可用字幕样本、来源和失败语义；不把未读视频宣称为已理解。
- [#759](https://github.com/xpzouying/xiaohongshu-mcp/pull/759)：只读评论已有数量/时间边界；其他发布、鼠标行为部分不属于当前范围。
- 发帖、回复、点赞、关注、商品、海外 RedNote 与写入流程不进入本轮出行研究工具。

## 验证

23项测试通过，包含真实Chrome运行的本地URL探针fixture；fixture验证路径识别机制，没有主动触发账号风控。
真实平台验证见 [脱敏记录](upstream-sync-2026-10-18.json)：同一浏览器中完成默认查询、30条搜索、排序及两篇详情。实际数量与耗时见记录，未作Go/Playwright性能优劣比较。
本次为PR候选0.1.1；主仓仍锁定已验收0.1.0，工具PR合并后再单独更新主仓固定SHA与lock并复验。
