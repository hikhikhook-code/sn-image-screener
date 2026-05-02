"""Parallel orchestrator for the AI Anatomy Inspector.

High-throughput sibling of :class:`AnatomyRunner`. Instead of processing
one image at a time, the parallel runner flattens **every image** into
individual inspection jobs (full + tiles) and dispatches them to a
:class:`concurrent.futures.ThreadPoolExecutor`.

With N usable API keys, up to N jobs run concurrently — for example a
folder of 20 images at ``DETAILED`` depth (200 inspection calls) can
finish in roughly the time of one image when N >= 10.

Per-image bookkeeping
---------------------
A thread-safe :class:`_ImageState` tracks the slot list (one slot for
the full inspection plus one per tile). When all slots are populated,
the orchestrator merges results, emits ``EVT_COMPLETE`` and
``image_done``, and tears down the tile temp dir.

Failure / failover
------------------
Each job runs the same retry + key-failover logic as the serial runner
(via :meth:`AnatomyRunner._inspect_with_failover`). Rate-limited keys
are cooled down for the rest of the batch via :class:`KeyManager`; the
remaining keys keep working in parallel. Jobs that ultimately fail
contribute an empty inspection so the merge step still produces a
real :class:`AnatomyResult` (with ``error`` set when **everything**
failed).

Worker count
------------
Default = ``min(len(usable_keys), 16)``. Callers can override via the
``max_workers`` argument.

Stop button
-----------
Call :meth:`ParallelAnatomyRunner.stop` to short-circuit. In-flight
jobs are allowed to finish so we don't strand HTTP connections, but
no new jobs are dispatched.
"""

from __future__ import annotations

import shutil
import tempfile
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional

from .key_manager import KeyManager
from .prompts.anatomy_prompt import ANATOMY_PROMPT, tile_prompt
from .run_anatomy_check import (
    EVT_COMPLETE,
    EVT_ERROR,
    EVT_FULL,
    EVT_MERGE,
    EVT_PREPARE,
    EVT_TILE,
    MAX_KEY_SWITCHES_PER_IMAGE,
    AnatomyRunner,
    _OneInspection,
    _error_result,
    _merge_inspections,
    _translate_tile_regions_in_place,
)
from .tiling import build_tiles, encode_for_provider, read_tile_bytes
from .types import (
    AnatomyResult, ImageInput, ScanDepth, Tile,
)


ImageStartedCb = Callable[[Path], None]
ImageProgressCb = Callable[[Path, str, dict], None]
ImageDoneCb = Callable[[Path, AnatomyResult], None]


# ---------------------------------------------------------------------------
# Internal job + per-image state
# ---------------------------------------------------------------------------

@dataclass
class _Job:
    path: Path
    kind: str  # "full" or "tile"
    slot: int  # 0 = full, 1..N = tile index + 1
    tile: Optional[Tile]


@dataclass
class _ImageState:
    path: Path
    depth: ScanDepth
    full_w: int
    full_h: int
    tiles: List[Tile]
    slots: List[Optional[_OneInspection]]
    started: float
    tmp_dir: Path
    total_tiles: int
    lock: threading.Lock = field(default_factory=threading.Lock)
    finalized: bool = False


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

