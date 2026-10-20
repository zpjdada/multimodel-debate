"""Offline counterfactual tests; all model IDs, speeches and URLs below are synthetic."""
import copy
import json
from pathlib import Path
import shutil
import tempfile
import unittest

import debate_tools as d


FAKE_IDS = ["mock/family-a", "mock/family-b", "mock/family-c",
            "mock/family-d", "mock/family-e", "mock/family-f"]


class ToolsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        shutil.copy(d.ROOT / "roles.json", self.root / "roles.json")
        shutil.copy(d.ROOT / "protocol.json", self.root / "protocol.json")
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
        shutil.copy(d.ROOT / "roles.json", self.root / "roles.json")
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
        self.assertEqual(result["candidates"][0]["support"], 6)
        self.assertEqual(result["candidates"][0]["threshold"], "6/10")
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
        self.assertEqual(result["candidates"][0]["support"], 5)
        self.assertFalse(result["candidates"][0]["threshold_met"])
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

    def test_proposal_default_mode_when_field_absent(self):
        d.atomic_json(self.root / "protocol.json", {"rounds": 3})
        protocol = d.load_protocol(self.root, 10)
        self.assertEqual(protocol["mode"], "proposal")
        self.assertEqual(protocol["threshold"], {"numerator": 8, "denominator": 10})


if __name__ == "__main__":
    unittest.main(verbosity=2)
