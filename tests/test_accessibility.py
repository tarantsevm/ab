import unittest
from types import SimpleNamespace

from ab_proofread.integration.accessibility import (
    CaptureError, SelectionSnapshot, UnsafeReplacement,
    capture_selection, replace_selection,
)


class App:
    def __init__(self, pid=321, name="Editor"):
        self.pid, self.name = pid, name

    def get_process_id(self): return self.pid
    def get_name(self): return self.name


class Text:
    def __init__(self, value="selected", calls=None):
        self.value, self.calls = value, calls if calls is not None else []

    def get_n_selections(self): self.calls.append("count"); return 1
    def get_selection(self, index): self.calls.append("selection"); return SimpleNamespace(start_offset=2, end_offset=10)
    def get_text(self, start, end): self.calls.append("content"); return self.value


class State:
    def contains(self, _state): return True
    def get_state_set(self): return self


class Node:
    def __init__(self, role="text", app=None, parent=None, text=None):
        self.role, self.app, self.parent, self.text = role, app or App(), parent, text
        self.calls = []

    def get_role_name(self): return self.role
    def get_application(self): return self.app
    def get_parent(self): return self.parent
    def get_name(self): return "field"
    def get_role_name(self): return self.role
    def get_child_count(self): return 0
    def get_state_set(self): return State()
    def get_child_at_index(self, _index): return None
    def get_text_iface(self): self.calls.append("text_iface"); return self.text


class FakeAtspi:
    Text = SimpleNamespace(get_n_selections=lambda x: x.get_n_selections(), get_selection=lambda x, i: x.get_selection(i), get_text=lambda x, a, b: x.get_text(a, b))
    class StateType: FOCUSED = object()
    def __init__(self, node): self.node = node
    def get_desktop(self, _index): return self.node


class AccessibilityTests(unittest.TestCase):
    def test_reads_bounded_selection_and_returns_identity(self):
        txt = Text()
        node = Node(text=txt)
        result = capture_selection(atspi=FakeAtspi(node), own_pid=999)
        self.assertEqual(result, SelectionSnapshot("selected", 321, "Editor", "text", "field", 2, 10))
        self.assertEqual(txt.calls, ["count", "selection", "content"])

    def test_password_role_blocks_before_text_interface_or_content(self):
        node = Node(role="password text", text=Text())
        with self.assertRaises(CaptureError):
            capture_selection(atspi=FakeAtspi(node), own_pid=999)
        self.assertEqual(node.calls, [])
        self.assertEqual(node.text.calls, [])

    def test_password_ancestor_blocks_before_text_interface(self):
        parent = Node(role="password container")
        node = Node(parent=parent, text=Text())
        with self.assertRaises(CaptureError):
            capture_selection(atspi=FakeAtspi(node), own_pid=999)
        self.assertEqual(node.calls, [])
        self.assertEqual(node.text.calls, [])

    def test_terminal_and_code_roles_block(self):
        for role in ("terminal", "code editor"):
            node = Node(role=role, text=Text())
            with self.subTest(role=role), self.assertRaises(CaptureError):
                capture_selection(atspi=FakeAtspi(node), own_pid=999)
            self.assertEqual(node.calls, [])
            self.assertEqual(node.text.calls, [])

    def test_own_process_is_excluded(self):
        node = Node(text=Text())
        with self.assertRaises(CaptureError):
            capture_selection(atspi=FakeAtspi(node), own_pid=321)
        self.assertEqual(node.calls, [])

    def test_oversized_range_does_not_read_content(self):
        class TooLong(Text):
            def get_selection(self, _index): self.calls.append('selection'); return SimpleNamespace(start_offset=0, end_offset=20_001)
        txt = TooLong()
        with self.assertRaises(CaptureError):
            capture_selection(atspi=FakeAtspi(Node(text=txt)), own_pid=999)
        self.assertEqual(txt.calls, ["count", "selection"])

    def test_ambiguous_marker_is_not_silently_stripped(self):
        with self.assertRaises(CaptureError):
            capture_selection(atspi=FakeAtspi(Node(text=Text('emoji 😃\ufeff'))), own_pid=999)

    def test_focused_container_does_not_hide_text_child(self):
        child = Node(text=Text())
        class Container(Node):
            def get_child_count(self): return 1
            def get_child_at_index(self, index): return child
        result = capture_selection(atspi=FakeAtspi(Container()), own_pid=999)
        self.assertEqual(result.text, 'selected')

    def test_replacement_always_fails_closed_and_does_not_mutate(self):
        snap = SelectionSnapshot("original", 321, "Editor", "text", "field", 2, 10)
        with self.assertRaises(UnsafeReplacement):
            replace_selection(snap, "corrected")


if __name__ == "__main__":
    unittest.main()
