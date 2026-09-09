"""
Търсене и сваляне на SDH субтитри от OpenSubtitles.com.

    python -m tools.fetch tt0133093
    python -m tools.fetch tt0133093 --limit 5 --lang en
    python -m tools.fetch tt0133093 tt0110912 tt0068646 --scan

Ключът се чете от .env (OPENSUBTITLES_API_KEY=...) или от средата.
Свалените файлове отиват в subs/ — тя е в .gitignore.
"""
from __future__ import annotations

import argparse
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from tiflo import srt

API = "https://api.opensubtitles.com/api/v1"
UA = "TIFLO/0.1"
ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "subs"


def api_key() -> str:
    key = os.environ.get("OPENSUBTITLES_API_KEY", "").strip()
    if not key:
        env = ROOT / ".env"
        if env.exists():
            for line in env.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line.startswith("OPENSUBTITLES_API_KEY="):
                    key = line.split("=", 1)[1].strip().strip("'\"")
    if not key:
        raise SystemExit(
            "няма ключ.\n"
            "Сложи го в .env:  OPENSUBTITLES_API_KEY=твоят_ключ\n"
            "Вади се от opensubtitles.com/en/consumers"
        )
    return key


def call(path: str, key: str, params: dict | None = None, body: dict | None = None):
    url = f"{API}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        method="POST" if data else "GET",
        headers={
            "Api-Key": key,
            "User-Agent": UA,
            "Accept": "application/json",
            **({"Content-Type": "application/json"} if data else {}),
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:400]
        raise SystemExit(f"HTTP {e.code} на {path}\n{detail}")
    except urllib.error.URLError as e:
        raise SystemExit(f"няма връзка: {e.reason}")


def search(key: str, imdb: str, lang: str, limit: int, only_sdh: bool = True):
    """Връща списък кандидати, подредени по популярност."""
    res = call("/subtitles", key, {
        "imdb_id": imdb.removeprefix("tt"),
        "languages": lang,
        "hearing_impaired": "only" if only_sdh else "include",
        "order_by": "download_count",
        "order_direction": "desc",
    })
    out = []
    for item in res.get("data", [])[:limit]:
        a = item.get("attributes", {})
        files = a.get("files") or []
        if not files:
            continue
        out.append({
            "file_id": files[0].get("file_id"),
            "release": a.get("release", "?"),
            "downloads": a.get("download_count", 0),
            "sdh": a.get("hearing_impaired", False),
            "fps": a.get("fps"),
            "title": (a.get("feature_details") or {}).get("movie_name", "?"),
        })
    return out


def download(key: str, file_id: int, dest: Path) -> Path:
    res = call("/download", key, body={"file_id": file_id, "sub_format": "srt"})
    link = res.get("link")
    if not link:
        raise SystemExit(f"няма линк в отговора: {json.dumps(res)[:300]}")
    left = res.get("remaining")
    if left is not None:
        print(f"    (остават {left} сваляния днес)")
    req = urllib.request.Request(link, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        dest.write_bytes(r.read())
    return dest


def coverage_of(path: Path) -> dict:
    raw = path.read_bytes()
    for enc in ("utf-8-sig", "utf-8", "cp1251", "cp1252", "latin-1"):
        try:
            return srt.stats(srt.parse(raw.decode(enc)))
        except UnicodeDecodeError:
            continue
    return {}


def cmd_scan(key: str, imdbs: list[str], lang: str) -> int:
    """Само проверява кои заглавия изобщо имат SDH. Не сваля нищо."""
    print(f"\n  {'IMDB':<12} {'SDH':<5} заглавие")
    for imdb in imdbs:
        try:
            hits = search(key, imdb, lang, limit=50)
        except SystemExit as e:
            print(f"  {imdb:<12} !     {e}")
            continue
        title = hits[0]["title"] if hits else "—"
        print(f"  {imdb:<12} {len(hits):<5} {title}")
        time.sleep(0.3)
    print()
    return 0


def cmd_fetch(key: str, imdb: str, lang: str, limit: int) -> int:
    hits = search(key, imdb, lang, limit)
    if not hits:
        print(f"\n  Няма SDH субтитри за {imdb} на '{lang}'.")
        print("  Пробвай друго заглавие — SDH има предимно за големи филми на английски.\n")
        return 1

    OUT.mkdir(exist_ok=True)
    print(f"\n  {hits[0]['title']} — {len(hits)} SDH кандидата\n")

    results = []
    for i, h in enumerate(hits, 1):
        name = f"{imdb}_{i}_{h['file_id']}.srt"
        print(f"  [{i}] {h['release'][:50]}  ({h['downloads']} сваляния)")
        try:
            path = download(key, h["file_id"], OUT / name)
        except SystemExit as e:
            print(f"      пропуснат: {e}")
            continue
        st = coverage_of(path)
        if not st:
            print("      не се декодира")
            continue
        results.append((st.get("coverage", 0), name, st))
        print(f"      coverage {st['coverage']:.0%}  ·  {st['distinct_speakers']} имена"
              f"  ·  {st['sound_cues']} звука  ·  {st['runtime_min']} мин")
        time.sleep(0.5)

    if not results:
        return 1

    results.sort(reverse=True)
    best = results[0]
    print(f"\n  Най-добър: subs/{best[1]}  (coverage {best[0]:.0%})")
    print(f"  Виж го с:  python -m tools.check subs/{best[1]}\n")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="SDH субтитри от OpenSubtitles")
    ap.add_argument("imdb", nargs="+", help="IMDB id, напр. tt0133093")
    ap.add_argument("--lang", default="en")
    ap.add_argument("--limit", type=int, default=3)
    ap.add_argument("--scan", action="store_true",
                    help="само провери кои имат SDH, без сваляне")
    args = ap.parse_args()

    key = api_key()
    if args.scan:
        return cmd_scan(key, args.imdb, args.lang)
    rc = 0
    for imdb in args.imdb:
        rc |= cmd_fetch(key, imdb, args.lang, args.limit)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