class ParallelAnatomyRunner:
    """Run AI Anatomy inspections for many images in parallel."""

    DEFAULT_CAP = 16

    def __init__(
        self,
        keys: KeyManager,
        *,
        max_workers: int = 0,
        timeout_seconds: int = 60,
    ) -> None:
        self.keys = keys
        usable = len(keys.usable_keys()) or 1
        if max_workers <= 0:
            max_workers = min(usable, self.DEFAULT_CAP)
        self.max_workers = max(1, max_workers)
        self.timeout = timeout_seconds
        self._stop = threading.Event()
        # Shared serial runner — its `_inspect_with_failover` method is
        # stateless aside from the (thread-safe) KeyManager, so it is
        # safe to call from multiple workers.
        self._serial = AnatomyRunner(keys, timeout_seconds=timeout_seconds)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def stop(self) -> None:
        """Signal the running batch to terminate as soon as possible."""
        self._stop.set()

    def reset_stop(self) -> None:
        """Clear the stop flag so the runner can be reused."""
        self._stop.clear()

    def run_batch(
        self,
        image_paths: List[Path],
        depth: ScanDepth,
        *,
        on_image_started: Optional[ImageStartedCb] = None,
        on_image_progress: Optional[ImageProgressCb] = None,
        on_image_done: Optional[ImageDoneCb] = None,
    ) -> Dict[Path, AnatomyResult]:
        """Process every image in parallel.

        Returns a dict ``{path -> AnatomyResult}`` after the whole
        batch completes (or :meth:`stop` is signalled).
        """
        on_image_started = on_image_started or (lambda _p: None)
        on_image_progress = on_image_progress or (lambda _p, _e, _x: None)
        on_image_done = on_image_done or (lambda _p, _r: None)

        results: Dict[Path, AnatomyResult] = {}

        # ------------------------------------------------------------
        # 1. Build per-image state and job list.
        # ------------------------------------------------------------
        image_state: Dict[Path, _ImageState] = {}
        jobs: List[_Job] = []

        for raw in image_paths:
            path = Path(raw)
            on_image_started(path)
            on_image_progress(path, EVT_PREPARE, {"depth": depth.value})

            tmp_dir = Path(tempfile.mkdtemp(prefix="sn_ai_par_"))
            try:
                full_w, full_h, tiles = build_tiles(
                    path, depth, tmp_dir=tmp_dir,
                )
            except Exception as exc:  # pragma: no cover - filesystem race
                err = f"Failed to prepare tiles: {exc}"
                on_image_progress(path, EVT_ERROR, {"message": err})
                result = _error_result(path, depth, err, time.time())
                results[path] = result
                on_image_done(path, result)
                shutil.rmtree(tmp_dir, ignore_errors=True)
                continue

            state = _ImageState(
                path=path,
                depth=depth,
                full_w=full_w,
                full_h=full_h,
                tiles=tiles,
                slots=[None] * (1 + len(tiles)),
                started=time.time(),
                tmp_dir=tmp_dir,
                total_tiles=len(tiles),
            )
            image_state[path] = state

            jobs.append(_Job(path=path, kind="full", slot=0, tile=None))
            for ti, tile in enumerate(tiles):
                jobs.append(_Job(
                    path=path, kind="tile", slot=ti + 1, tile=tile,
                ))

        if not image_state:
            return results

        # ------------------------------------------------------------
        # 2. Pre-flight: refuse to dispatch if no usable keys.
        # ------------------------------------------------------------
        if not self.keys.usable_keys():
            err = (
                "No usable API key. Add at least one enabled key in "
                "Settings → AI Keys before running."
            )
            for path, state in image_state.items():
                on_image_progress(path, EVT_ERROR, {"message": err})
                result = _error_result(path, state.depth, err, state.started)
                results[path] = result
                on_image_done(path, result)
                shutil.rmtree(state.tmp_dir, ignore_errors=True)
            return results

        # ------------------------------------------------------------
        # 3. Dispatch jobs to thread pool, finalize each image as
        #    its slots fill up.
        # ------------------------------------------------------------
        with ThreadPoolExecutor(max_workers=self.max_workers) as pool:
            futures: Dict[Future, _Job] = {}
            for job in jobs:
                if self._stop.is_set():
                    break
                fut = pool.submit(
                    self._run_job, job, image_state[job.path],
                    on_image_progress,
                )
                futures[fut] = job

            for fut in as_completed(futures):
                job = futures[fut]
                try:
                    inspection = fut.result()
                except Exception as exc:
                    inspection = _OneInspection(
                        parsed=None, provider="", key_label="",
                        error=f"Worker exception: {exc}",
                    )

                state = image_state[job.path]
                self._record_slot(
                    state, job.slot, inspection,
                    on_image_progress, on_image_done, results,
                )

                if self._stop.is_set():
                    pool.shutdown(wait=False, cancel_futures=True)
                    break

        # Any unfinished images get a stop-induced error result.
        for path, state in image_state.items():
            with state.lock:
                if state.finalized:
                    continue
                err = "Stopped by user before completion"
                result = _error_result(path, state.depth, err, state.started)
                results[path] = result
                on_image_progress(path, EVT_ERROR, {"message": err})
                on_image_done(path, result)
                state.finalized = True
            shutil.rmtree(state.tmp_dir, ignore_errors=True)

        return results

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _run_job(
        self,
        job: _Job,
        state: _ImageState,
        progress_cb: ImageProgressCb,
    ) -> _OneInspection:
        if self._stop.is_set():
            return _OneInspection(
                parsed=None, provider="", key_label="",
                error="Stopped before dispatch",
            )

        if job.kind == "full":
            data, mime = encode_for_provider(state.path)
            image_input = ImageInput(
                data=data, mime=mime, filename=state.path.name,
            )
            prompt = ANATOMY_PROMPT
            progress_cb(state.path, EVT_FULL, {"file": state.path.name})
        else:
            assert job.tile is not None
            image_input = ImageInput(
                data=read_tile_bytes(job.tile),
                mime="image/jpeg",
                filename=f"{state.path.stem}_tile{job.slot - 1}.jpg",
            )
            prompt = ANATOMY_PROMPT + tile_prompt(
                job.slot - 1, state.total_tiles,
            )
            progress_cb(state.path, EVT_TILE, {
                "tile_index": job.slot,
                "total_tiles": state.total_tiles,
            })

        outcome = self._serial._inspect_with_failover(
            image_input, prompt,
            progress=lambda e, p: progress_cb(state.path, e, p),
            switches_remaining=MAX_KEY_SWITCHES_PER_IMAGE,
        )
        return outcome.inspection

    def _record_slot(
        self,
        state: _ImageState,
        slot: int,
        inspection: _OneInspection,
        on_progress: ImageProgressCb,
        on_done: ImageDoneCb,
        results: Dict[Path, AnatomyResult],
    ) -> None:
        with state.lock:
            if state.finalized:
                return
            state.slots[slot] = inspection
            if any(s is None for s in state.slots):
                return

            on_progress(state.path, EVT_MERGE, {})
            full_inspection = state.slots[0]
            tile_inspections: List[_OneInspection] = []
            for ti, t_insp in enumerate(state.slots[1:]):
                assert t_insp is not None  # we've just checked all set
                if t_insp.parsed is not None:
                    _translate_tile_regions_in_place(
                        t_insp.parsed, state.tiles[ti],
                        state.full_w, state.full_h,
                    )
                tile_inspections.append(t_insp)

            assert full_inspection is not None
            result = _merge_inspections(
                state.path, full_inspection, tile_inspections,
                state.depth, state.started,
            )
            on_progress(state.path, EVT_COMPLETE, {
                "status": result.status.value,
                "score": result.quality_score,
            })
            results[state.path] = result
            on_done(state.path, result)
            state.finalized = True

        shutil.rmtree(state.tmp_dir, ignore_errors=True)
