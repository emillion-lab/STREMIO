"""
Тестове за двете поправки, дошли от истински файл:
кредити на риппера и прекалено тесен прозорец за пренасяне на име.
"""
from tiflo import srt

CREDITS = """1
00:00:01,000 --> 00:00:03,000
Improved & Synced by SomeUploader

2
00:00:05,000 --> 00:00:07,000
Subtitles by www.example.com

3
00:00:09,000 --> 00:00:11,000
MARTA: This is a real line.
"""

GAP = """1
00:00:10,000 --> 00:00:12,000
LIEUTENANT: I sent two units.

2
00:00:15,000 --> 00:00:17,000
They are bringing her down now.

3
00:00:30,000 --> 00:00:32,000
This is after a long pause.
"""


def test_ripper_credits_are_dropped():
    cues = srt.parse(CREDITS)
    assert len(cues) == 1
    assert cues[0].lines[0].speaker == "MARTA"


def test_credits_do_not_become_sounds():
    """Кредитът не бива да се спасява като звуково описание."""
    assert all(not c.sounds for c in srt.parse(CREDITS))


def test_name_carries_across_a_short_gap():
    cues = srt.parse(GAP)
    line = cues[1].lines[0]
    assert line.speaker == "LIEUTENANT"
    assert line.inferred is True


def test_name_does_not_carry_across_a_long_gap():
    cues = srt.parse(GAP)
    assert cues[2].lines[0].speaker is None
