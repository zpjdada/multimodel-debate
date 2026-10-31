#!/usr/bin/env python3
"""OpenCode debate setup and record audit. Standard library; no model API calls."""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent
SEAT_ID_RE = re.compile(r"a\d\d\Z")
MIN_RESPONSES = 2   # 互评/投票轮至少回应的其他席位数
MIN_SOURCES = 3     # 首轮至少核查的一手资料数
MAX_CANDIDATES = 5  # 归并后的固定候选上限
MIN_ROUNDS = 2      # 两轮是下限：独立提案 + 冻结后投票
MAX_ROUNDS = 4      # 再多轮也不改变“先冻结、后投票”的结构
DEFAULT_ROUNDS = 3  # 未提供 protocol.json 时的默认总轮数
PARTIAL_NOTE_RE = re.compile(r"首轮自述查重未完（retrieval_status=partial）：[^。]*。\s*")

# 三种模式共用同一套轮次、冻结、哈希与门槛检查，只有“一轮产出什么”和“票怎么算”不同。
# proposal：首轮各自提一个新方向，最后投票判断哪些候选值得优先做最小实验（要新意）。
# evaluate：首轮各自回答同一个问题，最后单选投票选出多数席位认可的结论（允许没有结论）。
# solve：首轮各自提一个可执行解法，最后多选投票选出多数席位认可、准备动手做的方案（不要求新意）。
# 提示词目录、目录文件名、票的字段名、门槛算法、以及各轮指令里那些随模式变化的句子全部放在这张表里：
# 运行器不再按模式名分支，加模式只需加一条表项和一整套提示词。
MODES = {
    "proposal": {
        "purpose": "找值得优先做最小实验的新方向",
        "source_prefix": "P-",          # 首轮产出编号前缀
        "source_id_field": "proposal_id",
        "source_key": "source_proposals",
        "excluded_key": "excluded_proposals",
        "items_key": "candidates",      # 目录里的固定条目键名
        "item_id_prefix": "K",
        "item_fields": ("title", "mechanism", "closest_work", "minimum_experiment",
                        "stop_condition", "source_proposals"),
        "urls_field": "closest_work_urls",
        "support_field": "recommend",
        "score_fields": ("novelty_score", "value_score", "feasibility_score"),
        "score_floor": {"novelty_score": 4, "value_score": 4, "feasibility_score": 3},
        "ballot_choice": False,          # 每个候选各投一票，可同时支持多个
        "preferred_field": "preferred_candidate",
        "approved_key": "approved_candidates",
        "catalog_file": "debate/candidates.json",
        "template": "templates/candidates.example.json",
        "prompts_dir": "prompts/proposal",
        "strict_majority": False,        # 八成席位愿意投入，才推进
        "default_ratio": 0.8,
        "noun": "候选",
        "round1_hint": "严格按其中要求完成第一轮独立检索与提案。",
        "merge_hint": "把首轮提案归并为",
        "source_noun": "提案",
        "merge_rule": ("中间轮的合并建议只能用于把已有首轮提案组合成候选；不得引入新的机制主张，"
                       "并要在候选里写清合并了哪几轮、哪些席位的哪条主张。"),
        "merge_closing": ("写完后只回复一行：CANDIDATES=<候选个数>。不要开始第 {vote_round} 轮。"),
        "deliberate_hint": ("如果你认为两个相近方案应当合并，就在正文和元数据里写明合并了哪些原提案；本轮不投票。"),
        "vote_hint": "投票前必须再做一次针对候选新意的检索，并在元数据里记录实际查询。",
        "final_verdict": "不得把未达 {bar} 的候选写成通过；有致命异议时先标待核查。",
        "final_extra": "要写清提案在中间轮里被如何修改或合并，以及投票前是否补做了新意检索。",
    },
    "evaluate": {
        "purpose": "对给定问题取多数认可的结论",
        "source_prefix": "S-",          # S = stance，首轮是立场而不是提案
        "source_id_field": "position_id",
        "source_key": "source_positions",
        "excluded_key": "excluded_positions",
        "items_key": "conclusions",
        "item_id_prefix": "C",
        "item_fields": ("statement", "reasoning", "evidence", "strongest_objection",
                        "what_would_change_it", "source_positions"),
        "urls_field": "evidence_urls",
        "support_field": "endorse",
        "score_fields": ("confidence",),
        "score_floor": {"confidence": 4},
        "ballot_choice": True,           # 单选：每个席位只认一个结论或 NONE
        "preferred_field": "preferred_conclusion",
        "approved_key": "adopted_conclusions",
        "catalog_file": "debate/conclusions.json",
        "template": "templates/conclusions.example.json",
        "prompts_dir": "prompts/evaluate",
        "strict_majority": True,         # 过半即达成，问题本身不需要投入资源
        "noun": "结论",
        "round1_hint": "严格按其中要求完成第一轮独立检索，并对 research_brief.md 里的问题给出你自己的立场。",
        "merge_hint": "把首轮立场归并为",
        "source_noun": "立场",
        "merge_rule": ("中间轮的互评只能用来把已有立场收窄成更精确的条件式或拆成互斥的两条；"
                       "不得引入任何席位都没提过的新论点。"),
        "merge_closing": ("每条结论必须互斥、可判真假；\"现有证据不足以判断\"若要保留，就单独写成一条结论，"
                          "不能塞进肯定结论的备注里。写完后只回复一行：CONCLUSIONS=<结论个数>。"
                          "不要开始第 {vote_round} 轮。"),
        "deliberate_hint": ("如果你要修改或收窄自己的立场，就在正文和元数据里写清改动与理由；本轮不投票。"),
        "vote_hint": "投票前必须再做一次针对性检索，并在元数据里记录实际查询。",
        "final_verdict": ("不得把未达 {bar} 的结论写成通过；票数分散在三条以上互斥结论上时，"
                          "明确写\"本轮没有形成多数认可的结论\"，不要挑票数最高的一条充当共识。"),
        "final_extra": "要写清各席位在中间轮里如何修改或收窄了自己的立场，以及投票前是否补做了检索。",
    },
    "solve": {
        "purpose": "对给定问题讨论出可执行的解决方案",
        "source_prefix": "D-",          # D = design，首轮是初步解法而不是提案
        "source_id_field": "design_id",
        "source_key": "source_designs",
        "excluded_key": "excluded_designs",
        "items_key": "solutions",
        "item_id_prefix": "S",
        "item_fields": ("title", "claim", "mechanism", "evidence", "preconditions",
                        "main_risk", "source_designs"),
        "urls_field": "evidence_urls",
        "support_field": "adopt",
        "score_fields": ("value_score", "soundness_score", "feasibility_score"),
        "score_floor": {"value_score": 4, "soundness_score": 4, "feasibility_score": 3},
        "ballot_choice": False,          # 一个问题可以有多个并行可用的方案
        "preferred_field": "preferred_solution",
        "approved_key": "adopted_solutions",
        "catalog_file": "debate/solutions.json",
        "template": "templates/solutions.example.json",
        "prompts_dir": "prompts/solve",
        "strict_majority": False,        # 采纳一个方案是要动手做的决定，门槛与 proposal 相同
        "default_ratio": 0.8,
        "noun": "方案",
        "round1_hint": "严格按其中要求完成第一轮独立检索，并对 research_brief.md 里的问题提出你自己的初步解法。",
        "merge_hint": "把首轮初步解法归并为",
        "source_noun": "初步解法",
        "merge_rule": ("中间轮的合并建议只能用于把已有初步解法组合、拆开或收窄；不得引入任何席位都没提过的新解法，"
                       "并要写清合并了哪几轮、哪些席位的哪条主张。"),
        "merge_closing": ("每条方案必须写清它在什么条件下成立、以及明确不解决什么；"
                          "只在边角细节上不同的两条要合并成一条。写完后只回复一行：SOLUTIONS=<方案个数>。"
                          "不要开始第 {vote_round} 轮。"),
        "deliberate_hint": ("如果你认为两条相近解法应当合并、或自己的解法已被更好的覆盖，"
                            "就在正文和元数据里写清；本轮不投票。"),
        "vote_hint": ("投票前必须再做一次针对性检索，确认你最认同的方案在 research_brief.md 写明的约束下确实做得到，"
                      "并在元数据里记录实际查询。"),
        "final_verdict": ("不得把未达 {bar} 的方案写成已采纳；多条方案同时达到门槛时，写清各自适用的条件与代价，"
                          "不要合成一条谁都没提过的\"综合方案\"。"),
        "final_extra": ("要写清各方案在中间轮里被如何修改、合并或放弃，以及投票前是否补做了针对可行性的检索。"),
    },
}


