# Agent 赛博辩论会

[English](README.md) · [详细使用指南](USAGE_zh.md)

![多个机器人围桌检索、思考、发言和投票](assets/cover-titled.png)

这是一个基于 OpenCode 的轻量 **harness（任务编排与运行框架）**：让多个模型席位独立检索、多轮互评，主持归并后，各席位对同一份冻结资料投票。每个席位由真实的 OpenCode 会话运行，过程与结果保存在本地。

包内自编了一个检索 skill：[source-search](.opencode/skills/source-search/SKILL.md)，指导席位在没有 `websearch` 时通过可用工具查找论文、官方文档、标准及数据来源，并记录正文读取情况。轮次调度、冻结和计票由 Python 脚本负责，三种模式另有各自的提示词。

单个 Agent 可能遗漏资料、忽略反例，或过早认定某个方向。这个 harness 尝试让不同侧重点的 Agent 分工检索、交叉审查，把更多依据与分歧带到同一张讨论桌上。你也可以按预算组合不同能力和成本的模型。

**让 AI 不只给答案，也给彼此挑挑毛病。**

**项目状态：早期实验框架。** 这是作者个人在 AI 协助下制作的小 harness，用来探索多模型讨论流程；功能和已验证场景仍有限，现有测试不代表全面验证，也未完成研究级系统评估。欢迎试用和反馈，后续可能继续修复、调整和更新。

推荐直接在本机运行：手动执行命令，或让 OpenCode 代理协助配置和启动；两种方式使用同一套程序。另提供可选 Docker 环境。

## 三种模式

| 模式         | 用来做什么    | 示例议题                                  |
| ---------- | -------- | ------------------------------------- |
| `proposal` | 寻找新方向    | 单张 24 GB 显卡上，还有哪些值得验证的推理提速机制？         |
| `evaluate` | 评估一个具体判断 | 在指定模型、硬件、批大小和测试集上，投机解码是否比普通解码更快？ |
| `solve`    | 讨论可执行方案 | 一台 16 GB 显卡、四周时间，如何搭建支持流式输出与请求排队的本地推理服务？ |

默认十席、六个模型系列、三轮。席位、模型、轮数（2–4）和门槛均可配置。默认`proposal`与`solve`需 8/10 支持，`evaluate`需 6/10；分母固定为全部席位。允许没有方向值得推进、没有多数结论或没有方案通过。**多数票不是事实证明。**

## 本机准备

- 安装 OpenCode V2 CLI，并配置好打算使用的模型；已验证版本为 **2.0.30**，其他 V2 版本需另行验证，V1 不在支持范围内。
- 安装 Python **3.9+**，只用标准库，无需额外 Python 包。
- 下载到专用目录，在该目录打开终端；确认 `python --version` 和 `opencode models` 可用。多版本 Python 环境请使用正确的解释器路径。

把 `research_brief.example.md` 复制为 `research_brief.md`，写明：**问题、资源约束、已知失败或否定结果**，没有的如实写“无”。

`materials/` 可留空，也可预先放入论文、官方文档、笔记或日志。建议在简报中列出文件名和用途，来源与阅读层级能补充则更好，不要求填满表格。请尽量提供可读取的正文或文本版，扫描件建议附文字稿。席位仍需自行检索，并如实记录自己读到的内容。**CNKI 目前无法直接检索**，需要时请自行下载并转换为可读的 PDF 或文本。

## 方式一：手动启动

**希望通过 GUI 配置？** Windows 可直接双击 `START_CONSOLE.cmd`，自动打开本机网页。在页面选择 CLI 中的模型、席位数、主持、模式和轮次，填写问题、背景与约束，添加材料，点击“启动辩论”；完成后在同一页面查看结果。需要已安装 Python 3.9+ 和可用的 OpenCode CLI，无需 Node.js、域名或托管服务。详见[本机控制台使用说明](CONSOLE.md)。下方是纯命令行方式。

1. 运行 `opencode models` 查看真实模型 ID。
2. 复制 `model_map.example.json` 为 `model_map.json`，把占位符换成自己的完整 `provider/model` ID。默认六个系列各对应一个不同 ID；想减少模型或席位时，先按[配置说明](USAGE_zh.md#修改配置)修改 `roles.json` 和门槛。
3. 配置、检查、启动：

```text
python debate_tools.py setup --mapping model_map.json --mode proposal --non-interactive
python debate_tools.py doctor
python run_debate.py all
```

按任务将 `proposal` 换成 `evaluate` 或 `solve`。`doctor` 通过后再启动；它检查配置和加载状态，不验证真实 API 请求。配置完成后，Windows 也可运行 `START_WINDOWS.cmd`，它会先检查再启动。

`all` 会完成检索、互评、归并、冻结、投票、审核和总结，不需要提前手动 `freeze`。已有配置不会被覆盖；换题请先备份旧场次，使用干净的专用目录。

## 方式二：让 OpenCode 代理启动

在本机 OpenCode 中打开项目，进入普通 Build 会话，发送：

> 请阅读 SETUP_PROMPT.txt，使用本机方式配置这个项目，不用 Docker。根据我提供的议题和 materials/ 整理 research_brief.md；信息不足时先问我。向我确认模式、席位和模型映射，完成 setup 与 doctor 后报告结果，等我确认再启动。

检查配置结果后，再发送：

> 确认，请执行 python run_debate.py all，完成讨论后告诉我结果文件在哪里。

操作代理负责配置和调用程序，**不能代替任何席位编写发言或选票**。正式席位由驱动程序启动真实模型会话。运行会产生模型调用费用，实际请求数通常多于“席位数 × 轮数”。

## 看结果

- `debate/final.md`：最终总结。
- `debate/round*/`：各席位原文。
- `debate/votes.csv`、`debate/audit.json`：选票和审核结果。
- `debate/logs/`：调用日志。

审核检查结构、资料版本和计票，不证明引用或结论真实。个人简报、材料及讨论记录已被 Git 忽略，不随开源包分发。

## 更多

- [详细指南](USAGE_zh.md)：席位配置、检索、分步运行与续接。
- [Docker（可选）](USAGE_zh.md#docker可选)：用于容器部署，本机两种启动方式都不依赖它。宿主机登录状态和环境变量不会自动迁入容器。
- 离线测试：`python -B -m unittest test_tools`；[验证记录](VALIDATION.md)。
- [MIT 许可证](LICENSE)。
