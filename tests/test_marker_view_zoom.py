"""Mouse-wheel zoom + pan + reset on :class:`MarkerView`.

Runs headless via the offscreen Qt platform.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, QPointF, Qt  # noqa: E402
from PySide6.QtGui import (  # noqa: E402
    QMouseEvent, QPixmap, QWheelEvent,
)
from PySide6.QtWidgets import QApplication  # noqa: E402

from sn_image_screener.ui.ai.marker_view import (  # noqa: E402
    _MAX_ZOOM, _MIN_ZOOM, MarkerView,
)


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def view(qapp) -> MarkerView:
    v = MarkerView()
    v.resize(800, 600)
    pm = QPixmap(2000, 1500)
    pm.fill(Qt.GlobalColor.black)
    v.set_image(pm)
    return v


def _wheel(angle_y: int, pos: QPointF) -> QWheelEvent:
    """Build a synthetic wheel event with the given y-angle delta."""
    return QWheelEvent(
        pos, pos, QPoint(0, 0), QPoint(0, angle_y),
        Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.NoScrollPhase, False,
    )


def test_wheel_up_zooms_in(view: MarkerView):
    assert view.zoom() == 1.0
    view.wheelEvent(_wheel(120, QPointF(400, 300)))
    assert view.zoom() > 1.0


def test_wheel_down_zooms_out_below_one(view: MarkerView):
    view.wheelEvent(_wheel(-120, QPointF(400, 300)))
    assert view.zoom() < 1.0


def test_wheel_zoom_clamped_to_max(view: MarkerView):
    # Pump enough wheel-up events to overshoot the cap.
    for _ in range(100):
        view.wheelEvent(_wheel(120, QPointF(400, 300)))
    assert view.zoom() == _MAX_ZOOM


def test_wheel_zoom_clamped_to_min(view: MarkerView):
    for _ in range(100):
        view.wheelEvent(_wheel(-120, QPointF(400, 300)))
    assert view.zoom() == pytest.approx(_MIN_ZOOM)


def test_wheel_zoom_anchored_at_cursor(view: MarkerView):
    """The image point under the cursor must stay under the cursor.

    We pick a cursor near the top-left of the image, capture the image
    fraction it sits at, zoom in one notch, and verify the same image
    fraction now sits under (or very close to) the same widget pixel.
    """
    cursor = QPointF(200, 150)

    def frac_at(rect, p):
        return (
            (p.x() - rect.x()) / rect.width(),
            (p.y() - rect.y()) / rect.height(),
        )

    before_rect = view._fit_rect()
    fx_before, fy_before = frac_at(before_rect, cursor)
    view.wheelEvent(_wheel(120, cursor))
    after_rect = view._fit_rect()
    fx_after, fy_after = frac_at(after_rect, cursor)
    # Allow ~1 px slop due to integer rounding in pan offsets.
    assert abs(fx_after - fx_before) < 0.005
    assert abs(fy_after - fy_before) < 0.005


def test_wheel_emits_zoom_changed(view: MarkerView, qtbot=None):
    seen: list[float] = []
    view.zoom_changed.connect(seen.append)
    view.wheelEvent(_wheel(120, QPointF(400, 300)))
    assert seen and seen[-1] > 1.0


def test_double_click_resets_zoom_and_pan(view: MarkerView):
    # Zoom in, then drag a bit, then double-click → back to fit + centred.
    view.wheelEvent(_wheel(120, QPointF(400, 300)))
    view.wheelEvent(_wheel(120, QPointF(400, 300)))
    assert view.zoom() > 1.0
    # Force a pan via the public API by simulating drag.
    view._pan_x = 50
    view._pan_y = 25
    ev = QMouseEvent(
        QMouseEvent.Type.MouseButtonDblClick,
        QPointF(400, 300), Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
    )
    view.mouseDoubleClickEvent(ev)
    assert view.zoom() == 1.0
    assert view._pan_x == 0 and view._pan_y == 0


def test_pan_only_active_when_zoomed_in(view: MarkerView):
    """At fit-zoom (1.0) the image already fills the viewport, so a
    left-click drag must not initiate panning (otherwise the user could
    drag the image off-canvas without zooming first).
    """
    press = QMouseEvent(
        QMouseEvent.Type.MouseButtonPress,
        QPointF(400, 300), Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
    )
    view.mousePressEvent(press)
    assert not view._dragging


def test_pan_drag_after_zoom(view: MarkerView):
    """When zoomed in, clicking and dragging shifts the pan offset."""
    view.set_zoom(3.0)
    assert view._pan_x == 0 and view._pan_y == 0
    press = QMouseEvent(
        QMouseEvent.Type.MouseButtonPress,
        QPointF(400, 300), Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
    )
    view.mousePressEvent(press)
    assert view._dragging
    move = QMouseEvent(
        QMouseEvent.Type.MouseMove,
        QPointF(450, 330), Qt.MouseButton.NoButton,
        Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
    )
    view.mouseMoveEvent(move)
    assert view._pan_x == 50 and view._pan_y == 30
    release = QMouseEvent(
        QMouseEvent.Type.MouseButtonRelease,
        QPointF(450, 330), Qt.MouseButton.LeftButton,
        Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
    )
    view.mouseReleaseEvent(release)
    assert not view._dragging


def test_set_image_resets_zoom(view: MarkerView):
    view.wheelEvent(_wheel(120, QPointF(400, 300)))
    view.wheelEvent(_wheel(120, QPointF(400, 300)))
    assert view.zoom() > 1.0
    new_pix = QPixmap(1000, 800)
    new_pix.fill(Qt.GlobalColor.white)
    view.set_image(new_pix)
    assert view.zoom() == 1.0
    assert view._pan_x == 0 and view._pan_y == 0


def test_pan_clamped_so_image_stays_on_screen(view: MarkerView):
    """Pan limit: the image cannot be dragged past the viewport edge."""
    view.set_zoom(2.0)
    view._pan_x = 100_000  # absurdly far
    view._pan_y = 100_000
    view._clamp_pan()
    rect = view._fit_rect()
    # After clamp, at least part of the image should still intersect
    # the viewport.
    assert rect.right() >= 0
    assert rect.bottom() >= 0
    assert rect.left() <= view.width()
    assert rect.top() <= view.height()
