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
orchestration pipeline, report layer, and LLM abstraction, plus working
plugins: an **example** reference plugin, a **Sherlock** username hunter, and a
**Have I Been Pwned** email breach check. Further integrations are dropped into
`plugins/` without touching the core.

## Architecture

```
aseye/                 main package
├── cli.py             Typer CLI (run, deep-research, plugins, config)
├── config.py          YAML + env config loading
├── models.py          Target, PluginResult, Report
├── core/
│   ├── plugin_base.py  BasePlugin interface + RunMode
│   ├── registry.py     auto-discovers plugins from plugins/
│   ├── orchestrator.py the pipeline (classify -> run -> merge -> insights -> write)
│   └── report.py       merge results, render JSON/Markdown
├── llm/               provider abstraction (OpenAI / Anthropic) + prompts
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

Cloud LLM providers (`openai`, `anthropic`) are **optional** — you only need them
for the insights step. Run with `--no-llm` to skip it entirely.

The **Sherlock** plugin shells out to the Sherlock CLI, which is an external
tool. Install it to enable that plugin:

```bash
pip install sherlock-project
```

If Sherlock isn't installed, its result is recorded as a failed plugin and the
rest of the run continues normally.

The **Have I Been Pwned** plugin (emails) needs a HIBP API key. Get one at
<https://haveibeenpwned.com/API/Key>, then provide it via environment variable
(preferred) or config:

```bash
export HIBP_API_KEY=your-key       # env wins over config
```

Without a key, the HIBP result is recorded as a failed plugin and the run
continues. In deep mode it also fetches pastes and includes unverified breaches.

## Usage

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

# Just Sherlock (requires `pip install sherlock-project`)
aseye run johndoe --plugins sherlock --no-llm

# Email breach check via Have I Been Pwned (requires HIBP_API_KEY)
aseye run someone@example.com --plugins hibp --no-llm

# Target an email, pick specific plugins, choose output format
aseye run someone@example.com --plugins example --format md
```

Everything also works via `python -m aseye ...` if you didn't install the script.

Reports are written to `reports/` as timestamped `.json` and/or `.md` files.

### Enabling AI insights

1. `aseye config init`, then in `config.yaml` set `llm.provider` (`openai` or
   `anthropic`) and `llm.model`.
2. Provide your key via environment variable (preferred):
   `OPENAI_API_KEY` or `ANTHROPIC_API_KEY`.
3. Run without `--no-llm`. The report gains an **AI Insights** section that
   cross-references findings across plugins.

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
