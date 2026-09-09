"""
Сливане на реплики в изказвания.

Субтитрите са нарязани за четене с очи — по два реда, по 2 секунди.
За глас това е неизползваемо: TTS-ът ще спира по средата на изречението.
Тук съседните редове на един и същ говорител стават едно изказване
с общ таймкод.

Звуковите описания стават отделни изказвания — те се четат от
разказвач, не от гласа на героя.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from .srt import Cue

UttKind = Literal["speech", "sound"]

MAX_GAP = 1.5        # пауза, над която не се слива
MAX_DURATION = 15.0  # по-дълго от това не се слива в едно


@dataclass
class Utterance:
    start: float
    end: float
    text: str
    kind: UttKind = "speech"
    speaker: str | None = None
    generic: bool = False       # родов етикет (MAN, WOMAN)
    inferred: bool = False      # името е пренесено, не прочетено
    parts: int = 1              # от колко реда е слято
    cues: list[int] = field(default_factory=list)
    slot: float = 0.0           # време до следващото изказване

    @property
    def duration(self) -> float:
        return self.end - self.start

    @property
    def chars_per_second(self) -> float:
        """Колко бързо трябва да се изговори, за да се побере в слота."""
        return len(self.text) / self.slot if self.slot else float("inf")


def _mergeable(a: Utterance, b: Utterance) -> bool:
    if a.kind != "speech" or b.kind != "speech":
        return False
    if a.speaker != b.speaker or a.speaker is None:
        return False
    if b.start - a.end > MAX_GAP:
        return False
    if b.end - a.start > MAX_DURATION:
        return False
    return True


def _join(a: Utterance, b: Utterance) -> Utterance:
    a.text = f"{a.text} {b.text}".strip()
    a.end = b.end
    a.parts += b.parts
    a.cues += b.cues
    # Явно прочетеното име бие пренесеното — иначе губим котва.
    a.inferred = a.inferred and b.inferred
    return a


def build(cues: list[Cue]) -> list[Utterance]:
    """Реплики -> изказвания, готови за превод и за TTS."""
    flat: list[Utterance] = []

    for cue in cues:
        for sound in cue.sounds:
            flat.append(Utterance(
                start=cue.start, end=cue.end, text=sound.strip(),
                kind="sound", cues=[cue.idx],
            ))
        for line in cue.lines:
            flat.append(Utterance(
                start=cue.start, end=cue.end, text=line.text,
                kind="speech", speaker=line.speaker,
                generic=line.generic, inferred=line.inferred,
                cues=[cue.idx],
            ))

    merged: list[Utterance] = []
    for utt in flat:
        if merged and _mergeable(merged[-1], utt):
            _join(merged[-1], utt)
        else:
            merged.append(utt)

    # Слотът е времето до следващото изказване — колко има за изговаряне.
    for i, utt in enumerate(merged):
        nxt = merged[i + 1].start if i + 1 < len(merged) else utt.end + 3.0
        utt.slot = max(utt.duration, nxt - utt.start)

    return merged


def stats(utts: list[Utterance]) -> dict:
    speech = [u for u in utts if u.kind == "speech"]
    merged = [u for u in speech if u.parts > 1]
    tight = [u for u in speech if u.chars_per_second > 17]
    return {
        "utterances": len(utts),
        "speech": len(speech),
        "sound": len(utts) - len(speech),
        "merged": len(merged),
        "avg_parts": round(sum(u.parts for u in speech) / len(speech), 2) if speech else 0,
        "longest_s": round(max((u.duration for u in speech), default=0), 1),
        "tight_slots": len(tight),
    }
