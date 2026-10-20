# OpenCode 多模型辩论启动包

这个目录帮助你在已经能调用多个模型系列的 OpenCode 中，建立多个讨论席位，完成多轮真实检索、互评和投票。它复用你已有的供应商配置，不需要把 API key 填进本包。

它提供配置生成器、主持/成员 prompt、统一研究背景与记录审核工具。实际模型调用由你的 OpenCode 执行；本包没有预先生成的科研答案，也没有替你在后台运行模型。随包附带的默认编排是六个模型系列、十个席位、三轮、8/10 门槛；这四个数字都在文件里，可以改，见「改席位、轮数与门槛」。

## 两种模式

同一套代码、同一套轮次与审核流程，只换「一轮产出什么」和「票怎么算」。用 `protocol.json` 的 `mode` 字段切换，默认 `proposal`。

|      | `proposal`（默认）                  | `evaluate`                       |
| ---- | ------------------------------- | -------------------------------- |
| 回答什么 | 这个方向还有没有值得做的新方案                 | 给定的这个问题，结论是什么                    |
| 首轮产出 | 每人一个主方案                         | 每人一个明确立场（支持 / 反对 / 有条件成立 / 证据不足） |
| 中间轮  | 合并相近方案、撤回站不住的                   | 收窄条件、修改或放弃立场                     |
| 目录文件 | `debate/candidates.json`，`K01`… | `debate/conclusions.json`，`C01`… |
| 投票   | 逐候选判断，可同时推荐多个                   | **单选**：只认一条结论或 `NONE`            |
| 默认门槛 | 八成席位（十席 → 8/10）                 | 严格多数（十席 → 6/10）                  |
| 认可键  | `approved_candidates`           | `adopted_conclusions`            |
| 提示词  | `prompts/proposal/`             | `prompts/evaluate/`              |
| 合法结果 | 没有值得推进的新方向                      | 没有多数认可的结论，或多数停在“证据不足”            |

`evaluate` 的门槛低不是放宽标准，而是问的问题不同：它问“大家怎么看”，不是“值不值得投入资源”。门槛与模式一起进入 `packet_sha256`；冻结之后再改模式，`audit` 会直接拒绝。

切换方式：在 `protocol.json` 写 `"mode": "evaluate"`，或运行 `python debate_tools.py setup --mode evaluate`（会按该模式重算默认门槛，并保留 `rounds`）。模式在 `setup` 时被写进 `opencode.json` 的席位提示词，所以换模式要连同旧的 `opencode.json`、`roster.lock.json` 一起删掉再 setup——和改席位表一样。

选择 `evaluate` 时，`research_brief.md` 里要有一个**能被判真假的具体问题**（“某个做法在某个设置下是否成立”“某个说法有没有证据”），而不是一个宽泛的主题。题目本身有歧义时，席位会在首轮先写清自己按哪种理解作答。

## 最少操作

1. 解压到一个专用目录，例如 `D:\research\multimodel_debate`，用 OpenCode 打开这个目录。先使用普通 Build 会话。
2. 把题目写进 `research_brief.md`。随包那份只是格式示例：复制 `research_brief.example.md` 改写机制段、已被占用的区域和已知负面证据。这一步不会替你想题目。
3. 决定用哪种模式：找新方向（`proposal`，默认）还是对给定问题取多数结论（`evaluate`）。后者需要在 `research_brief.md` 里写出一个能被判真假的具体问题，并用 `setup --mode evaluate` 配置。
4. 给 Build 发：**“请阅读 SETUP_PROMPT.txt，按里面的步骤完成配置。”** 生成器会读取 `opencode models` 的实际列表。能唯一识别时自动绑定，不能唯一识别时只需确认每个系列的真实模型 ID。不要把展示名当成 API ID。
5. 生成后运行 `python debate_tools.py doctor`。它会用运行中的 OpenCode 核对：席位是否真的加载、模型 ID 是否与冻结席位表一致、是否恰好一个 primary、成员检索权限、以及 websearch 配置是否与实际凭据相符。
6. 直接运行 `START_WINDOWS.cmd`（或 `python run_debate.py all`）。它逐席位启动真实会话，跑完全部轮次、冻结、审核并生成 `debate/final.md`。

