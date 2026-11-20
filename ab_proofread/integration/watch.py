"""Event-driven AT-SPI selection affordance for the system-wide shell UI."""
from __future__ import annotations

import json
import os
import re
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

from .inline_engine import CYRILLIC, InlineEngine
from .accessibility import CaptureError, _check_target
from .editor_adapter import EditorAdapter

_BLOCKED_APP_NAMES = (
    "terminal", "console", "visual studio code", "vscode", "code -",
    "pycharm", "intellij", "webstorm", "sublime text", "atom", "ptyxis", "kgx",
    "ab_proofread",
)


def _blocked_application(name: str) -> bool:
    folded = str(name or "").casefold()
    return any(term in folded for term in _BLOCKED_APP_NAMES)


class Protocol:
    """Newline JSON protocol; incoming checks are exclusively user clicks."""

    def __init__(self, write):
        self.write = write
        self._last_selection = None

    def emit(self, value: dict) -> None:
        self.write(json.dumps(value, separators=(",", ":"), ensure_ascii=False) + "\n")

    def emit_selection(self, selected: bool) -> None:
        selected = bool(selected)
        if selected != self._last_selection:
            self._last_selection = selected
            self.emit({"selection": selected})

    def handle_line(self, line: str):
        try:
            request = json.loads(line)
        except (TypeError, ValueError):
            return False
        if isinstance(request, dict) and set(request) == {"check"} and request["check"] is True:
            return True
        if isinstance(request, dict) and set(request) == {"replace"}:
            value = request["replace"]
            if isinstance(value, str) and re.fullmatch(r'[0-9a-f]{32}', value):
                return value
        return False


