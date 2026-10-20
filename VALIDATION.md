# 本地验证记录

2026-10-20 双模式改造：`proposal` 与 `evaluate` 共用同一套轮次、冻结、哈希与审核，只有"一轮产出什么"和"票怎么算"不同。模式写在 `protocol.json` 的 `mode`，默认 `proposal`；`evaluate` 用 `S-` 立场编号、`debate/conclusions.json`（`C01`…）、`endorse`/`confidence`、单选票与严格多数门槛（十席 6/10）。离线测试增至 42 项（`python -B -m unittest test_tools`，`ToolsTests` 32 项 + `EvaluateTests` 10 项），全部通过。

`EvaluateTests` 覆盖：默认门槛为严格多数、6/10 采纳与 5/10 不采纳、`endorse` 需要置信度下限与证据 URL、一个席位认同两条互斥结论被拒、写错目录文件名（`candidates.json` ↔ `conclusions.json`）时的报错指对文件、冻结后改模式被拒、`set_mode` 按新模式重算门槛并保留 `rounds`、未写 `threshold` 时按模式取默认、未知模式被拒。

模式与门槛一起进入 `packet_sha256`，并在 `packet_manifest.json` 与 `roster.lock.json` 里各留一份；`audit` 检查两者与当前 `protocol.json` 一致。`prompts/` 下按模式分为两套完整提示词（各 6 个文件），`setup` 只读当前模式那一套，缺文件时直接报错而不是退回另一套。

2026-10-20 离线测试增至 32 项，全部通过（`python -B -m unittest test_tools`）。新增席位级 `model` 覆盖（优先于系列映射、必须存在于模型列表、写进 `roster.lock.json`）、系列全部被覆盖时跳过 `model_map.json`、`audit.json` 的逐系列诊断 `family_breakdown`。随包文档与测试中的模型名已改为占位系列名 `family_a`–`family_f` 与 `mock/family-a`–`mock/family-f`；真实运行记录 `debate/audit.json`、`debate/votes.csv` 保持原样，不改写。

2026-10-19 在 Windows、Python 3.14.3、OpenCode v2.0.30 环境执行 `python -B -m unittest test_tools`，26 项离线测试全部通过。相对 10-18 的 22 项，新增可配置轮数（`rounds` 2–4）：3 轮全流程 30 份正式发言、2 轮兼容路径、越界轮数被拒、缺中间轮阻止 freeze、中间轮未记录检索查询被拒。

检查覆盖：

- Windows BOM、ANSI与换行形式的模型列表解析。
- 同前缀的两个系列（例如 `family_b` 与 `family_c`）区分；缺失或同系列多个供应商时不静默猜测。
- 默认编排映射为十席位，一个 primary 加其余 subagent，子 Agent 不再派生新成员。
- 席位表、主持席、轮数与门槛全部来自 `roles.json` / `protocol.json`；改成 7 席也只改这两个文件，不改代码。
- 既有项目配置保持原样，不被覆盖。
- V2 原生配置形状：顶层 `agents`/`commands`，`permissions` 为规则数组；出现 V1 的 `agent`/`command`/`permission` 键时 `packet_data` 直接拒绝。
- 用明确标注的模拟发言检查全部轮次记录、8/10 票数与 CSV 生成；`rounds=2` 与 `rounds=3` 两条路径都能跑通。
- 缺席不能降低分母，重复票不能多算。
- 修改资料包正文、候选定义、配置模型或票上的版本标识会被拒绝。
- 冻结后把门槛从 8/10 改成 6/10 会被 `packet_sha256` 拦住，不会悄悄放宽。
- 多数票不能掩盖待核查的致命异议。
- 检索状态为 `blocked` 的席位不能进入有效投票阶段；`partial` 允许入档，但必须出现在 `audit.json` 的 `retrieval_partial_seats` 与目录文件的 `scope_note` 里，且重复 `freeze` 不叠加、不改变 packet 哈希；席位在冻结前补齐检索后，过期名单会被清除。
- 中间轮与投票轮都必须记录至少两条实际检索过的查询；缺失时 `freeze` 或 `audit` 拒绝。
- `evaluate` 模式下，一个席位同时认同两条互斥结论会被 `audit` 拒绝：单选才有"多数认可的结论"可言。
- 冻结后再改 `mode` 会被 `packet_sha256` 与 manifest 的一致性检查拦住。

模拟模型 ID、发言、候选和 example.invalid 资料只存在于测试临时目录中；不是科研结果，不会被装成真实讨论输出。

## 2026-10-17 本机实测（真实调用）

