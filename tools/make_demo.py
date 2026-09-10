"""
Генерира пробното аудио за addon-а.

    python -m tools.make_demo addon/audio/tiflo-demo.mp3

Текстът е собствен — не са реплики от филм. Върти се в CI, така че
mp3-то в репото винаги отговаря на този файл.

Иска espeak-ng и ffmpeg.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import wave
from pathlib import Path

# (височина 0-99, текст). 50 е базата на espeak.
LINES = [
    (50, "Тифло. Аудио дескрипция за хора с увредено зрение."),
    (50, "Всеки герой получава различен глас."),
    (31, "Аз съм първият герой, най-ниският от четиримата."),
    (41, "Аз съм вторият. Малко по-висок."),
    (59, "Третият глас звучи ето така."),
    (69, "А аз съм четвъртият, най-високият."),
    (50, "Четири различими гласа, без да се пипа звукът на филма."),
    (50, "Това е проба с еспик. Истинският синтез ще е с невронни гласове."),
]


def synth(out: Path, tmp: Path) -> None:
    exe = shutil.which("espeak-ng") or shutil.which("espeak")
    if not exe:
        raise SystemExit("липсва espeak-ng")

    parts = []
    for i, (pitch, text) in enumerate(LINES):
        chunk = tmp / f"part{i:02d}.wav"
        subprocess.run(
            [exe, "-v", "bg", "-p", str(pitch), "-s", "148", "-w", str(chunk), text],
            check=True,
        )
        parts.append(chunk)

    joined = tmp / "joined.wav"
    with wave.open(str(joined), "wb") as dst:
        first = True
        for chunk in parts:
            with wave.open(str(chunk), "rb") as piece:
                if first:
                    dst.setparams(piece.getparams())
                    first = False
                dst.writeframes(piece.readframes(piece.getnframes()))

    out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", str(joined),
         "-codec:a", "libmp3lame", "-b:a", "64k", "-ar", "22050", str(out)],
        check=True,
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("out", type=Path, nargs="?",
                    default=Path("addon/audio/tiflo-demo.mp3"))
    args = ap.parse_args()

    tmp = Path(".demo-tmp")
    tmp.mkdir(exist_ok=True)
    try:
        synth(args.out, tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print(f"{args.out}  {args.out.stat().st_size} B")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
