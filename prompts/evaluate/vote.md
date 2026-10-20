这是投票轮，也是你的最后一次正式发言。请读 research_brief.md 和 debate/vote_packet.md，确认里面的 packet_sha256。资料包包含本轮之前各轮的全部原文（含你自己的）和冻结后的结论定义。

## 投票前的检索（必做）

投票前必须再做一次针对性检索，不能只凭前几轮的印象表态。至少两条查询，写进正文和元数据。要反驳或支持某条结论时，说出你搜了什么、范围到哪里、查到的最相近证据差在哪；不要用"据我所知"代替检索。

## 互评

针对明确主张实质回应至少两个其他席位，写明"支持 / 反对 / 建议修改"、论据与能推翻自己判断的证据。你可以修改原先立场，也可以认同别人的结论，或认为所有结论都不成立、证据仍然不足。对影响判断的关键文献，自己核对结果段，不要只转述别人的结论。

## 投票

投票是**单选**：在目录中的结论 C01、C02…… 里最多认同一条；都不认同就全部投不认同（即 NONE）。不能只给自己的立场投票，不能读取别人的投票，不能更换结论定义。若建议实质改动，只能把它写成下一版本建议；当前票仍然针对冻结版本。中间轮已经合并过的立场以资料包里的结论定义为准，不要自行再合并。

对目录中**每一条**结论都要单独写一票，用 `endorse` 表示是否认同；但 `endorse`=true 的条目最多一条。两条互斥结论同时为 true 的票会被 `audit` 判为无效——"多数认可的结论"在同时认同两条时没有意义。

正文之后附一个合法 JSON 代码块。以下只演示两条结论，实际 votes 必须覆盖资料包中全部结论。agent_id、packet_sha256、其他席位 ID 和结论 ID 都替换为真实值（条目键名沿用 `candidate_id`）：

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
      "candidate_id": "C01",
      "endorse": true,
      "confidence": 4,
      "unresolved_fatal_objection": false,
      "reason": "为什么这条结论与你的判断一致；证据强度到哪里",
      "evidence_urls": ["实际核查过的支撑或反驳证据URL"]
    },
    {
      "candidate_id": "C02",
      "endorse": false,
      "confidence": 2,
      "unresolved_fatal_objection": false,
      "reason": "为什么你不认同这条；它断定的范围在哪个观测上不成立",
      "evidence_urls": ["实际核查过的证据URL"]
    }
  ],
  "preferred_conclusion": "C01"
}
```

stance 只能为 support、oppose 或 modify，不必各选一种。`preferred_conclusion` 为你想选的那条结论，或 `NONE`；它必须与你 `endorse`=true 的条目一致（没有认同任何一条时写 NONE）。

`endorse`=true 表示"我自己的判断与这条结论一致，且我能给出支撑它的证据"，要求：`confidence` 至少 4 分、`evidence_urls` 里有你实际核查过的 URL，且你没有尚未解决的致命异议。三者缺一，这一票会被 `audit` 判为无效。置信度低于 4 分但仍大致认同方向时，请投 `endorse`=false 并在正文说明。

`unresolved_fatal_objection` 只用于你有明确理由或证据认为这条结论被已发表的结果直接推翻、或其推理链有硬错误的情况；普通保留意见写在正文与 reason 中，不必都标成致命。若你给自己认同的那条标了致命异议，这一票自身就是矛盾的，会被拒绝。
