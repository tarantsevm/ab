"""Opt-in GNOME Text Editor adapter on the local session bus only."""
from dataclasses import dataclass
import re
import time

BUS = 'org.freedesktop.DBus'
BUS_PATH = '/org/freedesktop/DBus'
EDITOR = 'local.ab_proofread.TextEditor1'
EDITOR_PATH = '/local/ab_proofread/TextEditor1'
TOKEN = re.compile(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\Z')


@dataclass(frozen=True)
class Offer:
    owner: str
    token: str
    expires: int


class EditorAdapter:
    def __init__(self, bus, gio):
        from gi.repository import GLib
        self.bus, self.gio, self.glib = bus, gio, GLib

    @classmethod
    def local(cls):
        from gi.repository import Gio
        return cls(Gio.bus_get_sync(Gio.BusType.SESSION, None), Gio)

    def _call(self, owner, path, iface, method, sig, args, reply):
        return self.bus.call_sync(
            owner, path, iface, method, self.glib.Variant(sig, args),
            self.glib.VariantType.new(reply), self.gio.DBusCallFlags.NO_AUTO_START,
            250, None,
        ).unpack()

    def prepare(self, pid, start, end, text):
        try:
            if not 0 < pid <= 0xffffffff or not 0 <= start < end <= 0x7fffffff:
                return None
            name = f'{EDITOR}.p{pid}'
            (owner,) = self._call(BUS, BUS_PATH, BUS, 'GetNameOwner', '(s)', (name,), '(s)')
            if not owner.startswith(':'):
                return None
            (actual_pid,) = self._call(BUS, BUS_PATH, BUS, 'GetConnectionUnixProcessID', '(s)', (owner,), '(u)')
            if actual_pid != pid or not 0 < len(text) <= 20_000 or '\0' in text:
                return None
            (token, expires) = self._call(owner, EDITOR_PATH, EDITOR, 'Prepare',
                                          '(iis)', (start, end, text), '(sx)')
            if TOKEN.fullmatch(token) and expires > time.monotonic_ns() // 1000:
                return Offer(owner, token, expires)
        except self.glib.Error:
            pass
        return None

    def replace(self, offer, text) -> bool | None:
        """True: applied, False: refused, None: no reliable reply."""
        now = time.monotonic_ns() // 1000
        if now >= offer.expires or len(text) > 20_000 or '\0' in text:
            return False
        # Reject a queued call that reaches the editor after the client times out.
        deadline = min(offer.expires, now + 200_000)
        try:
            (changed,) = self._call(offer.owner, EDITOR_PATH, EDITOR, 'Replace',
                                    '(ssx)', (offer.token, text, deadline), '(b)')
            return changed
        except self.glib.Error:
            # The editor may have already applied the edit before the reply was lost.
            return None