def mode_of(protocol):
    return MODES[protocol.get("mode", "proposal")]


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def atomic_text(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n",
                                     dir=path.parent, delete=False) as f:
        temp = Path(f.name)
        f.write(text)
    try:
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def atomic_json(path, value):
    atomic_text(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def parse_inventory(text):
    text = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", text)
    found = []
    for line in text.lstrip("\ufeff").splitlines():
        s = line.strip()
        if re.fullmatch(r"[^\s/]+/[^\s]+", s) and not s.startswith(("http:", "https:")):
            if s not in found:
                found.append(s)
    if not found:
        raise ValueError("未读到 provider/model 格式的模型 ID。请用 opencode models 的输出。")
    return found


def find_cli(explicit=None):
    if explicit:
        return str(explicit)
    for name in ("opencode", "opencode-cli"):
        found = shutil.which(name)
        if found:
            return unwrap_shim(found)
    return None


def unwrap_shim(path):
    """`cmd /c foo.cmd` 会破坏含引号/换行的参数（JSON 元数据就是这种）。

    PATH 上的 opencode 常常只是个转发到真实 exe 的 .cmd，这里读它指向的 exe，
    直接 exec，绕开 cmd 的引号处理。找不到就返回原路径。
    """
    candidate = Path(path)
    if candidate.suffix.lower() not in (".cmd", ".bat"):
        return str(candidate)
    try:
        text = candidate.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return str(candidate)
    found = re.findall(r'"([^"\r\n]+\.exe)"', text, flags=re.I)
    if len(found) == 1 and Path(found[0]).exists():
        return found[0]
    return str(candidate)


def run_cli(executable, args, cwd, timeout=90):
    command = [executable, *args]
    if Path(executable).suffix.lower() in (".cmd", ".bat"):
        command = ["cmd", "/c", *command]
    return subprocess.run(command, cwd=cwd, text=True, encoding="utf-8",
                          errors="replace", capture_output=True, timeout=timeout, check=False)


def inventory(root, source=None, executable=None):
    if source:
        return parse_inventory(Path(source).read_text(encoding="utf-8-sig"))
    executable = find_cli(executable)
    if not executable:
        raise ValueError("找不到 opencode 命令。可先在 PowerShell 执行 opencode models | Set-Content -Encoding utf8 models.txt，再用 --inventory models.txt。")
    result = run_cli(executable, ["models"], root)
    if result.returncode:
        raise ValueError("opencode models 执行失败；请先在同一目录确认此命令能列出你已配置的模型。")
    return parse_inventory(result.stdout)


def seat_ids(count):
    """席位 1..count 的零填充 ID；十席时正好是 a01–a10，保留旧行为。"""
    return [f"a{i:02d}" for i in range(1, count + 1)]


def family_token(family):
    """family_a -> familya：只留小写字母与数字，用于在模型 ID 里找候选。"""
    return re.sub(r"[^a-z0-9]", "", family.lower())


def families_of(roles):
    return list(dict.fromkeys(r["family"] for r in roles))


def chair_of(roles):
    chairs = [r for r in roles if r.get("chair")]
    if len(chairs) != 1:
        raise ValueError("roles.json 必须恰好有一个席位标有 \"chair\": true。")
    return chairs[0]["id"]


def default_protocol(seats, mode="proposal"):
    """未提供 protocol.json（或未写 threshold）时的默认门槛，按模式取。

    strict_majority 的模式（evaluate）只要过半席位认同就算达成，因为那里问的是“大家怎么看”，
    不是“值不值得投入资源”。proposal 与 solve 都要动手：一个候选要八成席位愿意先做才推进。
    """
    spec = MODES[mode]
    if spec["strict_majority"]:
        numerator = seats // 2 + 1
    else:
        numerator = max(1, round(seats * spec["default_ratio"]))
    return {"mode": mode, "rounds": DEFAULT_ROUNDS,
            "threshold": {"numerator": numerator, "denominator": seats}}


def load_protocol(root, seats):
    path = root / "protocol.json"
    protocol = read_json(path) if path.exists() else default_protocol(seats)
    mode = protocol.get("mode", "proposal")
    if mode not in MODES:
        raise ValueError("protocol.json 的 mode 应为 " + " / ".join(sorted(MODES))
                         + "：proposal 找新方向，evaluate 对给定问题取多数结论，solve 对给定问题讨论解决方案。")
    rounds = protocol.get("rounds")
    if type(rounds) is not int or not MIN_ROUNDS <= rounds <= MAX_ROUNDS:
        raise ValueError(f"protocol.json 的 rounds 应为 {MIN_ROUNDS}–{MAX_ROUNDS} 的整数；"
                         "最后一轮投票，之前各轮是检索与互评。")
    threshold = protocol.get("threshold") or {}
    numerator, denominator = threshold.get("numerator"), threshold.get("denominator")
    if numerator is None and denominator is None:
        # 允许只写 mode 和 rounds，门槛按模式推默认值；写了一半仍然报错，免得半截配置悄悄生效。
        return default_protocol(seats, mode) | {"rounds": rounds}
    if type(numerator) is not int or type(denominator) is not int:
        raise ValueError("protocol.json 的 threshold 需要整数 numerator 与 denominator。")
    if denominator != seats:
        raise ValueError("protocol.json 的分母必须等于席位数；固定分母是为了让缺席不能降低门槛。")
    if not 1 <= numerator <= denominator:
        raise ValueError("protocol.json 的 threshold 分子应在 1 到席位数之间。")
    return {"mode": mode, "rounds": rounds,
            "threshold": {"numerator": numerator, "denominator": denominator}}


def suggestions(ids, roles):
    return {family: [model for model in ids if family_token(family) in
                     re.sub(r"[^a-z0-9]", "", model.split("/", 1)[1].lower())]
            for family in families_of(roles)}


def resolve_models(ids, roles, supplied=None, interactive=False, input_fn=input):
    supplied = supplied or {}
    # 一个系列的所有席位都用了席位级 model 覆盖时，不需要再为该系列映射 ID。
    families = [f for f in families_of(roles)
                if any(not r.get("model") for r in roles if r["family"] == f)]
    if set(supplied) - set(families):
        raise ValueError("model_map.json 有 roles.json 中没有的模型系列键。")
    choices = suggestions(ids, roles)
    output = {}
    for family in families:
        chosen = supplied.get(family)
        candidates = choices[family]
        if chosen is None and len(candidates) == 1:
            chosen = candidates[0]
        if chosen is None and interactive:
            shown = candidates or ids
            print("\n请选择 " + family + " 的实际模型 ID：")
            for n, model in enumerate(shown, 1):
                print("  " + str(n) + ". " + model)
            answer = input_fn("输入序号或完整 provider/model ID：").strip()
            if answer.isdigit() and 1 <= int(answer) <= len(shown):
                chosen = shown[int(answer) - 1]
            else:
                chosen = answer
        if not isinstance(chosen, str) or chosen not in ids:
            raise ValueError(f"{family} 无法唯一确定。请从实际模型列表选择，填入 model_map.json；不能猜测或默认用其他模型。候选：{candidates}")
        output[family] = chosen
    if len(set(output.values())) != len(families):
        raise ValueError("每个模型系列必须映射到不同的实际模型 ID；同系列的多席位会自动复用该系列 ID。")
    return output


def load_roster(root):
    roles = read_json(root / "roles.json")
    if not isinstance(roles, list) or len(roles) < 3:
        raise ValueError("roles.json 至少需要三个席位（互评要求回应两个其他席位）。")
    ids = [r.get("id") for r in roles]
    if ids != seat_ids(len(roles)):
        raise ValueError(f"roles.json 的席位必须是从 a01 开始连续的 ID，共 {len(roles)} 个；实际为 {ids}。")
    if any(not isinstance(r.get("family"), str) or not r["family"].strip() for r in roles):
        raise ValueError("每个席位必须有非空的模型系列 family；允许所有席位使用同一系列。")
    for role in roles:
        if not role.get("role") or not role.get("focus"):
            raise ValueError(role.get("id", "?") + " 缺少 role 或 focus。")
        override = role.get("model")
        # 席位级覆盖：同系列的两个席位可以用不同 ID，但必须是完整 provider/model，不能只写展示名。
        if override is not None and (not isinstance(override, str) or "/" not in override):
            raise ValueError(role.get("id", "?") + " 的 model 应写成完整的 provider/model ID，"
                             "或直接省略以使用 family 在 model_map.json 中的映射。")
    chair_of(roles)
    load_protocol(root, len(roles))
    return roles


MEMBER_STEPS = 50
CHAIR_STEPS = 240


def rules(entries):
    return [{"action": action, "resource": resource, "effect": effect}
            for action, resource, effect in entries]


def member_permissions(search=True):
    # 先写在 agent 规则前，读 *.env 仍要确认；最后一条命中者生效。
    entries = [
        ("read", "*", "allow"),
        ("read", "*.env", "ask"),
        ("read", "*.env.*", "ask"),
        ("read", "*.env.example", "allow"),
        ("glob", "*", "allow"),
        ("grep", "*", "allow"),
        ("websearch", "*", "allow" if search else "deny"),
        ("webfetch", "*", "allow"),
        ("skill", "*", "allow"),
        ("edit", "*", "deny"),
        ("shell", "*", "deny"),
        ("subagent", "*", "deny"),
        ("question", "*", "deny"),
    ]
    return rules(entries)


def chair_permissions(roles, search=True):
    # edit 只放行讨论记录目录；python 审核命令按命令文本精确放行。
    entries = [
        ("read", "*", "allow"),
        ("read", "*.env", "ask"),
        ("read", "*.env.*", "ask"),
        ("read", "*.env.example", "allow"),
        ("glob", "*", "allow"),
        ("grep", "*", "allow"),
        ("websearch", "*", "allow" if search else "deny"),
        ("webfetch", "*", "allow"),
        ("skill", "*", "allow"),
        ("edit", "*", "deny"),
        ("edit", "debate/**", "allow"),
        ("edit", "debate", "allow"),
        ("shell", "*", "deny"),
        ("shell", "*debate_tools.py*", "allow"),
        ("subagent", "*", "deny"),
    ]
    entries += [("subagent", "debate-" + r["id"], "allow")
                for r in roles if r["id"] != chair_of(roles)]
    return rules(entries)


def chinese_number(value):
    """1–99 的中文写法；席位多时退化为阿拉伯数字，不编造更大的数词。"""
    digits = "零一二三四五六七八九"
    if not 0 <= value < 100:
        return str(value)
    if value < 10:
        return digits[value]
    tens, ones = divmod(value, 10)
    head = "" if tens == 1 else digits[tens]
    return head + "十" + (digits[ones] if ones else "")


def render_template(text, values):
    for key, value in values.items():
        text = text.replace("{{" + key + "}}", str(value))
    leftover = re.findall(r"\{\{[A-Z_]+\}\}", text)
    if leftover:
        raise ValueError("提示词里有未替换的占位符：" + ", ".join(sorted(set(leftover))))
    return text


def prompt_values(roles, protocol):
    chair = chair_of(roles)
    others = [r for r in roles if r["id"] != chair]
    threshold = protocol["threshold"]
    mode = mode_of(protocol)
    return {
        "SEAT_COUNT": len(roles),
        "SEAT_COUNT_CN": chinese_number(len(roles)),
        "NEXT_SEAT_CN": chinese_number(len(roles) + 1),
        "SEAT_IDS": "、".join(r["id"] for r in roles),
        "CHAIR": chair,
        "OTHER_COUNT": len(others),
        "OTHER_COUNT_CN": chinese_number(len(others)),
        "AGENT_NAMES": "、".join("debate-" + r["id"] for r in others),
        "MIN_RESPONSES": MIN_RESPONSES,
        "MIN_RESPONSES_CN": chinese_number(MIN_RESPONSES),
        "MIN_SOURCES": MIN_SOURCES,
        "MIN_SOURCES_CN": chinese_number(MIN_SOURCES),
        "MAX_CANDIDATES": MAX_CANDIDATES,
        "THRESHOLD": f"{threshold['numerator']}/{threshold['denominator']}",
        "THRESHOLD_NUM": threshold["numerator"],
        "ROUNDS": protocol["rounds"],
        "ROUNDS_CN": chinese_number(protocol["rounds"]),
        "DELIBERATION_COUNT": protocol["rounds"] - 1,
        "DELIBERATION_COUNT_CN": chinese_number(protocol["rounds"] - 1),
        "VOTE_ROUND": protocol["rounds"],
        "VOTE_ROUND_CN": chinese_number(protocol["rounds"]),
        # 以下按模式取值：提示词里不写死“候选/结论”“K01/C01”或文件名，换模式时同一份骨架仍然成立。
        "MODE": protocol.get("mode", "proposal"),
        "MODE_PURPOSE": mode["purpose"],
        "NOUN": mode["noun"],
        "ITEM_PREFIX": mode["item_id_prefix"],
        "SOURCE_PREFIX": mode["source_prefix"],
        "SOURCE_ID_FIELD": mode["source_id_field"],
        "SOURCE_KEY": mode["source_key"],
        "URLS_FIELD": mode["urls_field"],
        "SUPPORT_FIELD": mode["support_field"],
        "SCORE_FIELDS": "、".join(mode["score_fields"]),
        "SCORE_FLOOR_TEXT": "、".join(f"{f} 至少 {v} 分" for f, v in mode["score_floor"].items()),
        "CONFIDENCE_FLOOR": mode["score_floor"].get("confidence", ""),
        "PREFERRED_FIELD": mode["preferred_field"],
        "CATALOG_FILE": mode["catalog_file"],
        "CATALOG_TEMPLATE": mode["template"],
        "PROMPTS_DIR": mode["prompts_dir"],
    }


def make_config(root, mapping, search=True, protocol=None):
    roles = load_roster(root)
    protocol = protocol or load_protocol(root, len(roles))
    mode = mode_of(protocol)
    prompts = root / mode["prompts_dir"]
    values = prompt_values(roles, protocol)
    # 每种模式一套完整提示词：共用一份再打补丁会让另一模式的措辞渗进来，读起来自相矛盾。
    for name in ("member.md", "chair.md", "start.md", "round1.md", "deliberate.md", "vote.md"):
        if not (prompts / name).exists():
            raise ValueError("缺少 " + str(prompts / name) + "：该模式的提示词不完整，请检查安装目录。")
    # member.md 与 chair.md 会被渲染进 system prompt；其余四个由操作代理或席位直接读磁盘，
    # 程序不会替它们替换占位符，写进去就会原样落到提示词里。这里提前拦住。
    for name in ("start.md", "round1.md", "deliberate.md", "vote.md"):
        text = (prompts / name).read_text(encoding="utf-8-sig")
        left = sorted(set(re.findall(r"\{\{[A-Z_]+\}\}", text)))
        if left:
            raise ValueError(str(prompts / name) + " 里还有未渲染的占位符 " + "、".join(left)
                             + "：该文件由席位直接读取，只能写具体措辞。")
    common = render_template((prompts / "member.md").read_text(encoding="utf-8"), values)
    chair = render_template((prompts / "chair.md").read_text(encoding="utf-8"), values)
    chair_id = chair_of(roles)
    chair_role = next(r for r in roles if r["id"] == chair_id)
    agents, locked = {}, []
    for role in roles:
        is_chair = role["id"] == chair_id
        name = "debate-chair" if is_chair else "debate-" + role["id"]
        model = role.get("model") or mapping[role["family"]]
        identity = (f"你的席位 ID 是 {role['id']}，角色是 {role['role']}。\n"
                    f"你的研究切入点：{role['focus']}\n配置模型 ID：{model}。这只是配置标识，不得声称验证了中转背后的实际权重。\n")
        agents[name] = {
            "description": role["role"] + "；仅用于多模型科研辩论的 " + role["id"],
            "mode": "primary" if is_chair else "subagent",
            "model": model,
            "steps": CHAIR_STEPS if is_chair else MEMBER_STEPS,
            "system": identity + "\n" + common + ("\n" + chair if is_chair else ""),
            "permissions": chair_permissions(roles, search) if is_chair else member_permissions(search),
        }
        locked.append({**role, "agent_name": name, "model": model})
    config = {"$schema": "https://opencode.ai/config.json", "default_agent": "debate-chair",
              "model": mapping[chair_role["family"]],
              "agents": agents,
              "commands": {"debate-start": {
                   "description": f"由外层操作代理启动{values['SEAT_COUNT_CN']}席位{values['ROUNDS_CN']}轮科研讨论",
                   "agent": "build", "subagent": False,
                   "template": f"你是外层操作代理，不是正式讨论席位。请读取 {mode['prompts_dir']}/start.md，按其内容调用驱动完成讨论。"}}}
    return config, locked


def protocol_for_mode(root, mode):
    """按模式算出目标 protocol 内容，不落盘。setup 先拿它校验提示词，最后才写。

    门槛算法按模式不同：proposal 与 solve 要八成席位都愿意动手，
    evaluate 只要求过半席位认同同一条结论。沿用旧阈值会让新模式实际上得不出结论。
    但模式没变时不重算：那时手写的门槛是用户自己定的，重复 setup 不该把它抹掉。
    """
    if mode not in MODES:
        raise ValueError("--mode 应为 " + " / ".join(sorted(MODES)) + "。")
    roles = load_roster(root)
    path = root / "protocol.json"
    current = read_json(path) if path.exists() else {}
    if current.get("mode", "proposal") == mode and "threshold" in current:
        return load_protocol(root, len(roles))
    rounds = current.get("rounds", DEFAULT_ROUNDS)
    return default_protocol(len(roles), mode) | {"rounds": rounds}


def set_mode(root, mode):
    """切换模式并写回 protocol.json；只给单独改模式的命令行用。"""
    target = protocol_for_mode(root, mode)
    atomic_json(root / "protocol.json", target)
    return target


def check_fresh(root):
    for filename in ("opencode.json", "opencode.jsonc", "roster.lock.json"):
        if (root / filename).exists():
            raise ValueError(f"{filename} 已存在。请在新解压的专用目录配置，避免覆盖已有 OpenCode 配置或辩论。")


def setup(root, ids, supplied=None, interactive=False, search=True, mode=None):
    # 先把所有能失败的事情做完，最后才写文件。否则 `setup --mode solve` 被拒或映射
    # 校验失败时，目录里会留下新 protocol.json 与旧 opencode.json/roster.lock.json。
    check_fresh(root)
    roles = load_roster(root)
    unknown = [r for r in roles if r.get("model") and r["model"] not in ids]
    if unknown:
        # 覆盖 ID 必须真实存在；猜一个不存在的 ID 只会在开跑后整席失败。
        raise ValueError("这些席位的 model 不在本机 opencode models 列表中："
                         + "、".join(f"{r['id']}={r['model']}" for r in unknown))
    mapping = resolve_models(ids, roles, supplied, interactive)
    # 新模式只在这里算出来，不落盘：提示词缺失时 setup 会失败，而 protocol.json 应当保持原样。
    protocol = protocol_for_mode(root, mode) if mode else load_protocol(root, len(roles))
    config, locked = make_config(root, mapping, search, protocol)
    if mode:
        path = root / "protocol.json"
        current = read_json(path) if path.exists() else {}
        # 内容没变就不落盘，模式没变时手写门槛与该文件保持原样；额外键也一并保留。
        if current.get("mode", "proposal") != protocol["mode"] or current.get("threshold") != protocol["threshold"]:
            atomic_json(path, protocol | {k: v for k, v in current.items() if k not in protocol})
    atomic_json(root / "model_map.json", mapping)
    atomic_json(root / "roster.lock.json", {"seats": locked, "search": bool(search), "protocol": protocol})
    atomic_json(root / "opencode.json", config)
    return locked


def metadata(text):
    blocks = re.findall(r"```json\s*\n?(.*?)```", text, flags=re.S)
    for block in reversed(blocks):
        try:
            value = json.loads(block)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict) and "agent_id" in value and "round" in value:
            return value
    raise ValueError("发言缺少末尾有效 JSON 元数据。")


