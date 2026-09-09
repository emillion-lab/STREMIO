"""
Проверка на истински файл със субтитри.

    python -m tools.check path/to/file.srt
    python -m tools.check path/to/file.srt --lines 40

Показва статистиката и как са разпознати първите реплики, за да се види
веднага дали етикетите на конкретния рип се хващат от регексите.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from tiflo import srt


def read(path: Path) -> str:
    """SRT файловете са в какви ли не кодировки. Пробваме по ред."""
    raw = path.read_bytes()
    for enc in ("utf-8-sig", "utf-8", "cp1251", "cp1252", "iso-8859-5", "latin-1"):
        try:
            text = raw.decode(enc)
        except UnicodeDecodeError:
            continue
        if enc != "utf-8-sig":
            print(f"  (декодиран като {enc})", file=sys.stderr)
        return text
    raise SystemExit("не мога да декодирам файла")


def timecode(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h:d}:{m:02d}:{s:02d}"


def main() -> int:
    ap = argparse.ArgumentParser(description="Проверка на SDH субтитри")
    ap.add_argument("path", type=Path)
    ap.add_argument("--lines", type=int, default=25, help="колко реплики да покаже")
    args = ap.parse_args()

    if not args.path.exists():
        raise SystemExit(f"няма такъв файл: {args.path}")

    cues = srt.parse(read(args.path))
    if not cues:
        raise SystemExit("нула разпознати реплики — това SRT ли е?")

    st = srt.stats(cues)
    print(f"\n{args.path.name}")
    print(f"  реплики          {st['cues']}")
    print(f"  редове           {st['lines']}")
    print(f"  с говорител      {st['with_speaker']}  ({st['coverage']:.0%})")
    print(f"  имена            {st['distinct_speakers']}")
    print(f"  звукови описания {st['sound_cues']}")
    print(f"  времетраене      {st['runtime_min']} мин")

    if st["coverage"] < 0.1:
        print("\n  ВНИМАНИЕ: това почти сигурно не са SDH субтитри.")
        print("  Търси версия с етикети (OpenSubtitles: hearing impaired).")

    names = srt.anchors(cues)
    if names:
        top = sorted(names.items(), key=lambda kv: -len(kv[1]))[:12]
        print("\n  Най-често срещани имена:")
        for name, spans in top:
            print(f"    {name:<20} {len(spans)}")

    print(f"\n  Първите {args.lines} реплики:\n")
    shown = 0
    for cue in cues:
        if shown >= args.lines:
            break
        for line in cue.lines:
            if line.generic:
                who = f"~{line.speaker}"     # родов етикет
            elif line.inferred:
                who = f"({line.speaker})"    # пренесено име
            elif line.speaker:
                who = line.speaker
            else:
                who = "?"
            print(f"    {timecode(cue.start)}  {who:<18} {line.text[:60]}")
            shown += 1
        for sound in cue.sounds:
            print(f"    {timecode(cue.start)}  {'· звук':<18} {sound[:60]}")

    print("\n  легенда: ИМЕ = явно · (ИМЕ) = пренесено · ~ИМЕ = родово · ? = няма\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
