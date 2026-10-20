这是投票轮，也是你的最后一次正式发言。请读 research_brief.md 和 debate/vote_packet.md，确认里面的 packet_sha256。资料包包含本轮之前各轮的全部原文（含你自己的）和冻结后的方案定义。

## 投票前的检索（必做）

投票前必须再做一次针对性检索，不能只凭前几轮的印象表态。至少两条查询，写进正文和元数据。这一轮查的重点是**可行性**，不是新意：

- 你准备支持的那条方案，它依赖的关键前提有没有实际依据？
- 它在 research_brief.md 写明的资源、时间与权限下，第一步能不能真的开始做？
- 有没有已知的失效条件，正好落在这场问题的设定里？

不要用“据我所知”代替检索。

## 互评

针对明确主张实质回应至少两个其他席位，写明“支持/反对/建议修改”、论据与能推翻自己判断的证据。你可以改变原先立场，也可以支持别人的方案，或认为所有方案现在都不该采纳。对影响可行性判断的关键资料，自己核对方法段或文档，不要只转述别人的结论。

## 投票

对目录中的每条方案 S01、S02…… 各投一票。不能只给自己的方案投票，不能读取别人的投票，不能更换方案定义。若建议实质改动，只能把它写成下一版本建议；当前票仍然针对冻结版本。中间轮已经合并过的做法以资料包里的方案定义为准，不要自行再合并。

这里不是单选题：一个问题可以同时有两条各自成立、适用于不同条件的方案，你可以同时支持多条。但如果两条在同样条件下做同一件事，就不要都给 true——那等于没做取舍，报告里必须写清理由。

正文之后附一个合法 JSON 代码块。以下只演示一条方案，实际 votes 必须覆盖资料包中全部方案。agent_id、packet_sha256、其他席位 ID 和方案 ID 都替换为真实值（条目键名沿用 `candidate_id`）：

```json
{
  "agent_id": "你的席位ID",
  "round": 投票轮轮次,
  "packet_sha256": "资料包中的完整SHA256",
  "searched_queries": ["投票前实际用过的查询一", "投票前实际用过的查询二"],
  "responses": [
    {"to_agent": "其他席位一", "stance": "support", "claim": "针对哪条主张、为什么支持，附正文证据"},
    {"to_agent": "其他席位二", "stance": "oppose", "claim": "针对哪条主张、为什么反对，附正文证据"}
  ],
  "votes": [
    {
      "candidate_id": "S01",
      "adopt": true,
      "value_score": 4,
      "soundness_score": 4,
      "feasibility_score": 4,
      "unresolved_fatal_objection": false,
      "reason": "这条方案解决了哪一部分问题、凭什么认为它做得到；附你核查过的依据",
      "evidence_urls": ["实际核查过的支撑或反驳证据URL"]
    },
    {
      "candidate_id": "S02",
      "adopt": false,
      "value_score": 3,
      "soundness_score": 4,
      "feasibility_score": 3,
      "unresolved_fatal_objection": false,
      "reason": "为什么现在不该采纳；是前提不成立、覆盖不到卡点、还是代价过大",
      "evidence_urls": ["实际核查过的证据URL"]
    }
  ],
  "preferred_solution": "S01"
}
```

三个分数各 1–5 分，含义如下（都要填，采纳与否都要填）：

- `value_score`：它真的解决了 research_brief.md 指出的那个卡点，还是只缓解表面症状。
- `soundness_score`：机制与证据站得住，没有明显错误或未经检验的跳跃。
- `feasibility_score`：在 research_brief.md 写明的资源、时间与权限下，第一步真的能开始做。

`adopt`=true 表示“这个方案值得动手做，并且我现在就愿意按它开始”，要求：value_score 至少 4 分、soundness_score 至少 4 分、feasibility_score 至少 3 分，`evidence_urls` 里有你实际核查过的 URL，且你没有尚未解决的致命异议。缺一不可，这一票会被 `audit` 判为无效。分数低于下限但仍认为方向值得讨论时，请投 `adopt`=false 并在正文说明。

stance 只能为 support、oppose 或 modify，不必各选一种。`preferred_solution` 为你最想采纳的那条方案，或 `NONE`；它必须与你 `adopt`=true 的条目之一一致（没有采纳任何一条时写 NONE）。

`unresolved_fatal_objection` 只用于你有明确理由或证据认为这条方案根本不成立的情况：机制有硬错误、关键前提在给定条件下无法满足、或它解决的并不是这个问题。普通保留意见与代价权衡写在正文与 reason 中，不必都标成致命。若你给自己支持的那条标了致命异议，这一票自身就是矛盾的，会被拒绝。
