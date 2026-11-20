"""Bounded, on-demand AT-SPI selection capture.

Capture is read-only. Replacement deliberately fails closed: AT-SPI exposes
separate delete/insert operations, not an atomic range replacement.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import time

MAX_CAPTURE_CHARS = 20_000
_MAX_ANCESTORS = 32
_FORBIDDEN_ROLES = {
    "password text", "password", "terminal", "terminal emulator",
    "code editor", "code", "source code", "text editor",
}


class CaptureError(RuntimeError):
    """The focused accessibility target cannot be safely captured."""


class AccessibilityUnavailable(CaptureError):
    """AT-SPI is unavailable or no focused selection target exists."""


class UnsafeReplacement(RuntimeError):
    """Selection replacement cannot be done atomically and safely."""


@dataclass(frozen=True)
class SelectionSnapshot:
    text: str
    process_id: int
    application_name: str
    role: str
    accessible_name: str
    start_offset: int
    end_offset: int


def _value(obj: Any, name: str, default: Any = None) -> Any:
    try:
        value = getattr(obj, name)
        return value() if callable(value) else value
    except Exception:
        return default


def _role_name(accessible: Any) -> str:
    role = _value(accessible, "get_role_name", "")
    return str(role or "").strip().lower().replace("_", " ")


def _application(accessible: Any) -> Any:
    return _value(accessible, "get_application", None)


def _pid(app: Any) -> int:
    try:
        result = int(_value(app, "get_process_id", -1))
    except (TypeError, ValueError):
        result = -1
    if result <= 0:
        raise CaptureError("Focused application process identity is unavailable")
    return result


def _check_target(target: Any, own_pid: int) -> tuple[Any, int, str]:
    """Check target and every reachable ancestor before any text-content read."""
    seen: set[int] = set()
    node = target
    app = _application(target)
    if app is None:
        raise CaptureError("Focused target has no application identity")
    pid = _pid(app)
    if pid == own_pid:
        raise CaptureError("ab Proofread cannot capture its own UI")
    app_name = str(_value(app, "get_name", "") or "")
    for _ in range(_MAX_ANCESTORS):
        if node is None or id(node) in seen:
            break
        seen.add(id(node))
        role = _role_name(node)
        if role in _FORBIDDEN_ROLES or "password" in role or "terminal" in role or "code editor" in role:
            raise CaptureError(f"Capture blocked for protected {role or 'ancestor'} target")
        parent = _value(node, "get_parent", None)
        if parent is None:
            break
        parent_app = _application(parent)
        if parent_app is not None:
            parent_pid = _pid(parent_app)
            if parent_pid != pid:
                raise CaptureError("Accessibility ancestry crossed application identity")
        node = parent
    return app, pid, app_name


def _focused_accessible(atspi: Any) -> Any:
    try:
        desktop = atspi.get_desktop(0)
        # Bound traversal; only query child count and focused state, never document text.
        stack = [desktop]
        visited = 0
        candidate = None
        deadline = time.monotonic() + 2.5
        while stack and visited < 4_096 and time.monotonic() < deadline:
            node = stack.pop()
            visited += 1
            state_set = _value(node, "get_state_set", None)
            contains = getattr(state_set, "contains", None) if state_set is not None else None
            if callable(contains) and contains(atspi.StateType.FOCUSED):
                candidate = node
            count = int(_value(node, "get_child_count", 0) or 0)
            if count < 0 or count > 10_000:
                continue
            for index in range(count - 1, -1, -1):
                child = node.get_child_at_index(index)
                if child is not None:
                    stack.append(child)
        if candidate is not None:
            return candidate
    except Exception as exc:
        raise AccessibilityUnavailable(f"AT-SPI focus discovery failed: {exc}") from exc
    raise AccessibilityUnavailable("No focused AT-SPI target was found")


def capture_selection(*, own_pid: int | None = None, atspi: Any = None) -> SelectionSnapshot:
    """Read a bounded selected-text range from the currently focused AT-SPI object.

    Imports GI lazily. ``atspi`` injection is intended for tests and embedders.
    No listener, polling loop, clipboard access, or keyboard synthesis is used.
    """
    if atspi is None:
        try:
            import gi
            gi.require_version("Atspi", "2.0")
            from gi.repository import Atspi as atspi
            atspi.set_timeout(200, 2000)
        except Exception as exc:
            raise AccessibilityUnavailable(f"AT-SPI bindings unavailable: {exc}") from exc
    if own_pid is None:
        import os
        own_pid = os.getpid()
    target = _focused_accessible(atspi)
    app, pid, app_name = _check_target(target, own_pid)
    role = _role_name(target)
    # Only query Text after all role/ancestor/process guards have passed.
    try:
        text_iface = target.get_text_iface()
        if text_iface is None:
            raise CaptureError("Focused object does not expose AT-SPI Text")
        selected = int(atspi.Text.get_n_selections(text_iface))
        if selected != 1:
            raise CaptureError("No single unambiguous text selection is available")
        selection = atspi.Text.get_selection(text_iface, 0)
        start, end = selection.start_offset, selection.end_offset
        start, end = int(start), int(end)
        if start < 0 or end <= start or end - start > MAX_CAPTURE_CHARS:
            raise CaptureError("Selection is empty, invalid, or exceeds the capture limit")
        text = atspi.Text.get_text(text_iface, start, end)
    except CaptureError:
        raise
    except Exception as exc:
        raise CaptureError(f"Could not read focused text selection: {exc}") from exc
    if not isinstance(text, str) or not text or len(text) > MAX_CAPTURE_CHARS:
        raise CaptureError("AT-SPI returned an invalid or oversized selection")
    if '\ufeff' in text:
        raise CaptureError('AT-SPI returned an ambiguous invisible marker; use manual copy')
    return SelectionSnapshot(text, pid, app_name, role,
                             str(_value(target, "get_name", "") or ""), start, end)


def replace_selection(snapshot: SelectionSnapshot, replacement: str, **_kwargs: Any) -> None:
    """Never perform AT-SPI delete+insert; callers must use manual copy/paste."""
    raise UnsafeReplacement(
        "AT-SPI replacement is not atomic; copy the corrected text and paste manually"
    )
