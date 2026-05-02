# Changed-files summary

This is a clean rebuild from scratch — no source code from the old
`ImageScreener_AS.exe` was used or modified. The `.exe` was treated
purely as a behaviour reference (existing detection metrics, UI flow).

## Backend

A brand-new Python package was authored:

| File                                   | Reason                                        |
| -------------------------------------- | --------------------------------------------- |
| `sn_image_screener/core/detection.py`  | Blur / noise / exposure / artifact metrics    |
| `sn_image_screener/core/presets.py`    | Stock Strict / Normal / Loose threshold sets  |
| `sn_image_screener/core/classifier.py` | PASS/REVIEW/REJECT + 0..100 quality score     |
| `sn_image_screener/core/scanner.py`    | Path collection + read-only `screen_one`      |
| `sn_image_screener/core/exporter.py`   | CSV / JSON / copy-by-status helpers           |

Detection formulas mirror well-established references:

* **Blur** — variance of the Laplacian.
* **Noise** — stddev of `gray − GaussianBlur(gray)`.
* **JPEG artifact** — average 8-pixel block-boundary differential
  (JPG/JPEG only).
* **Exposure** — mean luminance, fraction of pixels clipped at the
  shadow / highlight tails, percentile-based dynamic range.

These formulas are deterministic and pixel-only, so behaviour is
reproducible across runs and across platforms.

## UI

A new PySide6 UI was authored under `sn_image_screener/ui/` with the
brutalist palette / typography described in `docs/design.md`. None of
the UI code touches the source images.

## Original-file safety

* All reads go through `open(path, "rb")` → `cv2.imdecode`.
* No write paths exist under `core/`.
* Exports always copy to a **user-selected** output folder; if the
  destination already contains a file with the same name, the copy is
  suffixed `(1)`, `(2)`, …, never overwriting either source or
  destination.
* Unit test `tests/test_scanner_exporter.py::test_screen_one_does_not_mutate_source`
  asserts that the source bytes are byte-identical before and after a
  scan.
