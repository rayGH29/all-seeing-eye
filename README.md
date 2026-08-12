# all-seeing-eye

**Modular, local-first OSINT tool with AI-assisted cross-referencing.**

You give it a **username or email**. It fans the target out across pluggable
**integrations** (Sherlock, Maigret, Holehe, HIBP, Toutatis, …), **merges**
everything into one report, and — optionally — sends that report to a **local
LLM** (via Ollama) that cross-references the findings and writes up insights.
A **deep-research** mode runs every plugin at its maximum settings.

It runs as an **interactive terminal app** (type `aseye` and start issuing
commands) and as a **one-shot CLI** (`aseye run <target>`) for scripting.

> ⚠️ **For legitimate, authorized research only.** Respect the law, platform
> terms of service, and people's privacy. Some plugins hit private endpoints or
> send probes to third-party sites — only use them against accounts and targets
> you are authorized to investigate.

---

## Contents

- [Features](#features)
- [Requirements](#requirements)
- [Installation](#installation)
- [Quick start](#quick-start)
- [The interactive app](#the-interactive-app)
- [One-shot CLI](#one-shot-cli)
- [Plugins](#plugins)
- [Normal vs deep mode](#normal-vs-deep-mode)
- [AI insights (local, via Ollama)](#ai-insights-local-via-ollama)
- [Configuration](#configuration)
- [Reports](#reports)
- [Writing your own plugin](#writing-your-own-plugin)
- [Updating](#updating)
- [Troubleshooting](#troubleshooting)
- [Project layout](#project-layout)

---

## Features

- **Modular plugin system** — drop a `.py` file into your user plugins folder
  (`~/.all-seeing-eye/plugins`), it's discovered automatically. No core changes.
- **Username & email targets** — the tool auto-detects which and only runs the
  plugins that support that target type.
- **Interactive shell** — history, tab-completion, and plugin on/off toggles.
- **Two run modes** — `run` (normal) and `deep-research` (every plugin at max
  settings).
- **Local AI insights** — cross-referencing done by a model on your machine
  (Ollama); nothing is sent to a third-party API. Fully optional.
- **Reports** — every run writes timestamped JSON and Markdown to `reports/`.
- **Resilient** — one failing/uninstalled plugin never crashes a run; it's
  recorded as a failed result and the rest continue.

---

## Requirements

- **Python 3.9 or newer** (`python --version` to check).
- **pip** (comes with Python).
- Optional: **[Ollama](https://ollama.com)** for AI insights.
- Optional: the external OSINT tools each plugin wraps (see [Plugins](#plugins)).

Core Python dependencies (installed automatically): `typer`, `rich`, `pydantic`,
`pyyaml`, `httpx`, `prompt-toolkit`.

---

## Installation

Pick **one** of the three methods below. On Windows, use PowerShell.

> **Windows note:** don't put the project inside `Documents`/`OneDrive`. OneDrive
> sync and Windows "Controlled Folder Access" can block installs and file writes
> (you'll see `could not create '…egg-info'` or `FileNotFoundError`). Clone to a
> plain path like `C:\dev\all-seeing-eye`. See [Troubleshooting](#troubleshooting).

### 1. Clone the repository

```bash
# macOS/Linux
git clone https://github.com/rayGH29/all-seeing-eye.git
cd all-seeing-eye
```

```powershell
# Windows (PowerShell) — clone outside Documents/OneDrive
mkdir C:\dev; cd C:\dev
git clone https://github.com/rayGH29/all-seeing-eye.git
cd all-seeing-eye
```

### 2a. Install with pipx (recommended — global `aseye` command)

[pipx](https://pipx.pypa.io) installs the tool in its own isolated environment
and puts `aseye` on your PATH.

```bash
python -m pip install --user pipx     # if you don't have pipx yet
python -m pipx ensurepath             # then reopen your terminal
pipx install .                        # from the repo folder
# bundle the external OSINT tools too:
pipx install ".[tools]"
```

Verify: `aseye --version`

### 2b. Editable install in a virtualenv (best for editing/updating)

Gives you the `aseye` command **and** picks up code changes with a plain
`git pull` (no reinstall).

```bash
python -m venv .venv
# activate it:
source .venv/bin/activate          # macOS/Linux
# .venv\Scripts\Activate.ps1       # Windows PowerShell
python -m pip install -e .
aseye --version
```

### 2c. No install — run from source

You don't have to install anything to use it. Install just the dependencies and
run it as a module from the repo folder:

```bash
python -m pip install -r requirements.txt
python -m aseye --help
```

Everywhere below, **`aseye ...`** and **`python -m aseye ...`** are
interchangeable — the second always works from the repo folder even without
installing.

---

## Quick start

```bash
# 1) create a config file you can edit (optional but recommended)
aseye config init

# 2) see the available plugins
aseye plugins list

# 3) run a sweep with no API key and no AI (fastest first run)
aseye run johndoe --no-llm

# 4) open the reports/ folder — you'll find a .json and .md report
```

To get AI insights, set up Ollama ([below](#ai-insights-local-via-ollama)) and
drop the `--no-llm` flag.

---

## The interactive app

Run `aseye` with **no arguments** to launch the mini-app. The banner shows once,
then you type commands directly:

```text
$ aseye
      <ASCII eye banner>
      all-seeing-eye  v0.1.0

aseye > help
aseye > plugins                      # list plugins with ON/OFF status
aseye > plugins off sherlock         # disable one (saved to config.yaml)
aseye > plugins on sherlock          # enable it again
aseye > plugins info sherlock        # show its normal vs deep settings
aseye > run johndoe --no-llm
aseye > deep-research someone@example.com
aseye > config                       # print the effective configuration
aseye > clear
aseye > exit
```

**Command reference (inside the app):**

| Command | Description |
|---|---|
| `run <target> [opts]` | Normal sweep. Opts: `--no-llm`, `-p a,b`, `-o dir`, `-f json\|md\|both` |
| `deep-research <target>` | Every plugin at maximum settings (alias: `deep`) |
| `plugins` | List all plugins with ON/OFF status |
| `plugins on\|off <name\|#>` | Toggle a plugin (persisted to `config.yaml`) |
| `plugins info <name>` | Show a plugin's normal vs deep settings side by side |
| `config` | Print the effective configuration |
| `help` | Show the command list |
| `clear` | Clear the screen |
| `exit` / `quit` | Leave the app |

Niceties: **arrow-key history**, **Tab completion** of commands and plugin names,
Ctrl-C to cancel the current line, Ctrl-D to exit.

---

## One-shot CLI

Every action is also a normal command for scripting/automation:

```bash
aseye run <target> [OPTIONS]
aseye deep-research <target> [OPTIONS]
aseye plugins list
aseye config init            # write config.yaml from the template
aseye config show            # print the effective config
aseye --version
aseye --help
```

**`run` / `deep-research` options:**

| Flag | Meaning |
|---|---|
| `-c, --config PATH` | Use a specific `config.yaml` |
| `-p, --plugins a,b` | Only run these plugins (comma-separated) |
| `--no-llm` | Skip the AI insights step |
| `-o, --output DIR` | Write reports to this directory |
| `-f, --format FMT` | Report format: `json`, `md`, or `both` |
| `-v, --verbose` | Debug logging (place before the command: `aseye -v run …`) |

**Examples:**

```bash
# username sweep across the no-key tools (install them first)
aseye run johndoe --plugins sherlock,maigret,socialscan --no-llm

# email checks with no key at all
aseye run someone@example.com --plugins holehe,gravatar,socialscan --no-llm

# email breach check (needs HIBP_API_KEY)
aseye run someone@example.com --plugins hibp

# deep research on everything, Markdown only, custom output dir
aseye deep-research johndoe -f md -o ./out
```

---

## Plugins

The tool auto-detects whether your input is a **username** or an **email** and
only runs plugins that support it.

| Plugin | Target | Needs a key/secret? | Install |
|---|---|---|---|
| `example` | username, email | no | built in (sample data) |
| `sherlock` | username | no | `pip install sherlock-project` |
| `maigret` | username | no | `pip install maigret` |
| `socialscan` | username, email | no | `pip install socialscan` |
| `holehe` | email | no | `pip install holehe` |
| `gravatar` | email | no | built in (HTTP only) |
| `toutatis` | username (Instagram) | **yes** — `TOUTATIS_SESSIONID` | `pip install toutatis` |
| `hibp` | email | **yes** — `HIBP_API_KEY` | built in (HTTP only) |

If a plugin's tool isn't installed or its key is missing, that plugin is recorded
as a **failed result** and the rest of the run continues normally.

### Install the external tools

None of these need an API key:

```bash
pip install sherlock-project maigret socialscan holehe
# or, if you installed all-seeing-eye with pipx and want them in the same env:
pipx inject all-seeing-eye sherlock-project maigret socialscan holehe toutatis
```

### Have I Been Pwned (email) — needs `HIBP_API_KEY`

1. Get a key at <https://haveibeenpwned.com/API/Key>.
2. Provide it via environment variable (preferred — never committed):

   ```bash
   export HIBP_API_KEY=your-key           # macOS/Linux
   ```
   ```powershell
   setx HIBP_API_KEY "your-key"           # Windows (reopen terminal after)
   ```
3. Deep mode also fetches pastes and includes unverified breaches.

### Toutatis (Instagram) — needs `TOUTATIS_SESSIONID`

Toutatis reads an Instagram account's public info using **your** logged-in
session cookie.

1. `pip install toutatis`
2. Log in to instagram.com in your browser, open DevTools → Application/Storage →
   Cookies → copy the value of the **`sessionid`** cookie.
3. Provide it:

   ```bash
   export TOUTATIS_SESSIONID=your-sessionid       # macOS/Linux
   ```
   ```powershell
   setx TOUTATIS_SESSIONID "your-sessionid"       # Windows (reopen terminal)
   ```
4. Normal mode returns profile info (name, verified/business flags, follower
   counts, public email/phone). Deep mode also runs the recovery lookup for the
   **obfuscated** email/phone.

> Toutatis hits Instagram's private endpoints with your cookie; Instagram may
> rate-limit or flag the session. Use responsibly and only where authorized.

---

## Normal vs deep mode

The two run modes **only change each plugin's settings** — same plugins, more
thorough behavior:

- `aseye run <target>` → **normal** (fast defaults).
- `aseye deep-research <target>` → **deep** (each plugin at maximum).

See exactly what changes for any plugin:

```text
aseye > plugins info sherlock
```

| Setting | normal | deep |
|---|---|---|
| nsfw | False | **True** |
| request_timeout | 15 | **30** |
| overall_timeout | 90 | **110** |

(Examples: Maigret scans more sites; Holehe enables password-recovery probing;
Toutatis adds the obfuscated email/phone lookup; HIBP includes pastes.)

---

## AI insights (local, via Ollama)

Insights are generated by a model **running on your machine** — no API key,
nothing leaves your computer. This step is optional (`--no-llm` skips it).

1. Install **[Ollama](https://ollama.com/download)** and start it (the desktop
   app runs a background server, or run `ollama serve`).
2. Pull a model:

   ```bash
   ollama pull llama3.1        # solid default; qwen3 / mistral also work well
   ```
3. Point the config at it — run `aseye config init`, then in `config.yaml`:

   ```yaml
   llm:
     enabled: true
     provider: ollama
     model: llama3.1           # must match `ollama list` exactly, e.g. qwen3:8b
     host: http://localhost:11434
   ```
   The defaults already target Ollama on localhost, so usually you only set
   `model`.
4. Run **without** `--no-llm`:

   ```bash
   aseye run someone@example.com
   ```

The report gains an **AI Insights** section that correlates handles, emails, and
names across plugins. If Ollama isn't running or the model isn't pulled, the
insights step fails gracefully with a note — the plugin data is still written.

---

## Configuration

Create an editable config with `aseye config init` (writes `config.yaml` from the
bundled template). `config.yaml` is gitignored. Key sections:

```yaml
llm:
  enabled: true
  provider: ollama
  model: llama3.1
  host: http://localhost:11434
  max_tokens: 1500
  temperature: 0.2
  timeout: 300

plugins:
  dir: ""                 # optional EXTRA folder (bundled + ~/.all-seeing-eye/plugins always searched)
  enabled: []             # allowlist (empty = all not disabled)
  disabled: []            # denylist (toggled by `plugins on/off`)
  settings:               # per-plugin overrides, keyed by plugin name
    sherlock:
      request_timeout: 15
      sites: [GitHub, Reddit]
    toutatis:
      sessionid: ""       # prefer the TOUTATIS_SESSIONID env var
    hibp:
      api_key: ""         # prefer the HIBP_API_KEY env var

output:
  dir: reports            # where reports are written
  format: both            # json | md | both

concurrency:
  max_workers: 8          # plugins run in parallel
  timeout: 120            # per-plugin hard timeout (seconds)
```

- **Secrets** (`HIBP_API_KEY`, `TOUTATIS_SESSIONID`) are best set as environment
  variables; the env var always wins over the config file.
- Use a non-default config with `aseye run <target> -c path/to/config.yaml`.
- Toggling plugins in the interactive app writes changes back to `config.yaml`.

---

## Reports

Every run writes to the output directory (`reports/` by default), named
`<target>_<UTC-timestamp>.<ext>`:

- **`.json`** — the full merged, machine-readable report (all plugin data +
  insights).
- **`.md`** — a human-readable summary with an AI Insights section.

Choose the format with `-f json|md|both`, or set `output.format` in the config.

---

## Writing your own plugin

The built-in plugins ship **inside the package** (`aseye/builtin_plugins/`), so
they're found from any directory and any install type. To add your own, drop a
`*.py` file into your **user plugins folder** — created automatically the first
time you run the tool:

- **Windows:** `C:\Users\<you>\.all-seeing-eye\plugins`
- **macOS/Linux:** `~/.all-seeing-eye/plugins`

(Or point `plugins.dir` in `config.yaml` at any extra folder.) Your file just
needs to subclass `BasePlugin`:

```python
from aseye.core.plugin_base import BasePlugin
from aseye.models import RunMode, Target

class MyPlugin(BasePlugin):
    name = "my_plugin"
    version = "1.0.0"
    description = "What it does."
    author = "you"
    supported_targets = {"username"}      # or {"email"}, or both

    default_settings = {"limit": 10}      # NORMAL mode
    deep_settings = {"limit": 200}        # DEEP mode ("run at max")

    def run(self, target: Target, mode: RunMode, settings: dict) -> dict:
        # do the work; honor DEEP mode by going deeper.
        # raise on failure — the framework records it as a failed result.
        return {"found": [...]}
```

It appears in `aseye plugins list` and runs automatically — no core changes.
Reference implementations (in `aseye/builtin_plugins/`):

- `example_plugin.py` — minimal working sample (no network).
- `sherlock_plugin.py` / `holehe_plugin.py` — wrapping an external CLI
  (subprocess + parsing output in a temp dir).
- `gravatar_plugin.py` / `hibp_plugin.py` — calling an HTTP API with `httpx`.

Plugins are merged by name across the bundled folder, your user folder, and any
`plugins.dir` — so a user plugin with the same `name` overrides a bundled one.

---

## Updating

```bash
git pull
```

- **Editable install (2b)** or **run-from-source (2c)** → that's it, changes are
  live.
- **pipx install (2a)** → run `pipx install . --force` after pulling to refresh.
- If a pull **adds a dependency**, re-run `pip install -r requirements.txt`
  (or `pip install -e .`). New plugins never require a reinstall.

---

## Troubleshooting

**`ModuleNotFoundError: No module named 'aseye'` when running `python aseye`**
Use `python -m aseye` (with `-m`) from the repo folder, or install the package.
`python aseye` runs a folder and breaks the import path; `-m` runs the package.

**`could not create '…egg-info'` / `FileNotFoundError` during install or run
(Windows)**
The project is under `Documents`/`OneDrive` and sync or "Controlled Folder
Access" is blocking writes. Fix by moving the repo to a plain path, e.g.
`C:\dev\all-seeing-eye`, and reinstalling there. Alternatively, allow
`python.exe` through *Windows Security → Ransomware protection → Controlled
folder access*, or pause OneDrive.

**`aseye : The term 'aseye' is not recognized` (Windows)**
The install put `aseye.exe` in a Scripts folder that isn't on PATH. Either:
- just use `python -m aseye ...` (always works), or
- add the Scripts folder to PATH — find it with
  `python -c "import sysconfig; print(sysconfig.get_path('scripts','nt_user'))"`,
  then add that folder via *Edit environment variables for your account → Path*,
  or use **pipx** which handles PATH for you.

**AI insights say "Could not reach Ollama…"**
Ollama isn't running. Start the Ollama app or run `ollama serve`, then retry.

**AI insights say "Ollama has no model '…'"**
The `model:` in `config.yaml` doesn't match `ollama list`. Pull it
(`ollama pull <model>`) or fix the name.

**A plugin shows as `error` / "not found"**
That plugin's external tool isn't installed or its key/sessionid is missing.
Install the tool (see [Plugins](#plugins)) or set the credential. The run still
completes with the other plugins.

**Interactive app doesn't accept input in a pipe/CI**
The shell requires a real terminal (TTY). In non-interactive contexts it prints
help and exits — use the one-shot CLI instead (`aseye run …`).

---

## Project layout

```
aseye/                 main package
├── cli.py             Typer CLI (run, deep-research, plugins, config)
├── shell.py           interactive REPL ("mini app") launched by bare `aseye`
├── config.py          config loading/saving (YAML + env)
├── models.py          Target, PluginResult, Report
├── core/
│   ├── plugin_base.py  BasePlugin interface + RunMode
│   ├── registry.py     discovers plugins (bundled + user folder + config dir)
│   ├── orchestrator.py the pipeline (classify -> run -> merge -> insights -> write)
│   └── report.py       merge results, render JSON/Markdown
├── llm/               local LLM abstraction (Ollama) + prompts
├── builtin_plugins/   plugins bundled with the tool (installed everywhere)
└── utils/             banner, logging, target classification
~/.all-seeing-eye/plugins/   your own drop-in plugins (auto-created)
ascii-eye.txt          the banner art (edit freely; loaded at runtime)
reports/               generated reports (gitignored)
config.example.yaml    template copied by `aseye config init`
```

---

## Roadmap

More integrations, cross-plugin entity resolution/de-duplication, persistent
storage, and a web UI. The architecture leaves clean seams for all of these.
