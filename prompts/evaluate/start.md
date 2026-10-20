现在开始多席位、多轮的科研讨论。具体轮数看 protocol.json 的 `rounds`（本包默认 3 轮），下面用 R 表示总轮数。

先读 research_brief.md、roster.lock.json、protocol.json、prompts/evaluate/round1.md、prompts/evaluate/deliberate.md、prompts/evaluate/vote.md。本次要回答的问题以 research_brief.md 为准：那里的"问题"就是全场要表态的对象，判断标准、适用范围和讨论边界也由它界定。目标不是提出新方案，而是让各席位基于检索到的证据各自回答这个问题，再看有多少席位认同同一条结论。**不预设一定有结论**：多数席位都停在"证据不足"、或票数分散在几条互斥结论上，都是合法结果，不要为了凑出结论而软化证据。

调度方式：全部席位由 `run_debate.py` 逐席位启动真实 `opencode run --agent <名>` 会话完成，彼此不共享上下文，只通过 `debate/` 下的文件通信。OpenCode 2.0.30 的 subagent 工具本身损坏（`Subagent session not found`），不要试图用它拉起其他席位，也不要模拟多个角色。

正确做法是执行：

```
python debate_tools.py doctor
python run_debate.py all
```

`run_debate.py all` 会依次完成：主持席首轮先封存 → 其余席位首轮各自给出立场 → 中间轮（第 2 轮到第 R−1 轮，逐轮互评、澄清分歧与重新检索；R 为 2 时没有这一步）→ 你归并结论并 freeze → 投票轮（第 R 轮）主持先封存 → 其余席位投票 → audit → 你写 final.md。中间你可以查看 `debate/logs/` 核对每次真实调用。

每一轮都要求真实检索：中间轮和投票轮都必须记录本轮实际用过的查询，只凭记忆评审会被 `audit` 拒绝。你自己的投票必须先在投票轮封存，不得根据之后的票修改。投票是单选：每个席位最多认同一条结论，以席位数（见 roster.lock.json）为固定分母，门槛见 protocol.json 的 threshold（evaluate 默认严格多数，十席时即 6/10），达到才算"多数席位认可该结论"。可以没有结论。

结果保存到 debate/：round1/、中间各轮目录（存在时）、conclusions.json、vote_packet.md、投票轮目录、votes.csv、audit.json、run_log.md、final.md。请完成资料冻结与票数检查。已有完成记录时先辨明阶段并加 `--resume` 续接，不覆盖有效原始发言、不重复发起整场讨论。

配置或网络工具确实缺失时，报告具体缺口与修复方式；其余情况下按协议执行，不要只回复讨论计划。