`reopen` 只是让你能在 TUI 里观察和追问；正式讨论不依赖 TUI 手动调度。

设置阶段不会启动研究请求。正式开始后，成员会多次调用模型与检索工具；“R 轮”指每人 R 次正式发言，并不表示总共只有 R×席位数 次 API 请求——每轮内部还会调用检索工具，实际请求数远高于此。

### 关于联网检索

OpenCode 的 `websearch` 需要已连接的搜索 provider 凭据（Exa / Tavily / Firecrawl / Parallel / TinyFish）。没有凭据时，每次 `websearch` 都会失败，而 CLI 会因此返回 **exit 1**——即使席位发言已经完整输出。所以：

- 没有凭据：`setup` 默认用 `--search off`，在权限里 deny `websearch`。席位改走 `webfetch`：arXiv API 检索，arXiv HTML / ar5iv 读正文，`r.jina.ai` 把 ACL、PMLR、NeurIPS 的 PDF 转成文本（已验证可读方法段），见 `.opencode/skills/paper-search/SKILL.md`。
- 有凭据：在 OpenCode 里 `/connect` 一个 provider，再用 `python debate_tools.py setup --search on ...` 重新生成配置。
- `doctor` 会检查这两者是否一致，不一致就报失败。

另外，`openreview.net` 会返回 Cloudflare 人机验证，任何席位都读不到；遇到时改用该论文的 arXiv 版本。

## 默认的十个席位

下表由 `roles.json` 生成，是随包默认编排，不是代码里的常量。`chair: true` 的那一席兼任主持。

| 席位  | 默认模型系列 | 切入点               |
| --- | ------ | ----------------- |
| a01 | A 系列   | 数学机制与可证伪假设        |
| a02 | A 系列   | 理论、反例与正确性边界       |
| a03 | B 系列   | GPU 推理系统与实际开销     |
| a04 | B 系列   | 解码、KV cache 与计算复用 |
| a05 | C 系列   | 主持，兼独立实验设计研究者     |
| a06 | C 系列   | 最相近工作与新意审查        |
| a07 | D 系列   | 架构与新问题            |
| a08 | D 系列   | 替代解释与方法审查         |
| a09 | E 系列   | 原论文、官方代码与文献证据     |
| a10 | F 系列   | 跨领域启发             |

主持席同时是一个普通研究席位，不会额外增加一个模型。实际配置是一个主 Agent 加其余席位的子 Agent。同一模型系列的多席位使用同一模型 ID，但拥有不同任务/会话与研究视角。角色只是检索切入点，不限制谁能提出或反驳某种观点。

OpenCode 的子 Agent 是子会话，并不是天然互通的群聊。这里通过主持把既有轮次的原文放入统一资料包，让每个人在投票轮读到相同内容并回应，形成有记录的讨论。只开互不共享信息的聊天窗口，尚未完成这个过程。

## 改席位、轮数与门槛

三个文件决定编排，改完重新运行 `setup` 即可（前提是删掉旧的 `opencode.json` 与 `roster.lock.json`，生成器不会覆盖已有配置）：

- **`roles.json`**：席位表。每个席位有 `id`、`family`、`role`、`focus`；恰好一个席位带 `"chair": true`。ID 必须从 `a01` 起连续；至少三个席位（互评要求回应两个其他席位），至少两个模型系列。
- **`protocol.json`**：`mode`、`rounds` 与 `threshold.numerator / denominator`。`rounds` 允许 2–4：最后一轮投票，之前各轮是检索与互评；设为 2 就是“独立提案 + 冻结后投票”，设为 3 会多一轮互评、合并与重新查重。分母必须等于席位数——固定分母是为了让缺席不能降低门槛。省略 `threshold` 时按模式取默认（`proposal` 80% 取整，十席 → 8/10；`evaluate` 严格多数，十席 → 6/10）；只写一半会报错，免得半截配置悄悄生效。省略 `mode` 时按 `proposal`。
- **`model_map.json`**：`family` → 实际 `provider/model` ID，由 `setup` 从 `opencode models` 解析生成；也可手动编辑后作为 `--mapping` 传入。
- **席位级 `model`**：在 `roles.json` 的某个席位上加 `"model": "provider/model-id"`，直接覆盖它所属系列的映射。ID 必须是完整形式（`provider/model`，不是展示名），且必须出现在 `opencode models` 里。覆盖优先于 `model_map.json`，并会写进 `roster.lock.json` 冻结；某个系列的席位全被覆盖时，该系列不需要 `model_map.json` 条目。想让同一系列的两个席位用不同模型，就用这个，不必为此多造一个系列。

