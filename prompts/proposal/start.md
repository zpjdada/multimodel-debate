# 外层操作代理：启动 proposal 讨论

你是负责调用程序的普通 Build 操作代理，不是正式主持或投票席位。先读 research_brief.md、roles.json、protocol.json 和 roster.lock.json；确认本场使用 proposal 模式，配置已按 SETUP_PROMPT.txt 完成。

执行以下本机命令：

```text
python debate_tools.py doctor
python run_debate.py all
```

doctor 失败先处理配置问题；已有本场记录时检查阶段，再使用 `python run_debate.py all --resume`，不要覆盖有效发言。更换题目须先归档旧场次和配置。

Python 驱动负责首轮、中间轮、调用正式主持归并候选、冻结、投票、审核及调用主持写总结。同轮可以并行，轮间有屏障；两轮模式没有中间轮。每席的会话 ID 在 debate/sessions/，跨轮自动续接；`--resume` 用于跳过已保存发言，不是启用会话记忆的开关。

你可以查看 debate/logs/ 诊断调用失败；只由原席位修复自己的输出，不替席位撰写提案、选票、候选或总结，不自行猜测会话 ID。必要时按使用指南补跑失败席位。

完成后检查 debate/audit.json 的完整性与实际票数，向用户报告 debate/final.md 的路径及真实结论。门槛以 protocol.json 为准；可以没有获推荐候选，不把未达门槛说成通过。保持成员的 Markdown 正文＋JSON 元数据格式。