def read_round(root, number, ids):
    directory = root / "debate" / f"round{number}"
    files = {p.stem: p for p in directory.glob("*.md")}
    if set(files) != set(ids):
        raise ValueError(f"第 {number} 轮记录不完整或有额外席位：缺少 {sorted(set(ids)-set(files))}，多出 {sorted(set(files)-set(ids))}")
    output = {}
    for agent_id in ids:
        text = files[agent_id].read_text(encoding="utf-8-sig")
        meta = metadata(text)
        if meta.get("agent_id") != agent_id or type(meta.get("round")) is not int or meta["round"] != number:
            raise ValueError(f"{files[agent_id].name} 的席位或轮次不一致。")
        output[agent_id] = {"text": text, "metadata": meta}
    return output


def is_url(value):
    return isinstance(value, str) and value.startswith(("https://", "http://"))


def _check_deliberation(root, number, ids):
    """中间轮：必须互相回应，并留下本轮真实检索过的查询与近邻 URL。"""
    mode = mode_of(load_protocol(root, len(ids)))
    speeches = read_round(root, number, ids)
    for agent_id, record in speeches.items():
        meta = record["metadata"]
        responses = meta.get("responses", [])
        targets = {r.get("to_agent") for r in responses}
        if not targets.issubset(set(ids)):
            raise ValueError(f"{agent_id} 第 {number} 轮回应了不存在的席位："
                             + "、".join(sorted(str(t) for t in targets - set(ids))))
        # 对自己的条目是自我修订，不是回应他人：允许保留，但不计入互评数量。
        if len(targets - {agent_id}) < MIN_RESPONSES:
            raise ValueError(f"{agent_id} 第 {number} 轮需要实质回应至少 {MIN_RESPONSES} 个其他席位。")
        for response in responses:
            if response.get("stance") not in ("support", "oppose", "modify") or not response.get("claim"):
                raise ValueError(f"{agent_id} 第 {number} 轮的互评缺少明确主张或立场。")
        queries = meta.get("searched_queries", [])
        if not isinstance(queries, list) or len([q for q in queries if isinstance(q, str) and q.strip()]) < 2:
            raise ValueError(f"{agent_id} 第 {number} 轮没有记录至少两条实际检索过的查询；"
                             "这一轮不允许只凭记忆评审。")
        urls = meta.get(mode["urls_field"], [])
        if not isinstance(urls, list) or not urls or not all(is_url(u) for u in urls):
            raise ValueError(f"{agent_id} 第 {number} 轮缺少至少一个实际核查过的 "
                             + mode["urls_field"] + " URL。")
    return speeches