门槛不是只写在 prompt 里：它进入 `packet_sha256` 的哈希输入，并在 `packet_manifest.json` 里留档。投票开始后再把 8/10 改成 5/10，`audit` 会因为 digest 不符直接拒绝，而不是悄悄放宽标准。

## 多轮具体发生什么

下面按 `proposal` 写；`evaluate` 的差别只在括号里注明。

**第一轮独立构思。** 主持席先写定自己的提案（`evaluate`：立场），其余席位分别真实检索并各提一个主方案（`evaluate`：各自的回答与理由）。每人至少核查三份一手资料，不能全靠摘要。成员不能先读取别人的首轮答案。主持保留完整原文，不改写成自己的概括。

**中间轮互评与收敛（rounds ≥ 3 时存在）。** 每人读此前各轮原文，重新检索后至少回应两个其他席位，并可以把几个相近提案合并成一个仍然做得完的候选、拆开只留有新意的一半，或撤回自己的方案（`evaluate`：把立场收窄成条件式、修改或明确放弃）。本轮不投票；每份记录必须写下实际用过的查询和最相近工作/证据 URL，缺记录的席位会被拒绝入档。合并后的新增判别点要写清楚，只把两个课题捆在一起不算合并。

**中间归并。** 主持把首轮提案与中间轮的合并建议归并为 1–5 个候选，每个方案都有确定机制、最相近工作、最小实验和停止条件（`evaluate`：归并为 1–5 条互斥、可判真假的结论，每条带最强反证和“什么观测会推翻它”）。所有首轮方案必须被保留/合并或明确说明排除原因；不能在这时添加未被讨论的新方案。然后生成含全部既有轮次原文的统一资料包，冻结版本。

**投票轮。** 所有人阅读统一资料包，至少回应两个其他席位，并在投票前再检索一次。主持席先写定自己的票，再收集其余席位的票。每人对所有候选逐一判断（`evaluate`：单选，只认一条结论或 `NONE`），不能看别人投票轮的票，也不能为了凑多数反复改票。

**最后汇总。** 以席位数为固定分母，默认 80% 推荐（十席即 8/10）表示值得优先做最小实验；`evaluate` 用严格多数（十席 6/10）表示多数席位认可同一条结论。评分与理由一起公开。主持保留异议。若没有方案（`evaluate`：结论）达到门槛，明确报告没有达到，不生成虚假共识。按协议轮数完成后停止，不自动追加轮次。

“新意、意义足够，建议小实验”与“已经证明方法新颖/能发论文”不同。`evaluate` 里“6/10 认可”也只表示“多数席位基于本轮证据这么认为”，不是对问题本身的证明。模型投票具有相关性，不能作为统计证明。一条有实质证据的严重异议也不能被多数票盖过。`evaluate` 的票数还要看分布：如果票分散在三条以上互斥结论上，说明这个问题本轮没被回答，不能挑票数最高的一条写成“多数认可”。

## 不提供论文全文可以吗

可以先不提供。`research_brief.md` 是新主题的背景摘要，通常写这几段：要解决什么问题与边界、此前相关讨论的结论（如果有）、已被占用的区域与已知负面证据、可以复用的实测方法与它不能说明什么，以及一张核对过编号和正文读取路径的文献线索表。这些足够开始构思。

包内自带的 `research_brief.md` 只是格式示例。换成你自己的题目时，复制 `research_brief.example.md` 改写即可；实际使用的 `research_brief.md` 不随仓库分发（已 gitignore）。

如果某个最终候选是否新颖取决于某篇论文的具体公式、router、KV 实现或实验设定，应在推进它之前补方法段/代码核查。没有全文时，成员必须把背景当作作者摘要，不能声称审阅过那篇论文的全文。

