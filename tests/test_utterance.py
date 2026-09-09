"""Сливането на реплики в изказвания."""
from pathlib import Path

from tiflo import srt, utterance

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


def build(name: str):
    return utterance.build(
        srt.parse((FIXTURES / name).read_text(encoding="utf-8-sig"))
    )


SPLIT = """1
00:00:01,000 --> 00:00:03,000
MARTA: I know, but I felt

2
00:00:03,200 --> 00:00:05,000
like taking your shift.
"""

TWO_SPEAKERS = """1
00:00:01,000 --> 00:00:03,000
MARTA: Yeah.
DANIEL: Is everything in place?
"""

LONG_PAUSE = """1
00:00:01,000 --> 00:00:03,000
MARTA: First thing.

2
00:00:20,000 --> 00:00:22,000
MARTA: Much later.
"""


def test_split_sentence_becomes_one_utterance():
    utts = utterance.build(srt.parse(SPLIT))
    assert len(utts) == 1
    assert utts[0].parts == 2
    assert utts[0].text == "I know, but I felt like taking your shift."
    assert utts[0].start == 1.0 and utts[0].end == 5.0


def test_different_speakers_never_merge():
    utts = utterance.build(srt.parse(TWO_SPEAKERS))
    assert len(utts) == 2
    assert [u.speaker for u in utts] == ["MARTA", "DANIEL"]


def test_long_pause_prevents_merge():
    utts = utterance.build(srt.parse(LONG_PAUSE))
    assert len(utts) == 2
    assert all(u.parts == 1 for u in utts)


def test_explicit_name_beats_inferred_when_merging():
    """Слятото изказване не бива да се води 'пренесено', ако едната
    част е носила явно име — иначе губим котва за диаризацията."""
    utts = utterance.build(srt.parse(SPLIT))
    assert utts[0].inferred is False


def test_sounds_are_separate_utterances():
    utts = build("brackets_and_sounds.srt")
    sounds = [u for u in utts if u.kind == "sound"]
    assert sounds
    assert all(u.speaker is None for u in sounds)
    assert "ENGINE RUMBLING" in [u.text for u in sounds]


def test_utterances_stay_in_order():
    for name in ("plain_colon.srt", "brackets_and_sounds.srt", "dashes_multi.srt"):
        starts = [u.start for u in build(name)]
        assert starts == sorted(starts)


def test_every_utterance_has_a_usable_slot():
    for name in ("plain_colon.srt", "brackets_and_sounds.srt"):
        for u in build(name):
            assert u.slot >= u.duration > 0


def test_no_text_is_lost():
    """Сливането не бива да яде реплики."""
    cues = srt.parse((FIXTURES / "plain_colon.srt").read_text(encoding="utf-8-sig"))
    words_in = sum(len(l.text.split()) for c in cues for l in c.lines)
    words_out = sum(
        len(u.text.split()) for u in utterance.build(cues) if u.kind == "speech"
    )
    assert words_in == words_out
