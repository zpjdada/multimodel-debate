这是投票轮，也是你的最后一次正式发言。请读 research_brief.md 和 debate/vote_packet.md，确认里面的 packet_sha256。资料包包含本轮之前各轮的全部原文（含你自己的）和冻结后的候选定义。

## 投票前的检索（必做）

投票前必须再做一次针对候选新意的检索，不能只凭前几轮的印象打分。至少两条查询，写进正文和元数据。判断"这个候选没人做过"时，要说出你搜了什么、范围到哪里、最相近的工作差在哪；不要用"据我所知"代替检索。

## 互评

针对明确主张实质回应至少两个其他席位，写明"支持/反对/建议修改"、论据与能推翻自己判断的证据。你可以改变原先立场，也可以推荐别人的候选，或认为所有候选都不值得推进。对影响新颖性判断的关键论文，自己核对方法段，不要只转述别人的结论。

## 投票

对目录中的每个候选 K01、K02……各投一票。不能只给自己的方案投票，不能读取别人的投票，不能更换候选定义。若建议实质改动，只能把它写成下一版本建议；当前票仍然针对冻结版本。中间轮已经合并过的方案以资料包里的候选定义为准，不要自行再合并。

正文之后附一个合法 JSON 代码块。以下只演示一个候选，实际 votes 必须覆盖资料包中全部候选。agent_id、packet_sha256、其他席位 ID 和候选 ID 都替换为真实值：

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
      "candidate_id": "K01",
      "recommend": false,
      "novelty_score": 3,
      "value_score": 4,
      "feasibility_score": 3,
      "unresolved_fatal_objection": false,
      "reason": "自己的判断理由；不推荐也要说明原因",
      "closest_work_urls": ["实际核查过的最相近工作URL"]
    }
  ],
  "preferred_candidate": "NONE"
}
```

stance 只能为 support、oppose 或 modify，不必各选一种。preferred_candidate 为你推荐的某个候选或 NONE。

recommend=true 表示"新意与意义各至少 4 分，可行性至少 3 分，并有具体相近工作对照，值得做最小实验"。它不能与 unresolved_fatal_objection=true 同时出现。

unresolved_fatal_objection 只用于你有明确理由/证据认为机制不成立、关键计算根本省不掉，或与已有工作没有实质差别的情况；普通保留意见写在正文与 reason 中，不必都标成致命。
