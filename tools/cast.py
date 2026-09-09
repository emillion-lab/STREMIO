"""
Пол на говорителите от TMDb.

    python -m tools.cast subs/tt0133093_3_4486137.srt tt0133093

Взима имената от SDH субтитрите, дърпа състава от TMDb и показва кой
герой какъв глас ще получи. Нищо не се записва — само проверка.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path

from tiflo import srt, voices
from tiflo.voices import Voice

ROOT = Path(__file__).resolve().parent.parent

# Български невронни гласове в Azure Speech. Провери имената в
# актуалната документация, преди да пуснеш истински TTS.
DEFAULT_POOL = [
    Voice("bg-BG-BorislavNeural", "male"),
    Voice("bg-BG-KalinaNeural", "female"),
]


def env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        path = ROOT / ".env"
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip().startswith(f"{name}="):
                    value = line.split("=", 1)[1].strip().strip("'\"")
    if not value:
        raise SystemExit(f"липсва {name} в .env")
    return value


def read(path: Path) -> str:
    raw = path.read_bytes()
    for enc in ("utf-8-sig", "utf-8", "cp1251", "cp1252", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    raise SystemExit("не мога да декодирам файла")


def main() -> int:
    ap = argparse.ArgumentParser(description="Пол на говорителите от TMDb")
    ap.add_argument("path", type=Path, help="файл със субтитри")
    ap.add_argument("imdb", help="IMDB id, напр. tt0133093")
    args = ap.parse_args()

    cues = srt.parse(read(args.path))
    anchors = srt.anchors(cues)
    if not anchors:
        raise SystemExit("няма явни имена — това SDH ли е?")

    weights = {name: len(spans) for name, spans in anchors.items()}
    cast = voices.fetch_cast(args.imdb, env("TMDB_API_KEY"))
    print(f"\n  TMDb състав: {len(cast)} записа")

    matches = voices.match_speakers(list(anchors), cast)
    st = voices.stats(matches)
    print(f"  говорители   {st['speakers']}  "
          f"({st['male']} м, {st['female']} ж, {st['unknown']} неясни)")
    print(f"  от TMDb      {st['from_tmdb']}   от етикет {st['from_label']}\n")

    assigned = voices.assign_voices(matches, DEFAULT_POOL, weights)

    print(f"  {'ГОВОРИТЕЛ':<16}{'РЕПЛ':>5}  {'ПОЛ':<8}{'ГЛАС':<26}ГЕРОЙ В TMDB")
    for name in sorted(anchors, key=lambda n: -weights[n]):
        m = matches[name]
        voice = assigned.get(name)
        mark = "" if m.confidence >= 0.9 or m.gender == "unknown" else " ?"
        print(f"  {name:<16}{weights[name]:>5}  {m.gender:<8}"
              f"{(voice.id if voice else '—'):<26}{m.character or ''}{mark}")

    if st["unknown"]:
        print(f"\n  {st['unknown']} говорителя без пол — те чакат диаризацията.")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
