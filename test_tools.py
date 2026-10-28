"""Offline counterfactual tests; all model IDs, speeches and URLs below are synthetic."""
import copy
import contextlib
import io
import json
from pathlib import Path
import re
import shutil
import tempfile
import unittest
import subprocess
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import debate_tools as d
import run_debate


FAKE_IDS = ["mock/family-a", "mock/family-b", "mock/family-c",
            "mock/family-d", "mock/family-e", "mock/family-f"]
FAKE_ROLES = [{"id": f"a{i:02d}", "family": "family_" + family,
               "role": "Synthetic researcher", "focus": "Synthetic focus",
               **({"chair": True} if i == 5 else {})}
              for i, family in enumerate("aabbccddef", 1)]


class ToolsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        d.atomic_json(self.root / "roles.json", FAKE_ROLES)
        d.atomic_json(self.root / "protocol.json", d.default_protocol(len(FAKE_ROLES)))
        shutil.copytree(d.ROOT / "prompts", self.root / "prompts")
        (self.root / "research_brief.md").write_text("Synthetic offline background, no research claims.", encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def write_round1(self, retrieval=None):
        retrieval = retrieval or {}
        for role in self.roles:
            aid = role["id"]
            data = {"agent_id": aid, "round": 1, "proposal_id": "P-" + aid,
                    "closest_work_urls": ["https://example.invalid/test-" + str(i) for i in range(3)],
                    "retrieval_status": retrieval.get(aid, "completed")}
            d.atomic_text(self.root / "debate/round1" / (aid + ".md"),
                          "Synthetic offline speech only.\n```json\n" + json.dumps(data) + "\n```\n")

    def vote_round(self):
        return d.load_protocol(self.root, len(self.roles))["rounds"]

    def write_deliberation(self, number):
        ids = [r["id"] for r in self.roles]
        for aid in ids:
            other = [x for x in ids if x != aid][:2]
            meta = {"agent_id": aid, "round": number,
                    "searched_queries": ["synthetic query one", "synthetic query two"],
                    "closest_work_urls": ["https://example.invalid/near-work"],
                    "responses": [{"to_agent": x, "stance": "modify", "claim": "Synthetic response"}
                                  for x in other],
                    "merges": [], "withdraws": []}
            d.atomic_text(self.root / f"debate/round{number}" / (aid + ".md"),
                          "Synthetic offline deliberation.\n```json\n" + json.dumps(meta) + "\n```\n")

    def write_catalog(self, scope_note=None):
        catalog = {"candidates": [{"id": "K01", "title": "Synthetic test case",
                    "source_proposals": ["P-" + r["id"] for r in self.roles],
                    "mechanism": "mock", "closest_work": ["mock"],
                    "minimum_experiment": "mock", "stop_condition": "mock"}], "excluded_proposals": []}
        if scope_note is not None:
            catalog["scope_note"] = scope_note
        d.atomic_json(self.root / "debate/candidates.json", catalog)

    def prepared(self, retrieval=None):
        self.roles = d.setup(self.root, FAKE_IDS)
        self.write_round1(retrieval)
        for number in range(2, self.vote_round()):
            self.write_deliberation(number)
        self.write_catalog()
        self.manifest = d.freeze(self.root)

    def test_resume_skips_merge_and_rejects_changed_frozen_packet(self):
        self.prepared()
        with patch.object(run_debate, "ROOT", self.root), patch.object(run_debate, "run_agent") as call:
            with contextlib.redirect_stdout(io.StringIO()):
                run_debate.merge(resume=True)
            call.assert_not_called()
            packet = self.root / "debate/vote_packet.md"
            packet.write_text(packet.read_text(encoding="utf-8") + "changed", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "冻结资料"):
                run_debate.merge(resume=True)
            call.assert_not_called()

    def ballots(self):
        ids = [r["id"] for r in self.roles]
        number = self.vote_round()
        # 推荐人数取门槛，恰好验证“刚好达到门槛即通过”而不是固定八票
        required = d.load_protocol(self.root, len(ids))["threshold"]["numerator"]
        for i, aid in enumerate(ids):
            other = [x for x in ids if x != aid][:2]
            recommend = i < required
            vote = {"candidate_id": "K01", "recommend": recommend,
                    "novelty_score": 4 if recommend else 2, "value_score": 4,
                    "feasibility_score": 3, "unresolved_fatal_objection": False,
                    "reason": "Synthetic test judgment, not a research recommendation.",
                    "closest_work_urls": ["https://example.invalid/mock-paper"]}
            meta = {"agent_id": aid, "round": number, "packet_sha256": self.manifest["packet_sha256"],
                    "searched_queries": ["synthetic vote query one", "synthetic vote query two"],
                    "responses": [{"to_agent": x, "stance": "modify", "claim": "Synthetic response"} for x in other],
                    "votes": [vote], "preferred_candidate": "K01" if recommend else "NONE"}
            d.atomic_text(self.root / f"debate/round{number}" / (aid + ".md"),
                          "Synthetic test ballot.\n```json\n" + json.dumps(meta) + "\n```\n")

    def change_ballot(self, aid, fn):
        path = self.root / f"debate/round{self.vote_round()}" / (aid + ".md")
        meta = d.metadata(path.read_text(encoding="utf-8"))
        fn(meta)
        d.atomic_text(path, "```json\n" + json.dumps(meta) + "\n```\n")

    def test_actual_inventory_format_with_windows_bom_and_ansi(self):
        raw = "\ufeffheader\r\n\x1b[32mmock/family-a\x1b[0m\r\nmock/family-a\r\nhttps://example.invalid/docs\r\n"
        self.assertEqual(d.parse_inventory(raw), [FAKE_IDS[0]])

    def test_six_families_remain_distinct_and_no_default_model_fallback(self):
        roles = d.load_roster(self.root)
        mapping = d.resolve_models(FAKE_IDS, roles)
        self.assertEqual(mapping["family_b"], "mock/family-b")
        self.assertEqual(mapping["family_c"], "mock/family-c")
        self.assertEqual(len(set(mapping.values())), 6)
        with self.assertRaises(ValueError):
            d.resolve_models(FAKE_IDS[:-1], roles)

    def test_ambiguous_provider_does_not_choose_silently(self):
        with self.assertRaises(ValueError):
            d.setup(self.root, FAKE_IDS + ["other/family-a"])
        self.assertFalse((self.root / "opencode.json").exists())

    def test_manual_alias_mapping_must_exist_in_inventory(self):
        supplied = dict(zip(d.families_of(d.load_roster(self.root)), FAKE_IDS))
        supplied["family_f"] = "nonexistent/fable-5-1"
        with self.assertRaises(ValueError):
            d.resolve_models(FAKE_IDS, d.load_roster(self.root), supplied)

    def test_seat_level_model_override_wins_over_family_mapping(self):
        roles = d.read_json(self.root / "roles.json")
        # 同系列两个席位使用不同 ID：这是 family 映射做不到的事。
        roles[0]["model"] = "mock/family-b"
        roles[1]["model"] = "mock/family-c"
        d.atomic_json(self.root / "roles.json", roles)
        locked = d.setup(self.root, FAKE_IDS)
        by_id = {r["id"]: r["model"] for r in locked}
        self.assertEqual(by_id["a01"], "mock/family-b")
        self.assertEqual(by_id["a02"], "mock/family-c")
        config = d.read_json(self.root / "opencode.json")
        self.assertEqual(config["agents"]["debate-a01"]["model"], "mock/family-b")
        self.assertEqual(config["agents"]["debate-a02"]["model"], "mock/family-c")

    def test_seat_level_override_must_exist_in_inventory(self):
        roles = d.read_json(self.root / "roles.json")
        roles[0]["model"] = "mock/does-not-exist"
        d.atomic_json(self.root / "roles.json", roles)
        with self.assertRaises(ValueError):
            d.setup(self.root, FAKE_IDS)
        self.assertFalse((self.root / "opencode.json").exists())

    def test_seat_level_override_must_be_full_provider_id(self):
        roles = d.read_json(self.root / "roles.json")
        roles[0]["model"] = "Model A"  # 展示名不是 ID
        d.atomic_json(self.root / "roles.json", roles)
        with self.assertRaises(ValueError):
            d.load_roster(self.root)

    def test_fully_overridden_family_needs_no_mapping_entry(self):
        roles = d.read_json(self.root / "roles.json")
        for role in roles:
            if role["family"] == "family_f":
                role["model"] = "mock/family-d"
        d.atomic_json(self.root / "roles.json", roles)
        supplied = dict(zip(d.families_of(d.load_roster(self.root)), FAKE_IDS))
        supplied.pop("family_f", None)
        mapping = d.resolve_models(FAKE_IDS, d.load_roster(self.root), supplied)
        self.assertNotIn("family_f", mapping)

    def test_exactly_ten_seats_nine_subagents_and_correct_model_counts(self):
        roles = d.setup(self.root, FAKE_IDS)
        config = d.read_json(self.root / "opencode.json")
        self.assertNotIn("agent", config)
        agents = config["agents"]
        self.assertEqual(len(agents), 10)
        self.assertEqual(sum(a["mode"] == "primary" for a in agents.values()), 1)
        self.assertEqual(sum(a["mode"] == "subagent" for a in agents.values()), 9)
        self.assertEqual(agents["debate-chair"]["model"], "mock/family-c")
        self.assertEqual(agents["debate-a01"]["steps"], 50)
        self.assertEqual(sorted([r["id"] for r in roles]), [f"a{i:02d}" for i in range(1, 11)])
        for name, a in agents.items():
            self.assertIn(a["model"], FAKE_IDS)
            self.assertTrue(a["system"])
            actions = {(r["action"], r["resource"]): r["effect"] for r in a["permissions"]}
            if a["mode"] == "subagent":
                self.assertEqual(actions[("subagent", "*")], "deny")
                self.assertEqual(actions[("edit", "*")], "deny")

    def test_existing_config_preserved(self):
        path = self.root / "opencode.json"
        path.write_text('{"provider":{"keep":"untouched"}}', encoding="utf-8")
        before = path.read_bytes()
        with self.assertRaises(ValueError):
            d.setup(self.root, FAKE_IDS)
        self.assertEqual(path.read_bytes(), before)

    def test_complete_three_round_records_and_eight_of_ten_tally(self):
        self.prepared()
        self.ballots()
        result = d.audit(self.root)
        self.assertTrue(result["complete"])
        self.assertEqual(result["formal_statements"], 30)
        self.assertEqual(result["candidates"][0]["support"], 8)
        self.assertEqual(result["candidates"][0]["threshold"], "8/10")
        self.assertEqual(result["approved_candidates"], ["K01"])

    def test_two_round_protocol_still_runs_end_to_end(self):
        d.atomic_json(self.root / "protocol.json", {"rounds": 2, "threshold": {"numerator": 8, "denominator": 10}})
        self.prepared()
        self.ballots()
        result = d.audit(self.root)
        self.assertEqual(result["formal_statements"], 20)
        self.assertEqual(result["approved_candidates"], ["K01"])

    def test_round_count_outside_supported_range_rejected(self):
        for rounds in (1, d.MAX_ROUNDS + 1, "3"):
            d.atomic_json(self.root / "protocol.json", {"rounds": rounds,
                                                        "threshold": {"numerator": 8, "denominator": 10}})
            with self.assertRaises(ValueError):
                d.load_protocol(self.root, 10)

    def test_missing_deliberation_round_blocks_freeze(self):
        self.roles = d.setup(self.root, FAKE_IDS)
        self.write_round1()
        self.write_catalog()
        with self.assertRaises(ValueError):
            d.freeze(self.root)

    def test_deliberation_without_recorded_search_rejected(self):
        self.roles = d.setup(self.root, FAKE_IDS)
        self.write_round1()
        self.write_deliberation(2)
        path = self.root / "debate/round2/a04.md"
        meta = d.metadata(path.read_text(encoding="utf-8"))
        meta["searched_queries"] = ["only one query"]
        d.atomic_text(path, "```json\n" + json.dumps(meta) + "\n```\n")
        self.write_catalog()
        with self.assertRaises(ValueError):
            d.freeze(self.root)

    def test_self_reference_does_not_count_as_peer_response(self):
        """席位可以把自己的条目列进 responses 表示自我修订，但不能凑满“回应他人”的数量。"""
        self.roles = d.setup(self.root, FAKE_IDS)
        self.write_round1()
        self.write_deliberation(2)
        path = self.root / "debate/round2/a04.md"
        meta = d.metadata(path.read_text(encoding="utf-8"))
        peers = [r["to_agent"] for r in meta["responses"] if r["to_agent"] != "a04"]
        meta["responses"] = meta["responses"][:1] + [
            {"to_agent": "a04", "stance": "modify", "claim": "Synthetic self-revision"}]
        self.assertGreaterEqual(len(peers), 2)
        d.atomic_text(path, "```json\n" + json.dumps(meta) + "\n```\n")
        self.write_catalog()
        with self.assertRaises(ValueError):
            d.freeze(self.root)

    def test_unknown_response_target_rejected(self):
        self.roles = d.setup(self.root, FAKE_IDS)
        self.write_round1()
        self.write_deliberation(2)
        path = self.root / "debate/round2/a04.md"
        meta = d.metadata(path.read_text(encoding="utf-8"))
        meta["responses"][0]["to_agent"] = "a99"
        d.atomic_text(path, "```json\n" + json.dumps(meta) + "\n```\n")
        self.write_catalog()
        with self.assertRaises(ValueError):
            d.freeze(self.root)

    def test_missing_dissenter_does_not_reduce_denominator(self):
        self.prepared()
        self.ballots()
        (self.root / f"debate/round{self.vote_round()}/a09.md").unlink()
        with self.assertRaises(ValueError):
            d.audit(self.root)

    def test_duplicate_ballot_not_counted_twice(self):
        self.prepared()
        self.ballots()
        self.change_ballot("a01", lambda m: m["votes"].append(copy.deepcopy(m["votes"][0])))
        with self.assertRaises(ValueError):
            d.audit(self.root)

    def test_modified_packet_with_same_hash_label_rejected(self):
        self.prepared()
        self.ballots()
        path = self.root / "debate/vote_packet.md"
        path.write_text(path.read_text(encoding="utf-8") + "\nChanged candidate description", encoding="utf-8")
        with self.assertRaises(ValueError):
            d.audit(self.root)

    def test_candidate_cannot_be_redefined_after_votes(self):
        self.prepared()
        self.ballots()
        path = self.root / "debate/candidates.json"
        catalog = d.read_json(path)
        catalog["candidates"][0]["mechanism"] = "Different mechanism"
        d.atomic_json(path, catalog)
        with self.assertRaises(ValueError):
            d.audit(self.root)
        with self.assertRaises(ValueError):
            d.freeze(self.root)

    def test_vote_for_wrong_packet_rejected(self):
        self.prepared()
        self.ballots()
        self.change_ballot("a01", lambda m: m.update(packet_sha256="0" * 64))
        with self.assertRaises(ValueError):
            d.audit(self.root)

    def test_eight_votes_do_not_hide_a_fatal_objection(self):
        self.prepared()
        self.ballots()
        self.change_ballot("a09", lambda m: m["votes"][0].update(unresolved_fatal_objection=True))
        result = d.audit(self.root)
        self.assertTrue(result["candidates"][0]["threshold_met"])
        self.assertEqual(result["candidates"][0]["fatal_objections_to_review"], ["a09"])
        self.assertEqual(result["approved_candidates"], [])

    def test_project_model_cannot_change_silently(self):
        self.prepared()
        self.ballots()
        path = self.root / "opencode.json"
        config = d.read_json(path)
        config["agents"]["debate-a01"]["model"] = "mock/wrong-model"
        d.atomic_json(path, config)
        with self.assertRaises(ValueError):
            d.audit(self.root)

    def test_unretrieved_seat_cannot_enter_vote_round(self):
        self.prepared()
        path = self.root / "debate/round1/a01.md"
        meta = d.metadata(path.read_text(encoding="utf-8"))
        meta["retrieval_status"] = "blocked"
        d.atomic_text(path, "```json\n" + json.dumps(meta) + "\n```\n")
        with self.assertRaises(ValueError):
            d.freeze(self.root)

    def test_partial_retrieval_is_recorded_not_silently_accepted(self):
        self.prepared(retrieval={"a03": "partial"})
        self.ballots()
        result = d.audit(self.root)
        self.assertEqual(result["retrieval_partial_seats"], ["a03"])
        note = d.read_json(self.root / "debate/candidates.json")["scope_note"]
        self.assertEqual(note.count("a03"), 1)
        # 再算一次 digest 不得漂移，说明也不得写两遍
        d.freeze(self.root)
        self.assertEqual(d.read_json(self.root / "debate/candidates.json")["scope_note"], note)

    def test_partial_note_clears_when_seat_finishes_before_freeze(self):
        self.roles = d.load_roster(self.root)
        d.setup(self.root, FAKE_IDS)
        self.write_round1({"a03": "partial"})
        self.write_deliberation(2)
        self.write_catalog("人工补充的说明。")
        d.freeze(self.root)
        self.assertIn("a03", d.read_json(self.root / "debate/candidates.json")["scope_note"])
        # 席位在冻结前补齐检索，说明应回到只剩人工那一条，而不是留着过期名单
        path = self.root / "debate/round1/a03.md"
        meta = d.metadata(path.read_text(encoding="utf-8"))
        meta["retrieval_status"] = "completed"
        d.atomic_text(path, "```json\n" + json.dumps(meta) + "\n```\n")
        self.assertEqual(d.packet_data(self.root)["retrieval_partial_seats"], [])
        note = d.read_json(self.root / "debate/candidates.json")["scope_note"]
        self.assertNotIn("a03", note)
        self.assertIn("人工补充的说明", note)

    def test_threshold_is_frozen_into_the_packet(self):
        self.prepared()
        # 冻结后把门槛从 8/10 降到 6/10：必须先被 packet 哈希拦住，而不是悄悄生效
        path = self.root / "protocol.json"
        protocol = d.read_json(path)
        protocol["threshold"]["numerator"] = 6
        d.atomic_json(path, protocol)
        with self.assertRaises(ValueError):
            d.audit(self.root)

    def test_seat_count_and_threshold_come_from_roles(self):
        # 同样的代码跑 7 席：席位数、主持、门槛全部来自 roles.json 与 protocol.json
        roles = d.read_json(self.root / "roles.json")[:7]
        d.atomic_json(self.root / "roles.json", roles)
        d.atomic_json(self.root / "protocol.json", {"rounds": 2, "threshold": {"numerator": 5, "denominator": 7}})
        self.roles = d.load_roster(self.root)
        locked = d.setup(self.root, FAKE_IDS)
        self.assertEqual([r["id"] for r in locked], d.seat_ids(7))
        config = d.read_json(self.root / "opencode.json")
        self.assertEqual(sum(a["mode"] == "primary" for a in config["agents"].values()), 1)
        self.assertIn("七席位", config["agents"]["debate-chair"]["system"])
        self.assertIn("5/7", config["agents"]["debate-a01"]["system"])
        self.write_round1()
        self.write_catalog()
        self.manifest = d.freeze(self.root)
        self.ballots()
        result = d.audit(self.root)
        self.assertEqual(result["seats"], 7)
        self.assertEqual(result["formal_statements"], 14)
        self.assertEqual(result["candidates"][0]["support"], 5)
        self.assertTrue(result["candidates"][0]["threshold_met"])

    def test_seven_seat_roster_without_explicit_threshold_defaults_to_eighty_percent(self):
        roles = d.read_json(self.root / "roles.json")[:7]
        d.atomic_json(self.root / "roles.json", roles)
        (self.root / "protocol.json").unlink(missing_ok=True)
        d.setup(self.root, FAKE_IDS)
        lock = d.read_json(self.root / "roster.lock.json")
        self.assertEqual(lock["protocol"]["threshold"], {"numerator": 6, "denominator": 7})

    def test_protocol_denominator_must_match_seat_count(self):
        d.atomic_json(self.root / "protocol.json", {"rounds": 2, "threshold": {"numerator": 6, "denominator": 10}})
        roles = d.read_json(self.root / "roles.json")[:7]
        d.atomic_json(self.root / "roles.json", roles)
        with self.assertRaises(ValueError):
            d.setup(self.root, FAKE_IDS)
        self.assertFalse((self.root / "opencode.json").exists())

    def test_roster_requires_one_chair_and_contiguous_ids(self):
        roles = d.read_json(self.root / "roles.json")
        for role in roles:
            role.pop("chair", None)
        d.atomic_json(self.root / "roles.json", roles)
        with self.assertRaises(ValueError):
            d.setup(self.root, FAKE_IDS)
        roles = d.read_json(d.ROOT / "roles.json")
        roles[1]["id"] = "a99"
        d.atomic_json(self.root / "roles.json", roles)
        with self.assertRaises(ValueError):
            d.setup(self.root, FAKE_IDS)


class EvaluateTests(unittest.TestCase):
    """evaluate 模式：回答同一个问题，单选投票，严格多数（十席时 6/10）。

    这里刻意不继承 ToolsTests：那 32 个用例锁的是 proposal 的字段名与八成门槛，
    在新模式下重跑只会证明“它确实不是 evaluate”。
    """

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        d.atomic_json(self.root / "roles.json", FAKE_ROLES)
        shutil.copytree(d.ROOT / "prompts", self.root / "prompts")
        d.atomic_json(self.root / "protocol.json", {"mode": "evaluate", "rounds": 3})
        (self.root / "research_brief.md").write_text("Synthetic offline background, no research claims.", encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def write_positions(self):
        for role in self.roles:
            aid = role["id"]
            meta = {"agent_id": aid, "round": 1, "position_id": "S-" + aid,
                    "stance": "支持",
                    "evidence_urls": ["https://example.invalid/test-" + str(i) for i in range(3)],
                    "retrieval_status": "completed"}
            d.atomic_text(self.root / "debate/round1" / (aid + ".md"),
                          "Synthetic offline speech only.\n```json\n" + json.dumps(meta) + "\n```\n")

    def vote_round(self):
        return d.load_protocol(self.root, len(self.roles))["rounds"]

    def write_deliberation(self, number):
        ids = [r["id"] for r in self.roles]
        for aid in ids:
            other = [x for x in ids if x != aid][:2]
            meta = {"agent_id": aid, "round": number,
                    "searched_queries": ["synthetic query one", "synthetic query two"],
                    "evidence_urls": ["https://example.invalid/evidence"],
                    "responses": [{"to_agent": x, "stance": "modify", "claim": "Synthetic response"}
                                  for x in other],
                    "position_change": {"changed": False, "from": "", "to": "", "why": ""}}
            d.atomic_text(self.root / f"debate/round{number}" / (aid + ".md"),
                          "Synthetic offline deliberation.\n```json\n" + json.dumps(meta) + "\n```\n")

    def write_catalog(self, split=None):
        """split: 结论 ID -> 该结论覆盖哪些首轮立场。省略时全部归入第一条。"""
        if split is None:
            split = {"C01": ["S-" + r["id"] for r in self.roles]}
        items = [{"id": cid, "statement": "Synthetic stance " + cid,
                  "source_positions": list(split[cid]),
                  "reasoning": "mock", "evidence": ["mock"],
                  "strongest_objection": "mock", "what_would_change_it": "mock"}
                 for cid in split]
        d.atomic_json(self.root / "debate/conclusions.json",
                      {"conclusions": items, "excluded_positions": []})

    def prepared(self, split=None):
        self.roles = d.setup(self.root, FAKE_IDS)
        self.write_positions()
        for number in range(2, self.vote_round()):
            self.write_deliberation(number)
        self.write_catalog(split)
        self.manifest = d.freeze(self.root)

    def endorsements(self, endorsed="C01"):
        ids = [r["id"] for r in self.roles]
        number = self.vote_round()
        required = d.load_protocol(self.root, len(ids))["threshold"]["numerator"]
        for i, aid in enumerate(ids):
            other = [x for x in ids if x != aid][:2]
            pick = i < required
            votes = [{"candidate_id": endorsed, "endorse": pick,
                      "confidence": 4 if pick else 2, "unresolved_fatal_objection": False,
                      "reason": "Synthetic test judgment, not a research claim.",
                      "evidence_urls": ["https://example.invalid/mock-paper"]}]
            meta = {"agent_id": aid, "round": number, "packet_sha256": self.manifest["packet_sha256"],
                    "searched_queries": ["synthetic vote query one", "synthetic vote query two"],
                    "responses": [{"to_agent": x, "stance": "modify", "claim": "Synthetic response"} for x in other],
                    "votes": votes, "preferred_conclusion": endorsed if pick else "NONE"}
            d.atomic_text(self.root / f"debate/round{number}" / (aid + ".md"),
                          "Synthetic test ballot.\n```json\n" + json.dumps(meta) + "\n```\n")

    def change_ballot(self, aid, fn):
        path = self.root / f"debate/round{self.vote_round()}" / (aid + ".md")
        meta = d.metadata(path.read_text(encoding="utf-8"))
        fn(meta)
        d.atomic_text(path, "```json\n" + json.dumps(meta) + "\n```\n")

    def test_evaluate_default_threshold_is_strict_majority(self):
        d.setup(self.root, FAKE_IDS)
        lock = d.read_json(self.root / "roster.lock.json")
        self.assertEqual(lock["protocol"]["mode"], "evaluate")
        self.assertEqual(lock["protocol"]["threshold"], {"numerator": 6, "denominator": 10})

    def test_six_of_ten_endorsements_adopt_the_conclusion(self):
        self.prepared()
        self.endorsements()
        result = d.audit(self.root)
        self.assertEqual(result["mode"], "evaluate")
        self.assertEqual(result["formal_statements"], 30)
        self.assertEqual(result["conclusions"][0]["support"], 6)
        self.assertEqual(result["conclusions"][0]["threshold"], "6/10")
        self.assertEqual(result["adopted_conclusions"], ["C01"])
        self.assertNotIn("approved_candidates", result)
        header = (self.root / "debate/votes.csv").read_text(encoding="utf-8-sig").splitlines()[0]
        self.assertIn("endorse", header)
        self.assertIn("confidence", header)

    def test_five_of_ten_does_not_adopt(self):
        self.prepared()
        self.endorsements()
        self.change_ballot("a06", lambda m: (m["votes"][0].update(endorse=False, confidence=2),
                                             m.update(preferred_conclusion="NONE")))
        result = d.audit(self.root)
        self.assertEqual(result["conclusions"][0]["support"], 5)
        self.assertFalse(result["conclusions"][0]["threshold_met"])
        self.assertEqual(result["adopted_conclusions"], [])

    def test_single_choice_ballot_rejects_two_endorsements(self):
        self.roles = d.load_roster(self.root)
        self.prepared({"C01": ["S-" + r["id"] for r in self.roles[:5]],
                       "C02": ["S-" + r["id"] for r in self.roles[5:]]})
        ids = [r["id"] for r in self.roles]
        number = self.vote_round()
        for aid in ids:
            other = [x for x in ids if x != aid][:2]
            votes = [{"candidate_id": cid, "endorse": True, "confidence": 5,
                      "unresolved_fatal_objection": False,
                      "reason": "Synthetic test judgment.",
                      "evidence_urls": ["https://example.invalid/mock-paper"]}
                     for cid in ("C01", "C02")]
            meta = {"agent_id": aid, "round": number, "packet_sha256": self.manifest["packet_sha256"],
                    "searched_queries": ["synthetic vote query one", "synthetic vote query two"],
                    "responses": [{"to_agent": x, "stance": "modify", "claim": "Synthetic response"} for x in other],
                    "votes": votes, "preferred_conclusion": "C01"}
            d.atomic_text(self.root / f"debate/round{number}" / (aid + ".md"),
                          "Synthetic test ballot.\n```json\n" + json.dumps(meta) + "\n```\n")
        with self.assertRaises(ValueError) as caught:
            d.audit(self.root)
        self.assertIn("C01", str(caught.exception))

    def test_endorse_requires_confidence_floor_and_evidence_url(self):
        self.prepared()
        self.endorsements()
        self.change_ballot("a02", lambda m: m["votes"][0].update(confidence=3))
        with self.assertRaises(ValueError):
            d.audit(self.root)

    def test_preferred_must_match_the_single_endorsed_conclusion(self):
        # 单选票只认 endorse，但 preferred_conclusion 是下一版建议的入口；
        # 两者矛盾时不能照原票计票，否则报告会引用当事人没投过的选择。
        self.prepared()
        self.endorsements()
        self.change_ballot("a01", lambda m: m.update(preferred_conclusion="NONE"))
        with self.assertRaises(ValueError) as caught:
            d.audit(self.root)
        self.assertIn("preferred_conclusion", str(caught.exception))

    def test_missing_conclusions_catalog_fails_freeze_with_mode_specific_message(self):
        self.roles = d.setup(self.root, FAKE_IDS)
        self.write_positions()
        self.write_deliberation(2)
        d.atomic_json(self.root / "debate/candidates.json", {"candidates": []})
        with self.assertRaises(ValueError) as caught:
            d.freeze(self.root)
        self.assertIn("debate/conclusions.json", str(caught.exception))

    def test_mode_cannot_change_after_freeze(self):
        self.prepared()
        self.endorsements()
        path = self.root / "protocol.json"
        protocol = d.read_json(path)
        protocol["mode"] = "proposal"
        d.atomic_json(path, protocol)
        with self.assertRaises(ValueError):
            d.audit(self.root)

    def test_set_mode_rewrites_threshold_for_the_new_mode(self):
        (self.root / "protocol.json").write_text(
            json.dumps({"rounds": 2, "threshold": {"numerator": 8, "denominator": 10}}), encoding="utf-8")
        self.assertEqual(d.set_mode(self.root, "evaluate"),
                         {"mode": "evaluate", "rounds": 2,
                          "threshold": {"numerator": 6, "denominator": 10}})
        # 换回 proposal 也要重新算回八成，而不是留着 evaluate 的 6/10
        self.assertEqual(d.set_mode(self.root, "proposal")["threshold"],
                         {"numerator": 8, "denominator": 10})

    def test_set_mode_keeps_a_hand_set_threshold_when_the_mode_is_unchanged(self):
        d.atomic_json(self.root / "protocol.json",
                      {"mode": "evaluate", "rounds": 3,
                       "threshold": {"numerator": 7, "denominator": 10}})
        self.assertEqual(d.set_mode(self.root, "evaluate")["threshold"],
                         {"numerator": 7, "denominator": 10})

    def test_unknown_mode_rejected(self):
        d.atomic_json(self.root / "protocol.json", {"mode": "review", "rounds": 3})
        with self.assertRaises(ValueError):
            d.load_protocol(self.root, 10)

    def test_setup_with_mode_leaves_protocol_untouched_when_config_exists(self):
        # 已配置过的目录：setup 必须整体拒绝，不能先把 protocol.json 改成新模式再报错。
        d.setup(self.root, FAKE_IDS)
        before = {"mode": "proposal", "rounds": 3, "threshold": {"numerator": 8, "denominator": 10}}
        d.atomic_json(self.root / "protocol.json", before)
        with self.assertRaises(ValueError) as caught:
            d.setup(self.root, FAKE_IDS, mode="evaluate")
        self.assertIn("opencode.json", str(caught.exception))
        self.assertEqual(d.read_json(self.root / "protocol.json"), before)

    def test_setup_with_mode_leaves_protocol_untouched_when_mapping_fails(self):
        # 映射校验失败也必须先失败：不能留下“模式已改、配置未生成”的半截目录。
        before = {"mode": "proposal", "rounds": 3, "threshold": {"numerator": 8, "denominator": 10}}
        d.atomic_json(self.root / "protocol.json", before)
        with self.assertRaises(ValueError):
            d.setup(self.root, FAKE_IDS, {"family_a": "mock/not-in-inventory"}, mode="evaluate")
        self.assertEqual(d.read_json(self.root / "protocol.json"), before)
        self.assertFalse((self.root / "opencode.json").exists())

    def test_setup_with_mode_leaves_protocol_untouched_when_prompt_missing(self):
        # 提示词缺失要在写 protocol.json 之前失败：否则目录会变成“模式已是 solve、配置没生成”。
        before = {"mode": "proposal", "rounds": 3, "threshold": {"numerator": 8, "denominator": 10}}
        d.atomic_json(self.root / "protocol.json", before)
        (self.root / "prompts/solve/vote.md").unlink()
        with self.assertRaises(ValueError) as caught:
            d.setup(self.root, FAKE_IDS, mode="solve")
        self.assertIn("vote.md", str(caught.exception))
        self.assertEqual(d.read_json(self.root / "protocol.json"), before)
        self.assertFalse((self.root / "opencode.json").exists())

    def test_setup_with_unchanged_mode_keeps_handwritten_threshold_bytes(self):
        # 模式没变时，手写门槛与多余键都不该被重写。
        path = self.root / "protocol.json"
        original = ("{\n  \"mode\": \"proposal\",\n  \"rounds\": 2,\n"
                    "  \"threshold\": {\"numerator\": 7, \"denominator\": 10},\n  \"note\": \"手写\"\n}\n")
        path.write_text(original, encoding="utf-8")
        d.setup(self.root, FAKE_IDS, mode="proposal")
        self.assertEqual(path.read_text(encoding="utf-8"), original)

    def test_proposal_default_mode_when_field_absent(self):
        d.atomic_json(self.root / "protocol.json", {"rounds": 3})
        protocol = d.load_protocol(self.root, 10)
        self.assertEqual(protocol["mode"], "proposal")
        self.assertEqual(protocol["threshold"], {"numerator": 8, "denominator": 10})


class SolveTests(unittest.TestCase):
    """solve 模式：对同一个问题讨论解法，多选投票，八成门槛（十席时 8/10）。

    与 evaluate 的两处关键差别都锁在这里：票不是单选（一个问题可以同时采纳
    多条并行可用的方案），并且已有工作不是淘汰理由，所以分里没有新意项。
    同样不继承 ToolsTests：那批用例锁的是 proposal 的字段名与候选语义。
    """

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        d.atomic_json(self.root / "roles.json", FAKE_ROLES)
        shutil.copytree(d.ROOT / "prompts", self.root / "prompts")
        d.atomic_json(self.root / "protocol.json", {"mode": "solve", "rounds": 3})
        (self.root / "research_brief.md").write_text("Synthetic offline background, no research claims.", encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def write_designs(self):
        for role in self.roles:
            aid = role["id"]
            meta = {"agent_id": aid, "round": 1, "design_id": "D-" + aid,
                    "title": "Synthetic design " + aid,
                    "evidence_urls": ["https://example.invalid/test-" + str(i) for i in range(3)],
                    "retrieval_status": "completed"}
            d.atomic_text(self.root / "debate/round1" / (aid + ".md"),
                          "Synthetic offline speech only.\n```json\n" + json.dumps(meta) + "\n```\n")

    def vote_round(self):
        return d.load_protocol(self.root, len(self.roles))["rounds"]

    def write_deliberation(self, number):
        ids = [r["id"] for r in self.roles]
        for aid in ids:
            other = [x for x in ids if x != aid][:2]
            meta = {"agent_id": aid, "round": number,
                    "searched_queries": ["synthetic query one", "synthetic query two"],
                    "evidence_urls": ["https://example.invalid/evidence"],
                    "responses": [{"to_agent": x, "stance": "modify", "claim": "Synthetic response"}
                                  for x in other],
                    "merges": [], "withdraws": []}
            d.atomic_text(self.root / f"debate/round{number}" / (aid + ".md"),
                          "Synthetic offline deliberation.\n```json\n" + json.dumps(meta) + "\n```\n")

    def write_catalog(self, split=None):
        """split: 方案 ID -> 该方案覆盖哪些首轮解法。省略时全部归入第一条。"""
        if split is None:
            split = {"S01": ["D-" + r["id"] for r in self.roles]}
        items = [{"id": sid, "title": "Synthetic solution " + sid,
                  "claim": "mock", "source_designs": list(split[sid]),
                  "mechanism": "mock", "evidence": ["mock"],
                  "preconditions": "mock", "main_risk": "mock"}
                 for sid in split]
        d.atomic_json(self.root / "debate/solutions.json",
                      {"solutions": items, "excluded_designs": []})

    def prepared(self, split=None):
        self.roles = d.setup(self.root, FAKE_IDS)
        self.write_designs()
        for number in range(2, self.vote_round()):
            self.write_deliberation(number)
        self.write_catalog(split)
        self.manifest = d.freeze(self.root)

    def score(self, adopt):
        return {"value_score": 4 if adopt else 3, "soundness_score": 4,
                "feasibility_score": 4 if adopt else 3}

    def ballots(self, adopted=("S01",), abstain_at=None):
        """adopted: 前 required 个席位采纳的方案；abstain_at: 该序号的席位改为不采纳。"""
        ids = [r["id"] for r in self.roles]
        number = self.vote_round()
        required = d.load_protocol(self.root, len(ids))["threshold"]["numerator"]
        catalog = d.read_json(self.root / "debate/solutions.json")["solutions"]
        for i, aid in enumerate(ids):
            other = [x for x in ids if x != aid][:2]
            supporting = i < required and i != abstain_at
            votes = []
            for item in catalog:
                take = supporting and item["id"] in adopted
                votes.append({"candidate_id": item["id"], "adopt": take,
                              "unresolved_fatal_objection": False,
                              "reason": "Synthetic test judgment, not a research claim.",
                              "evidence_urls": ["https://example.invalid/mock-paper"],
                              **self.score(take)})
            preferred = next((v["candidate_id"] for v in votes if v["adopt"]), "NONE")
            meta = {"agent_id": aid, "round": number, "packet_sha256": self.manifest["packet_sha256"],
                    "searched_queries": ["synthetic vote query one", "synthetic vote query two"],
                    "responses": [{"to_agent": x, "stance": "modify", "claim": "Synthetic response"} for x in other],
                    "votes": votes, "preferred_solution": preferred}
            d.atomic_text(self.root / f"debate/round{number}" / (aid + ".md"),
                          "Synthetic test ballot.\n```json\n" + json.dumps(meta) + "\n```\n")

    def change_ballot(self, aid, fn):
        path = self.root / f"debate/round{self.vote_round()}" / (aid + ".md")
        meta = d.metadata(path.read_text(encoding="utf-8"))
        fn(meta)
        d.atomic_text(path, "```json\n" + json.dumps(meta) + "\n```\n")

    def test_solve_default_threshold_is_eighty_percent(self):
        d.setup(self.root, FAKE_IDS)
        lock = d.read_json(self.root / "roster.lock.json")
        self.assertEqual(lock["protocol"]["mode"], "solve")
        self.assertEqual(lock["protocol"]["threshold"], {"numerator": 8, "denominator": 10})

    def test_eight_of_ten_adopts_the_solution(self):
        self.prepared()
        self.ballots()
        result = d.audit(self.root)
        self.assertEqual(result["mode"], "solve")
        self.assertEqual(result["formal_statements"], 30)
        self.assertEqual(result["solutions"][0]["support"], 8)
        self.assertEqual(result["solutions"][0]["threshold"], "8/10")
        self.assertEqual(result["adopted_solutions"], ["S01"])
        self.assertNotIn("approved_candidates", result)
        header = (self.root / "debate/votes.csv").read_text(encoding="utf-8-sig").splitlines()[0]
        for column in ("adopt", "value_score", "soundness_score", "feasibility_score"):
            self.assertIn(column, header)

    def test_seven_of_ten_does_not_adopt(self):
        self.prepared()
        self.ballots(abstain_at=7)
        result = d.audit(self.root)
        self.assertEqual(result["solutions"][0]["support"], 7)
        self.assertFalse(result["solutions"][0]["threshold_met"])
        self.assertEqual(result["adopted_solutions"], [])

    def test_two_solutions_can_be_adopted_in_the_same_ballot(self):
        # 与 evaluate 的本质区别：两个并行可用的方案各自过门槛，都进 adopted_solutions。
        self.roles = d.load_roster(self.root)
        self.prepared({"S01": ["D-" + r["id"] for r in self.roles[:5]],
                       "S02": ["D-" + r["id"] for r in self.roles[5:]]})
        self.ballots(adopted=("S01", "S02"))
        result = d.audit(self.root)
        self.assertEqual([s["support"] for s in result["solutions"]], [8, 8])
        self.assertEqual(result["adopted_solutions"], ["S01", "S02"])

    def test_adopt_requires_score_floors(self):
        self.prepared()
        self.ballots()
        self.change_ballot("a02", lambda m: m["votes"][0].update(feasibility_score=2))
        with self.assertRaises(ValueError) as caught:
            d.audit(self.root)
        self.assertIn("feasibility_score", str(caught.exception))

    def test_preferred_solution_must_be_one_of_the_adopted(self):
        self.roles = d.load_roster(self.root)
        self.prepared({"S01": ["D-" + r["id"] for r in self.roles[:5]],
                       "S02": ["D-" + r["id"] for r in self.roles[5:]]})
        self.ballots(adopted=("S01",))
        self.change_ballot("a01", lambda m: m.update(preferred_solution="S02"))
        with self.assertRaises(ValueError) as caught:
            d.audit(self.root)
        self.assertIn("preferred_solution", str(caught.exception))

    def test_missing_solutions_catalog_fails_freeze_with_mode_specific_message(self):
        self.roles = d.setup(self.root, FAKE_IDS)
        self.write_designs()
        self.write_deliberation(2)
        d.atomic_json(self.root / "debate/candidates.json", {"candidates": []})
        with self.assertRaises(ValueError) as caught:
            d.freeze(self.root)
        self.assertIn("debate/solutions.json", str(caught.exception))

    def test_proposal_shaped_ballot_is_rejected_in_solve(self):
        # 旧模式的票（recommend/novelty_score）在 solve 下必须被拒，而不是静默当成不采纳。
        self.prepared()
        self.ballots()
        self.change_ballot("a03", lambda m: m["votes"][0].pop("soundness_score"))
        with self.assertRaises(ValueError):
            d.audit(self.root)

    def test_mode_cannot_change_after_freeze(self):
        self.prepared()
        self.ballots()
        path = self.root / "protocol.json"
        protocol = d.read_json(path)
        protocol["mode"] = "evaluate"
        d.atomic_json(path, protocol)
        with self.assertRaises(ValueError):
            d.audit(self.root)

    def test_set_mode_recomputes_threshold_between_modes(self):
        (self.root / "protocol.json").write_text(
            json.dumps({"rounds": 2, "threshold": {"numerator": 6, "denominator": 10}}), encoding="utf-8")
        self.assertEqual(d.set_mode(self.root, "solve")["threshold"],
                         {"numerator": 8, "denominator": 10})
        self.assertEqual(d.set_mode(self.root, "evaluate")["threshold"],
                         {"numerator": 6, "denominator": 10})

    def test_rendered_packet_uses_solve_wording(self):
        self.prepared()
        packet = (self.root / "debate/vote_packet.md").read_text(encoding="utf-8")
        self.assertIn("方案目录", packet)
        self.assertIn("可以同时认同多条", packet)
        self.assertNotIn("候选目录", packet)

    def test_runner_audit_prints_mode_specific_key(self):
        # run_debate.audit() 曾写死 result["candidates"]，solve 下直接 KeyError。
        self.prepared()
        self.ballots()
        previous = run_debate.ROOT
        run_debate.ROOT = self.root
        try:
            with contextlib.redirect_stdout(io.StringIO()) as out:
                run_debate.audit()
        finally:
            run_debate.ROOT = previous
        printed = json.loads(out.getvalue())
        self.assertEqual(printed["approved"], ["S01"])
        self.assertIn("solutions", printed)
        self.assertNotIn("candidates", printed)

    def test_runner_repair_prompt_matches_the_round(self):
        # 首轮没有互评与票：修复提示词不能要求席位去改 responses/votes。
        self.prepared()
        self.ballots()
        captured = []
        previous_root, previous_run = run_debate.ROOT, run_debate.run_agent
        run_debate.ROOT = self.root

        def fake(_agent, prompt, _tag):
            captured.append(prompt)
            # repair 只改写元数据块；这里原样返回，足够检查提示词。
            return "```json\n" + json.dumps(d.metadata(self.round1_text)) + "\n```\n"

        self.round1_text = (self.root / "debate/round1" / "a01.md").read_text(encoding="utf-8")
        vote_text = (self.root / f"debate/round{self.vote_round()}" / "a01.md").read_text(encoding="utf-8")
        run_debate.run_agent = fake
        try:
            run_debate.repair("a01", 1, "synthetic problem")
            first = captured[-1]
            self.round1_text = vote_text
            run_debate.repair("a01", self.vote_round(), "synthetic problem")
            last = captured[-1]
        finally:
            run_debate.ROOT, run_debate.run_agent = previous_root, previous_run
        self.assertNotIn("responses", first)
        self.assertNotIn("votes", first)
        self.assertIn("本轮元数据", first)
        self.assertIn("responses", last)
        self.assertIn("votes", last)
        self.assertIn("投票轮元数据", last)


class RunnerSessionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.roles = [
            {"id": "a01", "agent_name": "debate-a01", "model": "mock/one"},
            {"id": "a02", "agent_name": "debate-chair", "model": "mock/two"},
        ]
        d.atomic_json(self.root / "roster.lock.json", {"seats": self.roles})
        d.atomic_json(self.root / "protocol.json", {
            "mode": "proposal", "rounds": 3,
            "threshold": {"numerator": 2, "denominator": 2}})
        (self.root / "research_brief.md").write_text("Synthetic brief", encoding="utf-8")
        self.addCleanup(patch.stopall)
        patch.object(run_debate, "ROOT", self.root).start()
        patch.object(run_debate, "cli", return_value="mock-cli").start()
        self.calls = []

    def events(self, sid, text="Synthetic response"):
        return "\n".join(json.dumps(e) for e in [
            {"type": "step_start", "sessionID": sid},
            {"type": "text", "sessionID": sid, "part": {
                "messageID": "msg_mock", "type": "text", "text": text}}])

    def fake_cli(self, executable, args, root, timeout):
        self.calls.append(args)
        agent = args[args.index("--agent") + 1]
        sid = "ses_" + agent.replace("-", "_")
        return subprocess.CompletedProcess(args, 0, self.events(sid), "")

    def invoke(self, seat="a01", label=None):
        role = next(r for r in self.roles if r["id"] == seat)
        return run_debate.run_agent(role["agent_name"], "Synthetic prompt", label or f"round1-{seat}")

    def test_sessions_are_independent_and_persist_across_calls(self):
        with patch.object(d, "run_cli", side_effect=self.fake_cli):
            with ThreadPoolExecutor(max_workers=2) as pool:
                list(pool.map(self.invoke, ["a01", "a02"]))
            self.assertTrue(all("--session" not in c for c in self.calls))
            for seat in ("a01", "a02"):
                state = d.read_json(self.root / f"debate/sessions/{seat}.json")
                self.invoke(seat, f"round2-{seat}")
                args = self.calls[-1]
                self.assertEqual(args[args.index("--session") + 1], state["session_id"])
                self.assertEqual(args[args.index("--model") + 1], state["model"])
            self.invoke("a02", "merge")
            self.invoke("a02", "round3-a02")
            self.invoke("a02", "final")
            self.assertEqual(len({c[c.index("--session") + 1] for c in self.calls[-3:]}), 1)
            with self.assertRaisesRegex(RuntimeError, "后续阶段"):
                self.invoke("a02", "round3-a02")

    def test_failed_call_keeps_real_session_for_retry(self):
        failed = subprocess.CompletedProcess([], 1, json.dumps({
            "type": "error", "sessionID": "ses_debate_a01"}), "auth failed")
        with patch.object(d, "run_cli", return_value=failed):
            with self.assertRaisesRegex(RuntimeError, "没有返回正文"):
                self.invoke()
        with patch.object(d, "run_cli", side_effect=self.fake_cli):
            self.invoke()
        self.assertIn("ses_debate_a01", self.calls[-1])

    def test_timeout_keeps_partial_session_and_log(self):
        partial = json.dumps({"type": "step_start", "sessionID": "ses_debate_a01"}).encode()
        with patch.object(d, "run_cli", side_effect=subprocess.TimeoutExpired("mock", 1, output=partial)):
            with self.assertRaises(subprocess.TimeoutExpired):
                self.invoke()
        self.assertEqual(d.read_json(self.root / "debate/sessions/a01.json")["session_id"], "ses_debate_a01")
        self.assertTrue((self.root / "debate/logs/round1-a01.jsonl").exists())

    def test_missing_or_wrong_session_is_not_silently_accepted(self):
        with patch.object(d, "run_cli", side_effect=self.fake_cli):
            with self.assertRaisesRegex(RuntimeError, "缺少持久会话"):
                self.invoke(label="round2-a01")
            self.invoke()
        for stdout in (self.events("ses_wrong"), self.events("ses_debate_a01") + "\n" + self.events("ses_other")):
            with patch.object(d, "run_cli", return_value=subprocess.CompletedProcess([], 0, stdout, "")):
                with self.assertRaises(RuntimeError):
                    self.invoke(label="round2-a01")
        (self.root / "research_brief.md").write_text("Different topic", encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "绑定"):
            self.invoke()

    def test_seats_cannot_share_session(self):
        result = subprocess.CompletedProcess([], 0, self.events("ses_shared"), "")
        with patch.object(d, "run_cli", return_value=result):
            self.invoke("a01")
            with self.assertRaisesRegex(RuntimeError, "不同席位"):
                self.invoke("a02")

    def test_response_without_session_id_is_rejected(self):
        event = {"type": "text", "part": {"messageID": "msg_mock", "type": "text", "text": "Synthetic"}}
        with patch.object(d, "run_cli", return_value=subprocess.CompletedProcess([], 0, json.dumps(event), "")):
            with self.assertRaisesRegex(RuntimeError, "没有可核验"):
                self.invoke()
        self.assertFalse((self.root / "debate/sessions/a01.json").exists())


class PromptRenderTests(unittest.TestCase):
    """席位直接读磁盘的四个提示词不经渲染，占位符会原样落到提示词里。

    member.md 与 chair.md 会被 render_template 处理并写进 system prompt；
    其余四个由席位在轮次中按路径自行读取，所以只能写具体措辞。
    """

    RUNTIME_FILES = ("start.md", "round1.md", "deliberate.md", "vote.md")

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        d.atomic_json(self.root / "roles.json", FAKE_ROLES)
        shutil.copytree(d.ROOT / "prompts", self.root / "prompts")
        (self.root / "research_brief.md").write_text("Synthetic offline background, no research claims.", encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def test_chair_does_not_launch_or_orchestrate_the_driver(self):
        for mode in d.MODES:
            text = (self.root / "prompts" / mode / "chair.md").read_text(encoding="utf-8")
            for command in ("python run_debate.py", "python debate_tools.py doctor",
                            "python debate_tools.py freeze", "python debate_tools.py audit"):
                self.assertNotIn(command, text)
            self.assertIn("你只完成本次调用指定的阶段", text)

    def test_start_command_targets_the_operator_in_all_modes(self):
        roles = d.load_roster(self.root)
        mapping = d.resolve_models(FAKE_IDS, roles)
        for mode in d.MODES:
            config, _ = d.make_config(self.root, mapping, protocol=d.default_protocol(len(roles), mode))
            self.assertEqual(config["commands"]["debate-start"]["agent"], "build")
            self.assertIn("外层操作代理", config["commands"]["debate-start"]["template"])

    def test_runtime_prompts_have_no_template_tokens(self):
        # 三个模式全查：solve 最先犯这个错，evaluate 的 vote.md 也一度写进 token。
        for mode in sorted(d.MODES):
            for name in self.RUNTIME_FILES:
                text = (self.root / "prompts" / mode / name).read_text(encoding="utf-8")
                self.assertIsNone(re.search(r"\{\{[A-Z_]+\}\}", text),
                                  msg=f"{mode}/{name} 含未渲染占位符")

    def test_make_config_rejects_token_in_runtime_prompt(self):
        # 守卫要在写任何文件之前失败，否则会留下半截配置。
        path = self.root / "prompts/solve/vote.md"
        path.write_text(path.read_text(encoding="utf-8") + "\n{{SCORE_FLOOR_TEXT}}\n", encoding="utf-8")
        d.atomic_json(self.root / "protocol.json", {"mode": "solve", "rounds": 3})
        with self.assertRaises(ValueError) as caught:
            d.setup(self.root, FAKE_IDS)
        message = str(caught.exception)
        self.assertIn("vote.md", message)
        self.assertIn("SCORE_FLOOR_TEXT", message)
        self.assertFalse((self.root / "opencode.json").exists())

    def test_solve_prompts_name_the_real_fields(self):
        # “结论”这类普通词在 solve 里也合法（指某篇文献的结论），只查属于别的模式的字段名与文件名。
        foreign = ("recommend", "novelty_score", "endorse", "confidence",
                   "approved_candidates", "adopted_conclusions",
                   "candidates.json", "conclusions.json")
        for name in self.RUNTIME_FILES:
            text = (self.root / "prompts/solve" / name).read_text(encoding="utf-8")
            self.assertNotIn("候选", text, msg=f"solve/{name} 出现 proposal 的词")
            for word in foreign:
                self.assertNotIn(word, text, msg=f"solve/{name} 引用了别的模式的 {word}")
        vote = (self.root / "prompts/solve/vote.md").read_text(encoding="utf-8")
        for field in ("evidence_urls", "preferred_solution", "value_score",
                      "soundness_score", "feasibility_score", "S01"):
            self.assertIn(field, vote)
        round1 = (self.root / "prompts/solve/round1.md").read_text(encoding="utf-8")
        self.assertIn("design_id", round1)
        self.assertIn("D-", round1)

    def test_solve_vote_prompt_literals_match_score_floor(self):
        # 这个文件不经渲染，分数线下限只能手写；改了 MODES 却忘了改提示词就会静默不一致。
        text = (self.root / "prompts/solve/vote.md").read_text(encoding="utf-8")
        for field, floor in d.MODES["solve"]["score_floor"].items():
            self.assertIn(f"{field} 至少 {floor} 分", text)
        self.assertIn(d.MODES["solve"]["urls_field"], text)
        self.assertIn(d.MODES["solve"]["preferred_field"], text)
        self.assertIn(d.MODES["solve"]["item_id_prefix"] + "01", text)
        self.assertIn(d.MODES["solve"]["item_id_prefix"] + "02", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
