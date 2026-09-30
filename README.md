# SimpleBox Studio

A local web interface for the published SimpleBox 4.04 environmental fate model, with 3,993 PFAS records, editable substance/emission/landscape inputs, and a local calculation engine.

The Studio feature adds a responsive forest-green workspace, section navigation, visual model overview and clearer results. It runs on port **8766**; the original `main` version can continue independently on **8765**. Use separate checkouts when running both. Calculation methods and API workflows are shared.

## Features

- Steady-state simulation across 33 compartments and five environmental scales
- Dynamic simulation with time-series charts
- Fate-factor matrix and residence times
- Chemical comparison and CSV-driven sensitivity exploration
- CSV, Excel, JSON and calculated-workbook downloads
- Scenario save and restore

All calculations run locally using LibreOffice, NumPy and SciPy. Microsoft Excel, cloud accounts and API keys are not required.

**This is an independent implementation, not the official hosted application.** Functional and numerical differences are documented in [LOCAL_WEB.md](LOCAL_WEB.md) and the application's user guide. Some upstream substance data are incomplete. Numerical equivalence to every output of the hosted service has not been established.

## Quick start

Install Python 3.14, [uv](https://docs.astral.sh/uv/) and [LibreOffice](https://www.libreoffice.org/).

```sh
git clone --branch codex/feature-studio-ui --recurse-submodules https://github.com/knightnemo/simplebox4planet-local.git
cd simplebox4planet-local
uv venv --python 3.14 .venv
uv pip install --python .venv/bin/python -r requirements.txt
.venv/bin/python server.py
```

Open **http://127.0.0.1:8766**. Use `--port 8767` to select another port.
If LibreOffice is not found automatically, set `SOFFICE` to its executable path.

On macOS, `启动本地网页.command` starts the app in the background and opens the browser; `停止本地网页.command` stops it. The launcher requires the Python environment above.

If cloned without submodules, run `git submodule update --init --recursive`.

## Tests

```sh
uv pip install --python .venv/bin/python pytest
.venv/bin/python -m pytest -q
```

Tests cover Excel reference values, changed inputs, PFBA selection, lake emissions, zero emissions, dynamic limits, fate-factor reconstruction, validation and all five HTTP calculation/export workflows.

## Project structure

`server.py` serves the local API and static frontend. `web/` contains the model adapter and field catalogue. `static/` contains the frontend. `tests/` contains numerical and HTTP tests.

`runtime/`, local working spreadsheets and virtual environments are ignored by Git. Source model data are pinned in the `SimpleBox4Planet` submodule.

## Attribution

The model and substance library come from [NovaMechanicsOpenSource/SimpleBox4Planet](https://github.com/NovaMechanicsOpenSource/SimpleBox4Planet), based on RIVM SimpleBox 4.04. See [THIRD_PARTY.md](THIRD_PARTY.md), the upstream README and upstream Apache 2.0 license.
