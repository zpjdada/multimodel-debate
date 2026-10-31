# Agent Cyber Debate — multi-model debate for OpenCode

[中文](README_zh.md) · [Detailed guide](USAGE.md)

![Robot seats searching, thinking, speaking and voting around a table](assets/cover-titled.png)

This lightweight OpenCode **harness (task orchestration and execution framework)**
runs real model seats through independent retrieval, multiple rounds of review,
and voting on a packet frozen after chair-led consolidation. Each seat is a
separate OpenCode session; records and results stay in your project.

The package includes one custom retrieval skill,
[source-search](.opencode/skills/source-search/SKILL.md), for finding papers,
official documents, standards and data through available tools when `websearch`
is unavailable, and recording what was actually read. Python scripts handle
round scheduling, freezing and vote counting; each mode has its own prompts.

A single agent may overlook sources, miss counterexamples, or settle on a
direction too early. This harness brings agents with different focuses together
to divide retrieval work and cross-review findings, putting more evidence and
disagreements on the same discussion table. You can also combine models with
different capabilities and costs to fit your budget.

**Let AI do more than answer—let agents challenge each other, too.**

**Local GUI:** On Windows, double-click `START_CONSOLE.cmd` to open the console
in your browser. Select models from your OpenCode CLI, configure seats, chair,
mode and rounds, attach materials, then start and review the debate in one page.
Requires Python 3.9+ and a working OpenCode V2 CLI; no Node.js, domain or hosting
is needed. See the [console guide (Chinese)](CONSOLE.md). All seats may use the
same model while retaining independent sessions.

**Status: early experimental framework.** Built by one person with AI assistance
to explore multi-model discussion, it has limited functionality and validated
use cases. Existing tests are not comprehensive, and no research-grade system
evaluation has been completed. Feedback is welcome; further fixes, changes and
updates may follow.

**Native execution is the recommended starting point. Docker is optional.**
Run the commands yourself or ask an OpenCode agent to configure and launch the
same program for you.

## Three modes

| Mode | Goal | Example question |
|---|---|---|
| `proposal` | Find new directions | Which inference-speed mechanisms are worth testing on one 24 GB GPU? |
| `evaluate` | Assess a specific claim | Does speculative decoding outperform ordinary decoding for the specified model, hardware, batch size and test set? |
| `solve` | Develop an executable plan | How can we build a local inference service with streaming output and request queuing on one 16 GB GPU within four weeks? |

Defaults: ten seats, six model families, three rounds. Seats, models, rounds
(2–4) and thresholds are configurable. Proposal/solve default to 8/10 support;
evaluate defaults to 6/10. The denominator stays fixed at the total seat count.
No promising direction, no majority conclusion, or no adopted solution are all
valid outcomes. **Votes are not proof.**

## Prepare locally

- Install OpenCode V2 CLI and configure the models you intend to use. **2.0.30**
  is the tested version; other V2 versions need verification. V1 is unsupported.
- Install Python **3.9+**; no additional Python packages are needed.
- Download into a dedicated directory and open a terminal there. Check
  `python --version` and `opencode models`; use an explicit Python path if needed.

Copy `research_brief.example.md` to `research_brief.md`. State the **question,
resource constraints and known failed approaches or negative results**. Write
“none” where appropriate rather than inventing background.

Optionally preload papers, official documents, notes or logs in `materials/`.
Listing filenames and intended uses in the brief is recommended; source and
reading-depth details are helpful, not mandatory form fields. Supply readable
full text where possible, including a transcript for scans. Seats must still do
their own retrieval and report what they actually read; sources are not limited to papers. **Direct CNKI
retrieval is currently unavailable**; download relevant material yourself and
place readable PDF or text versions in `materials/`.

## Option 1: start manually

1. Run `opencode models` to see real model IDs.
2. Copy `model_map.example.json` to `model_map.json` and replace the placeholders
   with your full `provider/model` IDs. Defaults require six distinct family
   mappings; for fewer models or seats, first adjust `roles.json` and the threshold
   using the [configuration guide](USAGE.md#changing-seats-rounds-and-threshold).
3. Configure, check, then start:

```text
python debate_tools.py setup --mapping model_map.json --mode proposal --non-interactive
python debate_tools.py doctor
python run_debate.py all
```

Replace `proposal` with `evaluate` or `solve` as appropriate. Proceed after doctor
passes; it checks configuration and loading, not live API connectivity. On
Windows, `START_WINDOWS.cmd` can check and launch an already configured project.

`all` handles retrieval, review, merging, freezing, voting, auditing and the final
report. Do not freeze manually before the rounds. Setup refuses to overwrite
existing configuration; back up earlier runs and use a clean dedicated directory
for a new topic.

## Option 2: ask an OpenCode agent

Open the project in a normal local OpenCode Build session and send:

> Read SETUP_PROMPT.txt and configure this project for native execution, without
> Docker. Draft research_brief.md from my topic and materials/. Ask about missing
> information. Confirm the mode, seats and model mapping with me, complete setup
> and doctor, then report the results and wait for my confirmation to start.

After reviewing the configuration, send:

> Confirmed. Run python run_debate.py all and tell me where to find the results.

The operator agent prepares configuration and invokes the program. **It must
never fabricate another seat's statements or votes.** The driver launches real
model sessions. Runs incur model usage charges; requests usually exceed
“seats × rounds”.

## Results

- `debate/final.md`: final report.
- `debate/round*/`: original seat statements.
- `debate/votes.csv` and `debate/audit.json`: ballots and audit results.
- `debate/logs/`: invocation logs.

The audit checks structure, versions and vote counts, not whether citations or
conclusions are true. Personal briefs, materials and debate records are
gitignored and are not shipped with the project.

## More

- [Detailed guide](USAGE.md): configuration, retrieval, staged runs and resuming.
- [Optional Docker deployment](USAGE.md#docker-optional): neither native workflow
  requires it. Host login accounts and environment variables do not automatically
  carry into the container.
- Offline tests: `python -B -m unittest test_tools`; [validation record](VALIDATION.md).
- [MIT license](LICENSE).
