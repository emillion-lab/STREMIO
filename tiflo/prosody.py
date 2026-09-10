"""
Различими гласове от малък набор.

Azure дава два български невронни гласа. Дванадесет мъже с един и същ
глас са неизползваеми за незрящ слушател — гласът е единственият сигнал
кой говори.

Тук всеки говорител получава отместване по височина и темпо върху
базовия глас. Ако има измерен основен тон от филма, отместването се
смята от него и гласът се доближава до оригинала. Ако няма, гласовете
просто се разпръскват равномерно, за да са различими.

Границите не са естетика, а разбираемост: над ±4 полутона невронният
глас започва да звучи изкуствено и се разбира по-трудно. Когато двама
души са прекалено близо по тон, различимостта бие верността — по-важно
е да се чуе, че са двама, отколкото всеки да е точен.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

MAX_SEMITONES = 4.0    # над това звучи изкуствено
MIN_SEPARATION = 1.2   # под това два гласа не се различават на слух
MAX_RATE_PCT = 12.0    # темпо, отвъд което се губи разбираемост
BASE_SYLLABLES = 4.5   # приблизително темпо на базовия глас

# Ориентировъчен основен тон на базовите гласове. Измерва се веднъж от
# кратка проба на самия синтезатор — не се гадае.
BASE_F0 = {"male": 115.0, "female": 195.0}


@dataclass
class Profile:
    """Каквото сме измерили за един говорител от аудиото на филма."""
    speaker: str
    f0_hz: float | None = None          # медиана на основния тон
    syllables_per_s: float | None = None


@dataclass
class Prosody:
    """Готово за SSML."""
    speaker: str
    pitch_st: float = 0.0
    rate_pct: float = 0.0
    measured: bool = False

    @property
    def ssml(self) -> str:
        return f'pitch="{self.pitch_st:+.1f}st" rate="{self.rate_pct:+.0f}%"'

    @property
    def pitch_ratio(self) -> float:
        """Височината като множител — така я искат Android TTS и ffmpeg."""
        return round(2 ** (self.pitch_st / 12.0), 3)

    @property
    def rate_ratio(self) -> float:
        return round(1 + self.rate_pct / 100.0, 3)


def semitones(target_hz: float, base_hz: float) -> float:
    """Разлика в полутонове между два основни тона."""
    if target_hz <= 0 or base_hz <= 0:
        raise ValueError("честотата трябва да е положителна")
    return 12.0 * math.log2(target_hz / base_hz)


def _clamp(value: float, limit: float) -> float:
    return max(-limit, min(limit, value))


def _separate(pairs: list[tuple[str, float]]) -> dict[str, float]:
    """
    Разбутва стойности, които са прекалено близо, без да излиза от
    границата. Редът по височина се пази — по-високият глас си остава
    по-висок.
    """
    if not pairs:
        return {}
    ordered = sorted(pairs, key=lambda kv: kv[1])
    out = [list(p) for p in ordered]

    for i in range(1, len(out)):
        if out[i][1] - out[i - 1][1] < MIN_SEPARATION:
            out[i][1] = out[i - 1][1] + MIN_SEPARATION

    # Ако сме излезли нагоре, свиваме целия набор обратно в границите.
    overflow = out[-1][1] - MAX_SEMITONES
    if overflow > 0:
        span = out[-1][1] - out[0][1]
        room = 2 * MAX_SEMITONES
        if span > room:
            scale = room / span
            low = out[0][1]
            for row in out:
                row[1] = -MAX_SEMITONES + (row[1] - low) * scale
        else:
            for row in out:
                row[1] -= overflow

    return {name: round(_clamp(value, MAX_SEMITONES), 2) for name, value in out}


def build(profiles: list[Profile], gender: dict[str, str],
          base_f0: dict[str, float] | None = None) -> dict[str, Prosody]:
    """
    От измервания към отмествания, отделно за мъжките и женските гласове.
    Говорители без измерен тон се разпръскват равномерно в остатъка.
    """
    base = {**BASE_F0, **(base_f0 or {})}
    out: dict[str, Prosody] = {}

    for sex in ("male", "female"):
        group = [p for p in profiles if gender.get(p.speaker) == sex]
        if not group:
            continue

        measured = [p for p in group if p.f0_hz]
        plain = [p for p in group if not p.f0_hz]

        pairs = [
            (p.speaker, _clamp(semitones(p.f0_hz, base[sex]), MAX_SEMITONES))
            for p in measured
        ]

        # Неизмерените се разпръскват — само за да са различими.
        if plain:
            step = (2 * MAX_SEMITONES) / (len(plain) + 1)
            for i, p in enumerate(plain, 1):
                pairs.append((p.speaker, -MAX_SEMITONES + step * i))

        spread = _separate(pairs)

        for p in group:
            rate = 0.0
            if p.syllables_per_s:
                rate = _clamp(
                    (p.syllables_per_s / BASE_SYLLABLES - 1) * 100, MAX_RATE_PCT
                )
            out[p.speaker] = Prosody(
                speaker=p.speaker,
                pitch_st=spread[p.speaker],
                rate_pct=round(rate, 1),
                measured=bool(p.f0_hz),
            )

    return out


def distinguishable(prosody: dict[str, Prosody], gender: dict[str, str]) -> bool:
    """Проверка, че никои два гласа от един пол не са се слели."""
    for sex in ("male", "female"):
        vals = sorted(p.pitch_st for s, p in prosody.items() if gender.get(s) == sex)
        for a, b in zip(vals, vals[1:]):
            if b - a < MIN_SEPARATION - 0.01:
                return False
    return True
