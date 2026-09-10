"""Отмествания по височина и темпо — различимост преди вярност."""
import pytest

from tiflo.prosody import (
    MAX_SEMITONES, MIN_SEPARATION, Profile, build, distinguishable, semitones,
)


def test_octave_is_twelve_semitones():
    assert semitones(230, 115) == pytest.approx(12.0)
    assert semitones(115, 230) == pytest.approx(-12.0)


def test_same_pitch_is_zero():
    assert semitones(120, 120) == pytest.approx(0.0)


def test_zero_or_negative_frequency_is_rejected():
    with pytest.raises(ValueError):
        semitones(0, 115)


GENDER = {"A": "male", "B": "male", "C": "male", "F": "female"}


def test_measured_pitch_drives_the_offset():
    """По-нисък глас от базовия дава отрицателно отместване."""
    p = build([Profile("A", f0_hz=95)], {"A": "male"})["A"]
    assert p.pitch_st < 0
    assert p.measured is True


def test_offset_never_exceeds_the_limit():
    """Дори при екстремен вход гласът остава разбираем."""
    for hz in (40, 400):
        p = build([Profile("A", f0_hz=hz)], {"A": "male"})["A"]
        assert abs(p.pitch_st) <= MAX_SEMITONES


def test_close_voices_get_pushed_apart():
    profs = [Profile("A", f0_hz=110), Profile("B", f0_hz=111)]
    got = build(profs, {"A": "male", "B": "male"})
    assert abs(got["A"].pitch_st - got["B"].pitch_st) >= MIN_SEPARATION - 0.01


def test_pitch_order_is_preserved():
    """По-високият глас си остава по-висок след разбутването."""
    profs = [Profile("A", f0_hz=100), Profile("B", f0_hz=101), Profile("C", f0_hz=150)]
    got = build(profs, GENDER)
    assert got["A"].pitch_st < got["B"].pitch_st < got["C"].pitch_st


def test_unmeasured_speakers_are_still_distinguishable():
    got = build([Profile(n) for n in ("A", "B", "C")], GENDER)
    assert distinguishable(got, GENDER)
    assert all(p.measured is False for p in got.values())


def test_many_speakers_stay_within_limits_and_distinct():
    gender = {f"M{i}": "male" for i in range(7)}
    got = build([Profile(f"M{i}") for i in range(7)], gender)
    assert distinguishable(got, gender)
    assert all(abs(p.pitch_st) <= MAX_SEMITONES for p in got.values())


def test_genders_are_spread_independently():
    """Мъжки и женски глас не се разбутват един спрямо друг."""
    gender = {"A": "male", "F": "female"}
    got = build([Profile("A", f0_hz=115), Profile("F", f0_hz=195)], gender)
    assert got["A"].pitch_st == pytest.approx(0.0, abs=0.05)
    assert got["F"].pitch_st == pytest.approx(0.0, abs=0.05)


def test_speaking_rate_is_capped():
    p = build([Profile("A", f0_hz=115, syllables_per_s=20)], {"A": "male"})["A"]
    assert p.rate_pct <= 12.0


def test_ssml_is_well_formed():
    p = build([Profile("A", f0_hz=100)], {"A": "male"})["A"]
    assert 'pitch="' in p.ssml and "st" in p.ssml
    assert 'rate="' in p.ssml and "%" in p.ssml


def test_speaker_without_gender_is_skipped():
    assert build([Profile("A", f0_hz=100)], {}) == {}
