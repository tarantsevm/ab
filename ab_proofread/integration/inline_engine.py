"""Persistent in-process wrapper around the local LanguageTool service."""
from dataclasses import replace
from itertools import groupby
from pathlib import Path
import re
import threading

from ..core import corrected_text
from ..engines.languagetool import LTClient, LTService

MAX_TEXT = 20_000
MAX_SUGGESTIONS = 100
CYRILLIC = re.compile(r'[\u0400-\u052f]')
LATIN = re.compile(r'[A-Za-z]')


def _language_runs(text, language):
    """Yield newline-preserving runs; Cyrillic lines use Russian, others stay untouched."""
    def line_language(line):
        if CYRILLIC.search(line):
            return 'ru-RU'
        if LATIN.search(line):
            return None
        return language

    return [(lang, ''.join(lines)) for lang, lines in
            groupby(text.splitlines(keepends=True), key=line_language)]


class InlineEngine:
    def __init__(self, *, client=None, service=None):
        self.client = client or LTClient("http://127.0.0.1:18084", timeout=8)
        self.service = service
        self._warm_lock = threading.Lock()
        self._warmed = False
        self._warming = False

    @classmethod
    def local(cls):
        jar = Path('/usr/share/ab-proofread-languagetool/languagetool-server.jar')
        return cls(service=LTService(jar, port=18084))

    def start(self):
        """Start the local service without sending any text to it."""
        if self.service:
            self.service.ensure_running()

    def warm_russian(self):
        """Warm the Russian pipeline once using a fixed, non-user phrase."""
        with self._warm_lock:
            if self._warmed or self._warming:
                return
            self._warming = True
        try:
            self.start()
            self.client.check("Это проверочная фраза.", "ru-RU")
        except Exception:
            with self._warm_lock:
                self._warming = False
            raise
        with self._warm_lock:
            self._warmed = True
            self._warming = False

    def review(self, text, language):
        if not isinstance(text, str) or not text.strip() or len(text) > MAX_TEXT:
            raise ValueError("invalid or oversized selection")
        runs = _language_runs(text, language)
        # Bound serial requests for selections with frequent language switches.
        if len(runs) > 12:
            raise ValueError('too many language transitions for inline review')
        suggestions = []
        findings = False
        offset = 0
        for lang, chunk in runs:
            if lang is None:
                offset += len(chunk)
                continue
            matches = self.client.check(chunk, lang)
            findings = findings or bool(matches)
            suggestions.extend(replace(s, start=s.start + offset, end=s.end + offset)
                               for s in matches[:MAX_SUGGESTIONS - len(suggestions)]
                               if 0 <= s.start <= s.end <= len(chunk))
            offset += len(chunk)
            if len(suggestions) >= MAX_SUGGESTIONS:
                break
        accepted = {}
        parts = []
        cursor = 0
        last_start = -1
        for i, item in sorted(enumerate(suggestions), key=lambda pair: (pair[1].start, pair[1].end)):
            if not (cursor <= item.start <= item.end <= len(text)) or item.start == last_start:
                continue
            spelling = item.rule_id in ('MORFOLOGIK_RULE_RU_RU', 'MORFOLOGIK_RULE_EN_US')
            if not item.replacements or (len(item.replacements) != 1 and not spelling):
                continue
            replacement = item.replacements[0]
            if replacement == text[item.start:item.end] or len(replacement) > 512:
                continue
            parts.extend(({"text": text[cursor:item.start], "changed": False},
                          {"text": replacement, "changed": True}))
            accepted[i] = replacement
            cursor, last_start = item.end, item.start
        if cursor < len(text):
            parts.append({"text": text[cursor:], "changed": False})
        parts = [p for p in parts if p["text"] or p["changed"]]
        result = corrected_text(text, suggestions, accepted)
        if len(result) > MAX_TEXT:
            raise ValueError("oversized result")
        changes = len(accepted)
        return {"review":"result", "text":result, "changes":changes, "findings":findings, "parts":parts}

    def close(self):
        if self.service:
            self.service.stop()
