# all-seeing-eye — Documentation

A complete guide to the **all-seeing-eye** OSINT tool: what it is, how it works,
how to install and use it, how to extend it, and answers to common questions.

> ⚠️ **For legitimate, authorized research only.** Respect the law, platform
> terms of service, and people's privacy. Several plugins query private endpoints
> or send probes to third-party sites — only use them against accounts and
> targets you are authorized to investigate.

---

## Table of contents

1. [What it is](#1-what-it-is)
2. [Core concepts](#2-core-concepts)
3. [How a scan runs (the pipeline)](#3-how-a-scan-runs-the-pipeline)
4. [Installation](#4-installation)
5. [Quick start](#5-quick-start)
6. [The interactive app](#6-the-interactive-app)
7. [Command reference](#7-command-reference)
8. [Plugins](#8-plugins)
9. [Normal vs deep mode & editing settings](#9-normal-vs-deep-mode--editing-settings)
10. [Entity resolution (correlation)](#10-entity-resolution-correlation)
11. [Auto-pivot](#11-auto-pivot)
12. [AI insights (local, via Ollama)](#12-ai-insights-local-via-ollama)
13. [Configuration reference](#13-configuration-reference)
14. [Reports](#14-reports)
15. [Writing your own plugin](#15-writing-your-own-plugin)
16. [Files & folders](#16-files--folders)
17. [Updating](#17-updating)
18. [Troubleshooting](#18-troubleshooting)
19. [FAQ](#19-faq)

---

## 1. What it is

all-seeing-eye is a **local, modular OSINT tool**. You give it a **username** or
an **email address**; it runs that target through a set of pluggable
**integrations** (Sherlock, Maigret, Holehe, GitHub, HIBP, Hunter, and more),
**merges** everything into one report, **correlates** the identifiers it finds
(emails, usernames, names, profiles…), automatically **pivots** between usernames
and emails to follow the same person across both, and optionally sends the whole
picture to a **local LLM** (via Ollama) for cross-referenced insights.

**Key properties**

- **Local-first.** The AI step runs on your machine (Ollama) — nothing is sent to
  a third-party API. Most plugins need no key at all.
- **Modular.** Every data source is a plugin. Drop a `.py` file into a folder and
  it's discovered automatically — no core changes.
- **Two interfaces.** An interactive terminal app (run `aseye` with no arguments)
  and a one-shot CLI (`aseye run <target>`) for scripting.
- **Resilient.** A failing or missing plugin never crashes a run; it's recorded
  as a failed result and the rest continue.

---

## 2. Core concepts

| Concept | Meaning |
|---|---|
| **Target** | What you investigate — a `username` or an `email`. The tool auto-detects which. |
| **Plugin** | One data source/integration. Declares which target kinds it supports and how it behaves per mode. |
| **Mode** | `normal` (`aseye run`) or `deep` (`aseye deep-research`). The mode only changes each plugin's *settings*, not which code runs. |
| **PluginResult** | One plugin's outcome: `success` / `error` / `timeout`, plus its data. |
| **Report** | The merged result of a run: all plugin results + correlation + optional AI insights, written as JSON and Markdown. |
| **Correlation** | The "entity resolution" step: identifiers pulled from every plugin, deduped, tagged with which plugins reported them and a confidence. |
| **Pivot** | When a scan links your target to an identifier of the *opposite* kind, a second pass runs it through that kind's tools. |
| **Insights** | The local LLM's cross-referenced written analysis, built on top of the correlation. |

---

## 3. How a scan runs (the pipeline)

Everything below happens inside `orchestrator.run()`:

1. **Classify the target** — a regex decides `email` vs `username`.
2. **Discover plugins** — from the bundled folder, your user folder, and any
   configured folder; merged by name; filtered by enable/disable lists.
3. **Select** — keep only plugins whose `supported_targets` include the target's
   kind (and match `--plugins` if you passed it).
4. **Run concurrently** — each plugin runs in its own daemon thread, capped by
   `max_workers`, under one overall time budget. A slow/failing plugin is marked
   and abandoned — it can't crash or hang the run.
5. **Merge** into a `Report`.
6. **Correlate** — extract emails/usernames/names/phones/profiles/domains across
   all results, with provenance and confidence.
7. **Pivot** — follow strongly-linked opposite-kind identifiers through their
   tools; re-correlate over everything.
8. **AI insights** — optional; the local model gets the correlation + raw data.
9. **Write** — timestamped JSON + Markdown to `~/.all-seeing-eye/reports/`.

There is a visual version of this in the project's workflow diagram.

---

## 4. Installation

**Requirements:** Python 3.9+ and pip. Optional: [Ollama](https://ollama.com) for
AI insights, and the external tools some plugins wrap.

> **Windows note:** don't put the project inside `Documents`/`OneDrive`. OneDrive
> sync and Windows "Controlled Folder Access" can block installs and file writes
> (`could not create '…egg-info'`, `FileNotFoundError`). Clone to a plain path
> like `C:\dev\all-seeing-eye`.

### Get the code

```bash
git clone https://github.com/rayGH29/all-seeing-eye.git
cd all-seeing-eye
```

### Choose an install method

**A) pipx (recommended — global `aseye` command)**
```bash
python -m pip install --user pipx
python -m pipx ensurepath          # then reopen your terminal
pipx install .
pipx install ".[tools]"            # also install the external OSINT tools
```

**B) Editable install in a venv (best for updating/editing)**
```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\Activate.ps1
python -m pip install -e .
```

**C) No install — run from source**
```bash
python -m pip install -r requirements.txt
python -m aseye --help
```

Throughout the docs, `aseye ...` and `python -m aseye ...` are interchangeable —
the second always works from the repo folder even without installing.

---

## 5. Quick start

```bash
aseye config init                       # create ~/.all-seeing-eye/config.yaml
aseye doctor                            # see what's ready / what needs a tool or key
aseye plugins list                      # list all plugins
aseye run johndoe --no-llm              # first run: no key, no AI
```

Reports appear in `~/.all-seeing-eye/reports/` as `.json` and `.md`. To enable AI
insights, set up Ollama (section 12) and drop `--no-llm`.

---

## 6. The interactive app

Run `aseye` with **no arguments** to launch the mini-app. The banner shows once,
then you type commands directly (no need to retype `aseye`):

```text
aseye > help
aseye > doctor
aseye > plugins
aseye > plugins off toutatis
aseye > plugins set sherlock deep request_timeout 45
aseye > run johndoe --no-llm
aseye > deep-research someone@example.com
aseye > exit
```

Features: command **history** (arrow keys), **Tab completion** of commands and
plugin names, Ctrl-C to cancel a line, Ctrl-D to exit. Plugin toggles and setting
changes are saved to `config.yaml`.

---

## 7. Command reference

### Run commands (CLI and shell)

| Command | What it does |
|---|---|
| `run <target>` | Normal sweep. |
| `deep-research <target>` (shell alias `deep`) | Every plugin at maximum settings. |

**Options** (both commands):

| Flag | Meaning |
|---|---|
| `-c, --config PATH` | Use a specific `config.yaml`. |
| `-p, --plugins a,b` | Only run these plugins. |
| `--no-llm` | Skip the AI insights step. |
| `--no-pivot` | Don't auto-pivot to linked identifiers. |
| `-o, --output DIR` | Write reports to this directory. |
| `-f, --format FMT` | `json`, `md`, or `both`. |
| `-v, --verbose` | Debug logging (place before the command: `aseye -v run …`). |

### Plugin commands

| Command | What it does |
|---|---|
| `plugins list` | List discovered/enabled plugins. |
| `plugins info <name>` | Effective normal vs deep settings (overrides marked `*`). |
| `plugins on\|off <name>` | Enable/disable a plugin (persisted). |
| `plugins set <name> <normal\|deep> <key> <value>` | Override a setting for a mode (only the plugin's own keys). |
| `plugins reset <name> [mode]` | Clear a plugin's setting overrides. |
| `plugins new <name>` | Scaffold a starter plugin in your user folder. |

### Utility commands

| Command | What it does |
|---|---|
| `doctor` | Environment + per-plugin readiness (tool present / key set / ready) + LLM reachability. |
| `config init` | Write the global `config.yaml` from the template. |
| `config show` (CLI) / `config` (shell) | Print the effective configuration. |
| `help`, `clear`, `exit` (shell) | In-app helpers. |
| `aseye --version`, `aseye --help` (CLI) | Version / help. |

---

## 8. Plugins

The tool auto-detects the target's kind and only runs plugins that support it.

| Plugin | Target | Needs a key/tool? | Enable with |
|---|---|---|---|
| `example` | username, email | no | built in (sample data) |
| `sherlock` | username | no | `pip install sherlock-project` |
| `maigret` | username | no | `pip install maigret` |
| `whatsmyname` | username | no | built in (HTTP only) |
| `socialscan` | username, email | no | `pip install socialscan` |
| `holehe` | email | no | `pip install holehe` |
| `gravatar` | email | no | built in (HTTP only) |
| `github` | username **and** email | no (optional `GITHUB_TOKEN`) | built in (HTTP only) |
| `toutatis` | username (Instagram) | **yes** — `TOUTATIS_SESSIONID` | `pip install toutatis` |
| `hibp` | email | **yes** — `HIBP_API_KEY` | built in (HTTP only) |
| `hunter` | email | **yes** — `HUNTER_API_KEY` | built in (HTTP only) |

**Install the external CLIs** (none need a key):
```bash
pip install sherlock-project maigret socialscan holehe toutatis
```

**Provide keys/secrets** — environment variable is preferred (it always wins over
config, and never gets committed):

| Plugin | Variable | Where to get it |
|---|---|---|
| `hibp` | `HIBP_API_KEY` | <https://haveibeenpwned.com/API/Key> |
| `hunter` | `HUNTER_API_KEY` | <https://hunter.io/api-keys> |
| `toutatis` | `TOUTATIS_SESSIONID` | your browser's `sessionid` cookie for instagram.com (logged in) |
| `github` | `GITHUB_TOKEN` (optional) | GitHub → Settings → Developer settings → tokens (raises rate limit) |

If a plugin's tool or key is missing, that plugin is recorded as a **failed
result** and the rest of the run continues. Run `aseye doctor` to see readiness at
a glance.

**`github` is the strongest username ↔ email bridge:** a username → its public
commit emails, an email → the usernames behind it. It's what makes most pivots
fire.

---

## 9. Normal vs deep mode & editing settings

The two run modes **only change each plugin's settings** — same plugins, more
thorough behavior:

- `aseye run <target>` → **normal** (fast defaults).
- `aseye deep-research <target>` → **deep** (each plugin at maximum: more sites,
  longer timeouts, extra lookups).

A plugin has one `run()` — it reads the `mode` and the already-merged `settings`;
it never needs a second function.

**See a plugin's settings per mode:**
```text
aseye plugins info sherlock
```

**Override settings per mode** (only keys the plugin defines; persisted to
`config.yaml`):
```text
aseye plugins set sherlock deep request_timeout 45     # deep runs only
aseye plugins set sherlock normal sites GitHub, Reddit
aseye plugins reset sherlock deep                      # undo
```
Values are coerced to the setting's type (`true` → bool, `a,b` → list, etc.).
Unknown keys and bad modes are rejected.

---

## 10. Entity resolution (correlation)

Before the AI step, every run correlates the plugin results into one set of
**identifiers** — emails, usernames, real names, phone numbers, profile URLs, and
domains. Each is:

- **deduped** across plugins,
- tagged with `sources` (which plugins reported it),
- given a **confidence** that rises with agreement (an email seen by both `github`
  and `hibp` is `high`; one plugin is `medium`).

It appears as a **Correlated Identifiers** section in the report and is fed to the
LLM as the backbone for cross-referencing. It runs even with `--no-llm`.

---

## 11. Auto-pivot

When correlation links your target to an identifier of the **opposite kind**, the
tool runs a **second pass** on it through that kind's tools:

- **email scan** → finds a linked username → runs the **username tools** on it.
- **username scan** → finds a linked email → runs the **email tools** on it.

Pivot results merge into the report (a **Pivot →** section) and into the final
correlation. Example: scanning `alice@example.com` that resolves (via GitHub) to
`alice_dev` then runs `alice_dev` through Sherlock, Maigret, WhatsMyName, etc.

**Controls** (`pivot` config block):

| Setting | Meaning | Default |
|---|---|---|
| `enabled` | Turn auto-pivot on/off. | `true` |
| `min_sources` | How many distinct plugins must link the identifier before pivoting. | `1` |
| `max_targets` | Cap how many pivots a run may spawn. | `3` |

Pivoting is **one level deep** (pivots don't spawn pivots). Disable per run with
`--no-pivot`. Raise `min_sources` to `2` if you only want to pivot on identifiers
confirmed by multiple plugins.

---

## 12. AI insights (local, via Ollama)

Insights are generated by a model **running on your machine** — no API key,
nothing leaves your computer. Optional (`--no-llm` skips it).

1. Install **[Ollama](https://ollama.com/download)** and start it (the desktop app
   runs a background server, or `ollama serve`).
2. Pull a model: `ollama pull llama3.1` (or `qwen3`, `mistral`, …).
3. In `config.yaml`, set `llm.model` to the exact name from `ollama list`. The
   defaults (`provider: ollama`, `host: http://localhost:11434`) work out of the
   box.
4. Run **without** `--no-llm`.

If Ollama isn't running or the model isn't pulled, the insights step fails
gracefully with a note in the report — the plugin data is still written. Check
status with `aseye doctor`.

---

## 13. Configuration reference

`aseye config init` writes a **global** `config.yaml` under `~/.all-seeing-eye/`,
so settings apply from any directory. A `config.yaml` in your current folder still
takes precedence (handy for project-local overrides). Full reference:

```yaml
llm:
  enabled: true
  provider: ollama
  model: llama3.1
  host: http://localhost:11434
  max_tokens: 1500
  temperature: 0.2
  timeout: 300                # seconds to wait for the local model

plugins:
  dir: ""                     # optional EXTRA folder; bundled + ~/.all-seeing-eye/plugins always searched
  enabled: []                 # allowlist (empty = all not disabled)
  disabled: []                # denylist (toggled by `plugins on/off`)
  settings:                   # per-plugin overrides, keyed by plugin name
    sherlock:
      sites: [GitHub, Reddit] # flat key -> applies to BOTH modes
      deep:
        request_timeout: 45   # deep runs only
    hibp:
      api_key: ""             # prefer the HIBP_API_KEY env var
      rate_limit: 1.6         # min seconds between requests

output:
  dir: ~/.all-seeing-eye/reports
  format: both                # json | md | both

concurrency:
  max_workers: 8              # plugins run in parallel (daemon threads)
  timeout: 120                # per-plugin time budget; run bounded by timeout x batches

pivot:
  enabled: true
  min_sources: 1
  max_targets: 3
```

Notes:
- **Secrets** are best set as environment variables; the env var wins over config.
- **Per-source rate limiting:** HTTP plugins (`hibp`, `hunter`, `toutatis`,
  `gravatar`, `github`) accept a `rate_limit` (seconds) that spaces out their
  requests so you don't get throttled or flagged. Raise it if you hit limits.
- Use a non-default config with `-c path/to/config.yaml`.

---

## 14. Reports

Every run writes to the output directory (`~/.all-seeing-eye/reports` by default),
named `<target>_<UTC-timestamp>.<ext>`:

- **`.json`** — the full machine-readable report: all plugin data, pivots,
  correlation, and insights.
- **`.md`** — a human-readable summary with **Correlated Identifiers**, any
  **Pivot →** sections, an **AI Insights** section, and the raw plugin blocks.

Choose the format with `-f json|md|both` or `output.format` in the config.

---

## 15. Writing your own plugin

Fastest start — scaffold one into your user folder:
```bash
aseye plugins new my_source        # creates ~/.all-seeing-eye/plugins/my_source_plugin.py
```

Or write it by hand. Any `*.py` file in your user plugins folder
(`~/.all-seeing-eye/plugins`) that subclasses `BasePlugin` is auto-discovered:

```python
from aseye.core.plugin_base import BasePlugin
from aseye.models import RunMode, Target

class MyPlugin(BasePlugin):
    name = "my_source"                     # unique; shown in `plugins list`
    version = "1.0.0"
    description = "What it does."
    author = "you"
    supported_targets = {"username"}       # {"email"}, or both

    default_settings = {"limit": 10}       # NORMAL
    deep_settings = {"limit": 100}         # DEEP (merged on top)

    # Optional — surfaced by `aseye doctor`:
    # requires_tool = "some_cli_or_module"
    # requires_key_env = "SOME_API_KEY"
    # requires_key_setting = "api_key"

    def run(self, target: Target, mode: RunMode, settings: dict) -> dict:
        # target.value / target.kind ; settings already merged for this mode
        # return any JSON-serializable dict; raise on failure
        return {"found": [f"result for {target.value}", settings["limit"]]}
```

Rules of the road:
- **One `run()`** — the mode changes the `settings` you receive, not which method
  is called. Branch on `mode` only for logic that isn't just a setting.
- **Raise on failure** — the framework records it as a failed result and keeps
  going.
- **Be polite** — for HTTP sources, call `self.throttle("source_name", seconds)`
  before each request.
- **The `aseye` package must be importable** — i.e. installed, or run via
  `python -m aseye` from the repo.
- Reference implementations live in `aseye/builtin_plugins/`:
  `example_plugin.py` (minimal), `sherlock_plugin.py`/`holehe_plugin.py`
  (subprocess CLIs), `gravatar_plugin.py`/`github_plugin.py` (HTTP APIs).

---

## 16. Files & folders

```
aseye/                      main package
├── cli.py                  Typer CLI
├── shell.py                interactive REPL
├── config.py               config load/save
├── models.py               Target, PluginResult, Report, PivotReport
├── core/
│   ├── plugin_base.py      BasePlugin + RunMode + settings resolution
│   ├── registry.py         plugin discovery
│   ├── orchestrator.py     the pipeline + auto-pivot
│   ├── resolve.py          entity resolution (correlation)
│   └── report.py           merge + render JSON/Markdown
├── llm/                    local LLM abstraction (Ollama) + prompts
├── builtin_plugins/        the shipped plugins
├── data/                   packaged config.example.yaml + ascii-eye.txt
└── utils/                  banner, logging, validators, rate limiting

~/.all-seeing-eye/          your home for the tool
├── config.yaml             global config (config init writes here)
├── plugins/                your own drop-in plugins
├── reports/                generated reports
├── history                 shell command history
└── ascii-eye.txt           optional: your custom banner art (overrides default)
```

To customize the banner, edit `aseye/data/ascii-eye.txt` (in the repo) or drop an
`ascii-eye.txt` into `~/.all-seeing-eye/`.

---

## 17. Updating

```bash
git pull
```

- **Editable install (`-e`)** or **run-from-source** → usually that's it; only
  re-run `pip install -e .` (or `-r requirements.txt`) when an update adds a
  dependency.
- **pipx / regular `pip install .`** → also `pipx install . --force` (or
  `pip install .`) since those copy a snapshot.

New plugins never require a reinstall. If a run errors with `ModuleNotFoundError`
after a pull, reinstall deps.

---

## 18. Troubleshooting

**`ModuleNotFoundError: No module named 'aseye'` running `python aseye`**
Use `python -m aseye` (with `-m`) from the repo, or install the package. `python
aseye` runs a folder and breaks the import path.

**`could not create '…egg-info'` / `FileNotFoundError` on Windows**
The project is under `Documents`/`OneDrive`. Move it to a plain path like
`C:\dev\all-seeing-eye`, or allow `python.exe` through *Windows Security →
Ransomware protection → Controlled folder access*, or pause OneDrive.

**`aseye : term not recognized` (Windows)**
The install put `aseye.exe` in a Scripts folder not on PATH. Use `python -m aseye`,
or add that folder to PATH (find it with
`python -c "import sysconfig; print(sysconfig.get_path('scripts','nt_user'))"`),
or use **pipx** (handles PATH for you).

**AI insights say "Could not reach Ollama…"** — start Ollama (`ollama serve` or
the app). **"Ollama has no model '…'"** — the `model:` doesn't match `ollama list`;
pull it or fix the name.

**A plugin shows `error`** — its external tool isn't installed or its key/sessionid
is missing. Run `aseye doctor`; install the tool or set the credential.

**socialscan `Could not contact DNS servers` (Windows)** — the async DNS resolver
(`aiodns`) can't read your DNS on Windows. Remove it so it falls back:
`python -m pip uninstall aiodns pycares`.

**Interactive app in a pipe/CI** — the shell needs a real terminal; in
non-interactive contexts it prints help and exits. Use the one-shot CLI instead.

---

## 19. FAQ

**Do I need an internet connection?**
For the plugins, yes — they query online services. The AI step is local (Ollama)
and needs no internet. You can run with `--no-llm` and only offline-usable
plugins, but most plugins are network tools.

**Does it send my data anywhere?**
The AI insights run **locally** via Ollama — nothing goes to a third-party AI API.
The plugins themselves do contact the services they check (that's their job), and
key-based plugins send your query to those services (HIBP, Hunter, etc.).

**Do I need API keys?**
No, to get started. Most plugins are keyless. Only `hibp` and `hunter` require a
key, and `toutatis` needs an Instagram session cookie. `github` works keyless
(optional token raises the rate limit). Run `aseye doctor` to see what's ready.

**Where are my config and reports?**
Both live under `~/.all-seeing-eye/` by default — `config.yaml` and `reports/`.
That's the same on any OS (`C:\Users\<you>\.all-seeing-eye\` on Windows). A
`config.yaml` in your current directory overrides the global one.

**Can it link a username to an email (or vice-versa)?**
Yes — that's a core feature. The `github` plugin bridges both directions, and the
**auto-pivot** then follows the link: scan an email, find the username, and it
automatically runs the username tools on it (and vice-versa).

**What's the difference between `run` and `deep-research`?**
Same plugins; deep mode gives each plugin its maximum settings (more sites, longer
timeouts, extra lookups, wider pivots). See a plugin's exact differences with
`plugins info <name>`.

**Can I change a plugin's settings?**
Yes — `plugins set <name> <normal|deep> <key> <value>` (only the keys the plugin
defines), and `plugins reset` to undo. Changes persist to `config.yaml`.

**How do I turn a plugin off?**
`plugins off <name>` (persisted). `plugins on <name>` re-enables it. Or restrict a
single run with `-p name1,name2`.

**How do I add my own data source?**
`aseye plugins new <name>` scaffolds a plugin in `~/.all-seeing-eye/plugins/`; edit
its `run()`. It's picked up automatically — no reinstall. See section 15.

**Why did a plugin say "error" or "timeout"?**
Error usually means its external tool isn't installed or a key is missing (check
`aseye doctor`). Timeout means it exceeded the time budget — raise
`concurrency.timeout`, or the plugin's own `timeout`/`overall_timeout` setting.

**A run is slow / a plugin takes forever.**
Deep mode and site-sweeping plugins (Maigret, WhatsMyName) are inherently slow.
Use `-p` to run fewer plugins, lower a plugin's `max_sites`/`top_sites`, or reduce
`concurrency.timeout`. A hung plugin can't wedge the run — it's marked timeout and
abandoned.

**I'm getting rate-limited (HTTP 429).**
Raise the plugin's `rate_limit` setting (seconds between requests), e.g.
`plugins set hibp normal rate_limit 2`. For GitHub, set a `GITHUB_TOKEN`.

**How do I update to the latest version?**
`git pull` (+ reinstall if you used pipx/`pip install .`, or if a dependency was
added). See section 17.

**Can I run it from any folder?**
Yes. Plugins are discovered from the installed package and your user folder, and
config/reports live under `~/.all-seeing-eye/`, so `aseye` behaves the same
regardless of your current directory.

**How do I change the banner art?**
Edit `aseye/data/ascii-eye.txt` in the repo, or drop your own `ascii-eye.txt` into
`~/.all-seeing-eye/` (it overrides the default).

**Is this legal?**
The tool only queries public/permitted data sources, but *how you use it* is your
responsibility. Use it only against targets you're authorized to investigate, and
follow the law and platform terms. Some plugins (e.g. Toutatis, Holehe's recovery
probing) are more intrusive — treat them accordingly.

**Which Python versions are supported?**
Python 3.9 and newer.

**Does it work on Windows / macOS / Linux?**
Yes, all three. The Windows notes in section 4 and 18 cover the OneDrive/PATH
quirks specific to Windows.
