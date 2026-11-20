"""Safe, explicit LanguageTool suggestion handling."""
from dataclasses import dataclass
from typing import Mapping, Sequence
import re

@dataclass(frozen=True)
class Suggestion:
    start: int
    end: int
    message: str
    replacements: tuple[str, ...]
    rule_id: str

def utf16_to_codepoint(text: str, offset: int) -> int:
    """Convert UTF-16 code units; reject invalid offsets and surrogate splits."""
    if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0: raise ValueError("offset must be a non-negative integer")
    units = 0
    for index, char in enumerate(text):
        if units == offset: return index
        width = 2 if ord(char) > 0xFFFF else 1
        if units < offset < units + width: raise ValueError("offset splits a UTF-16 surrogate pair")
        units += width
    if units == offset: return len(text)
    raise ValueError("UTF-16 offset is outside the text")

_PROTECTED = re.compile(r"```[\s\S]*?```|`[^`]*`|(?:https?://|www\.)[^\s<>]+|[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}|\b(?:\d{1,3}\.){3}\d{1,3}\b|\b[0-9A-Fa-f]{2}(?::[0-9A-Fa-f]{2}){5}\b|(?:/|~/|\.\.?/)[^\s]+|(?<!\w)#[\w-]+")
_TECHNICAL = re.compile(r'\b(?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,63}\b|\b[0-9a-fA-F]{16,}\b|\b(?:[A-Za-z0-9]+[-_]){2,}[A-Za-z0-9]+\b')
def _protected_spans(text):
    return [(m.start(), m.end()) for pattern in (_PROTECTED, _TECHNICAL) for m in pattern.finditer(text)]

def parse_matches(text: str, payload: dict, dictionary_exclusions: Sequence[str] = ()) -> list[Suggestion]:
    """Parse LT v2/check matches. Offsets are UTF-16 units."""
    if not isinstance(payload, dict) or not isinstance(payload.get("matches"), list): raise ValueError("invalid LanguageTool response")
    protected, excluded, result = _protected_spans(text), {x.casefold() for x in dictionary_exclusions}, []
    for match in payload["matches"]:
        try:
            offset, length = match["offset"], match["length"]
        except (KeyError, TypeError) as exc:
            raise ValueError("malformed LanguageTool match") from exc
        if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0: raise ValueError("invalid match offset")
        if isinstance(length, bool) or not isinstance(length, int) or length < 0: raise ValueError("invalid match length")
        start, end = utf16_to_codepoint(text, offset), utf16_to_codepoint(text, offset + length)
        if any((start < b and end > a) or (start == end and a < start < b) for a, b in protected) or text[start:end].casefold() in excluded: continue
        replacements = tuple(r["value"] for r in match.get("replacements", []) if isinstance(r, dict) and isinstance(r.get("value"), str))
        rule = match.get("rule") or {}
        result.append(Suggestion(start, end, str(match.get("message", "")), replacements, str(rule.get("id", ""))))
    return result

def corrected_text(text: str, suggestions: Sequence[Suggestion], accepted: Mapping[int, str]) -> str:
    """Apply explicit accepted replacement strings; proposals are never automatic."""
    if not isinstance(accepted, Mapping): raise TypeError("accepted must map indices to replacement strings")
    chosen = []
    for index, replacement in accepted.items():
        if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < len(suggestions): raise ValueError(f"invalid suggestion index: {index!r}")
        item = suggestions[index]
        if not isinstance(replacement, str) or replacement not in item.replacements: raise ValueError(f"replacement is not offered for suggestion {index}")
        if not isinstance(item.start, int) or not isinstance(item.end, int) or not 0 <= item.start <= item.end <= len(text): raise ValueError(f"invalid bounds for suggestion {index}")
        chosen.append((item.start, item.end, replacement))
    chosen.sort()
    if any(chosen[i][0] < chosen[i-1][1] or chosen[i][0] == chosen[i-1][0] for i in range(1, len(chosen))): raise ValueError("accepted suggestions overlap")
    for start, end, value in reversed(chosen): text = text[:start] + value + text[end:]
    return text