def packet_data(root):
    lock = read_json(root / "roster.lock.json")
    roles = lock["seats"]
    ids = [r["id"] for r in roles]
    if ids != seat_ids(len(roles)):
        raise ValueError("席位表必须是从 a01 起连续的 ID。")
    # 门槛进哈希：冻结后改 protocol.json 会改变 digest，audit 会拒绝。否则可以先投票再降门槛。
    protocol = load_protocol(root, len(roles))
    mode = mode_of(protocol)
    if lock.get("protocol") and lock["protocol"] != protocol:
        raise ValueError("roster.lock.json 的 protocol 与 protocol.json 不一致；请重新运行 setup。")
    if not lock.get("protocol"):
        raise ValueError("roster.lock.json 缺少 protocol（旧版 setup 生成）；请重新运行 setup。")
    config = read_json(root / "opencode.json")
    if "agent" in config or "command" in config or "permission" in config:
        raise ValueError("opencode.json 仍是 V1 形状（agent/command/permission）。请重新运行 setup 生成 V2 原生配置。")
    chair_id = chair_of(roles)
    for role in roles:
        configured = config.get("agents", {}).get(role["agent_name"], {})
        expected_mode = "primary" if role["id"] == chair_id else "subagent"
        if configured.get("model") != role["model"] or configured.get("mode") != expected_mode:
            raise ValueError(role["id"] + " 的项目配置与冻结席位表不一致。")
    vote_round = protocol["rounds"]
    speeches = read_round(root, 1, ids)
    partial = []
    for agent_id, record in speeches.items():
        meta = record["metadata"]
        # partial 表示席位自查后声明查重没做完；允许入档，但必须在 audit 里显式列名，不能静默当成完成。
        if (meta.get(mode["source_id_field"]) != mode["source_prefix"] + agent_id
                or meta.get("retrieval_status") not in ("completed", "partial")):
            raise ValueError(agent_id + " 的编号或检索完成状态无效（应为 "
                             + mode["source_prefix"] + " 前缀、completed 或 partial）。")
        if meta.get("retrieval_status") == "partial":
            partial.append(agent_id)
        urls = meta.get(mode["urls_field"], [])
        if not isinstance(urls, list) or len(set(urls)) < MIN_SOURCES or not all(is_url(u) for u in urls):
            raise ValueError(f"{agent_id} 缺少至少 {MIN_SOURCES} 个不同的论文/一手资料 URL。URL 结构检查不代表已验证内容。")
    deliberation = {"1": speeches}
    for number in range(2, vote_round):
        deliberation[str(number)] = _check_deliberation(root, number, ids)
    catalog_path = root / mode["catalog_file"]
    if not catalog_path.exists():
        raise ValueError("缺少 " + mode["catalog_file"] + "：主持席还没有归并" + mode["noun"]
                         + "；格式参考 " + mode["template"] + "。")
    catalog = read_json(catalog_path)
    # scope_note 由首轮实际状态派生，不靠席位自填。旧句子先剥掉再写当前事实，重复运行既不会叠加也不会留过期名单。
    note = "首轮自述查重未完（retrieval_status=partial）：" + ", ".join(partial) + "。" if partial else ""
    scope = PARTIAL_NOTE_RE.sub("", catalog.get("scope_note") or "").strip()
    catalog["scope_note"] = (scope + " " + note).strip() if note else scope
    if catalog.get("scope_note") != (read_json(catalog_path).get("scope_note") or ""):
        atomic_json(catalog_path, catalog)
    items = catalog.get(mode["items_key"], [])
    if not 1 <= len(items) <= MAX_CANDIDATES:
        raise ValueError(f"{mode['catalog_file']} 应包含 1–{MAX_CANDIDATES} 个固定{mode['noun']}。")
    item_ids = [c.get("id") for c in items]
    if item_ids != [f"{mode['item_id_prefix']}{i:02d}" for i in range(1, len(items)+1)]:
        raise ValueError(f"{mode['noun']}编号应连续为 {mode['item_id_prefix']}01、{mode['item_id_prefix']}02……，不能重复。")
    covered = set()
    for item in items:
        for key in mode["item_fields"]:
            if not item.get(key):
                raise ValueError(item["id"] + " 缺少 " + key)
        covered.update(item[mode["source_key"]])
    excluded = catalog.get(mode["excluded_key"], [])
    excluded_ids = set()
    for entry in excluded:
        if not entry.get("reason"):
            raise ValueError("被排除的首轮" + mode["source_noun"] + "必须记录理由。")
        excluded_ids.add(entry.get(mode["source_id_field"]))
    sources = {mode["source_prefix"] + agent_id for agent_id in ids}
    if covered & excluded_ids or covered | excluded_ids != sources:
        raise ValueError(f"{len(ids)} 个首轮产出必须全部被保留/合并或说明排除理由，不得静默遗漏。")
    brief_path = root / "research_brief.md"
    if not brief_path.exists():
        raise ValueError("缺少 research_brief.md：先把你自己的题目背景写进去（可复制 research_brief.example.md 作为格式参考）。")
    brief = brief_path.read_text(encoding="utf-8-sig")
    return {"roster": roles, "protocol": protocol, "research_brief": brief, "round1": speeches,
            "deliberation": deliberation, "catalog": catalog, "retrieval_partial_seats": partial}


