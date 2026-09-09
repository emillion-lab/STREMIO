"""SRT/SDH парсер — първи слой на TIFLO."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

CueKind = Literal["dialogue", "sound", "mixed"]

_TIME = re.compile(
    r"(\d{1,2}):(\d{2}):(\d{2})[,.](\d{1,3})\s*-->\s*"
    r"(\d{1,2}):(\d{2}):(\d{2})[,.](\d{1,3})"
)
_TAGS = re.compile(r"</?[a-zA-Z][^>]*>|\{\\[^}]*\}")

_LABEL_BRACKET = re.compile(r"^\s*[\[(]\s*([A-ZА-Я][A-ZА-Я0-9 .'\-]{1,28})\s*[\])]\s*:?\s*")
_LABEL_PLAIN = re.compile(r"^\s*([A-ZА-Я][A-ZА-Я0-9 .'\-]{1,28})\s*:\s+")
_SOUND_ONLY = re.compile(r"^\s*[\[(][^\])]*[\])]\s*$")
_SOUND_ANY = re.compile(r"[\[(][^\])]*[\])]")
_DASH = re.compile(r"^\s*[-\u2013\u2014]\s*")

# Кредити на риппера — не са реплика и не бива да се четат на глас.
_CREDIT = re.compile(
    r"(subtitle|subs|sync|synced|corrected|improved|translat|encoded|ripped)"
    r"[\s\w]{0,20}(by|:)|www\.|https?://|opensubtitles|addic7ed|yify|@\w+\.\w",
    re.I,
)

_NOT_A_NAME = {
    "OK", "TV", "CD", "USA", "FBI", "CIA", "OH", "AH", "NO", "YES",
    "МЪЖ", "ЖЕНА", "ГЛАС", "MAN", "WOMAN", "VOICE",
}
_GENERIC_SPEAKER = {"MAN", "WOMAN", "VOICE", "МЪЖ", "ЖЕНА", "ГЛАС", "BOY", "GIRL"}


@dataclass
class Line:
    text: str
    speaker: str | None = None
    generic: bool = False
    dashed: bool = False      # редът започваше с тире = смяна на говорителя
    inferred: bool = False    # името е пренесено, не е прочетено


@dataclass
class Cue:
    idx: int
    start: float
    end: float
    lines: list[Line] = field(default_factory=list)
    kind: CueKind = "dialogue"
    sounds: list[str] = field(default_factory=list)

    @property
    def duration(self) -> float:
        return self.end - self.start

    @property
    def text(self) -> str:
        return " ".join(l.text for l in self.lines if l.text)

    @property
    def speakers(self) -> list[str]:
        return [l.speaker for l in self.lines if l.speaker]

    @property
    def is_multi_speaker(self) -> bool:
        return len(set(self.speakers)) > 1


def _to_seconds(h, m, s, ms) -> float:
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms.ljust(3, "0")) / 1000


def _clean(raw: str) -> str:
    return _TAGS.sub("", raw).replace("\u200e", "").replace("\u200f", "").strip()


def _looks_like_sound(name: str) -> bool:
    """[DOOR SLAMS] е звук, [MARTA] е говорител. Разликата е глаголът."""
    words = name.split()
    if len(words) > 3:
        return True
    return any(w.endswith("ING") for w in words) or (
        len(words) > 1 and words[-1].endswith("S") and not words[-1].endswith("SS")
    )


def _extract_label(text: str, known: set[str] | None = None):
    """
    Връща (говорител, останал текст, дали е родов).
    `known` са имената, срещнати в безспорна форма `ИМЕ:` другаде във файла —
    те решават спора при квадратни скоби.
    """
    body = _DASH.sub("", text)

    for pattern in (_LABEL_BRACKET, _LABEL_PLAIN):
        m = pattern.match(body)
        if not m:
            continue
        name = m.group(1).strip(" .'-")
        if not name or (name in _NOT_A_NAME and name not in _GENERIC_SPEAKER):
            continue
        rest = body[m.end():].strip()
        if not rest:
            continue

        if pattern is _LABEL_BRACKET and name not in _GENERIC_SPEAKER:
            trusted = known is not None and name in known
            if not trusted and _looks_like_sound(name):
                return None, body.strip(), False

        return name, rest, name.split()[0] in _GENERIC_SPEAKER

    return None, body.strip(), False


def _plain_names(content: str) -> set[str]:
    """Първи проход: само `ИМЕ:` — формата, която не се бърка със звук."""
    return {
        m.group(1).strip(" .'-")
        for line in content.split("\n")
        if (m := _LABEL_PLAIN.match(_DASH.sub("", _clean(line))))
    } - _NOT_A_NAME


def parse(content: str) -> list[Cue]:
    content = content.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n")
    known = _plain_names(content)
    cues: list[Cue] = []
    auto_idx = 0

    for block in re.split(r"\n{2,}", content):
        block = block.strip("\n")
        if not block:
            continue
        rows = block.split("\n")
        time_at = next((i for i, r in enumerate(rows) if _TIME.search(r)), None)
        if time_at is None:
            continue
        m = _TIME.search(rows[time_at])
        start = _to_seconds(*m.group(1, 2, 3, 4))
        end = _to_seconds(*m.group(5, 6, 7, 8))
        if end <= start:
            continue

        idx_row = rows[time_at - 1].strip() if time_at else ""
        auto_idx += 1
        idx = int(idx_row) if idx_row.isdigit() else auto_idx

        cue = Cue(idx=idx, start=start, end=end)
        has_dialogue = False

        for raw in rows[time_at + 1:]:
            row = _clean(raw)
            if not row:
                continue
            if _CREDIT.search(row):
                continue
            if _SOUND_ONLY.match(row):
                cue.sounds.append(row.strip("[]() "))
                continue
            dashed = bool(_DASH.match(row))
            speaker, body, generic = _extract_label(row, known)
            for s in _SOUND_ANY.findall(body):
                cue.sounds.append(s.strip("[]() "))
            body = _SOUND_ANY.sub("", body).strip()
            if not body:
                if speaker:
                    cue.sounds.append(speaker)
                continue
            cue.lines.append(
                Line(text=body, speaker=speaker, generic=generic, dashed=dashed)
            )
            has_dialogue = True

        if not has_dialogue and not cue.sounds:
            continue
        cue.kind = "mixed" if (has_dialogue and cue.sounds) else (
            "dialogue" if has_dialogue else "sound"
        )
        cues.append(cue)

    return _carry_speakers(cues)


CARRY_GAP = 4.0   # секунди пауза, след която името вече не се пренася


def _carry_speakers(cues):
    last = None
    last_end = -99.0
    for cue in cues:
        for line in cue.lines:
            if line.speaker:
                last = line.speaker
                continue
            # Тире означава смяна на говорителя — там няма какво да се пренесе.
            if line.dashed or cue.is_multi_speaker:
                continue
            if last and cue.start - last_end < CARRY_GAP:
                line.speaker = last
                line.inferred = True
        if cue.lines:
            last_end = cue.end
    return cues


def anchors(cues):
    """Само явните имена — това, на което може да се стъпи при диаризацията."""
    out = {}
    for cue in cues:
        for line in cue.lines:
            if line.speaker and not line.generic and not line.inferred:
                out.setdefault(line.speaker, []).append((cue.start, cue.end))
    return out


def stats(cues):
    named = sum(1 for c in cues for l in c.lines if l.speaker)
    total = sum(len(c.lines) for c in cues)
    return {
        "cues": len(cues),
        "lines": total,
        "with_speaker": named,
        "coverage": round(named / total, 3) if total else 0.0,
        "distinct_speakers": len(anchors(cues)),
        "sound_cues": sum(1 for c in cues if c.kind == "sound"),
        "runtime_min": round(cues[-1].end / 60, 1) if cues else 0,
    }