背景里已有的负面结果属于**上一场讨论**，本场不必延伸它；它写在简报里是为了标出已被占满的区域，以及作者已有的实测方法学（validation 筛选 → 独立 test 复测、执行了哪些层单独报告、一致率不等于质量）。换题目时只需重写这几段，其余流程不变。

可选补充材料放入 `materials/`。模型只能访问实际接入或提供的知识库，不能因 prompt 写了“检索各种知识库”就自动获得账号或付费数据库访问。

## 自己用命令配置

需要本机已安装 OpenCode CLI 与 Python 3.10+，Python 不需要额外依赖。你既然已经在 OpenCode 配置好模型，不需要在这里再填密钥。

```powershell
opencode models
python debate_tools.py models
python debate_tools.py setup                              # proposal 模式（默认）
python debate_tools.py setup --mode evaluate              # 对给定问题取多数结论
```

如 `python` 不可用，可使用 `py -3`，Linux 常用 `python3`。有多个同名供应商时，交互配置会列出真实 ID 让你选择。

若由 OpenCode Build 自动执行，建议：

```text
python debate_tools.py setup --non-interactive
```

如果不能唯一识别系列名，复制 `model_map.example.json` 为 `model_map.json`，用 `opencode models` 中的真实完整 ID 填好六项，再执行：

```text
python debate_tools.py setup --mapping model_map.json --non-interactive
```

Windows 也可先导出列表供脚本读取：

```powershell
opencode models | Set-Content -Encoding utf8 models.txt
python debate_tools.py setup --inventory models.txt --mapping model_map.json --non-interactive
```

不确定的映射不会静默回退到默认模型。脚本也不会覆盖已有 `opencode.json`、`opencode.jsonc` 或 `roster.lock.json`，因此请在专用新目录使用。

若只有桌面程序附带的 CLI 不在 PATH，找到它的实际路径后，可给 `models` 或 `setup` 添加 `--opencode "完整CLI路径"`；也可先用该 CLI 导出列表，再用 `--inventory`。这些参数不需要模型密钥。

Windows 启动：

```powershell
.\START_WINDOWS.cmd
```

它先跑 `doctor`，再执行 `python run_debate.py all`。若想自己控制节奏：

```powershell
python run_debate.py round1          # 全部首轮
python run_debate.py deliberate --round 2   # 第 2 轮互评（rounds ≥ 3 时）
python run_debate.py merge           # 主持归并候选 + freeze
python run_debate.py vote            # 全部投票轮席位
python run_debate.py audit           # 统计与完整性检查
python run_debate.py final           # 主持写 final.md
```

每一步都可加 `--resume` 跳过已完成的席位；`round1`、`deliberate` 与 `vote` 还可加 `--seats a01,a03` 只跑个别席位做低成本的格式与检索预检。

同一轮内的席位可并行：`--parallel N`（默认 4，`1` 表示串行）。轮与轮之间仍然串行，主持自己那一步不会和其他席位同时跑，因为每一轮都要读上一轮的文件。

这里的模型名称沿用你的供应商显示名。具体完整 ID 与工具调用支持以你本机实际能力为准；模型自称某品牌不能验证其背后的权重身份。如果某席位缺少检索/工具能力，应报告未完成，不能用另一个模型偷偷代替它。

## Docker（可选）

容器跑的是同一份代码、同一个 `debate/` 目录。省掉在本机装 Python 与 OpenCode CLI，也让十席位不必开十个终端。

```bash
cp .env.example .env          # 把 OPENCODE_CONFIG 改成绝对路径
docker compose build
docker compose run --rm setup # 只需一次：生成 model_map.json 与 opencode.json
docker compose run --rm doctor
docker compose up             # 完整运行，日志直接打到终端
```

