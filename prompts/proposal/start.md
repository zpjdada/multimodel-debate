现在开始多席位、多轮的科研讨论。具体轮数看 protocol.json 的 `rounds`（本包默认 3 轮），下面用 R 表示总轮数。

先读 research_brief.md、roster.lock.json、protocol.json、prompts/proposal/round1.md、prompts/proposal/deliberate.md、prompts/proposal/vote.md。本次主题以 research_brief.md 为准：它界定问题、范围、硬约束与验收方式；相邻问题是否在范围内，也由它界定。目标是寻找值得优先投入一次最小判别实验的候选，不预设一定有新方向；"这条线只剩边角"如果能被论证成立，是合法结论。

调度方式：全部席位由 `run_debate.py` 逐席位启动真实 `opencode run --agent <名>` 会话完成，彼此不共享上下文，只通过 `debate/` 下的文件通信。OpenCode 2.0.30 的 subagent 工具本身损坏（`Subagent session not found`），不要试图用它拉起其他席位，也不要模拟多个角色。

正确做法是执行：

```
python debate_tools.py doctor
python run_debate.py all
```

`run_debate.py all` 会依次完成：主持席首轮先封存 → 其余席位首轮 → 中间轮（第 2 轮到第 R−1 轮，逐轮互评、合并与重新检索；R 为 2 时没有这一步）→ 你归并候选并 freeze → 投票轮（第 R 轮）主持先封存 → 其余席位投票 → audit → 你写 final.md。中间你可以查看 `debate/logs/` 核对每次真实调用。

每一轮都要求真实检索：中间轮和投票轮都必须记录本轮实际用过的查询，只凭记忆评审会被 `audit` 拒绝。你自己的投票必须先在投票轮封存，不得根据之后的票修改。每个候选以席位数（见 roster.lock.json）为固定分母，门槛见 protocol.json 的 threshold（默认约八成，十席时即 8/10），达到才算值得先做实验的候选，允许没有共识。

结果保存到 debate/：round1/、中间各轮目录（存在时）、candidates.json、vote_packet.md、投票轮目录、votes.csv、audit.json、run_log.md、final.md。请完成资料冻结与票数检查。已有完成记录时先辨明阶段并加 `--resume` 续接，不覆盖有效原始发言、不重复发起整场讨论。

配置或网络工具确实缺失时，报告具体缺口与修复方式；其余情况下按协议执行，不要只回复讨论计划。