def fingerprint(data):
    raw = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def render_packet(data, digest):
    mode = mode_of(data["protocol"])
    threshold = data["protocol"]["threshold"]
    rounds = data["protocol"]["rounds"]
    text = "# 投票轮统一资料包\n\npacket_sha256: " + digest + "\n\n"
    text += ("投票门槛：{numerator}/{denominator}（分母为席位数，缺席不降低门槛）。\n\n"
             .format(**threshold))
    text += (f"本轮是第 {rounds} 轮（最后一轮），投票对象是冻结后的{mode['noun']}。"
             f"前 {rounds - 1} 轮的全部原文一并附上，供你核对每条{mode['noun']}是否被忠实转述。\n\n")
    if mode["ballot_choice"]:
        text += ("以下" + mode["noun"] + "定义和全部原始发言是本轮统一投票对象。"
                 "每个席位只能选一条" + mode["noun"] + "或 NONE，不能同时认两条；"
                 "投票后不得替换" + mode["noun"] + "。\n\n")
    else:
        text += ("以下" + mode["noun"] + "定义和全部原始发言是本轮统一投票对象。"
                 "每个席位对每条" + mode["noun"] + "各投一票，可以同时认同多条；"
                 "投票后不得替换" + mode["noun"] + "。\n\n")
    text += "## " + mode["noun"] + "目录\n\n"
    text += "```json\n" + json.dumps(data["catalog"], ensure_ascii=False, indent=2) + "\n```\n\n"
    for number, speeches in data["deliberation"].items():
        for agent_id, record in speeches.items():
            text += f"\n---\n\n## 第 {number} 轮原文：{agent_id}\n\n" + record["text"] + "\n"
    return text


