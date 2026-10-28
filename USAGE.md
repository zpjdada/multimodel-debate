<p align="center">
  <img src="assets/cover-titled.png" alt="Cover: five robot seats around a round table — one reading documents, two thinking, the centre one making the case, one holding a vote token" width="100%">
</p>

# Detailed usage guide

[Quick start](README.md) · [中文指南](USAGE_zh.md)

This package makes several real model seats — each its own OpenCode agent and
session — independently search the literature, read each other's full text
across rounds, and then vote on a frozen catalog. Every seat is a separate
`opencode run` session resumed across rounds, with no cross-seat shared context; files under `debate/` are the
only channel between them. It runs in three switchable modes: find new research
directions (`proposal`), settle a given question by majority (`evaluate`), or
work out a solution to a stated problem with your own knowledge base (`solve`).

The shipped default is six model families across ten seats, three rounds, with
an 8/10 threshold. Those numbers live in `roles.json` and `protocol.json`, not
in code.

## Who this is for

Not a one-click tool. Before you start, you should be comfortable with:

- choosing models in OpenCode and reading `opencode models` output, including
  full `provider/model` IDs;
- editing JSON (`roles.json`, `protocol.json`) and running
  `python debate_tools.py` / `run_debate.py`;
- reading an error message. `setup`, `doctor` and `audit` each name what is
  missing; re-running after skipping one just reproduces it;
- having a question worth arguing about, and resource limits you can state.

You do not need to write prompts, call a model API, or know Docker (the
container is optional). The step most first runs get wrong is not
configuration but an empty `research_brief.md`: with no boundaries, the seats
drift into a literature review.