- **配置是挂载进去的，不复制。** `OPENCODE_CONFIG` 指向你已有的 `opencode.json` 与供应商凭据所在目录，只读挂载；`.dockerignore` 已把 `debate/`、`.env`、`roster.lock.json` 排除在构建上下文之外。镜像和仓库里都没有密钥。`.env` 由用户自己建、不进仓库；`OPENCODE_CONFIG` 留空时 compose 直接拒绝启动并点名缺哪个变量，而不是挂一个空目录然后报成供应商错误。
- **compose 不展开 `~`。** 必须写绝对路径：Linux/macOS 用 `/home/you/.config/opencode`，Windows 用 `C:/Users/you/.config/opencode`。
- **运行状态在具名卷 `opencode-state` 里**，保存 `~/.local/share` 与 `~/.local/state`。OpenCode 的 SQLite 数据库用 WAL 模式，需要宿主绑定挂载（Windows/macOS）提供不了的共享内存语义：指到宿主机副本会报 `disk I/O error`，随后 CLI 报“Background service failed to start”。所以只有配置目录和工作目录是绑定挂载。`docker compose down -v` 会清掉这个卷，包括正在进行的会话数据库。
- **构建镜像源。** `.env` 里的 `DEBIAN_MIRROR` 替换 `apt-get` 使用的 Debian 源，留空则用 `deb.debian.org`。构建参数必须留在 `docker-compose.yml` 里——在 `docker compose build` 命令行上临时传的不会带到下一次 `docker compose run`。
- **uid。** 镜像以 uid/gid 1000 运行。你的 uid 不同时加 `--user "$(id -u):$(id -g)"`；入口脚本会创建所需目录，只要挂载路径可读，换 uid 也能跑。
- **另一种做法（非默认）：** 不挂配置目录，改用环境变量传供应商密钥。这需要改 `docker-compose.yml`（删掉 `OPENCODE_CONFIG` 那一行挂载）；默认选择挂配置目录，是因为只有一条路径需要审计，compose 文件里也不出现密钥。

## 输出在哪里、怎样查看

正式运行后，由主持写入 `debate/`：

| 文件                                               | 含义                                                    |
| ------------------------------------------------ | ----------------------------------------------------- |
| `run_log.md`                                     | 席位与配置模型、阶段、失败与续接情况                                    |
| `logs/`                                          | 每席位每次调用的原始 JSON 事件流、stderr 和工具错误清单，用于核对真实调用           |
| `round1/a01.md` … `a10.md`                       | 第一轮每席位一份完整发言                                          |
| `round2/`、`round3/`（存在时）                         | 中间轮与投票轮每席位一份完整原文                                      |
| `candidates.json`（`evaluate`：`conclusions.json`） | 固定候选定义与全部首轮方案的去向                                      |
| `vote_packet.md`、`packet_manifest.json`          | 每人投票轮读取的相同资料与版本                                       |
| `votes.csv`、`audit.json`                         | 实际票数、完整性与版本检查结果                                       |
| `final.md`                                       | 主持总结：优先候选、证据、异议、最小实验（`evaluate`：每条结论的票数与最强反证），或没有足够支持 |

主持的本地审核命令：

```text
python debate_tools.py freeze
python debate_tools.py audit
```

缺票、重复投同一候选、资料版本变动、配置模型与席位表不一致等会阻止生成有效推荐。审核器只检查记录与票数，无法证明引用内容真实，也无法证明每个席位确实由对应后端执行。要核对真实调用，看 `debate/logs/` 里每个席位的原始 JSON 事件流（含 `sessionID`、`model`、每次工具调用及结果）；不要只信一张角色自述表。

模型的推荐理由、最相近论文差异和没有解决的问题，比票数本身更值得读。整个过程不启动GPU训练；选出方向后再决定是否运行最小实验。

## 验证与依据

本包本地的验证记录见 `VALIDATION.md`。本地测试不调用任何模型 API；真实跨供应商与网页工具能力需要在你的 OpenCode 环境确认。

以下是2026-10-17核对的 OpenCode 官方文档：

- Agents，自定义模型、primary/subagent、Task权限：https://opencode.ai/docs/agents/
- Config，项目配置与全局配置合并、默认Agent：https://opencode.ai/docs/config/
- CLI，`opencode models`、`--agent` 与模型 ID：https://opencode.ai/docs/cli/
- Tools，websearch/webfetch与检索启用环境变量：https://opencode.ai/docs/tools/
- Commands，自定义启动命令：https://opencode.ai/docs/commands/