def freeze(root):
    data = packet_data(root)
    mode = mode_of(data["protocol"])
    digest = fingerprint(data)
    vote_round = data["protocol"]["rounds"]
    path = root / "debate/packet_manifest.json"
    if path.exists() and read_json(path).get("packet_sha256") != digest:
        raise ValueError(f"{mode['noun']}、背景或既有轮次记录已改变。不能在同一轮中替换投票对象；请为新版本开新目录。")
    if not path.exists() and any((root / f"debate/round{vote_round}").glob("*.md")):
        raise ValueError(f"已有第 {vote_round} 轮发言却没有冻结记录，不能事后补建投票版本。")
    manifest = {"packet_sha256": digest, "mode": data["protocol"].get("mode", "proposal"),
                "candidate_ids": [c["id"] for c in data["catalog"][mode["items_key"]]],
                "agent_ids": [r["id"] for r in data["roster"]], "protocol": data["protocol"],
                "vote_round": vote_round}
    atomic_text(root / "debate/vote_packet.md", render_packet(data, digest))
    atomic_json(path, manifest)
    return manifest


def audit(root):
    data = packet_data(root)
    mode = mode_of(data["protocol"])
    manifest = read_json(root / "debate/packet_manifest.json")
    digest = fingerprint(data)
    if digest != manifest.get("packet_sha256"):
        raise ValueError("投票资料被改动；本轮票数不能用于修改后的" + mode["noun"] + "。")
    packet = (root / "debate/vote_packet.md").read_text(encoding="utf-8-sig")
    if packet != render_packet(data, digest):
        raise ValueError("投票轮实际读取的资料包内容被改动。")
    ids = [r["id"] for r in data["roster"]]
    noun = mode["noun"]
    candidates = manifest["candidate_ids"]
    if manifest.get("mode", "proposal") != data["protocol"].get("mode", "proposal"):
        raise ValueError("冻结清单的模式与当前 protocol.json 不一致；请为新模式重新 setup。")
    if candidates != [c["id"] for c in data["catalog"][mode["items_key"]]] or set(manifest["agent_ids"]) != set(ids):
        raise ValueError("冻结清单与" + noun + "/席位不一致。")
    if manifest.get("protocol") != data["protocol"]:
        raise ValueError("冻结清单里的门槛/轮数与当前 protocol.json 不一致。")
    vote_round = data["protocol"]["rounds"]
    if manifest.get("vote_round") != vote_round:
        raise ValueError("冻结清单没有记录投票轮次；请重新 freeze。")
    rounds = read_round(root, vote_round, ids)
    rows = []
    for agent_id, record in rounds.items():
        meta = record["metadata"]
        if meta.get("packet_sha256") != digest:
            raise ValueError(agent_id + " 投票使用了不同版本的资料。")
        queries = meta.get("searched_queries", [])
        if not isinstance(queries, list) or len([q for q in queries if isinstance(q, str) and q.strip()]) < 2:
            raise ValueError(agent_id + " 投票前没有记录至少两条实际检索过的查询；"
                             "投票轮不能只凭记忆判断。")
        responses = meta.get("responses", [])
        targets = {r.get("to_agent") for r in responses}
        if not targets.issubset(set(ids)):
            raise ValueError(agent_id + " 回应了不存在的席位："
                             + "、".join(sorted(str(t) for t in targets - set(ids))))
        if len(targets - {agent_id}) < MIN_RESPONSES:
            raise ValueError(f"{agent_id} 需要实质回应至少 {MIN_RESPONSES} 个其他席位。")
        for response in responses:
            if response.get("stance") not in ("support", "oppose", "modify") or not response.get("claim"):
                raise ValueError(agent_id + " 的互评缺少明确主张或立场。")
        votes = meta.get("votes", [])
        if len(votes) != len(candidates) or {v.get("candidate_id") for v in votes} != set(candidates):
            raise ValueError(agent_id + " 必须对每个固定" + noun + "逐一表态，不能重复或遗漏。")
        supported = set()
        support_field = mode["support_field"]
        for vote in votes:
            if type(vote.get(support_field)) is not bool or type(vote.get("unresolved_fatal_objection")) is not bool:
                raise ValueError(agent_id + " 的" + support_field + "与严重异议字段必须为布尔值。")
            for field in mode["score_fields"]:
                if type(vote.get(field)) is not int or not 1 <= vote[field] <= 5:
                    raise ValueError(agent_id + " 的 " + field + " 应为 1–5 整数。")
            if not vote.get("reason"):
                raise ValueError(agent_id + " 的每张票必须有理由。")
            if vote[support_field]:
                urls = vote.get(mode["urls_field"], [])
                low = [f for f in mode["score_fields"] if f in mode["score_floor"]
                       and vote[f] < mode["score_floor"][f]]
                if low or vote["unresolved_fatal_objection"] or not urls or not all(is_url(u) for u in urls):
                    raise ValueError(agent_id + " 的赞同票与其评分、引用或严重异议互相矛盾"
                                     + ("（" + "、".join(low) + " 未达下限）" if low else "") + "。")
                supported.add(vote["candidate_id"])
            rows.append({"agent_id": agent_id, **vote})
        if mode["ballot_choice"] and len(supported) > 1:
            # evaluate 是单选题：每个席位只认一个结论，否则同一个人可以同时支持互斥的两条，
            # “多数人认可的结论”就没法定义。
            raise ValueError(agent_id + " 同时认可了多个" + noun
                             + "（" + "、".join(sorted(supported)) + "）；本轮只能在一条" + noun
                             + "与 NONE 之间选一个。")
        # 两种模式都查：首选必须与自己的票一致。单一手写字段不参与计票，但它是下一版建议
        # 唯一的结构化入口，和 endorse 矛盾时不报错，报告就会引用一个当事人并未投过的选择。
        # 有认可项时首选必须是其中之一；没有认可项时只能写 NONE（写成某条等于默认推荐它）。
        preferred = meta.get(mode["preferred_field"])
        if preferred not in (supported or {"NONE"}):
            raise ValueError(agent_id + " 的 " + mode["preferred_field"] + " 必须是自己"
                             + ("认可的那条" if mode["ballot_choice"] else "推荐的") + noun
                             + ("或 NONE。" if supported else "，没有认可任何" + noun + "时只能写 NONE。"))
    counts = []
    seats = len(ids)
    threshold = data["protocol"]["threshold"]
    required = threshold["numerator"]
    family_of = {r["id"]: r.get("family", "?") for r in data["roster"]}
    families = list(dict.fromkeys(family_of[a] for a in ids))
    for candidate in candidates:
        votes = [r for r in rows if r["candidate_id"] == candidate]
        support = sum(v[mode["support_field"]] for v in votes)
        objections = [v["agent_id"] for v in votes if v["unresolved_fatal_objection"]]
        # 诊断而非加权：同系列席位本来就不是独立观测，这里只显示结论是否由某一个系列撑起来。
        breakdown = {}
        for family in families:
            members = [a for a in ids if family_of[a] == family]
            breakdown[family] = {
                "support": sum(1 for v in votes if v[mode["support_field"]] and family_of[v["agent_id"]] == family),
                "seats": len(members),
                "unanimous_oppose": all(not v[mode["support_field"]] for v in votes
                                        if family_of[v["agent_id"]] == family),
            }
        counts.append({"candidate_id": candidate, "support": support, "denominator": seats,
                       "threshold": f"{required}/{seats}", "threshold_met": support >= required,
                       "fatal_objections_to_review": objections,
                       "family_breakdown": breakdown,
                       "provisional_recommendation": support >= required and not objections})
    approved = [c["candidate_id"] for c in counts if c["provisional_recommendation"]]
    result = {"complete": True, "mode": data["protocol"].get("mode", "proposal"),
              "packet_sha256": digest, "seats": seats,
              "formal_statements": data["protocol"]["rounds"] * seats,
              "protocol": data["protocol"],
              "retrieval_partial_seats": data["retrieval_partial_seats"],
              mode["items_key"]: counts, mode["approved_key"]: approved,
              "scope": "只检查记录、版本与票数，不证明内容真实、新意成立或中转背后的实际模型身份。"}
    atomic_json(root / "debate/audit.json", result)
    out = io.StringIO(newline="")
    fields = (["agent_id", "candidate_id"] + list(mode["score_fields"])
              + [mode["support_field"], "unresolved_fatal_objection", "reason"])
    writer = csv.DictWriter(out, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    atomic_text(root / "debate/votes.csv", out.getvalue())
    return result


def doctor(root, executable=None):
    """检查运行时是否真的按冻结席位表加载本目录；不调用任何模型。"""
    report = {"root": str(root), "checks": [], "ok": False}
    checks = report["checks"]

    def add(name, ok, detail):
        checks.append({"check": name, "ok": bool(ok), "detail": detail})

    cli = find_cli(executable)
    add("opencode CLI", bool(cli), cli or "未找到；可用 --opencode 指定完整路径")
    if not cli:
        return report

    version = run_cli(cli, ["--version"], root)
    add("version", version.returncode == 0, (version.stdout or "").strip() or version.stderr.strip())

    roles = read_json(root / "roster.lock.json")["seats"]
    config = read_json(root / "opencode.json")
    legacy = [k for k in ("agent", "command", "permission") if k in config]
    add("V2 原生配置", not legacy, "顶层键：" + ", ".join(sorted(config)) + ("；残留 V1 键 " + ",".join(legacy) if legacy else ""))

    try:
        available = inventory(root, executable=cli)
        missing = sorted({r["model"] for r in roles} - set(available))
        families = len(families_of(roles))
        add("模型 ID 存在", not missing,
            "缺少：" + ", ".join(missing) if missing
            else f"{families} 个系列的 {len({r['model'] for r in roles})} 个 ID 均在 opencode models 中")
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        add("模型 ID 存在", False, str(exc))

    loaded = run_cli(cli, ["debug", "agents"], root)
    try:
        agents = {a["id"]: a for a in json.loads(loaded.stdout)}
    except (json.JSONDecodeError, TypeError, KeyError):
        add("运行时加载", False, "opencode debug agents 未返回可解析的列表；请在本目录重新打开 OpenCode")
        return report
    chair_id = chair_of(roles)
    expected = {r["agent_name"]: r for r in roles}
    problems = []
    for name, role in expected.items():
        agent = agents.get(name)
        if not agent:
            problems.append(name + " 未加载")
            continue
        got_model = agent.get("model") or {}
        if isinstance(got_model, str):
            got_model = {"providerID": got_model.split("/", 1)[0], "id": got_model.split("/", 1)[-1]}
        if (got_model.get("providerID") or "") + "/" + (got_model.get("id") or "") != role["model"]:
            problems.append(name + " 模型不符：" + str(got_model))
        want_mode = "primary" if role["id"] == chair_id else "subagent"
        if agent.get("mode") != want_mode:
            problems.append(name + " mode 应为 " + want_mode)
    primaries = [a for a in agents.values() if a.get("mode") == "primary" and a["id"].startswith("debate-")]
    if len(primaries) != 1:
        problems.append("debate-* 主 Agent 数量为 " + str(len(primaries)))
    add("运行时加载", not problems,
        f"{len(roles)} 席位均按配置加载" if not problems else "；".join(problems))

    chair = agents.get("debate-chair", {})
    subagent_rules = [r for r in chair.get("permissions", []) if r.get("action") in ("subagent", "task")]
    allowed = {r["resource"] for r in subagent_rules if r.get("effect") == "allow"}
    want = {r["agent_name"] for r in roles if r["id"] != chair_id}
    add("主持可调其余席位", want <= allowed and "debate-chair" not in allowed,
        "可调：" + ", ".join(sorted(allowed)) if allowed else "未解析出 subagent 规则")

    member_name = next(r["agent_name"] for r in roles if r["id"] != chair_id)
    member = agents.get(member_name, {})
    member_rules = member.get("permissions", [])
    web = {r["action"]: r["effect"] for r in member_rules if r["action"] in ("websearch", "webfetch")}
    add("成员检索权限", web.get("webfetch") == "allow", str(web))

    # /api/websearch/provider 只返回 provider 目录，不代表已连接；连接数要看 /api/integration。
    wanted = read_json(root / "roster.lock.json").get("search", False)
    integrations = run_cli(cli, ["api", "get", "/api/integration"], root)
    connected = []
    try:
        entries = json.loads(integrations.stdout).get("data", [])
        connected = [e.get("id") for e in entries
                     if e.get("id") in ("exa", "firecrawl", "parallel", "tavily", "tinyfish")
                     and e.get("connections")]
    except (json.JSONDecodeError, AttributeError, TypeError):
        pass
    if wanted:
        add("websearch 配置", web.get("websearch") == "allow" and bool(connected),
            ("已连接：" + ", ".join(connected)) if connected
            else "配置为启用 websearch，但五个 provider 都没有连接凭据。v2.0.30 下每次 websearch 会返回 "
                 "exit 1（发言仍完整）。要么在 OpenCode 里 /connect 一个 provider，要么重跑 setup 用 --search off。")
    else:
        add("websearch 配置", web.get("websearch") == "deny",
            "已按 --search off 禁用 websearch，席位改走 webfetch + arXiv API"
            + ("；但检测到已连" + ", ".join(connected) + "，可考虑 --search on") if connected
            else "已按 --search off 禁用 websearch，席位改走 webfetch + arXiv API")
    report["ok"] = all(c["ok"] for c in checks)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    install = sub.add_parser("setup")
    install.add_argument("--inventory", type=Path)
    install.add_argument("--opencode", type=Path)
    install.add_argument("--mapping", type=Path)
    install.add_argument("--non-interactive", action="store_true")
    install.add_argument("--search", choices=("on", "off"), default="off",
                         help="是否启用 websearch。off 时权限里 deny，成员改走 webfetch；"
                              "没有搜索 provider 凭据时应保持 off。默认 off。")
    install.add_argument("--mode", choices=sorted(MODES),
                         help="proposal=找值得做的新方向（默认）；evaluate=对给定问题取多数认可的结论；"
                              "solve=对给定问题讨论出可执行的解法。"
                              "会写进 protocol.json，并按该模式重算默认门槛。")
    listing = sub.add_parser("models")
    listing.add_argument("--inventory", type=Path)
    listing.add_argument("--opencode", type=Path)
    check = sub.add_parser("doctor")
    check.add_argument("--opencode", type=Path)
    sub.add_parser("freeze")
    sub.add_parser("audit")
    args = parser.parse_args()
    try:
        if args.command in ("setup", "models"):
            available = inventory(ROOT, args.inventory, args.opencode)
            roles = load_roster(ROOT)
            if args.command == "models":
                print(json.dumps({"available_models": available,
                                  "families": families_of(roles),
                                  "suggested": suggestions(available, roles)},
                                 ensure_ascii=False, indent=2))
            else:
                supplied = read_json(args.mapping) if args.mapping else None
                seats = setup(ROOT, available, supplied, not args.non_interactive and sys.stdin.isatty(),
                              args.search == "on", args.mode)
                protocol = read_json(ROOT / "roster.lock.json")["protocol"]
                print(json.dumps({"configured": True, "search": args.search,
                                  "mode": protocol.get("mode", "proposal"),
                                  "seats": len(seats), "chairs": [s["id"] for s in seats if s.get("chair")],
                                  "protocol": protocol,
                                  "next": "运行 python debate_tools.py doctor，再运行 python run_debate.py all。"},
                                 ensure_ascii=False, indent=2))
        elif args.command == "doctor":
            report = doctor(ROOT, args.opencode)
            print(json.dumps(report, ensure_ascii=False, indent=2))
            if not report["ok"]:
                return 2
        else:
            print(json.dumps(freeze(ROOT) if args.command == "freeze" else audit(ROOT), ensure_ascii=False, indent=2))
    except (ValueError, KeyError, TypeError, AttributeError, OSError, subprocess.SubprocessError) as exc:
        if args.command == "audit":
            # 失败时也写清模式：否则下游报告不知道该读 approved_candidates 还是 adopted_conclusions。
            try:
                mode = mode_of(load_protocol(ROOT, len(load_roster(ROOT))))
            except (ValueError, OSError, KeyError, TypeError):
                mode = MODES["proposal"]
            atomic_json(ROOT / "debate/audit.json",
                        {"complete": False, mode["approved_key"]: [], "error": str(exc)})
        print("未完成：" + str(exc), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