If the first two items are already fine, the cheapest path is to let an agent
do the configuration and drafting — see
[Delegating to an agent](#delegating-to-an-agent).

## Three modes

One code path, one set of rounds and one audit. The `mode` field in
`protocol.json` changes only what a round produces and what a vote means.

| | `proposal` (default) | `evaluate` | `solve` |
|---|---|---|---|
| The question | is there a new direction worth building | what is the answer to this given question | what should we actually do about this given problem |
| Round one | one proposal per seat | one stated position per seat (support / oppose / conditional / insufficient evidence) | one draft solution per seat |
| Middle rounds | merge nearby proposals, withdraw broken ones | narrow conditions, revise or drop a position | merge complementary steps, split or narrow a solution |
| Catalog | `debate/candidates.json`, `K01`… | `debate/conclusions.json`, `C01`… | `debate/solutions.json`, `S01`… |
| Vote | one judgment per candidate, several may be recommended | **single choice**: one conclusion or `NONE` | one judgment per solution, several may be adopted |
| Scores | novelty / value / feasibility | confidence | value / soundness / feasibility |
| Default threshold | `round(0.8 × seats)` (10 → 8/10) | strict majority (10 → 6/10) | `round(0.8 × seats)` (10 → 8/10) |
| Approved key in `audit.json` | `approved_candidates` | `adopted_conclusions` | `adopted_solutions` |
| Prompts | `prompts/proposal/` | `prompts/evaluate/` | `prompts/solve/` |
| Legitimate outcome | no direction worth pursuing | no majority conclusion, or most seats stop at "insufficient evidence" | no solution worth adopting |

The lower `evaluate` bar is not a laxer standard — it asks "what do we think"
rather than "is this worth committing to". `proposal` and `solve` share the 80%
bar because both end in a decision to spend effort. Mode and threshold both go
into `packet_sha256`, so switching mode after `freeze` is rejected.

`proposal` is the only mode where novelty is a criterion: closest work is a
veto there, because a direction that already exists is not a direction. In
`solve` prior art is *evidence* — reusing a known method correctly is a
legitimate answer, and the ballot asks whether the solution works under the
constraints in your brief, not whether anyone thought of it first.

To switch, put `"mode": "solve"` in `protocol.json`, or run
`python debate_tools.py setup --mode solve`, which recalculates the default
threshold for that mode and keeps `rounds`. The mode is baked into the agents'
system prompts at setup time, so changing it means regenerating
`opencode.json` and `roster.lock.json`, exactly as changing the seat table does.

### What to write in `research_brief.md`

Each mode expects a different shape of brief:

- **`proposal`** — a field with boundaries, resources and an honest statement
  that no new direction may exist. Example: *"Local LLM inference on a single
  24 GB GPU. Which mechanism-level change would cut decode latency enough to be
  worth a minimal discriminating experiment?"*
- **`evaluate`** — one **falsifiable question** — "does X hold under Y", "is
  there evidence for Z" — not a broad topic. When the question is ambiguous,
  seats are told to state which reading they answer. Example: *"Does
  speculative decoding still beat plain decoding at batch size 32 on a single
  A100, given current draft-model overheads?"*
- **`solve`** — a problem, the resources and permissions you actually have, and
  what counts as done. Example: *"We have 3,000 scanned Chinese contracts as
  PDFs, no OCR budget, one workstation with a 16 GB GPU and four weeks. Extract
  party names, effective dates and penalty clauses with an auditable error
  rate. What do we build?"* Put the knowledge base under `materials/`.

## Your own knowledge base

Two optional inputs, both of them listed in `research_brief.md`. Leaving either
out is normal: every seat must search on its own, including sources beyond your
list and fresh checks in later rounds.

- **A reference list.** Title, venue, ID with a version suffix
  (`2404.16710v4`; bare IDs often resolve to nothing), and the path that gets
  you the body text. Use it to skip re-searching well-known baselines, or to
  make sure a specific baseline is not missed. The package guarantees nothing
  about these entries — check each one yourself before listing it, since a seat
  will otherwise spend a round chasing an ID that does not exist.
- **Local material under `materials/`.** For anything seats cannot reach
  themselves: paywalled proceedings, Chinese-language papers, internal notes,
   logs, code snapshots. A filename and intended use are helpful; author, source
   and your reading depth are recommended context, not mandatory form fields.

Two limits are worth knowing:

- **Text, not PDFs.** Seats read files with ordinary tools; whether a PDF is
  readable depends on the provider and the tool set. Prefer plain text,
   Markdown, TeX or source code. Scans need image-reading or OCR capabilities;
   supply a text transcript where possible rather than assuming they are readable.
- **Provided, not subscribed.** A seat can only use material that is actually
  present here or reachable through the configured retrieval tools. A prompt
  saying "search the literature" does not grant access to a paid database, and
  a seat that could not read something is required to say so rather than
  pretend.

**CNKI (知网) is not reachable.** Its search page stops at a security
verification, and the full text additionally requires login and institutional
subscription; there is no channel through the retrieval tools. Download what you
need yourself and put it under `materials/` — and convert CNKI's `.caj` exports
to PDF or plain text first, because seats cannot read `.caj`.

`materials/README.md` documents the format; everything else in the directory is
gitignored, so your material is never published with the package.

## What it does not do

- It does not generate research results for you. There is no bundled answer.
- It does not simulate seats. A seat that fails is reported as failed, not
  replaced by another model.
- Votes are not evidence. Seats of the same family are separate sessions but
  their votes are not statistically independent, and a configured model ID
  never proves which weights answered.

## Requirements

- OpenCode V2 CLI; tested with 2.0.30. Other V2 versions require verification;
  V1 is unsupported. Configure the models used by your roster (six distinct
  family mappings in the default configuration).
- Python 3.9+ (standard library only; no packages to install).

## Quick start

1. Unpack into a dedicated directory and open it in OpenCode.
2. Write your topic into `research_brief.md`. This personal file is not shipped;
   copy `research_brief.example.md` and rewrite the problem, the hard
   constraints and the known negative evidence. The reference list and
   `materials/` are optional — see "Your own knowledge base" above. Nothing is
   chosen for you here.
3. Ask the Build agent: read `SETUP_PROMPT.txt` and follow it.
4. Run `python debate_tools.py doctor` — it checks the seats against the
   running OpenCode, not just against the config file.
5. Run `.\START_WINDOWS.cmd` (Windows) or `python run_debate.py all`.

`setup` refuses to overwrite an existing `opencode.json` or
`roster.lock.json`, so regenerate only after backing both up and deleting them.

## Delegating to an agent

An agent can do the mechanical parts for you: rewrite `focus` entries for a new
field, fill in `research_brief.md` from a description you give it, run `setup`,
`doctor` and the driver. What it must not do is write the discussion. If an
agent composes seat statements itself, the run becomes one model talking to
itself, and `audit` will not catch it — it checks file structure, versions and
tally, not who wrote the text. The driver launches a real session per seat; that
is the part worth having.

A workable division:

- **You supply** the problem, the hard constraints, and what you have already
  tried and failed at. Those cannot be invented: a brief padded with generic
  framing becomes the factual base every seat reasons from.
- **The agent supplies** the formatting (copying the example and filling each
  section), a rewritten `focus` list when you change field, and the command
  sequence. Ask it to show you the ten `focus` lines before it runs `setup` —
  if they all read "find new directions", ten seats will search the same
  papers and the vote is a sample of one view.
- **The package supplies** the seats. Point the agent at `SETUP_PROMPT.txt` and
  it will stop and ask you for the topic rather than inventing one.

## Layout

```
roles.json           seat table: id, family, role, focus, one "chair": true
protocol.json        mode (proposal | evaluate | solve), rounds and threshold
model_map.json       family -> real provider/model ID, produced by setup
model_map.example.json
research_brief.md    the background brief the seats start from (yours, gitignored)
research_brief.example.md   the shipped template for it
materials/           optional local papers / notes (gitignored except its README)
prompts/proposal/    member / chair / start / round1 / deliberate / vote
prompts/evaluate/    the same six files for evaluate mode
prompts/solve/       the same six files for solve mode
templates/           candidates.example.json, conclusions.example.json, solutions.example.json
debate_tools.py      setup, freeze, audit, doctor
run_debate.py        driver: one real session per seat, resumed across rounds
test_tools.py        offline tests, synthetic IDs only
.opencode/skills/source-search/SKILL.md   how a seat retrieves without websearch
.github/workflows/tests.yml  runs the offline suite on 3.9 and 3.12
assets/              the cover image, its SVG source and the generator
Dockerfile           optional container image
docker-compose.yml   optional container run
.env.example         where the container finds your config directory
```

Generated per machine and not meant to be committed: `opencode.json`,
`roster.lock.json`, `model_map.json`, `research_brief.md`, and `debate/`.

## Changing seats, rounds and threshold

- **`roles.json`** — IDs must run `a01`, `a02`, … with no gaps; exactly one seat
  has `"chair": true`; at least three seats and two families. Every review
  round asks a seat to respond to two others, which is why three is the floor.
  The shipped `focus` strings are deliberately topic-agnostic so a new topic
  usually needs no edit; rewrite them only when you change field entirely (see
  [Delegating to an agent](#delegating-to-an-agent)).
- **The chair's model** — prioritize sufficient context, faithful summarization
  and instruction following. It must preserve all seats' statements, including
  its own (ten first-round statements by default), and evidence links in a
  votable catalog. `merge_rule` forbids adding claims no seat made. There is no
  universal “strongest model” choice; evaluate it on the size of your packet. In the
  shipped table `a05` (chair) and `a06` (novelty review) share a family and
  therefore a model ID, so one view of "what counts as new" lands in two seats;
  give `a05` its own `"model": "..."` if that matters to you.
- **`protocol.json`** — `mode`, `rounds`, and `threshold`. `rounds` accepts 2–4.
  The last round is the vote; every earlier round is independent search, review
  and consolidation. `rounds: 2` is the minimal "propose, freeze, vote" run.
  `threshold.denominator` must equal the seat count. A fixed denominator is
  deliberate: absences cannot lower the bar. Omit `threshold` and the mode's
  default applies (proposal and solve ~80%: 10 → 8/10; evaluate strict majority:
  10 → 6/10); write half of it and setup refuses, so a truncated config cannot
  take effect. Omit `mode` and it defaults to `proposal`.
- **`model_map.json`** — one real ID per family. `python debate_tools.py models`
  suggests candidates from `opencode models`; ambiguous lookups must be
  resolved by hand, never guessed.
- **Per-seat `model`** — add `"model": "provider/model-id"` to a seat in
  `roles.json` to override its family mapping. The ID must be complete
  (`provider/model`, not a display name) and must exist in `opencode models`.
  An override wins over `model_map.json` and is frozen into `roster.lock.json`;
  a family whose seats are all overridden needs no mapping entry. This is how
  you give two seats of one family different models without inventing a family
   for each. Known limitation: overriding every seat in the chair's family
   currently causes a `KeyError` during configuration. Keep its family mapping
   and at least one seat using that mapping until the implementation is fixed.

The threshold is an input to `packet_sha256`, and `packet_manifest.json`
records it. Lowering 8/10 to 5/10 after voting starts makes `audit` fail on a
digest mismatch instead of quietly passing.

## What the rounds are

Described for `proposal`; the `evaluate` and `solve` differences are in
parentheses.

**Round one — independent.** Every seat, including the chair, runs its own
session, searches the web for primary sources, and
submits one proposal with at least three distinct source URLs (in `evaluate`: a
stated position with its evidence URLs; in `solve`: one draft solution with the
sources backing each step, plus the preconditions it needs). No seat may read
another seat's round-one file.

**Middle rounds — review and consolidation** (when `rounds` ≥ 3). Each seat
reads every earlier round, runs fresh searches, responds to at least two other
seats, and may merge nearby proposals into one candidate that still fits a
single paper, split a proposal down to its novel half, or withdraw its own (in
`evaluate`: narrow a claim to a conditional form, revise, or drop it; in
`solve`: merge complementary steps into one doable procedure, split it, or
narrow the part it claims to solve). No votes in these rounds. Each record must
name at least two queries it actually ran and at least one closest-work /
evidence URL; `audit` rejects records without them.

**Merge — freeze.** The chair merges the first-round proposals, using the
middle-round merge suggestions, into 1–5 candidates, each with a mechanism, an
assumption, the closest prior work and the difference, a minimum experiment,
and a stop condition (in `evaluate`: 1–5 mutually exclusive, truth-apt
conclusions, each with its strongest objection and what observation would
overturn it, with "insufficient evidence" kept as its own conclusion rather
than as a footnote; in `solve`: 1–5 executable solutions, each with what it
claims to solve, why it works, its evidence, its preconditions, and the step
most likely to fail, and each stating what it explicitly does *not* solve).
Every proposal must be kept, merged, or excluded with a stated reason; nothing
new may appear at this step. `freeze` then writes `debate/vote_packet.md`
containing the catalog plus every earlier round's text verbatim, and records its
SHA256.

**Vote round.** Every seat reads the same packet, must search once more,
respond substantively to at least two other seats, and vote on each candidate
(in `evaluate`: single choice — one conclusion or `NONE`; two endorsements from
one seat are rejected, since "the majority-endorsed conclusion" is undefined
when a seat endorses two mutually exclusive ones; in `solve`: one judgment per
solution and several may be adopted, scored on value / soundness / feasibility,
since two solutions that apply under different conditions are not in conflict).
With the default parallel driver, the chair can run alongside other seats;
the prompts forbid reading other seats' votes.

**Audit and report.** `audit` checks completeness, version, structure, recorded
retrieval, and the tally against the fixed denominator. `final` writes
`debate/final.md`, which must report "no direction found enough support" when
that is the result. In `evaluate` mode the report must also show the spread: if
the votes scatter across three or more mutually exclusive conclusions, the
question was not answered this round, and the highest count must not be written
up as a consensus. In `solve` mode the report must state each adopted solution's
conditions and cost, and must not fuse several adopted solutions into a
"combined plan" that no seat ever voted on.

## Retrieval

`websearch` needs a connected search provider. Without one, `setup` defaults to
`--search off`, which denies `websearch` and sends seats through `webfetch`:
arXiv API and OpenAlex for papers, arXiv HTML / ar5iv for full text, `r.jina.ai`
to attempt PDF-to-text conversion, and the source named in `research_brief.md` read
directly when the topic is not a paper topic (official documents, standards,
government pages, statistical databases). The package does not assume an
academic field. See `.opencode/skills/source-search/SKILL.md`.

Retrieval status is three-state and machine-checked:

- `completed` — the seat says it read the required depth.
- `partial` — allowed into the record, but named in `audit.json`
  (`retrieval_partial_seats`) and in the catalog (`scope_note`).
- `blocked` — hard failure; the packet cannot be frozen.

`openreview.net` sits behind a Cloudflare challenge and is unreadable from
every route tried here; use the arXiv version instead.

## Commands

```
python debate_tools.py setup --mapping model_map.json --non-interactive
python debate_tools.py setup --mode evaluate --non-interactive
python debate_tools.py doctor
python debate_tools.py models
python debate_tools.py freeze
python debate_tools.py audit

python run_debate.py all
python run_debate.py round1
python run_debate.py deliberate --round 2
python run_debate.py merge
python run_debate.py vote
python run_debate.py audit
python run_debate.py final
```

`all`, `round1`, `deliberate` and `vote` accept `--resume` to skip existing seat files.
This does not validate those files or make a changed frozen packet resumable. `round1`,
`deliberate` and `vote` also accept `--seats a01,a03` for a cheap format and
retrieval probe.

### Persistent sessions and operator responsibilities

The driver stores the CLI's actual session ID in `debate/sessions/aXX.json`
and passes `--session` and the configured model on subsequent calls. This is
automatic; `--resume` only skips existing speech files. Seats have distinct
sessions, including when running concurrently. The chair reuses its own session
for research, merging, voting and the final report. `all --resume` validates an
existing frozen packet and skips merging rather than taking a chair that has
already voted back to a pre-vote stage. Earlier research stages cannot be replayed
after later stages; metadata repair remains the original seat's responsibility.

Failed calls and timeouts retain any real session ID present in their output.
A hard process termination may prevent persistence. Missing session records are
an error, not an excuse to silently start a replacement session: restore the
records or start a new debate. The JSON files are bindings, not OpenCode database
backups. Preserve OpenCode's state too: `--session` may recreate a missing ID,
which does not restore its history. Context compaction can summarize old tool
results, so important evidence still belongs in public speeches.

Changed backgrounds, configuration or project locations invalidate the binding.
Archive the entire `debate/` directory before a new topic. Use one driver process
per debate; `--parallel` handles concurrency within it.

The outer operator handles setup, doctor, startup and recovery. The formal chair
handles only the research, merge, vote or report stage requested by the driver.
Python saves the unchanged Markdown-plus-JSON speeches, freezes the packet and
tallies votes. Separate metadata files are not required.

Existing `opencode.json` files embed old prompts. For a new run after upgrading,
back up and move the old generated configuration and `debate/` out, then rerun
setup with your mapping and doctor to activate the updated prompts.

Seats inside one round run in parallel: `--parallel N` (default 4, `1` for
serial). Run `deliberate --round 2` only when rounds ≥ 3; for four rounds also
run `deliberate --round 3` before merging. Rounds run sequentially, but the chair can overlap other seats within
one round. Same-round reading restrictions are prompt rules, not filesystem isolation.

## Docker (optional)

The container runs the same code on the same `debate/` directory. It saves you
installing Python and the OpenCode CLI, and lets ten seats fan out without ten
terminals.

For agent-assisted use, keep the operator agent in an ordinary OpenCode session
on the host and ask it to follow `SETUP_PROMPT.txt` using Docker. It prepares the
brief and runs the commands; the debate seats run inside the container. Manual
users run the same commands. Project materials and results are shared through
the project mount at `/work`.

```bash
cp .env.example .env          # set OPENCODE_CONFIG to an absolute path
docker compose build
docker compose run --rm setup models # list models visible inside the container
# Fill model_map.json using model_map.example.json, then configure:
docker compose run --rm setup setup --mapping model_map.json --non-interactive
docker compose run --rm doctor
docker compose up harness     # full run, logs streamed
```

`setup` and `doctor` are on-demand tool services. Plain `docker compose up`
also starts only `harness`. Use a dedicated directory without an existing
`opencode.json` or `roster.lock.json`; back up earlier runs first.

The first build downloads platform binaries and may take over ten minutes on a
slow connection. Later builds reuse the cache. With Docker Desktop, a host HTTP
proxy can be passed for the build only (replace the example port with yours):

```text
docker compose --progress plain build --build-arg HTTP_PROXY=http://host.docker.internal:10090 --build-arg HTTPS_PROXY=http://host.docker.internal:10090
```

The proxy must accept connections from Docker. Container `127.0.0.1` refers to
the container itself. These arguments do not configure runtime model requests;
base-image pulls use Docker Desktop's own proxy configuration.

- **Config is imported at runtime, never baked into the image.**
  `OPENCODE_CONFIG` points to your OpenCode configuration and provider credentials.
  It is mounted read-only at `/mnt/opencode-config`; the entrypoint copies it
  into the container's writable runtime directory, skipping host `service.json`
  so host-local proxy and service settings do not leak into container networking.
  The copy is removed with a `run --rm` container; the host stays unchanged.
  `.dockerignore` excludes private materials, transcripts and generated config.
  `.env` is yours to create and stays gitignored;
  while `OPENCODE_CONFIG` is empty, compose refuses to start and names the
  missing variable instead of mounting an empty directory.
- **Runtime proxy.** Set `DEBATE_HTTP_PROXY` and `DEBATE_HTTPS_PROXY` in `.env`
  when model requests or retrieval need a proxy (Docker Desktop example:
  `http://host.docker.internal:10090`). Leave them empty for direct access.
  Keep `DEBATE_NO_PROXY=localhost,127.0.0.1,::1` for CLI-to-service connections.
  Build proxy arguments do not configure the runtime proxy.
- **Compose does not expand `~`.** Give an absolute path —
  `/home/you/.config/opencode` on Linux/macOS, `C:/Users/you/.config/opencode`
  on Windows.
- **Runtime state lives in a named volume**, `opencode-state`, holding
  `~/.local/share` and `~/.local/state`. OpenCode keeps its SQLite database in
  WAL mode, which needs shared-memory semantics a Windows or macOS bind mount
  does not offer: pointing it at the host copy fails with `disk I/O error`,
  and the CLI then reports "Background service failed to start". Only the config
  directory and the working tree are bind-mounted. `docker compose down -v`
  wipes that volume, including the session database of a run in progress.
- **Build mirror.** `DEBIAN_MIRROR` in `.env` replaces the Debian mirror used
  during `apt-get`; leave it empty for `deb.debian.org`. The build arg has to
  stay in `docker-compose.yml` — passing it on a one-off `docker compose build`
  command line does not carry over to the next `docker compose run`.
- **uid.** The image runs as uid/gid 1000. If yours differs, add
  `--user "$(id -u):$(id -g)"`; the entrypoint creates the directories it
  needs, so a different uid works as long as the mounted paths are readable.
- **Credential portability:** only credentials in the imported configuration
  were tested here. V2 login accounts live in SQLite; the container has its own
  database. Host environment variables and keys in the skipped `service.json`
  are not inherited. These paths need explicit container authentication or
  environment forwarding. Removing the config mount alone is insufficient.
- **Switching mode under Docker.** Arguments after the service name replace
  its default command, so include the `setup` subcommand explicitly:
  `docker compose run --rm setup setup --mode evaluate --mapping model_map.json --non-interactive`.
  This recalculates the mode's default threshold when switching modes. Back up
  and remove old generated configuration first, as with native setup.

## Tests

```
python -B -m unittest test_tools
```

Offline and synthetic: fake model IDs, fake speeches, `example.invalid` URLs.
They verify that missing votes cannot shrink the denominator, that a changed
packet or config is rejected, that a post-freeze threshold change is rejected,
that both a 2-round and a 3-round run complete, that a missing middle round or
an unrecorded search blocks the freeze, that a 7-seat / 5-of-7 run completes,
and that `partial` is recorded rather than silently accepted. Sixteen `evaluate`
cases lock the second mode: 6/10 adopts and 5/10 does not, a ballot endorsing two
conclusions is rejected, the confidence floor is enforced, the wrong catalog
file fails with a message naming the right one, a mode change after freeze is
rejected, and switching mode recalculates the default threshold. Thirteen `solve`
cases lock the third: 8/10 adopts and 7/10 does not, two solutions can be
adopted in one ballot, the soundness floor is enforced, a proposal-shaped ballot
missing `soundness_score` is rejected, `preferred_solution` must be one of the
adopted, the packet renders "方案目录" rather than the proposal wording,
switching between `solve` and `evaluate` recomputes 8/10 ↔ 6/10, `audit` prints
the mode's own key, and the `repair` prompt only asks for the fields that exist
in the round being repaired. Four `PromptRenderTests` guard the files seats read
straight off disk: no `{{TOKEN}}` may survive in `start.md`, `round1.md`,
`deliberate.md` or `vote.md`, `setup` refuses to write a config when one does,
and the score floors written into `vote.md` must match
`MODES["solve"]["score_floor"]`. They say nothing about whether a paper exists.

## Licence

MIT. See `LICENSE`.
