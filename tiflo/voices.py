"""
От име на говорител към глас.

SDH етикетът дава име ("MORPHEUS"), но не и пол. TMDb дава актьорския
състав с поле за пол на актьора. Слепването на двете покрива повечето
герои, без да се пипа звукът на филма.

Мрежовата част е само в fetch_cast(). Останалото са чисти функции —
затова се тества без ключ и без интернет.
"""

from __future__ import annotations

import difflib
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Literal

TMDB = "https://api.themoviedb.org/3"

Gender = Literal["male", "female", "unknown"]

# TMDb кодира пола на АКТЬОРА: 0 неизвестен, 1 жена, 2 мъж, 3 небинарен.
_TMDB_GENDER: dict[int, Gender] = {1: "female", 2: "male"}

# Етикети, които сами си казват пола.
_BY_LABEL: dict[str, Gender] = {
    "MAN": "male", "BOY": "male", "FATHER": "male", "МЪЖ": "male",
    "WOMAN": "female", "GIRL": "female", "MOTHER": "female", "ЖЕНА": "female",
}

# Титли и наставки, които пречат на съвпадението.
_NOISE = re.compile(
    r"^(agent|officer|detective|dr|doctor|mr|mrs|ms|captain|sergeant|"
    r"lieutenant|colonel|general|young|old)\b[.\s]*", re.I
)
_TRAILING_NUM = re.compile(r"\s*#?\d+$")


@dataclass
class Voice:
    id: str
    gender: Gender


@dataclass
class Match:
    speaker: str
    gender: Gender
    character: str | None = None   # как се води в TMDb
    actor: str | None = None
    confidence: float = 0.0
    source: str = "none"           # tmdb | label | none


def _norm(name: str) -> str:
    name = _TRAILING_NUM.sub("", name.strip())
    name = _NOISE.sub("", name)
    return name.strip(" .'-").casefold()


def fetch_cast(imdb_id: str, api_key: str) -> list[dict]:
    """Актьорският състав по IMDB id. Две заявки: find -> credits."""
    def get(path: str, **params) -> dict:
        params["api_key"] = api_key
        url = f"{TMDB}{path}?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            raise SystemExit(f"TMDb HTTP {e.code} на {path}\n"
                             f"{e.read().decode(errors='replace')[:300]}")
        except urllib.error.URLError as e:
            raise SystemExit(f"няма връзка с TMDb: {e.reason}")

    found = get(f"/find/{imdb_id}", external_source="imdb_id")
    movies = found.get("movie_results") or []
    if not movies:
        raise SystemExit(f"TMDb не намира {imdb_id}")
    return get(f"/movie/{movies[0]['id']}/credits").get("cast", [])


def match_speakers(speakers: list[str], cast: list[dict]) -> dict[str, Match]:
    """
    Слепва SDH имената с TMDb героите.

    Три опита по ред на сигурност: точно съвпадение, съвпадение по дума
    (SMITH в "Agent Smith"), после размито. Каквото не се хване, пада
    на етикета (MAN/WOMAN) или остава неизвестно — за диаризацията.
    """
    by_exact: dict[str, dict] = {}
    by_token: dict[str, dict] = {}
    for entry in cast:
        char = (entry.get("character") or "").strip()
        if not char:
            continue
        by_exact.setdefault(_norm(char), entry)
        for token in re.split(r"[\s/,]+", char):
            token = _norm(token)
            if len(token) > 2:
                by_token.setdefault(token, entry)

    out: dict[str, Match] = {}
    for speaker in speakers:
        key = _norm(speaker)
        entry, conf, how = None, 0.0, "none"

        if key in by_exact:
            entry, conf, how = by_exact[key], 1.0, "tmdb"
        elif key in by_token:
            entry, conf, how = by_token[key], 0.9, "tmdb"
        else:
            near = difflib.get_close_matches(key, by_exact, n=1, cutoff=0.85)
            if near:
                entry = by_exact[near[0]]
                conf = difflib.SequenceMatcher(None, key, near[0]).ratio()
                how = "tmdb"

        if entry is not None:
            gender = _TMDB_GENDER.get(entry.get("gender", 0), "unknown")
            if gender != "unknown":
                out[speaker] = Match(
                    speaker=speaker, gender=gender,
                    character=entry.get("character"), actor=entry.get("name"),
                    confidence=round(conf, 2), source=how,
                )
                continue

        parts = _TRAILING_NUM.sub("", speaker.strip()).upper().split()
        head = parts[0] if parts else ""
        if head in _BY_LABEL:
            out[speaker] = Match(speaker=speaker, gender=_BY_LABEL[head],
                                 confidence=0.7, source="label")
        else:
            out[speaker] = Match(speaker=speaker, gender="unknown")

    return out


def assign_voices(matches: dict[str, Match], pool: list[Voice],
                  weights: dict[str, int] | None = None) -> dict[str, Voice]:
    """
    Раздава гласове. Героите с най-много реплики получават първи избор,
    за да не се повтарят гласовете при главните роли.
    """
    males = [v for v in pool if v.gender == "male"]
    females = [v for v in pool if v.gender == "female"]
    if not males or not females:
        raise ValueError("нужен е поне един мъжки и един женски глас")

    order = sorted(matches, key=lambda s: -(weights or {}).get(s, 0))
    used = {"male": 0, "female": 0}
    out: dict[str, Voice] = {}

    for speaker in order:
        gender = matches[speaker].gender
        if gender == "unknown":
            continue                       # чака диаризацията
        bank = males if gender == "male" else females
        out[speaker] = bank[used[gender] % len(bank)]
        used[gender] += 1
    return out


def stats(matches: dict[str, Match]) -> dict:
    vals = list(matches.values())
    return {
        "speakers": len(vals),
        "male": sum(1 for m in vals if m.gender == "male"),
        "female": sum(1 for m in vals if m.gender == "female"),
        "unknown": sum(1 for m in vals if m.gender == "unknown"),
        "from_tmdb": sum(1 for m in vals if m.source == "tmdb"),
        "from_label": sum(1 for m in vals if m.source == "label"),
    }
