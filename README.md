# all-seeing-eye

Modular, **local** OSINT tool with AI integration for insights and cross-referencing.

You give it a **username or email**; it fans the target out across pluggable
**integrations** (e.g. Sherlock), **merges** everything into a single report, and
(optionally) sends that report to an **LLM** to cross-reference the findings and
surface insights. A **deep-research** mode runs every plugin at its maximum
settings.

> ⚠️ For legitimate, authorized research only. Respect laws, platform terms, and
> people's privacy.

This repository contains the **skeleton**: the framework, CLI, config,
orchestration pipeline, report layer, and LLM abstraction, plus a set of working
plugins. Further integrations are dropped into `plugins/` without touching the
core.

**Bundled plugins**

| Plugin | Target | Needs a key? | Enable with |
|---|---|---|---|
| `example` | username, email | no | built in |
| `sherlock` | username | no | `pip install sherlock-project` |
| `maigret` | username | no | `pip install maigret` |
| `socialscan` | username, email | no | `pip install socialscan` |
| `holehe` | email | no | `pip install holehe` |
| `gravatar` | email | no | built in (HTTP only) |
| `toutatis` | username (Instagram) | **yes** (`TOUTATIS_SESSIONID`) | `pip install toutatis` |
| `hibp` | email | **yes** (`HIBP_API_KEY`) | built in |

## Architecture

```
aseye/                 main package
├── cli.py             Typer CLI (run, deep-research, plugins, config)
├── shell.py           interactive REPL ("mini app") launched by bare `aseye`
├── config.py          YAML + env config loading
├── models.py          Target, PluginResult, Report
├── core/
│   ├── plugin_base.py  BasePlugin interface + RunMode
│   ├── registry.py     auto-discovers plugins from plugins/
│   ├── orchestrator.py the pipeline (classify -> run -> merge -> insights -> write)
│   └── report.py       merge results, render JSON/Markdown
├── llm/               local LLM abstraction (Ollama) + prompts
└── utils/             logging, target classification
plugins/               drop-in plugins live here
reports/               generated reports (gitignored)
```

## Install

Requires Python 3.9+.

```bash
pip install -e .            # installs the `aseye` command
# or, without installing the package:
pip install -r requirements.txt
```

The AI insights step runs on a **local model** — nothing is sent to any
third-party API. It's optional: run with `--no-llm` to skip it entirely (no
model needed). To enable it, install [Ollama](https://ollama.com) and pull a
model — see [Enabling AI insights](#enabling-ai-insights) below.

Several plugins shell out to external OSINT CLIs. None of these need an API key
— install any subset to enable them:

```bash
pip install sherlock-project maigret socialscan holehe
```

`gravatar` needs nothing extra (HTTP only). If a tool isn't installed, its
result is recorded as a failed plugin and the rest of the run continues
normally. Deep mode (`aseye deep-research`) runs each of these at its maximum
settings (more sites, longer timeouts; `holehe` additionally enables
password-recovery probing).

The **Have I Been Pwned** plugin (emails) needs a HIBP API key. Get one at
<https://haveibeenpwned.com/API/Key>, then provide it via environment variable
(preferred) or config:

```bash
export HIBP_API_KEY=your-key       # env wins over config
```

Without a key, the HIBP result is recorded as a failed plugin and the run
continues. In deep mode it also fetches pastes and includes unverified breaches.

The **Toutatis** plugin (Instagram usernames) needs a valid Instagram
**sessionid** cookie — grab it from your browser's cookies for instagram.com
while logged in:

```bash
pip install toutatis
export TOUTATIS_SESSIONID=your-sessionid   # env wins over config
```

It returns profile data (name, verified/business flags, follower counts, public
email/phone); in deep mode it also runs the recovery lookup for the obfuscated
email/phone. Use only against accounts you're authorized to investigate.

## Interactive app

Run `aseye` with **no arguments** to launch the interactive shell. The banner
shows once, then you type commands directly (no need to retype `aseye`):

```text
aseye
aseye > help
aseye > plugins                     # list plugins with ON/OFF status
aseye > plugins off sherlock        # turn one off (saved to config.yaml)
aseye > plugins info sherlock       # see how deep mode changes its settings
aseye > run johndoe --no-llm
aseye > deep-research someone@example.com
aseye > exit
```

Features: command history (arrow keys), tab-completion of commands and plugin
names, and plugin on/off toggles that persist to `config.yaml`. Every command is
also available one-shot from your OS shell for scripting (below).

## Usage (one-shot)

```bash
# One-time: create a config you can edit
aseye config init
aseye config show

# See what plugins are available
aseye plugins list

# Run a normal sweep (no API key needed with --no-llm)
aseye run johndoe --no-llm

# Deep research: every plugin at max settings
aseye deep-research johndoe

# Username sweep across the keyless tools (install them first)
aseye run johndoe --plugins sherlock,maigret,socialscan --no-llm

# Email checks with no API key at all (Holehe + Gravatar)
aseye run someone@example.com --plugins holehe,gravatar,socialscan --no-llm

# Email breach check via Have I Been Pwned (requires HIBP_API_KEY)
aseye run someone@example.com --plugins hibp --no-llm

# Target an email, pick specific plugins, choose output format
aseye run someone@example.com --plugins example --format md
```

Everything also works via `python -m aseye ...` if you didn't install the script.

Reports are written to `reports/` as timestamped `.json` and/or `.md` files.

### Enabling AI insights

Insights are generated by a **local** model via [Ollama](https://ollama.com) —
no API key, nothing leaves your machine.

1. Install Ollama and start it (the desktop app runs it, or `ollama serve`).
2. Pull a model, e.g. `ollama pull llama3.1`.
3. `aseye config init`, then in `config.yaml` set `llm.model` to that model
   (default `llama3.1`). The defaults (`provider: ollama`,
   `host: http://localhost:11434`) work out of the box.
4. Run without `--no-llm`. The report gains an **AI Insights** section that
   cross-references findings across plugins.

If Ollama isn't running or the model isn't pulled, the insights step fails
gracefully with a note in the report — the plugin data is still there.

## Writing a plugin

Drop a `*.py` file into `plugins/` that subclasses `BasePlugin`:

```python
from aseye.core.plugin_base import BasePlugin
from aseye.models import RunMode, Target

class MyPlugin(BasePlugin):
    name = "my_plugin"
    version = "1.0.0"
    description = "What it does."
    author = "you"
    supported_targets = {"username"}          # or {"email"}, or both

    default_settings = {"limit": 10}          # NORMAL mode
    deep_settings = {"limit": 200}            # DEEP mode ("run at max")

    def run(self, target: Target, mode: RunMode, settings: dict) -> dict:
        # do the work; honor DEEP mode by going deeper
        return {"found": [...]}
```

That's it — it will appear in `aseye plugins list` and run automatically. See
`plugins/example_plugin.py` (working sample) and `plugins/sherlock_plugin.py`
(a real external-CLI wrapper: subprocess + CSV parsing) for reference.

## Roadmap / out of scope for the skeleton

More integrations, entity resolution/de-duplication across plugins, persistent
storage, and a web UI. The skeleton leaves clean seams for all of these.