- `debate_tools.py doctor` 全绿：十席位被运行时按配置加载（`opencode debug agents`），六个模型 ID 全部存在于 `opencode models`，一个 primary 加其余 subagent，主持可调其余席位，成员检索权限正确。
- 供应商接口支持原生工具调用：OpenAI 兼容的 `/chat/completions` 端点返回 `finish_reason=tool_calls` 与真实 `tool_calls`；Anthropic `/messages` 端点返回 `stop_reason=tool_use` 与 `tool_use` 块。两端都支持工具调用。
- OpenCode 端到端工具回路可用：模型发出 tool call → OpenCode 执行 `webfetch` → 结果回传 → 模型据此作答。
- 六个系列各一次低成本实测：a01/a03/a06/a07/a08/a09 均成功读到 arXiv API 返回的真实标题。
- 首轮单席位完整试跑（a01、a05）：自主检索、按格式返回、写入 `debate/round1/`，末尾 JSON 元数据合格；抽查引用的 arXiv ID 与 LayerSkip README 均真实存在。
- 已知故障：
  - `websearch` 无 provider 凭据时返回 “Web search cancelled”，且 CLI 因此 **exit 1**，但发言仍完整。因此默认 `--search off` 在权限里 deny websearch，席位改走 `webfetch`。
  - `openreview.net` 返回 Cloudflare 人机验证，读不到；经 `r.jina.ai` 转换其 PDF 也一样（返回 428 字节的验证页）。
  - 子 Agent 工具（`subagent`/Task）在 v2.0.30 下报 `Subagent session not found`，连内置 `general` 也失败。因此改为 `run_debate.py` 逐席位启动真实 `opencode run --agent` 会话，席位间只通过文件通信。

## 2026-10-18 正文读取通道实测

`webfetch` 不能直接读 PDF（`application/pdf` 被拒）。以下三条通道逐条实测，均返回含方法段的正文：

| 通道 | 实测结果 |
|---|---|
| `https://arxiv.org/html/<编号>` | 15 篇清单论文全部 200，正文 111–767 KB |
| `https://ar5iv.labs.arxiv.org/html/<编号>` | 200，老论文可用（LayerSkip 314 KB 正文）；有官方 HTML 时不必用 |
| `https://r.jina.ai/<PDF 完整 URL>` | ACL 2025 论文 47 KB、PMLR ICML 2021 论文 46 KB、NeurIPS 2022 论文 70 KB、arXiv PDF 92 KB，均含章节与表格；公式会失真 |

元数据检索可用：OpenAlex、Crossref、DBLP（无正文）；arXiv API（题名、摘要、日期）。不可用：`api.github.com`（匿名配额 60/60 用尽时 403，改用 `raw.githubusercontent.com`）、`api.semanticscholar.org`（常 429）。

单席位复测（a06）：`retrieval_status` 按新规则自填 `partial` 并在正文写明未覆盖的近邻；四篇引用（LayerSkip 2404.16710、SkipDecode 2307.02628、Draft & Verify 2309.08168、ADEPT 2601.03700）全部经 arXiv API 核对存在，题名与日期相符。同期观察到每席约 3 次工具调用参数为空（`read: Missing key`、`skill: Missing key`），属模型侧操作错误，重试后成功，不影响结果。

## 2026-10-20 Docker 构建与容器内实测

Windows 11 + Docker Desktop（engine 27.5.1，overlayfs，WSL2 后端）。镜像 `node:22-bookworm-slim`，内装 `@opencode/cli@2.0.30`、Python 3.11.2、git 2.39.5，以 uid/gid 1000 的非 root 用户运行，镜像 1.78 GB。

| 检查 | 结果 |
|---|---|
| `docker compose build` | 成功；`apt-get` 在 `npm` 之前装好 `ca-certificates git python3`，联网依赖不再被 npm 的证书状态挡住 |
| `DEBIAN_MIRROR` 构建参数 | 生效；必须写在 `docker-compose.yml` 里，命令行临时传的不会带到下一次 `docker compose run` |
| `docker compose run --rm doctor` | `"ok": true`：十席位被运行时加载，六个系列/六个 ID 全部存在，主持可调其余九席，`websearch: deny` / `webfetch: allow` |
| `docker compose run --rm harness audit` | 正常输出，含逐系列诊断 `family_breakdown` |
| 配置目录挂载 | 只读挂载有效；镜像内确认没有 `debate/`、`opencode.json`、`roster.lock.json`、`materials/` |

已知限制：

- OpenCode 的 SQLite 数据库是 WAL 模式。把 `~/.local/share` 或 `~/.local/state` 绑到 Windows 宿主目录会报 `disk I/O error`，随后 CLI 报 “Background service failed to start”。两个目录改用具名卷 `opencode-state` 后正常；只有配置目录与工作目录是绑定挂载。
- 具名卷不随仓库走，`docker compose down -v` 会连会话数据库一起删掉。
- Windows 宿主路径必须写绝对路径（`C:/Users/...`），compose 不展开 `~`。
- 容器内 uid 固定 1000；宿主 uid 不同时要用 `--user` 覆盖。

记录审核只验证文件、版本、结构与计票。它不能代替查阅论文，也不能验证中转实际执行的底层权重。调用真实性要结合 `debate/logs/` 里的原始 JSON 事件流（含 `sessionID`、`model`、工具调用与结果）检查。
