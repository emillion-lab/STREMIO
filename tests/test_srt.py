"""
Регресионни тестове на SRT/SDH парсера.

Фикстурите във fixtures/ са измислени — не са реални субтитри от филм.
Целта им е да покрият форматите, не съдържанието.
"""
from pathlib import Path

import pytest

from tiflo import srt

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


def load(name: str):
    if name == "messy":
        return srt.parse(MESSY)
    return srt.parse((FIXTURES / name).read_text(encoding="utf-8-sig"))


# BOM, CRLF, HTML/ASS тагове, липсващ индекс, обърнат таймкод.
# Строи се тук, а не като файл — git нормализира точно тези байтове.
MESSY = (
    "\ufeff"
    "1\r\n00:00:01,000 --> 00:00:03,000\r\n"
    "<i>MARTA:</i> With tags and CRLF.\r\n\r\n"
    "\r\n00:00:04,000 --> 00:00:06,000\r\n"
    "Missing index above this one.\r\n\r\n"
    "3\r\n00:00:08,000 --> 00:00:07,000\r\n"
    "Broken timing, must be skipped.\r\n\r\n"
    "4\r\n00:00:09,000 --> 00:00:11,500\r\n"
    "{\\an8}DANIEL: With an ASS override tag.\r\n"
)

ALL_FIXTURES = [
    "plain_colon.srt", "brackets_and_sounds.srt",
    "dashes_multi.srt", "no_labels.srt", "messy",
]


# --- основен формат ИМЕ: -------------------------------------------------

def test_plain_colon_finds_all_speakers():
    cues = load("plain_colon.srt")
    assert len(cues) == 5
    assert srt.stats(cues)["distinct_speakers"] == 2
    assert cues[0].lines[0].speaker == "MARTA"
    assert cues[0].lines[0].text == "You said you would call."


def test_unlabelled_continuation_carries_speaker():
    cues = load("plain_colon.srt")
    line = cues[1].lines[0]
    assert line.speaker == "MARTA"
    assert line.inferred is True


def test_carried_speaker_is_not_an_anchor():
    """Пренесеното име не бива да се брои за котва при диаризацията."""
    cues = load("plain_colon.srt")
    assert (4.8, 6.2) not in srt.anchors(cues)["MARTA"]


# --- скоби и звуци -------------------------------------------------------

def test_bracket_label_is_a_speaker():
    cues = load("brackets_and_sounds.srt")
    assert cues[1].lines[0].speaker == "MARTA"
    assert cues[1].lines[0].text == "Turn the car around."


def test_sound_effect_is_not_mistaken_for_a_speaker():
    cues = load("brackets_and_sounds.srt")
    cue = next(c for c in cues if "Get out." in c.text)
    assert "DOOR SLAMS" in cue.sounds
    assert "DOOR SLAMS" not in srt.anchors(cues)
    assert cue.kind == "mixed"


def test_sound_only_cue_has_no_dialogue():
    cues = load("brackets_and_sounds.srt")
    assert cues[0].kind == "sound"
    assert cues[0].sounds == ["ENGINE RUMBLING"]
    assert cues[0].lines == []


@pytest.mark.parametrize("name", ["MAN", "WOMAN"])
def test_generic_labels_are_flagged_not_anchored(name):
    cues = load("brackets_and_sounds.srt")
    line = next(l for c in cues for l in c.lines if l.speaker == name)
    assert line.generic is True
    assert name not in srt.anchors(cues)


# --- тирета и няколко говорителя в една реплика --------------------------

def test_dash_separated_speakers():
    cues = load("dashes_multi.srt")
    assert cues[0].is_multi_speaker
    assert cues[0].speakers == ["MARTA", "DANIEL"]
    assert cues[0].lines[0].text == "Everything is a choice."


def test_dashes_without_names_stay_unlabelled():
    """Тирето е смяна на говорител — там не се пренася предишното име."""
    cues = load("dashes_multi.srt")
    assert all(l.speaker is None for l in cues[1].lines)


def test_two_speakers_on_separate_lines():
    cues = load("dashes_multi.srt")
    assert cues[2].speakers == ["DANIEL", "MARTA"]


# --- мръсен вход ---------------------------------------------------------

def test_bom_crlf_and_html_tags():
    cues = load("messy")
    assert cues[0].lines[0].speaker == "MARTA"
    assert "<i>" not in cues[0].text


def test_missing_index_gets_one():
    cues = load("messy")
    assert all(isinstance(c.idx, int) for c in cues)


def test_reversed_timing_is_dropped():
    cues = load("messy")
    assert all(c.end > c.start for c in cues)
    assert not any("Broken timing" in c.text for c in cues)


def test_ass_override_tag_stripped():
    cues = load("messy")
    assert cues[-1].lines[0].speaker == "DANIEL"
    assert "{" not in cues[-1].text


# --- отрицателен случай --------------------------------------------------

def test_plain_subtitles_report_zero_coverage():
    """Ако това падне, значи бъркаме обикновени субтитри за SDH."""
    st = srt.stats(load("no_labels.srt"))
    assert st["coverage"] == 0.0
    assert st["distinct_speakers"] == 0


# --- инварианти ----------------------------------------------------------

@pytest.mark.parametrize("name", ALL_FIXTURES)
def test_invariants_hold_for_every_fixture(name):
    cues = load(name)
    assert cues, f"{name} се парсна на нула реплики"
    for c in cues:
        assert c.end > c.start
        assert c.duration > 0
        assert c.lines or c.sounds
        assert not any(l.text.strip() == "" for l in c.lines)
    starts = [c.start for c in cues]
    assert starts == sorted(starts), "репликите не са хронологични"


def test_empty_and_garbage_input_do_not_crash():
    assert srt.parse("") == []
    assert srt.parse("не е субтитър\n\nнито това") == []