class SelectionWatcher:
    """Maintain selection affordance from AT-SPI events, never by polling."""

    def __init__(self, atspi, protocol: Protocol, *, own_pid=None, engine=None, dispatch=None, adapter=None):
        self.atspi = atspi
        self.protocol = protocol
        self.own_pid = os.getpid() if own_pid is None else own_pid
        self.engine = engine
        self.adapter = adapter
        self.proposal: tuple | None = None
        self.dispatch = dispatch or (lambda fn: fn())
        self.pending = None
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ab_proofread-inline")
        self._generation = 0
        self.source = None
        self.start = self.end = None
        self.focused = False

    def clear(self) -> None:
        self._generation += 1
        self.proposal = None
        self.source = None
        self.start = self.end = None
        self.focused = False
        self.protocol.emit_selection(False)

    def _focused_source(self):
        try:
            from .accessibility import _focused_accessible
            return _focused_accessible(self.atspi)
        except CaptureError:
            return None

    def _read_selection(self, target):
        app, _pid, app_name = _check_target(target, self.own_pid)
        if _blocked_application(app_name):
            raise CaptureError("Application is excluded from the selection watcher")
        if not target.get_state_set().contains(self.atspi.StateType.EDITABLE):
            raise CaptureError("Focused target is not an editable text object")
        iface = target.get_text_iface()
        if iface is None or int(self.atspi.Text.get_n_selections(iface)) != 1:
            raise CaptureError("No single selection")
        selection = self.atspi.Text.get_selection(iface, 0)
        start, end = int(selection.start_offset), int(selection.end_offset)
        if start < 0 or end <= start or end - start > 20_000:
            raise CaptureError("Invalid or oversized selection")
        return iface, start, end

    def refresh(self, event=None):
        """Re-evaluate metadata on AT-SPI event; never reads selected contents."""
        target = event.source if event is not None else self._focused_source()
        if target is None:
            self.clear()
            return
        try:
            if not target.get_state_set().contains(self.atspi.StateType.FOCUSED):
                raise CaptureError("Focus changed")
            _iface, start, end = self._read_selection(target)
        except Exception:
            self.clear()
            return
        if self.source is not None and (target, start, end) != (self.source, self.start, self.end):
            self.clear()
        self.source, self.start, self.end, self.focused = target, start, end, True
        self.protocol.emit_selection(True)

    def on_event(self, event, *_):
        if event.type.startswith(("object:text-selection-changed", "object:selection-changed",
                                  "object:text-caret-moved")):
            self.refresh(event)
        elif not event.type.startswith('object:text-changed') or event.source == self.source:
            self.clear()

    def check_clicked(self):
        """Read the live range after an explicit click on the same focused source."""
        target = self.source
        self.proposal = None
        generation = self._generation
        if target is None or not self.focused:
            self.clear()
            return False
        try:
            if not target.get_state_set().contains(self.atspi.StateType.FOCUSED):
                raise CaptureError("Focus changed")
            iface, start, end = self._read_selection(target)
            if generation != self._generation or target != self.source:
                raise CaptureError("Selection source changed")
            text = self.atspi.Text.get_text(iface, start, end)
            if generation != self._generation or target != self.source:
                raise CaptureError("Selection source changed")
            if not isinstance(text, str) or not text.strip() or len(text) > 20_000 or "\ufeff" in text:
                raise CaptureError("Invalid selected text")
            self.start, self.end = start, end
            if not CYRILLIC.search(text):
                self.protocol.emit({"review": "unsupported"})
                return False
            language = "ru-RU"
            if self.pending and not self.pending.done():
                self.protocol.emit({"review": "error"})
                return False
            self.protocol.emit({"review": "loading"})
            offer = None
            if self.adapter is not None:
                offer = self.adapter.prepare(target.get_process_id(), start, end, text)
                if offer and not self._live_range(target, start, end, generation):
                    self.clear()
                    return False
            self.pending = self.executor.submit(self._review, text, language, generation, offer)
            return True
        except Exception:
            self.clear()
            return False

    def register(self):
        """Register AT-SPI event listeners and announce readiness."""
        self.event_names = ("object:text-selection-changed", "object:selection-changed",
                            "object:text-caret-moved",
                            "object:state-changed:focused", "window:deactivate", "object:text-changed")
        self.listener = self.atspi.EventListener.new(self.on_event)
        for name in self.event_names:
            if not self.listener.register(name):
                raise RuntimeError('AT-SPI listener registration failed')
        self.protocol.emit({"ready": True})

    def _live_range(self, target, start, end, generation):
        try:
            if self._focused_source() != target or not target.get_state_set().contains(self.atspi.StateType.FOCUSED):
                return False
            _, live_start, live_end = self._read_selection(target)
            return generation == self._generation and (start, end) == (live_start, live_end)
        except Exception:
            return False

    def replace_clicked(self, proposal_id):
        if not self.proposal or self.proposal[0] != proposal_id:
            self.protocol.emit({'replacement': 'refused', 'id': proposal_id})
            return False
        _, offer, text, source, start, end, generation = self.proposal
        self.proposal = None
        changed = False
        if self.adapter is not None and self._live_range(source, start, end, generation):
            changed = self.adapter.replace(offer, text)
        self.clear()
        outcome = 'unknown' if changed is None else 'applied' if changed else 'refused'
        self.protocol.emit({'replacement': outcome, 'id': proposal_id})
        return changed

    def _review(self, text, language, generation, offer):
        try:
            if self.engine is None:
                raise RuntimeError('local engine unavailable')
            self.engine.start()
            result = self.engine.review(text, language)
        except Exception:
            result = {"review":"error"}
        def deliver():
            if generation == self._generation and self.source is not None:
                preview = {key: val for key, val in result.items() if key != 'text'}
                corrected = result.get('text')
                if (offer and offer.expires > time.monotonic_ns() // 1000 and
                        result.get('changes', 0) > 0 and isinstance(corrected, str) and corrected != text):
                    proposal_id = uuid.uuid4().hex
                    self.proposal = (proposal_id, offer, corrected, self.source, self.start, self.end, generation)
                    preview['replace'] = proposal_id
                self.protocol.emit(preview)
            return False
        self.dispatch(deliver)

    def close(self):
        self.executor.shutdown(wait=False, cancel_futures=True)
        if self.engine:
            self.engine.close()
        for name in self.event_names:
            self.listener.deregister(name)


def _main():
    try:
        import gi
        gi.require_version("Atspi", "2.0")
        from gi.repository import Atspi, GLib
    except Exception as exc:
        print(f"ab Proofread AT-SPI unavailable: {exc}", file=sys.stderr)
        return 1
    Atspi.init()
    Atspi.set_timeout(200, 2000)
    protocol = Protocol(lambda line: (sys.stdout.write(line), sys.stdout.flush()))
    try:
        engine = InlineEngine.local()
    except OSError:
        engine = None
    try:
        adapter = EditorAdapter.local()
    except GLib.Error:
        adapter = None
    watcher = SelectionWatcher(Atspi, protocol, engine=engine, dispatch=GLib.idle_add, adapter=adapter)
    if engine is not None:
        watcher.executor.submit(engine.warm_russian)
    loop = GLib.MainLoop()
    watcher.register()
    def input_reader():
        try:
            while line := sys.stdin.readline(256):
                if not line.endswith('\n'):
                    break
                request = watcher.protocol.handle_line(line)
                if request is True:
                    GLib.idle_add(lambda: (watcher.check_clicked(), GLib.SOURCE_REMOVE)[1])
                elif isinstance(request, str):
                    GLib.idle_add(lambda proposal_id=request: (watcher.replace_clicked(proposal_id), GLib.SOURCE_REMOVE)[1])
        finally:
            GLib.idle_add(loop.quit)
    threading.Thread(target=input_reader, daemon=True).start()
    try:
        loop.run()
    finally:
        watcher.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
