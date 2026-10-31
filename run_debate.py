#!/usr/bin/env python3
"""Drive the multi-seat debate by launching each seat as its own `opencode run` session.

Why this exists: the harness `subagent` tool in OpenCode 2.0.30 fails with
"Subagent session not found", so a chair cannot launch seats itself. This driver
launches a real independent session per seat and resumes it across rounds;
files remain the only channel between seats. Prompts come from the current mode's directory
(prompts/proposal/, prompts/evaluate/ or prompts/solve/); no seat is simulated.
Seat count, chair, mode and threshold come from roles.json / protocol.json.
Per-mode wording lives in debate_tools.MODES; nothing here branches on the mode name.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import threading
import time

import debate_tools as d

ROOT = Path(__file__).resolve().parent
DEFAULT_PARALLEL = 4  # 同轮并行上限；十个会话同时打同一个 provider 容易撞限流
CLI_PATH = None  # 由 --opencode 指定；容器里 CLI 常常不在 PATH 上


def seats():
    """席位表以 roles.json 为准；这里不缓存，改了 roles.json 立刻生效。"""
    return d.seat_ids(len(d.load_roster(ROOT)))


def chair():
    return d.chair_of(d.load_roster(ROOT))


def agent_name(seat):
    """主持席在配置里叫 debate-chair，不是 debate-<id>。"""
    return "debate-chair" if seat == chair() else "debate-" + seat


def mode():
    """当前模式（proposal / evaluate / solve）。提示词目录、目录文件、票的含义都由它决定。"""
    return d.mode_of(d.load_protocol(ROOT, len(seats())))


SESSION_LOCK = threading.Lock()


def session_ids(stdout: str) -> set:
    """Only top-level CLI events identify the invoked session, not nested tool data."""
    ids = set()
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
        except (ValueError, TypeError):
            continue
        if isinstance(event, dict) and isinstance(event.get("sessionID"), str):
            sid = event["sessionID"]
            if not re.fullmatch(r"ses_[A-Za-z0-9_-]+", sid):
                raise RuntimeError("CLI 返回了无效的 sessionID。")
            ids.add(sid)
    return ids


def session_context(agent, label):
    lock = d.read_json(ROOT / "roster.lock.json")
    matches = [r for r in lock["seats"] if r["agent_name"] == agent]
    if len(matches) != 1:
        raise RuntimeError(f"无法确定 {agent} 对应的唯一席位。")
    role = matches[0]
    seat = role["id"]
    path = ROOT / "debate/sessions" / (seat + ".json")
    identity = {"seat": seat, "agent": agent, "model": role["model"],
                "context_sha256": d.fingerprint({
                    "root": str(ROOT.resolve()), "roster": lock,
                    "protocol": d.read_json(ROOT / "protocol.json"),
                    "brief": (ROOT / "research_brief.md").read_text(encoding="utf-8-sig"),
                })}
    rounds = d.load_protocol(ROOT, len(lock["seats"]))["rounds"]
    match = re.fullmatch(r"round(\d+)-" + re.escape(seat), label)
    stage = int(match[1]) * 10 if match else {
        "merge": rounds * 10 - 5, "final": rounds * 10 + 10,
    }.get(label)
    with SESSION_LOCK:
        state = d.read_json(path) if path.exists() else None
        if state:
            if any(state.get(k) != v for k, v in identity.items()):
                raise RuntimeError(f"{seat} 的会话绑定与当前背景/配置不一致；请归档旧场次后重新开始。")
            if not re.fullmatch(r"ses_[A-Za-z0-9_-]+", str(state.get("session_id", ""))):
                raise RuntimeError(f"{path} 缺少有效 session_id。")
            if stage is not None and stage < state.get("stage", 0):
                raise RuntimeError(f"{seat} 会话已进入后续阶段，不能回到 {label}；请使用 --resume 跳过已有记录。")
        elif label != f"round1-{seat}" or any((ROOT / "debate").glob(f"round*/{seat}.md")):
            raise RuntimeError(f"{seat} 缺少持久会话记录；不能将新会话冒充跨轮续接。请恢复 debate/sessions 或另开新场次。")
    return path, identity, state, stage


def remember_session(path, identity, state, stage, stdout):
    ids = session_ids(stdout)
    if not ids:
        return False
    if len(ids) != 1:
        raise RuntimeError("一次 CLI 调用返回了多个 sessionID，拒绝绑定席位。")
    sid = ids.pop()
    if state and state["session_id"] != sid:
        raise RuntimeError("CLI 返回的 sessionID 与请求续接的会话不一致。")
    with SESSION_LOCK:
        for other in path.parent.glob("*.json"):
            if other != path and d.read_json(other).get("session_id") == sid:
                raise RuntimeError("不同席位不能绑定同一个 session_id。")
        d.atomic_json(path, {**identity, "session_id": sid,
                            "stage": max(stage or 0, (state or {}).get("stage", 0))})
    return True


def cli():
    found = d.find_cli(CLI_PATH)
    if not found:
        raise SystemExit("找不到 opencode 命令；请先把 CLI 加入 PATH，或用 --opencode 指定路径。")
    return found


def last_text(stdout: str) -> str:
    """Preserve all assistant text from this invocation, including resumed fragments.

    A transport retry can split one speech over multiple message IDs. Keeping
    only the last message silently drops its mechanism and evidence. Intermediate
    assistant prose is retained too; metadata parsing uses the last valid block.
    """
    messages = {}
    order = []
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        part = event.get("part") or {}
        mid = part.get("messageID")
        if not mid:
            continue
        if mid not in messages:
            messages[mid] = []
            order.append(mid)
        if event.get("type") == "text" and part.get("type") == "text":
            messages[mid].append(part.get("text", ""))
    return "\n\n".join(text for mid in order
                       if (text := "".join(messages[mid]).strip()))


def tool_errors(stdout: str) -> list:
    """工具级错误不算席位失败。websearch 被取消时 CLI 会返回 exit 1，但发言仍然完整。"""
    seen = []
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        part = event.get("part") or {}
        if event.get("type") == "tool_use":
            state = part.get("state") or {}
            if state.get("status") == "error":
                seen.append(str(part.get("tool")) + ": " + str(state.get("error"))[:120])
    return seen


def run_agent(agent: str, prompt: str, label: str, timeout: int = 3600, extra=()) -> str:
    executable = cli()
    if any(arg in ("--session", "-s", "--continue", "-c", "--fork", "--model", "-m")
           or arg.startswith(("--session=", "--model=")) for arg in extra):
        raise ValueError("会话和模型由席位绑定管理，不能通过 extra 覆盖。")
    path, identity, state, stage = session_context(agent, label)
    log = ROOT / "debate/logs"
    log.mkdir(parents=True, exist_ok=True)
    args = ["run", "--agent", agent, "--model", identity["model"], "--format", "json"]
    if state:
        args += ["--session", state["session_id"]]
    try:
        result = d.run_cli(executable, [*args, *extra, prompt], ROOT, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        # subprocess may return bytes even with text=True. Keep the real session
        # on timeouts so the next invocation can resume rather than start over.
        stdout = exc.stdout or ""
        if isinstance(stdout, bytes):
            stdout = stdout.decode("utf-8", errors="replace")
        (log / (label + ".jsonl")).write_text(stdout, encoding="utf-8")
        remember_session(path, identity, state, stage, stdout)
        raise
    stdout = result.stdout or ""
    (log / (label + ".jsonl")).write_text(stdout, encoding="utf-8")
    if result.stderr:
        (log / (label + ".stderr.txt")).write_text(result.stderr, encoding="utf-8")
    remembered = remember_session(path, identity, state, stage, stdout)
    text = last_text(stdout)
    if not text:
        raise RuntimeError(f"{label} 没有返回正文（exit {result.returncode}）："
                            f"{(result.stderr or '')[:400]}")
    if not remembered:
        raise RuntimeError(f"{label} 返回正文但没有可核验的 sessionID，拒绝伪造持续会话。")
    if result.returncode != 0:
        # 记录但不中断：判定放在 write_seat 里，以能否解析出合格发言为准。
        print(f"  注意：{label} exit {result.returncode}，但已拿到 {len(text)} 字正文，继续。", flush=True)
        errors = tool_errors(stdout)
        if errors:
            (log / (label + ".tool-errors.txt")).write_text("\n".join(errors), encoding="utf-8")
            print(f"  工具错误 {len(errors)} 条：{errors[0]}", flush=True)
    return text


def quarantine(path: Path, text: str, kind: str) -> Path:
    """把不合格或备份的原文移出轮次目录。

    read_round 会把 roundN/*.md 全部当成席位记录，任何附加文件都会让它报“多出席位”。
    """
    out = ROOT / "debate/backups" / f"{path.parent.name}-{path.stem}.{kind}.md"
    d.atomic_text(out, text)
    return out


def write_seat(path: Path, text: str, agent_id: str, round_no: int) -> None:
    if not text:
        raise RuntimeError(f"{agent_id} 第 {round_no} 轮没有返回正文。")
    try:
        meta = d.metadata(text)
    except ValueError as exc:
        out = quarantine(path, text, "raw")
        raise RuntimeError(f"{agent_id} 第 {round_no} 轮缺少末尾 JSON 元数据：{exc}。"
                           f"原文已存为 {out.relative_to(ROOT)}。") from exc
    if meta.get("agent_id") != agent_id or meta.get("round") != round_no:
        out = quarantine(path, text, "raw")
        raise RuntimeError(f"{agent_id} 返回的 agent_id/round 与席位不一致；"
                           f"原文已存为 {out.relative_to(ROOT)}。")
    d.atomic_text(path, text)


def round1(resume=False, only=None, parallel=1):
    m = mode()
    prompt = (f"读取 research_brief.md 与 {m['prompts_dir']}/round1.md，" + m["round1_hint"]
              + "不要读取 debate/ 目录下任何其他席位的文件。正文末尾必须附 "
              + f"{m['prompts_dir']}/round1.md 规定的 JSON 代码块，agent_id 必须是你的席位 ID。"
              "只返回正文本身，不要解释你在做什么。")

    def work(seat):
        path = ROOT / "debate/round1" / (seat + ".md")
        if resume and path.exists():
            return f"[round1] {seat} 已存在，跳过"
        text = run_agent(agent_name(seat), prompt, f"round1-{seat}")
        write_seat(path, text, seat, 1)
        return f"[round1] {seat} ok"

    run_seats(order1(only), work, parallel)


def order1(only=None):
    order = [chair()] + [s for s in seats() if s != chair()]
    if only:
        order = [s for s in order if s in only]
    return order


def run_seats(order, work, parallel=1):
    """轮内并行、轮间屏障。

    同一轮的席位互不读取对方文件，所以可以同时跑；只有“整轮跑完”才需要面对下一轮。
    并行度默认保守（4 路），因为同一个 provider 上十个会话同时打过去很容易撞限流。
    """
    if parallel <= 1 or len(order) <= 1:
        for seat in order:
            print(f"  {seat} ...", flush=True)
            print("  " + work(seat), flush=True)
        return
    lock = threading.Lock()
    failures = []
    with ThreadPoolExecutor(max_workers=min(parallel, len(order))) as pool:
        futures = {pool.submit(work, seat): seat for seat in order}
        for future in as_completed(futures):
            seat = futures[future]
            try:
                message = future.result()
            except Exception as exc:  # 单个席位失败不拖垮整批，交给调用方决定是否 --resume 补跑
                with lock:
                    print(f"  {seat} 失败：{exc}", flush=True)
                failures.append(seat)
                continue
            with lock:
                print("  " + message, flush=True)
    if failures:
        raise RuntimeError("这些席位本轮没有完成：" + "、".join(failures)
                           + "。其余席位已保存，可用 --resume 只补跑失败的席位。")


def merge(resume=False):
    order = seats()
    m = mode()
    protocol = d.load_protocol(ROOT, len(order))
    vote_round = protocol["rounds"]
    if resume and (ROOT / "debate/packet_manifest.json").exists():
        # Do not feed the chair back into pre-vote work after it has voted or
        # seen the final tally. Validate the frozen inputs before skipping.
        data = d.packet_data(ROOT)
        digest = d.fingerprint(data)
        manifest = d.read_json(ROOT / "debate/packet_manifest.json")
        packet = (ROOT / "debate/vote_packet.md").read_text(encoding="utf-8-sig")
        if manifest.get("packet_sha256") != digest or packet != d.render_packet(data, digest):
            raise RuntimeError("冻结资料已变化，不能续跑；请恢复原资料或另开新场次。")
        print("[merge] 冻结资料已核验，跳过归并", flush=True)
        return
    earlier = "、".join(f"debate/round{n}/" for n in range(1, vote_round))
    merges = [f"第 {n} 轮" for n in range(2, vote_round)]
    closing = m["merge_closing"].format(vote_round=vote_round)
    prompt = (f"读取 {earlier} 下全部 {len(order)} 个席位在各轮的完整发言，"
              f"按 {m['prompts_dir']}/chair.md 第 4 步" + m["merge_hint"]
              + f" 1–{d.MAX_CANDIDATES} 个固定{m['noun']}，写入 {m['catalog_file']}，"
              f"格式参照 {m['template']}。"
              f"{len(order)} 个首轮{m['source_noun']}必须逐一保留/合并/说明排除理由，"
              f"不得新增未被讨论的{m['noun']}。"
              + (m["merge_rule"] if merges else "")
              + closing)
    print(f"[merge] 主持归并{m['noun']} ...", flush=True)
    text = run_agent("debate-chair", prompt, "merge")
    manifest = d.freeze(ROOT)
    print(f"[merge] 已冻结 packet_sha256={manifest['packet_sha256'][:16]}… "
          f"门槛 {manifest['protocol']['threshold']['numerator']}/{manifest['protocol']['threshold']['denominator']}"
          f"，主持回复：{text[:200]}", flush=True)


def deliberate(number: int, resume=False, only=None, parallel=1):
    """中间轮：互评、合并邻近的产出、带着新检索再查一遍。不投票。"""
    m = mode()
    prompt = (f"读取 research_brief.md、{m['prompts_dir']}/deliberate.md 与 debate/round1/ 到 "
              f"debate/round{number - 1}/ 的全部发言，"
              f"按 deliberate.md 的要求完成第 {number} 轮互评。"
              f"不要读取 debate/round{number}/ 下同轮的其他人文件、任何投票、audit.json 或 final.md。"
              + m["deliberate_hint"]
              + f"正文末尾必须附 {m['prompts_dir']}/deliberate.md 规定的 JSON 代码块，agent_id 与 round 用真实值。"
              "只返回正文本身。")

    def work(seat):
        path = ROOT / f"debate/round{number}" / (seat + ".md")
        if resume and path.exists():
            return f"[round{number}] {seat} 已存在，跳过"
        text = run_agent(agent_name(seat), prompt, f"round{number}-{seat}")
        write_seat(path, text, seat, number)
        return f"[round{number}] {seat} ok"

    run_seats(order1(only), work, parallel)


def vote(resume=False, only=None, parallel=1):
    count = len(seats())
    m = mode()
    protocol = d.load_protocol(ROOT, count)
    number = protocol["rounds"]
    prompt = (f"读取 research_brief.md、{m['prompts_dir']}/vote.md 与 debate/vote_packet.md，"
              "按 vote.md 的要求完成互评与投票。"
              f"资料包里有全部 {count} 席此前各轮的原文和冻结{m['noun']}；"
              f"不要读取 debate/round{number}/ 下任何文件、votes.csv、audit.json 或 final.md。"
              + m["vote_hint"]
              + f"正文末尾必须附 {m['prompts_dir']}/vote.md 规定的 JSON 代码块，"
              "packet_sha256 用资料包里的完整值。"
              "只返回正文本身。")

    def work(seat):
        path = ROOT / f"debate/round{number}" / (seat + ".md")
        if resume and path.exists():
            return f"[round{number}] {seat} 已存在，跳过"
        text = run_agent(agent_name(seat), prompt, f"round{number}-{seat}")
        write_seat(path, text, seat, number)
        return f"[round{number}] {seat} ok"

    run_seats(order1(only), work, parallel)


def split_metadata(text: str):
    """Return (body, metadata) where metadata is the last parseable ```json block."""
    matches = list(re.finditer(r"```json\s*\n?(.*?)```", text, flags=re.S))
    for match in reversed(matches):
        try:
            value = json.loads(match.group(1))
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict) and "agent_id" in value and "round" in value:
            return text[:match.start()].rstrip() + "\n", value
    raise ValueError("找不到可解析的末尾 JSON 元数据块。")


def repair(seat: str, round_no: int, problem: str):
    """只让原席位重写元数据 JSON，正文由程序原样保留。

    之前让模型重发整篇的做法不可靠：它会缩写正文，或者只回一句确认。
    正文已经是有效科研产出，没有理由让模型再生成一次。
    """
    path = ROOT / f"debate/round{round_no}" / (seat + ".md")
    if not path.exists():
        raise RuntimeError(f"{path.name} 不存在，无法修复。")
    m = mode()
    previous = path.read_text(encoding="utf-8")
    body, old_meta = split_metadata(previous)
    keep = ("agent_id", "round", "packet_sha256", m["preferred_field"])
    payload = {key: old_meta.get(key) for key in keep if key in old_meta}
    vote_round = d.load_protocol(ROOT, len(seats()))["rounds"]
    # 第 1 轮与中间轮没有票，说成“投票轮”会让席位去找不存在的票。
    kind = "投票轮" if round_no == vote_round else "本轮"
    # 第 1 轮没有互评与票；对首轮提这些字段，模型会照着规则 1 造出不存在的回应。
    if round_no == 1:
        rules_1 = ""
        rules_3 = "3. `searched_queries` 只保留你正文里真实列出的查询。\n"
    else:
        rules_1 = ("1. `responses` 每条的 `to_agent` 必须恰好是一个席位 ID 字符串"
                   f"（{'、'.join(seats())} 之一，不能是你自己 {seat}）。复合的那条要拆成多条，"
                   "各自保留你在正文里对该席位说的内容；其余字段逐字不动。\n")
        if round_no == vote_round:
            rules_3 = ("3. `votes` 的条目、分值、objection、reason 一律不得增加、删除或改写。"
                       + ("单选：`endorse`=true 的条目最多一条，不得因为修复变成多条。"
                          if m["ballot_choice"] else "")
                       + "`searched_queries` 只保留你正文里真实列出的查询。\n")
        else:
            rules_3 = ("3. `merges` 与 `withdraws` 只保留你正文里真实说过的内容，"
                       "`searched_queries` 同样只留实际用过的查询。\n")
    prompt = (f"你的{kind}元数据 JSON 有一个机器校验失败的地方，只需要修这一处。"
              "下面是你的**原文元数据**，不要读任何文件，不要找其他 JSON：\n\n"
              "```json\n" + json.dumps(old_meta, ensure_ascii=False, indent=2) + "\n```\n\n"
              f"问题：{problem}\n\n"
              "规则：\n" + rules_1
              + "2. 这些字段必须与上面完全一致："
              + json.dumps(payload, ensure_ascii=False) + "\n"
              + rules_3
              + "4. 输出只有一个 ```json 代码块，内容是上面 JSON 修好后的完整对象。"
              "不要输出正文、不要解释、不要确认语、不要附加其他字段。")
    text = run_agent(agent_name(seat), prompt, f"repair-r{round_no}-{seat}")
    try:
        new_meta = d.metadata(text)
    except ValueError as exc:
        out = quarantine(path, text, "bad-metadata")
        raise RuntimeError(f"{seat} 的修复没有返回可解析的 JSON：{exc}。"
                           f"已存为 {out.relative_to(ROOT)}") from exc
    if set(new_meta) != set(old_meta):
        raise RuntimeError(f"{seat} 的修复增删了字段：{sorted(set(new_meta) ^ set(old_meta))}。拒绝写回。")
    for key, value in payload.items():
        if new_meta.get(key) != value:
            raise RuntimeError(f"{seat} 的修复改动了冻结字段 {key}："
                               f"{value!r} → {new_meta.get(key)!r}。拒绝写回。")
    if len(new_meta.get("votes", [])) != len(old_meta.get("votes", [])):
        raise RuntimeError(f"{seat} 的修复改动了票数：{len(old_meta.get('votes', []))} → "
                           f"{len(new_meta.get('votes', []))}。拒绝写回。")
    rebuilt = body + "\n```json\n" + json.dumps(new_meta, ensure_ascii=False, indent=2) + "\n```\n"
    quarantine(path, previous, "before-repair")
    write_seat(path, rebuilt, seat, round_no)
    print(f"[repair] 正文 {len(body)} 字原样保留，只替换了元数据块。", flush=True)


def audit():
    result = d.audit(ROOT)
    m = d.mode_of(result["protocol"])
    print(json.dumps({m["items_key"]: result[m["items_key"]],
                      "approved": result[m["approved_key"]]}, ensure_ascii=False, indent=2))


def final():
    m = mode()
    audit_data = d.read_json(ROOT / "debate/audit.json")
    partial = audit_data.get("retrieval_partial_seats") or []
    count = len(seats())
    protocol = d.load_protocol(ROOT, count)
    vote_round = protocol["rounds"]
    sources = "、".join(f"debate/round{n}/" for n in range(1, vote_round + 1))
    threshold = audit_data.get("protocol", {}).get("threshold") or protocol["threshold"]
    bar = f"{threshold['numerator']}/{threshold['denominator']}"
    verdict = m["final_verdict"].format(bar=bar)
    extra = m["final_extra"]
    prompt = (f"读取 debate/audit.json、debate/votes.csv、{m['catalog_file']} 和 {sources} 下全部 "
              f"{count} 个席位在各轮的原文，按 {m['prompts_dir']}/chair.md 第 8 步用中文写 debate/final.md。"
              "必须按 audit.json 的真实票数写，" + verdict + extra
              + ("本场首轮自述检索未完成的席位是 " + "、".join(partial)
                 + "，必须在报告里点名并写清各自缺哪一块检索，不能当作已完成。" if partial else "")
              + "写完只回复一行 FINAL_DONE。")
    print("[final] 主持撰写总结 ...", flush=True)
    print(run_agent("debate-chair", prompt, "final")[:300], flush=True)


def check_agents():
    """开跑前确认运行时真的加载了这些 agent，避免跑到一半才发现名字不对。

    这个查询偶发返回空清单（同一台机器上不复现），所以不要一次解析失败就终止整场。
    """
    expected = {agent_name(s) for s in seats()}
    missing = []
    parsed = False
    for attempt in range(3):
        result = d.run_cli(cli(), ["debug", "agents"], ROOT, timeout=120)
        try:
            loaded = {a["id"] for a in json.loads(result.stdout or "")}
            parsed = True
        except (json.JSONDecodeError, TypeError, KeyError):
            loaded = set()
        missing = sorted(expected - loaded)
        if not missing:
            break
        if attempt < 2:
            time.sleep(2)
    if not parsed:
        raise RuntimeError("无法读取 opencode debug agents 的输出；请先运行 python debate_tools.py doctor。")
    if missing:
        raise RuntimeError("运行时缺少这些 agent：" + ", ".join(missing)
                           + "。请在本目录重新运行 setup，并确认 opencode.json 已生成。")
    locked = {r["agent_name"] for r in d.read_json(ROOT / "roster.lock.json")["seats"]}
    if locked != expected:
        raise RuntimeError("roster.lock.json 与 roles.json 的席位数不一致；请删掉 opencode.json 与 "
                           "roster.lock.json 后重新运行 setup。")


def main():
    global CLI_PATH
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--opencode", help="opencode CLI 的完整路径；容器里常用")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("round1", "deliberate", "vote", "all"):
        p = sub.add_parser(name)
        p.add_argument("--resume", action="store_true")
        p.add_argument("--seats", help="只跑指定席位，逗号分隔，例如 a05,a01")
        p.add_argument("--parallel", type=int, default=DEFAULT_PARALLEL,
                       help=f"同轮并行启动的席位数，默认 {DEFAULT_PARALLEL}；1 为串行")
        if name in ("deliberate", "vote"):
            p.add_argument("--round", type=int, help="轮次编号，默认取 protocol.json 的对应值")
    sub.add_parser("merge")
    sub.add_parser("audit")
    sub.add_parser("final")
    fix = sub.add_parser("repair")
    fix.add_argument("--seat", required=True)
    fix.add_argument("--round", type=int, required=True)
    fix.add_argument("--problem", required=True)
    args = parser.parse_args()
    CLI_PATH = args.opencode
    only = {s.strip() for s in args.seats.split(",") if s.strip()} if getattr(args, "seats", None) else None
    if only:
        unknown = only - set(seats())
        if unknown:
            print("未知席位：" + ", ".join(sorted(unknown)), file=sys.stderr)
            return 2
    if getattr(args, "parallel", 1) < 1:
        print("--parallel 至少为 1（1 表示串行）。", file=sys.stderr)
        return 2
    try:
        check_agents()
        protocol = d.load_protocol(ROOT, len(seats()))
        vote_round = protocol["rounds"]
        if args.command == "round1":
            round1(args.resume, only, args.parallel)
        elif args.command == "merge":
            merge()
        elif args.command == "deliberate":
            number = getattr(args, "round", None)
            if number is None:
                if vote_round < 3:
                    print("protocol.json 的 rounds 为 2：没有中间轮，直接运行 vote。", file=sys.stderr)
                    return 2
                number = 2
            if not 2 <= number < vote_round:
                print(f"中间轮编号应在 2–{vote_round - 1}。", file=sys.stderr)
                return 2
            deliberate(number, args.resume, only, args.parallel)
        elif args.command == "vote":
            number = getattr(args, "round", None)
            if number is not None and number != vote_round:
                print(f"投票轮是第 {vote_round} 轮（protocol.json 的 rounds）。", file=sys.stderr)
                return 2
            vote(args.resume, only, args.parallel)
        elif args.command == "audit":
            audit()
        elif args.command == "final":
            final()
        elif args.command == "repair":
            if args.seat not in seats():
                print("未知席位：" + args.seat, file=sys.stderr)
                return 2
            if not 1 <= args.round <= vote_round:
                print(f"轮次应在 1–{vote_round}。", file=sys.stderr)
                return 2
            repair(args.seat, args.round, args.problem)
            print(f"[repair] {args.seat} 第 {args.round} 轮已重写，原文件另存为 .before-repair.md", flush=True)
        else:
            round1(args.resume, only, args.parallel)
            if only:
                print("--seats 只用于单轮试跑，all 模式不继续。", file=sys.stderr)
                return 2
            for number in range(2, vote_round):
                deliberate(number, args.resume, None, args.parallel)
            merge(args.resume)
            vote(args.resume, None, args.parallel)
            audit()
            final()
    except (RuntimeError, ValueError, OSError, subprocess.SubprocessError) as exc:
        print("未完成：" + str(exc), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
