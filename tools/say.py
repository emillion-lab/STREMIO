"""
Чуй как звучат гласовете.

    pkg install espeak-ng
    python -m tools.say subs/файл.srt --from 60 --count 12
    python -m tools.say subs/файл.srt --out проба.wav
    python -m tools.say subs/файл.srt --dry

Два начина за говорене, избират се сами:
  espeak-ng    работи само с pkg install espeak-ng, може и във файл
  termux-tts   вграденият глас на Android, иска приложението Termux:API
               (то трябва да е от СЪЩИЯ източник като Termux — иначе
                подписите не съвпадат и не тръгва)

Това е проба на РАЗЛИЧИМОСТТА на гласовете, не на крайното качество.
Истинският синтез ще е с български невронни гласове.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import wave
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


def _espeak_pitch(semitones: float) -> int:
    """espeak иска 0-99, а не полутонове. 50 е базата."""
    return max(5, min(95, round(50 + semitones * 7)))


def _espeak_speed(rate_pct: float) -> int:
    """espeak иска думи в минута; 165 е спокойно темпо."""
    return max(80, min(300, round(165 * (1 + rate_pct / 100))))


def _concat(parts: list[Path], out: Path) -> None:
    """Слепва парчетата в един wav, без външни зависимости."""
    with wave.open(str(out), "wb") as dst:
        first = True
        for chunk in parts:
            with wave.open(str(chunk), "rb") as piece:
                if first:
                    dst.setparams(piece.getparams())
                    first = False
                dst.writeframes(piece.readframes(piece.getnframes()))
            chunk.unlink()


def main() -> int:
    ap = argparse.ArgumentParser(description="Проба на гласовете")
    ap.add_argument("path", type=Path)
    ap.add_argument("--from", dest="start", type=float, default=0,
                    help="от коя минута нататък")
    ap.add_argument("--count", type=int, default=10)
    ap.add_argument("--dry", action="store_true", help="само покажи, не говори")
    ap.add_argument("--out", type=Path, help="запиши във wav вместо да говориш")
    ap.add_argument("--voice", default="en", help="език за espeak-ng, напр. bg")
    ap.add_argument("--backend", choices=("auto", "espeak", "termux"), default="auto")
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

    backend = args.backend
    if backend == "auto":
        if shutil.which("espeak-ng") or shutil.which("espeak"):
            backend = "espeak"
        elif shutil.which("termux-tts-speak"):
            backend = "termux"
        else:
            backend = "none"

    if backend == "none" and not args.dry:
        print("няма синтезатор.  pkg install espeak-ng", file=sys.stderr)
        print("Засега минавам на --dry.\n", file=sys.stderr)
        args.dry = True
    if args.out and backend != "espeak":
        raise SystemExit("--out работи само с espeak-ng")

    print(f"\n  {len(speakers)} говорителя, {len(chosen)} реплики"
          f"{'' if args.dry else '  (' + backend + ')'}\n")
    for s in speakers:
        p = prosody[s]
        print(f"    {s:<16} pitch ×{p.pitch_ratio}  ({p.pitch_st:+.1f} полутона)")
    print()

    parts: list[Path] = []
    for i, u in enumerate(chosen):
        p = prosody[u.speaker]
        print(f"  {u.speaker:<16} ×{p.pitch_ratio}  {u.text[:60]}")
        if args.dry:
            continue

        if backend == "espeak":
            exe = shutil.which("espeak-ng") or shutil.which("espeak")
            cmd = [exe, "-v", args.voice,
                   "-p", str(_espeak_pitch(p.pitch_st)),
                   "-s", str(_espeak_speed(p.rate_pct))]
            if args.out:
                chunk = args.out.with_suffix(f".{i:03d}.wav")
                cmd += ["-w", str(chunk)]
                parts.append(chunk)
            subprocess.run(cmd, input=u.text, text=True)
        else:
            subprocess.run(
                ["termux-tts-speak", "-p", str(p.pitch_ratio),
                 "-r", str(p.rate_ratio)],
                input=u.text, text=True,
            )

    if parts:
        _concat(parts, args.out)
        print(f"\n  записано: {args.out}")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
