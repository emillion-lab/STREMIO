"""
Чуй как звучат гласовете — през вградения TTS на Android.

    python -m tools.say subs/файл.srt --from 60 --count 12
    python -m tools.say subs/файл.srt --dry

Нужно е:  pkg install termux-api  + приложението Termux:API
С --dry само показва командите, без да говори.

Това е проба на РАЗЛИЧИМОСТТА на гласовете, не на крайното качество.
Истинският синтез ще е с български невронни гласове.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

from tiflo import srt, utterance
from tiflo.prosody import Profile, build


def read(path: Path) -> str:
    raw = path.read_bytes()
    for enc in ("utf-8-sig", "utf-8", "cp1251", "cp1252", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    raise SystemExit("не мога да декодирам файла")


def main() -> int:
    ap = argparse.ArgumentParser(description="Проба на гласовете")
    ap.add_argument("path", type=Path)
    ap.add_argument("--from", dest="start", type=float, default=0,
                    help="от коя минута нататък")
    ap.add_argument("--count", type=int, default=10)
    ap.add_argument("--dry", action="store_true", help="само покажи, не говори")
    ap.add_argument("--engine", default=None, help="TTS engine за termux-tts-speak")
    args = ap.parse_args()

    cues = srt.parse(read(args.path))
    utts = [u for u in utterance.build(cues)
            if u.kind == "speech" and u.speaker and u.start >= args.start * 60]
    if not utts:
        raise SystemExit("няма реплики с говорител в този участък")

    chosen = utts[:args.count]
    speakers = sorted({u.speaker for u in chosen})

    # Без измерен тон — гласовете просто се разпръскват, за да са различими.
    # Полът тук е без значение: пробваме различимостта, не верността.
    gender = {s: "male" for s in speakers}
    prosody = build([Profile(s) for s in speakers], gender)

    if not shutil.which("termux-tts-speak") and not args.dry:
        print("termux-tts-speak липсва.  pkg install termux-api", file=sys.stderr)
        print("плюс приложението Termux:API. Засега минавам на --dry.\n",
              file=sys.stderr)
        args.dry = True

    print(f"\n  {len(speakers)} говорителя, {len(chosen)} реплики\n")
    for s in speakers:
        p = prosody[s]
        print(f"    {s:<16} pitch ×{p.pitch_ratio}  ({p.pitch_st:+.1f} полутона)")
    print()

    for u in chosen:
        p = prosody[u.speaker]
        print(f"  {u.speaker:<16} ×{p.pitch_ratio}  {u.text[:60]}")
        if args.dry:
            continue
        cmd = ["termux-tts-speak", "-p", str(p.pitch_ratio), "-r", str(p.rate_ratio)]
        if args.engine:
            cmd += ["-e", args.engine]
        subprocess.run(cmd, input=u.text, text=True)

    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
