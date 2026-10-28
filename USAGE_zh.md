# 详细使用指南

[快速开始](README_zh.md) · [English guide](USAGE.md)

<p align="center">
  <img src="assets/cover-titled.png" alt="Agent 赛博辩论会：多个机器人席位围着一张圆桌，有的在检索，有的在思考，有的在陈述，有的在投票" width="100%">
</p>

用 OpenCode 中已配置的模型，组织多轮检索、互评和投票。目前设计了三类任务：围绕一个研究方向找新方案、针对一个具体问题形成结论，或用给定的问题和知识库讨论出能执行的解法。

项目包含配置生成器、主持和成员提示词、研究背景模板，以及讨论记录审核工具。模型调用由 OpenCode 执行，直接复用已有的供应商配置，无需另填 API key。

默认配置是六个模型系列、十个席位、三轮讨论。提案模式下，候选方案需要获得 8/10 的推荐。席位、轮数和门槛都可以修改，见[修改配置](#修改配置)。

## 适用者

这个包不是一键工具，用它之前需要有这些准备：

- 能用 OpenCode 选模型、能读 `opencode models` 的输出，理解 `provider/model` 这种完整 ID 的写法；
- 能改 JSON（`roles.json`、`protocol.json`），能跑 `python debate_tools.py` 和 `run_debate.py` 这几条命令；
- 愿意读失败信息。`setup`、`doctor`、`audit` 报错时都说明了具体缺什么，跳过报错直接重跑只会得到同一个错误；
- 手上有一个值得让人工检索和争论的题目，以及能写清的资源边界。

不需要的是：会写提示词、会调模型 API、会配 Docker（Docker 只是可选路径）。第一次使用最容易卡住的不是配置，是 `research_brief.md` 写得太空——席位拿不到边界，就会退化成泛泛综述。

如果上面第 1、2 条对你不是问题，最省事的方式是把配置和写作交给一个代理去做，见[用代理代笔](#用代理代笔)。

## 三种讨论模式

通过 `protocol.json` 的 `mode` 字段选择模式，默认是 `proposal`。三种模式共用运行和审核流程，区别在于讨论目标、一轮产出什么，以及票怎么算。

| 项目    | `proposal`（默认）                     | `evaluate` | `solve` |
| ----- | ---------------------------------- | -------------------------------------- | -------------------------------------- |
| 讨论目标  | 寻找值得做的新方案                          | 对给定问题形成结论                              | 对给定问题讨论出能执行的解法 |
| 首轮产出  | 每人一个主方案                            | 每人一个明确立场：支持、反对、有条件成立或证据不足              | 每人一个初步解法 |
| 中间轮   | 合并相近方案，修改或撤回方案                     | 收窄条件，修改或放弃立场                           | 合并互补步骤，拆开或收窄方案 |
| 目录文件  | `debate/candidates.json`，编号 `K01`… | `debate/conclusions.json`，编号 `C01`…    | `debate/solutions.json`，编号 `S01`… |
| 投票方式  | 逐项判断，可推荐多个候选                       | 单选一条结论，或选 `NONE`                       | 逐项判断，可采纳多个方案 |
| 评分项   | 新意、价值、可行性 | 置信度 | 价值、可靠性、可行性 |
| 默认门槛 | `round(0.8 × 席位数)`，十席为 8/10 | 严格多数，十席为 6/10 | `round(0.8 × 席位数)`，十席为 8/10 |
| 结果键   | `approved_candidates`              | `adopted_conclusions`                  | `adopted_solutions` |
| 提示词目录 | `prompts/proposal/`                | `prompts/evaluate/`                    | `prompts/solve/` |

三种模式都允许没有结果：提案可以全部未达门槛，结论可以没有多数支持或多数认为证据不足，方案也可以没有一条值得采纳。

`proposal` 是唯一把新意当作标准的模式：已有的工作在那里是淘汰理由。`evaluate` 的门槛用于判断是否形成多数意见，需要一个具体、可判定的问题，例如“某个做法在某种设置下是否成立”或“某个说法是否有证据支持”。`solve` 回答的是“那我们该怎么做”：已有方法不是淘汰理由，正确复用某个已知做法是合法答案，票判断的是它在 `research_brief.md` 写明的资源、时间与权限下能不能真的做出来。

切换时，可以在 `protocol.json` 中设置 `"mode": "solve"`，也可以运行：

```text
python debate_tools.py setup --mode solve
```

该命令会按模式重新计算默认门槛，保留 `rounds`。模式还会影响 `opencode.json` 中的席位提示词，因此已有配置需要先删除 `opencode.json` 和 `roster.lock.json`，再运行 `setup`。模式和门槛都会计入 `packet_sha256`，冻结资料后再改会导致审核失败。

### 各模式该写什么样的题目

`research_brief.md` 的写法随模式不同：

- **`proposal`**——一个有边界的方向、可用资源，并如实说明可能不存在值得做的新方向。示例：*“单张 24 GB 显卡上的本地大模型推理。哪一处机制层面的改动，能把 decode 延迟降到值得做最小判别实验的程度？”*
- **`evaluate`**——一个有**明确真假**的问题，不是宽泛主题。示例：*“在单张 A100、批大小 32 的设定下，考虑当前草稿模型的额外开销，投机解码是否仍然快于普通解码？”*
- **`solve`**——问题本身、你实际拥有的资源与权限、以及什么算做完。示例：*“我们有三万份扫描的中文合同 PDF，没有 OCR 预算，只有一台 16 GB 显卡的工作站和四周时间。要提取当事人名称、生效日期和违约金条款，并且错误率可审计。该怎么搭？”* 知识库材料放在 `materials/` 下。

## 开始使用

1. 解压到专用目录，例如 `D:\research\multimodel_debate`，用 OpenCode 打开，进入普通 Build 会话。
2. 参考 `research_brief.example.md`，把自己的题目写进 `research_brief.md`。重点是问题边界、硬约束和已知负面结果；文献线索与 `materials/` 下的补充材料可选，见后文"准备研究背景"。
3. 选择讨论模式：找新方向用 `proposal`；讨论具体问题用 `evaluate`；用给定问题和知识库讨论解法用 `solve`。配置时分别加上 `--mode evaluate` 或 `--mode solve`。
4. 给 Build 发送：**“请阅读 SETUP_PROMPT.txt，按里面的步骤完成配置。”** 生成器会读取 `opencode models`，自动匹配能够唯一识别的模型；有多个匹配时，需要确认实际模型 ID。这里要填完整 API ID，不能用展示名代替。
5. 运行 `python debate_tools.py doctor`。它会检查 OpenCode 实际加载的席位、模型 ID、primary 数量、成员检索权限，以及 `websearch` 配置和凭据是否一致。
6. 运行 `START_WINDOWS.cmd`，或执行 `python run_debate.py all`。脚本会依次完成各轮讨论、资料冻结、审核和总结，结果写入 `debate/final.md`。

需要在 TUI 中查看会话或继续追问时，可以使用 `reopen`。正式讨论由脚本调度。

配置阶段不会发起研究请求。正式运行后，每个席位每轮发言都可能多次调用模型和检索工具，因此实际请求数通常远多于“轮数 × 席位数”。

### 用代理代笔

代理可以承担机械性的部分：为新领域重写 `focus`、按你给的信息填 `research_brief.md`、按顺序跑 `setup`、`doctor` 和驱动脚本。**代理不能替席位发言。** 如果代理自己写出十份“席位发言”，这场讨论就退化成单模型自问自答，而 `audit` 查不出来——它查文件结构、版本和计票，不查文字是谁写的。脚本会为每个席位启动真实会话，这正是这套机制的价值所在。

可行的分工：

- **你提供的**：问题本身、硬约束、你已经试过并失败的路。这些不能编——一份靠通用话术撑起来的简报会成为所有席位的事实基础。
- **代理提供的**：格式（照示例逐节填）、换领域时重写的 `focus` 列表、命令顺序。让它先把十条 `focus` 给你看一眼再跑 `setup`：如果十条都写成“寻找新方向”，十个席位会搜到同一批论文，投票也就成了同一种视角的重复计数。
- **包提供的**：席位本身。把 `SETUP_PROMPT.txt` 交给代理，它会先停下来问你题目，而不是自己编一个。

### 联网检索

`websearch` 需要连接搜索 provider，并配置相应凭据，支持 Exa、Tavily、Firecrawl、Parallel 和 TinyFish。缺少凭据时，搜索会失败，CLI 也会返回 `exit 1`，即使席位发言已经输出完毕。

- **没有搜索凭据**：`setup` 默认使用 `--search off`，禁用 `websearch`。席位通过 `webfetch` 访问一手来源：论文可用 arXiv API 与 OpenAlex 检索，全文优先选实际可读的页面；PDF 可尝试 `r.jina.ai` 转文本，但不保证成功。政策、标准、数据库等题目按 `research_brief.md` 指定的来源检索。具体见 `.opencode/skills/source-search/SKILL.md`。
- **已有搜索凭据**：先在 OpenCode 中通过 `/connect` 连接 provider，再用 `python debate_tools.py setup --search on ...` 重新生成配置。

`doctor` 会核对配置和凭据，不一致时检查失败。访问 `openreview.net` 遇到 Cloudflare 人机验证时，改用论文的 arXiv 版本。

## 默认席位

默认的十个席位定义在 `roles.json` 中，其中 `chair: true` 的席位兼任主持。

| 席位  | 默认模型系列 | 主要关注点             |
| --- | ------ | ----------------- |
| a01 | A 系列   | 数学机制与可证伪假设        |
| a02 | A 系列   | 理论、反例与正确性边界       |
| a03 | B 系列   | 系统路径与实际开销     |
| a04 | B 系列   | 组件复用与成立条件 |
| a05 | C 系列   | 主持、独立实验设计         |
| a06 | C 系列   | 最相近工作与新意审查        |
| a07 | D 系列   | 架构与新问题            |
| a08 | D 系列   | 替代解释与方法审查         |
| a09 | E 系列   | 原论文、官方代码与文献证据     |
| a10 | F 系列   | 跨领域启发             |

主持也参与研究和投票，计入十个席位。OpenCode 中对应一个主 Agent 和其余子 Agent。同一系列默认使用相同模型 ID，但各席位有独立的任务、会话和研究视角。表中的分工只决定检索重点，所有席位都可以提出方案或反驳其他观点。

`roles.json` 默认的 `focus` 写成与具体题目无关的检索角度，换题时通常不必改动。只有换到完全不同的领域（例如从推理加速换到生物信息）时才需要重写，见[用代理代笔](#用代理代笔)。

### 主持选什么模型

主持优先看**上下文容量、忠实归并能力和指令遵循**。它需要处理包括自己在内的所有席位原文（默认十份首轮发言），保留证据、分歧和条件，整理成可投票的目录；不得引入任何席位没提过的新主张。不存在通用的“无脑选最强”，应按实际资料包长度和表现选择。

默认配置里 `a05`（主持）与 `a06`（新意审查）属于同一系列，因此同一个模型 ID。这会让"判断什么算新"的偏差被写进两个席位。如果在意这一点，在 `roles.json` 里给 `a05` 单独写 `"model": "..."` 换成另一个系列即可。

子 Agent 的会话不会自动互通。主持会把此前各轮的完整发言整理成统一资料包，供后续互评和投票使用。

## 目录结构

```text
roles.json          席位表：id、family、role、focus，恰好一个 "chair": true
protocol.json       mode（proposal | evaluate | solve）、rounds 和 threshold
model_map.json      系列 -> 实际 provider/model ID，由 setup 生成
model_map.example.json
research_brief.md   席位起步用的研究背景（你自己的，已 gitignore）
research_brief.example.md   它的模板
materials/          可选的本地论文/笔记（除 README 外已 gitignore）
prompts/proposal/   member / chair / start / round1 / deliberate / vote
prompts/evaluate/   evaluate 模式的同六个文件
prompts/solve/      solve 模式的同六个文件
templates/          candidates.example.json、conclusions.example.json、solutions.example.json
debate_tools.py     setup、freeze、audit、doctor
run_debate.py       驱动：每席一个真实会话，跨轮续接
test_tools.py       离线测试，只用合成 ID
.opencode/skills/source-search/SKILL.md   没有 websearch 时席位怎么检索
Dockerfile          可选镜像
docker-compose.yml  可选容器运行
.env.example        容器从这里找到你的配置目录
assets/             封面图及其生成脚本
```

按机器生成、不进入仓库的：`opencode.json`、`roster.lock.json`、`model_map.json`、`research_brief.md` 和 `debate/`。

## 运行要求

- OpenCode V2 CLI，已验证 2.0.30；其他 V2 版本需另行验证，V1 不在支持范围内。配置好席位表所用的模型，默认六个系列映射到六个不同模型 ID。
- Python 3.9+（只用标准库，不需要安装依赖）。

## 它不做什么

- 它不替你产出研究结果，包里没有任何现成答案。
- 它不模拟席位。某个席位失败了会记为失败，不会拿另一个模型顶替。
- 票数不是证据。同系列席位是各自独立的会话，但它们的判断并不统计独立；某个模型 ID 也证明不了背后实际是哪个权重在回答。

## 修改配置

配置主要由以下三个文件控制。修改后，需要删除旧的 `opencode.json` 和 `roster.lock.json`，再运行 `setup`；生成器不会覆盖已有配置。

- `roles.json`：定义席位。每个席位包含 `id`、`family`、`role` 和 `focus`，且恰好一个席位设置 `"chair": true`。ID 从 `a01` 起连续编号。至少需要三个席位、两个模型系列，因为互评时每人要回应另外两个席位。
- `protocol.json`：定义 `mode`、`rounds` 和 `threshold.numerator / denominator`。轮数可设为 2–4，最后一轮用于投票。设为 2 时，首轮结束后归并、冻结，再直接投票；设为 3 时，中间增加一轮互评、合并和查重。省略 `mode` 时使用 `proposal`；省略 `threshold` 时，提案模式与方案模式取席位数的 80%（取整），评估模式取严格多数。门槛的分子和分母需要同时填写，分母必须等于席位数，缺席不会降低门槛。
- `model_map.json`：将 `family` 映射到实际的 `provider/model` ID。可由 `setup` 根据 `opencode models` 生成，也可手动填写后通过 `--mapping` 传入。

如果想让同一系列的两个席位使用不同模型，可以在 `roles.json` 的相应席位中添加 `"model": "provider/model-id"`。这个设置优先于系列映射，ID 必须完整且出现在 `opencode models` 中。覆盖结果会写入 `roster.lock.json`。已知限制：主持所在系列的所有席位都单独指定 model 时，目前生成器会报 KeyError；修复前请保留该系列映射，并让至少一个该系列席位使用映射。

门槛会写入 `packet_manifest.json`，并参与 `packet_sha256` 计算。投票开始后修改门槛会造成摘要不一致，`audit` 将拒绝通过。

## 讨论流程

下面以默认的 `proposal` 模式为例，`evaluate` 与 `solve` 的区别另作说明。

### 1. 独立构思

所有席位（含主持）独立检索，各提出一个主方案。每人至少核查三份一手资料，需要阅读正文，不能只依据摘要。首轮提示词禁止读取其他席位的答案，驱动程序保存各席位原文；默认并行运行不保证主持先完成。

`evaluate` 模式下，每人提交对问题的回答、立场和理由。`solve` 模式下，每人提交一个初步解法：对准问题卡在哪一步，写清可执行的步骤、每一步需要什么、以及最可能失败的地方。

### 2. 互评与修改

轮数不少于三轮时，才有这一阶段。

各席位阅读此前各轮原文，补充检索，并至少回应另外两个席位。可以合并相近提案、保留方案中有新意的部分，也可以撤回方案。合并后的方案需要说明新意，工作量也要可控。

这一阶段不投票。每份记录都需要包含实际使用的查询和最相近工作或证据的 URL，缺少这些记录会被拒绝入档。

`evaluate` 模式下，各席位可以补充成立条件、修改立场或明确放弃原立场。`solve` 模式下，可以合并互补的步骤、把方案拆开或收窄到它真正能解决的那一部分；如果前提在给定资源下满足不了，应当直接说出来。

### 3. 归并与冻结

主持根据已有讨论整理出 1–5 个候选方案，每个方案需写清机制、最相近工作、最小实验和停止条件。所有首轮方案都要注明去向：保留、合并，或说明排除原因。归并时不能加入此前没有讨论过的新方案。

`evaluate` 模式下，主持整理出 1–5 条互斥、可判定的结论，并列出各自最强的反证，以及什么观测会推翻它。`solve` 模式下，整理出 1–5 条可执行的方案，每条写清它解决哪一部分、为什么成立、依据是什么、需要哪些前提、最可能失败的一步，以及它明确不解决什么。

随后生成包含此前各轮完整原文的统一资料包，并冻结版本。

### 4. 投票

所有席位阅读同一份资料包，在投票前再次检索，并至少回应另外两个席位。默认并行运行时主持也可与其他席位同时投票，提示词禁止读取他人的票。

`proposal` 对所有候选逐项判断，可以推荐多个；`evaluate` 只能选择一条结论或 `NONE`；`solve` 对每条方案逐项判断，可以同时采纳多条——适用于不同条件的两个方案并不冲突。投票期间，各席位看不到其他人的票，也不能为了达到门槛反复改票。

### 5. 汇总

票数以全部席位为固定分母。默认情况下，提案获得 8/10 推荐后，列为优先进行最小实验的方向；评估结论获得 6/10 支持后，列为多数认可的结论；方案获得 8/10 采纳后，列为准备动手做的做法。总结中同时保留评分、理由和异议。没有候选达到门槛时，如实记录结果。完成设定轮数后停止，不自动追加讨论。

这些票数用于辅助判断。方案获得推荐，还需要实验验证新意和效果；结论获得多数支持，也只代表各席位基于当前证据的判断；多条方案同时被采纳时，报告要写清各自适用的条件与代价，不能合成一条谁都没投过的“综合方案”。模型之间的判断可能相关，票数不能作为统计证明，有实质证据的严重异议仍需单独处理。

在 `evaluate` 模式下，如果选票分散在三条以上互斥结论中，且没有一条达到门槛，应报告未形成多数结论，不能把得票最高直接写成多数认可。

## 准备研究背景

`research_brief.md` 是你唯一必须写的文件。`research_brief.example.md` 是格式化过的完整骨架，整份复制过去逐节替换即可；三种模式共用同一份骨架，只有"本场要解决的问题"和"交付什么"随模式变化，示例文件开头有一张对照表。

必须写清的（缺了讨论会退化成综述）：

- 要解决的问题、适用范围和硬约束（硬件、预算、时间、权限）；
- 已知的负面结论——哪条路已经被占满、哪条实测没跑通；
- 可以复用的实测方法，以及这些结果**不能**支持什么判断。

可选的两节，留空是正常用法：

- 想预先指定一批文献线索时，填一张题名 / 编号 / 正文可读路径的表。编号带上版本号（如 `2404.16710v4`），裸编号常常查不到。席位本来就会自己检索，清单只是省掉重复搜公认基线的时间。
- 有席位自己拿不到的材料（付费论文集、中文文献、内部笔记、日志）时，放进 `materials/` 并在简报里列一张"文件名 / 来源 / 读到哪一层 / 你要它支撑什么"的表。

**知网（CNKI）目前无法直接检索**：此前访问停在安全验证，全文还可能需要登录与机构订阅。请自行下载需要的材料，转换为可读 PDF 或文本放进 `materials/`；当前流程不支持直接读取 `.caj`。扫描版 PDF 依赖图像/OCR 能力，建议附文字稿，不保证一定可读。

包内提供 `research_brief.example.md` 作为格式示例。个人的 `research_brief.md` 和 `materials/` 中的材料已 gitignore，不随仓库分发。

如果背景沿用了上一场讨论的负面结果，写清它排除了哪些方向、留下了哪些可复用的方法即可。例如，是否经过 validation 筛选和独立 test 复测，执行了哪些层，一致率能否代表质量。本场讨论可以从新的问题开始。

当某个候选的新意取决于具体公式、router、KV 实现或实验设定时，需要在推进前补查论文方法段或代码。只拿到背景摘要时，记录中也应注明依据是摘要。可访问的材料取决于实际接入的检索工具和账号权限。

## 命令行配置

本机需要安装 OpenCode CLI 和 Python 3.9+，Python 无需额外依赖。模型凭据沿用 OpenCode 的现有配置。

```powershell
opencode models
python debate_tools.py models
python debate_tools.py setup                              # 默认 proposal 模式
python debate_tools.py setup --mode evaluate              # 评估具体问题
python debate_tools.py setup --mode solve                 # 讨论可执行的解法
```

如果 `python` 不可用，Windows 可尝试 `py -3`，Linux 可使用 `python3`。有多个同名供应商时，交互配置会列出完整 ID 供选择。

由 OpenCode Build 自动执行时，使用非交互模式：

```text
python debate_tools.py setup --non-interactive
```

如果无法唯一识别模型系列，复制 `model_map.example.json` 为 `model_map.json`，填入 `opencode models` 中的完整 ID。默认配置需要填写六个系列，然后执行：

```text
python debate_tools.py setup --mapping model_map.json --non-interactive
```

Windows 也可以先导出模型列表：

```powershell
opencode models | Set-Content -Encoding utf8 models.txt
python debate_tools.py setup --inventory models.txt --mapping model_map.json --non-interactive
```

无法确定映射时，脚本会要求补全配置，不会自动换用默认模型。已有的 `opencode.json`、`opencode.jsonc` 和 `roster.lock.json` 也不会被覆盖，建议在专用目录中使用。

如果桌面程序附带的 CLI 不在 PATH 中，可以给 `models` 或 `setup` 添加 `--opencode "完整CLI路径"`，或者先用该 CLI 导出模型列表，再通过 `--inventory` 读取。

### 运行与续接

Windows 可直接运行：

```powershell
.\START_WINDOWS.cmd
```

启动脚本会先执行 `doctor`，再运行 `python run_debate.py all`。也可以分步执行：

```powershell
python run_debate.py round1                # 第一轮
python run_debate.py deliberate --round 2  # 第二轮互评，rounds ≥ 3 时使用
python run_debate.py merge                 # 主持归并候选并冻结资料
python run_debate.py vote                  # 投票轮
python run_debate.py audit                 # 统计与完整性检查
python run_debate.py final                 # 生成 final.md
```

只有 `all`、`round1`、`deliberate`、`vote` 支持 `--resume`，按文件是否存在跳过席位，并不保证该文件合格，也不能绕过冻结版本检查。`round1`、`deliberate` 和 `vote` 还支持 `--seats a01,a03`，便于选少量席位检查格式和检索。

### 席位会话与职责边界

- 驱动将 CLI 实际返回的 `sessionID` 保存到 `debate/sessions/aXX.json`，后续调用自动传 `--session` 续接该席位，并显式指定其配置模型。会话续接不依赖 `--resume`；后者只控制跳过已有发言文件。不同席位使用不同会话，同轮并发不会覆盖彼此的会话记录。
- 主持的独立发言、归并、投票和总结也续接其自己的会话。`all --resume` 遇到已有冻结资料时，校验其内容后跳过归并，避免把已投票或看过结果的主持带回归并阶段。会话进入后续阶段后，不能重跑更早的研究轮次；元数据修复仍由原席位处理。
- API 失败或超时的部分输出只要含真实 sessionID，也会保存供重试。强制终止整个 Python 进程可能来不及保存；旧版没有会话记录的场次不能自动冒充持续会话。缺记录时恢复对应的 `debate/sessions/`，否则另开新场次，不使用“最近会话”猜测归属。
- 会话文件只保存绑定，不包含 OpenCode 会话数据库。换机器或删除数据库后，仅复制这些 JSON 不会恢复历史；CLI 的 `--session` 可能重新创建不存在的 ID，故须同时保留 OpenCode 状态。上下文压缩也可能摘要化旧工具结果，重要证据仍须写入公开发言。
- 配置、背景或目录改变时，原会话绑定不再适用。换题先归档整个 `debate/`。同一场次只运行一个驱动进程，`--parallel` 用于该进程内的席位并发。
- 外层操作代理负责 setup、doctor、启动和故障处理；正式主持只完成当前调用指定的研究、归并、投票或总结。Python 负责保存成员的“Markdown 正文＋JSON 元数据”、冻结和计票；不要求改为独立元数据文件。

升级包后，既有 `opencode.json` 内嵌的是旧提示词。新场次需先备份并移出旧生成配置和旧 `debate/`，再按原映射执行 setup 与 doctor，让新主持提示词生效。

同一轮内可用 `--parallel N` 控制并发数，默认是 4，设为 1 时串行运行。轮次之间按顺序执行；同轮主持可与其他席位并行。禁止读取同轮记录是提示词约束，不是文件系统隔离。两轮模式跳过 deliberate，四轮模式需在 merge 前依次执行 deliberate --round 2 和 deliberate --round 3。

模型名称和完整 ID 以供应商及本机的 `opencode models` 列表为准。模型的自述不能用于确认后端权重身份。某个席位不具备所需的检索或工具能力时，应记录为未完成，不能用其他模型代替。

## Docker（可选）

Docker 使用同一套代码和 `debate/` 目录，可以省去本机安装 Python 和 OpenCode CLI 的步骤。

使用代理时，推荐在宿主机的普通 OpenCode 会话中让代理阅读 `SETUP_PROMPT.txt`，并明确说“使用 Docker”。代理负责整理材料、确认模型映射和执行 Docker 命令；各辩论席位的 OpenCode 会话在容器内运行。手动使用时执行相同命令即可。材料放在宿主机项目的 `materials/`，容器通过 `/work` 访问，结果也直接写回项目目录。

```bash
cp .env.example .env          # 将 OPENCODE_CONFIG 改为绝对路径
docker compose build
docker compose run --rm setup models # 查看容器可用的模型 ID
# 按 model_map.example.json 填好 model_map.json 后配置；可加 --mode evaluate 或 --mode solve
docker compose run --rm setup setup --mapping model_map.json --non-interactive
docker compose run --rm doctor
docker compose up harness     # 完整运行，日志输出到终端
```

`setup` 和 `doctor` 属于按需工具服务；普通 `docker compose up` 也只启动 `harness`。首次运行需使用没有旧 `opencode.json` / `roster.lock.json` 的专用目录，旧场次请先备份。

首次构建需要下载 OpenCode 平台二进制包，网络较慢时可能超过十分钟；后续构建会复用缓存。若使用 Docker Desktop 且宿主机有 HTTP 代理，可临时传入构建参数（下面以端口 10090 为例，请替换成实际端口）：

```text
docker compose --progress plain build --build-arg HTTP_PROXY=http://host.docker.internal:10090 --build-arg HTTPS_PROXY=http://host.docker.internal:10090
```

代理需允许来自 Docker 的连接。容器里的 `127.0.0.1` 指容器自身，不是宿主机；上述参数只用于构建，不会给运行中的模型请求设置代理。镜像拉取的代理由 Docker Desktop 自身配置。

`.env` 中的 `OPENCODE_CONFIG` 应指向已有的 OpenCode 配置和供应商凭据目录。源目录只读挂载在 `/mnt/opencode-config`，入口脚本将配置复制到容器自己的运行目录，跳过宿主机的 `service.json`，以免继承指向宿主机 localhost 的代理或服务设置。这份运行时副本不会写回宿主机，也不会进入构建镜像；使用 `run --rm` 时随容器删除。`.dockerignore` 排除了私人材料、讨论记录和生成配置。

容器运行时如需代理，在 `.env` 中设置 `DEBATE_HTTP_PROXY` 和 `DEBATE_HTTPS_PROXY`（Docker Desktop 例如 `http://host.docker.internal:10090`）；默认留空直连。保留 `DEBATE_NO_PROXY=localhost,127.0.0.1,::1`，避免 OpenCode CLI 与容器内后台服务之间的连接绕进代理。仅修改构建参数不会设置这些运行时代理。

配置时注意以下几点：

- **使用绝对路径。** Compose 不展开 `~`。Linux/macOS 例如 `/home/you/.config/opencode`，Windows 例如 `C:/Users/you/.config/opencode`。
- **会话状态保存在具名卷 `opencode-state` 中。** 该卷保存 `~/.local/share` 和 `~/.local/state`。OpenCode 的 SQLite 数据库使用 WAL 模式，在 Windows/macOS 上直接绑定宿主机状态目录可能出现 `disk I/O error`，随后报 `Background service failed to start`。因此默认只对配置目录和工作目录使用绑定挂载。执行 `docker compose down -v` 会删除状态卷，包括其中的会话数据库。
- **Debian 镜像源可配置。** 在 `.env` 中填写 `DEBIAN_MIRROR`，可替换 `apt-get` 使用的源，留空时使用 `deb.debian.org`。构建参数需保留在 `docker-compose.yml` 中；只在 `docker compose build` 命令行临时传入的参数不会带到下一次 `docker compose run`。
- **默认 uid/gid 为 1000。** 如果宿主机使用其他 uid，可加 `--user "$(id -u):$(id -g)"`。入口脚本会创建所需目录，挂载路径需要具备相应访问权限。

当前只实测了配置文件内凭据的导入。V2 登录账户存于 SQLite，容器使用独立数据库；宿主机环境变量和被跳过的 `service.json` 中的密钥不会自动继承。这些方式需另行配置容器登录或环境变量转发，仅删除配置目录挂载并不足够。

## 输出与审核

运行结果保存在 `debate/`：

| 文件                                          | 内容                                    |
| ------------------------------------------- | ------------------------------------- |
| `run_log.md`                                | 席位、配置模型、执行阶段、失败和续接记录                  |
| `logs/`                                     | 各席位调用的原始 JSON 事件流、stderr 和工具错误        |
| `round1/a01.md` … `a10.md`                  | 各席位的首轮完整发言                            |
| `round2/`、`round3/`（存在时）                    | 后续互评或投票轮的完整原文                         |
| `candidates.json`（评估模式为 `conclusions.json`） | 冻结的候选定义，以及各首轮方案的去向                    |
| `vote_packet.md`、`packet_manifest.json`     | 投票使用的统一资料包和版本信息                       |
| `votes.csv`、`audit.json`                    | 票数统计、完整性和版本检查结果                       |
| `final.md`                                  | 主持总结：候选、证据、异议和最小实验；评估模式下包含各结论的票数和最强反证 |

没有候选达到门槛时，`final.md` 会说明这一结果。

本地冻结和审核命令：

```text
python debate_tools.py freeze
python debate_tools.py audit
```

缺票、对同一候选重复投票、资料版本变化、配置模型与席位表不一致等问题，都会阻止审核通过。审核器检查的是记录和票数；引用是否准确，需要结合原文判断。核对模型调用时，可查看 `debate/logs/` 中的 `sessionID`、`model`、工具调用和结果，而不能仅凭角色自述确认后端。

阅读结果时，建议连同推荐理由、与最相近论文的差异、尚未解决的问题一起看。讨论过程不会启动 GPU 训练，选定方向后再安排最小实验。

## 测试

运行离线测试：

```text
python -B -m unittest test_tools
```

65 个测试全部离线、全部使用合成数据：假模型 ID、假发言、`example.invalid` 链接。检查的内容包括：缺票不会缩小分母、改过的资料包或配置会被拒绝、冻结后改门槛会被拒绝、两轮和三轮都能走完、缺中间轮或没有记录检索会阻止冻结、7 席位 5/7 的情况能走完，以及 `partial` 会被记录而不是被默默接受。其中 16 个 `evaluate` 用例锁定第二种模式：6/10 通过、5/10 不通过、一张票选两条结论会被拒绝、置信度下限会生效、拿错目录文件时报错会指出正确文件名、冻结后改模式会被拒绝、切模式会重算默认门槛。13 个 `solve` 用例锁定第三种：8/10 采纳、7/10 不采纳、一张票可以同时采纳多个方案、可靠性下限会生效、缺 `soundness_score` 的提案式选票会被拒绝、`preferred_solution` 必须是被采纳的方案之一、资料包里渲染的是“方案目录”而不是提案措辞、solve 与 evaluate 互切时 8/10 ↔ 6/10 会重算、`audit` 打印的是该模式自己的键、`repair` 提示词只问当前轮确实存在的字段。另有 4 个 `PromptRenderTests` 守住席位直接读的那几个文件：`start.md`、`round1.md`、`deliberate.md`、`vote.md` 里不能残留 `{{TOKEN}}`，有一个时 `setup` 会拒绝写配置，`vote.md` 里写死的评分下限必须和 `MODES["solve"]["score_floor"]` 一致。

这些测试不会告诉你某篇论文是否存在。

## 验证记录与参考文档

本地验证记录见 `VALIDATION.md`。本地测试不调用模型 API，跨供应商调用和网页工具能力需要在实际 OpenCode 环境中检查。

OpenCode V2 官方参考文档（以实际使用版本为准）：

- [Agents](https://opencode.ai/v2/docs/agents/)：自定义模型与 Agent
- [Config](https://opencode.ai/v2/docs/config/)：项目与全局配置
- [CLI](https://opencode.ai/v2/docs/cli/)：命令行使用
- [Tools](https://opencode.ai/v2/docs/tools/)：工具说明
- [Commands](https://opencode.ai/v2/docs/commands/)：自定义命令
