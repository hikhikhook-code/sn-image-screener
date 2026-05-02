# SN IMAGE SCREENER

> **Local image quality screening — fully offline, originals never modified.**

A clean rebuild of an in-house image screening utility, with a
brutalism-inspired PySide6 desktop UI. Screens images for blur, noise,
exposure problems and JPEG artifacts; classifies each shot as
**PASS / REVIEW / REJECT / ERROR** and gives it a 0–100 quality score.

![Brutalist UI](docs/screenshot.png)

## Features

* **Local & offline** — no network calls, no telemetry, no uploads.
* **Read-only on sources** — the app only ever reads your originals; exports are copies.
* **Batch scan** — add folders, individual files, or both.
* **Detection metrics**
  * Blur (Laplacian variance)
  * Noise (high-pass residual stddev)
  * Exposure (luminance mean, dynamic range, shadow / highlight clipping)
  * JPEG block artifacts (8×8 boundary differential, JPG/JPEG only)
  * File size + minimum resolution gates
* **Three quality presets** — `Stock Strict`, `Normal`, `Loose`.
* **Advanced overrides** — every threshold is editable from the collapsed Advanced drawer.
* **Live results table** — thumbnail, filename, status tag, quality bar, issue chips.
* **Inspector** — large preview, headline metric blocks, issue tags.
* **Activity log** — internal scroll, copy / clear buttons.
* **Export**
  * CSV report
  * JSON report
  * Copy `PASS` (and optionally `REVIEW`) files into a `selected/` folder

## Stack

* Python 3.10+
* [PySide6](https://pypi.org/project/PySide6/) for the desktop UI
* OpenCV, scikit-image, NumPy, Pillow for analysis

## Run from source

```bash
python -m venv .venv
source .venv/bin/activate                  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python run.py
```

…or after `pip install -e .`:

```bash
sn-image-screener
```

## Build a Windows `.exe`

The project ships a [PyInstaller](https://pyinstaller.org) spec and a
convenience batch script.

```bat
rem on Windows
py -3.11 -m venv .venv
.venv\Scripts\activate
pip install -r requirements-dev.txt
build_windows.bat
```

The single-file build appears in `dist\SN_Image_Screener.exe`.

## Project layout

```
sn-image-screener/
├── sn_image_screener/
│   ├── core/                # pure analysis / classification (no Qt)
│   │   ├── detection.py     # blur, noise, exposure, artifact, dynamic range
│   │   ├── presets.py       # Stock Strict / Normal / Loose
│   │   ├── classifier.py    # PASS/REVIEW/REJECT + 0..100 quality score
│   │   ├── scanner.py       # collect + read-only screen_one
│   │   └── exporter.py      # CSV / JSON / copy-by-status
│   ├── ui/                  # brutalist PySide6 UI
│   │   ├── theme.py         # palette + QSS
│   │   ├── widgets.py       # StatusTag, IssueChip, CollapsibleGroup …
│   │   ├── command_bar.py
│   │   ├── control_panel.py
│   │   ├── results_table.py
│   │   ├── inspector.py
│   │   ├── log_panel.py
│   │   ├── workers.py       # QThread scan worker
│   │   └── main_window.py
│   ├── main.py              # entry point
│   └── __init__.py
├── tests/                   # pytest unit tests for the pure core
├── scripts/
│   └── make_sample_images.py
├── build_windows.bat
├── sn_image_screener.spec   # PyInstaller spec
├── pyproject.toml
├── requirements.txt
└── requirements-dev.txt
```

## Running tests

```bash
pip install -r requirements-dev.txt
pytest
```

The test suite covers the pure detection / classification / scanner /
exporter logic and does **not** require a display.

## Design notes — brutalism

* Warm off-white base (`#F4F1EA`) with charcoal `#111111` borders.
* Vivid orange / lime / cobalt accents, used sparingly for actions and tags.
* 2px hard borders, square corners, flat surfaces, no gradients.
* Heavy uppercase headings + monospaced numerics for a "tool with attitude" feel.

## License

MIT — see [LICENSE](LICENSE).
