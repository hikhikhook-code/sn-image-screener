"""Tests for sn_image_screener.core.deleter."""

from pathlib import Path

import pytest

from sn_image_screener.core.deleter import (
    human_size, total_size, trash_files,
)


def test_human_size():
    assert human_size(0) == "0 B"
    assert human_size(512) == "512 B"
    assert human_size(2048).endswith("KB")
    assert human_size(5 * 1024 * 1024).endswith("MB")
    assert human_size(7 * 1024 ** 3).endswith("GB")


def test_total_size_handles_missing(tmp_path):
    a = tmp_path / "a.bin"
    a.write_bytes(b"x" * 100)
    missing = tmp_path / "nope.bin"
    assert total_size([a, missing]) == 100


def test_trash_permanent_removes_files(tmp_path):
    f1 = tmp_path / "a.txt"; f1.write_text("a")
    f2 = tmp_path / "b.txt"; f2.write_text("b")
    deleted, errors = trash_files([f1, f2], permanent=True)
    assert set(deleted) == {f1, f2}
    assert errors == []
    assert not f1.exists() and not f2.exists()


def test_trash_permanent_reports_missing_file(tmp_path):
    missing = tmp_path / "ghost.txt"
    deleted, errors = trash_files([missing], permanent=True)
    assert deleted == []
    assert len(errors) == 1
    assert errors[0][0] == missing
