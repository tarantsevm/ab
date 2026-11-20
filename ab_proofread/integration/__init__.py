"""Optional desktop integrations (loaded only when explicitly requested)."""

from .accessibility import (
    AccessibilityUnavailable,
    CaptureError,
    SelectionSnapshot,
    UnsafeReplacement,
    capture_selection,
    replace_selection,
)

__all__ = [
    "AccessibilityUnavailable", "CaptureError", "SelectionSnapshot",
    "UnsafeReplacement", "capture_selection", "replace_selection",
]
