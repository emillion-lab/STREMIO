"""Слепване на SDH имена с TMDb състав. Без мрежа — чисти функции."""
import pytest

from tiflo.voices import Voice, assign_voices, match_speakers, stats

CAST = [
    {"character": "Neo", "name": "Actor A", "gender": 2},
    {"character": "Trinity", "name": "Actor B", "gender": 1},
    {"character": "Agent Smith", "name": "Actor C", "gender": 2},
    {"character": "Morpheus", "name": "Actor D", "gender": 2},
    {"character": "Oracle", "name": "Actor E", "gender": 1},
    {"character": "Unnamed Extra", "name": "Actor F", "gender": 0},
]

POOL = [Voice("m1", "male"), Voice("m2", "male"),
        Voice("f1", "female"), Voice("f2", "female")]


def test_exact_name_matches():
    m = match_speakers(["NEO"], CAST)["NEO"]
    assert m.gender == "male"
    assert m.source == "tmdb"
    assert m.confidence == 1.0


def test_title_prefix_is_ignored():
    """SMITH трябва да намери 'Agent Smith'."""
    m = match_speakers(["SMITH"], CAST)["SMITH"]
    assert m.gender == "male"
    assert m.character == "Agent Smith"


def test_trailing_number_is_ignored_for_real_names():
    assert match_speakers(["NEO 2"], CAST)["NEO 2"].gender == "male"


def test_generic_label_falls_back_to_itself():
    m = match_speakers(["WOMAN", "MAN"], CAST)
    assert m["WOMAN"].gender == "female"
    assert m["MAN"].gender == "male"
    assert m["WOMAN"].source == "label"


def test_unknown_speaker_stays_unknown():
    """Каквото не се хване, се оставя на диаризацията — не се гадае."""
    m = match_speakers(["SOMEBODYELSE"], CAST)["SOMEBODYELSE"]
    assert m.gender == "unknown"
    assert m.source == "none"


def test_cast_entry_without_gender_is_not_trusted():
    assert match_speakers(["UNNAMED EXTRA"], CAST)["UNNAMED EXTRA"].gender == "unknown"


def test_stats_add_up():
    st = stats(match_speakers(["NEO", "TRINITY", "WOMAN", "NOBODY"], CAST))
    assert st["speakers"] == 4
    assert st["male"] + st["female"] + st["unknown"] == 4
    assert st["from_tmdb"] == 2


# --- родови роли: TMDb ги слива, а зад тях стоят различни хора -----------

CROWD = [
    {"character": "Cop", "name": "Actor G", "gender": 1},
    {"character": "Neo", "name": "Actor A", "gender": 2},
]


def test_numbered_role_is_not_trusted():
    """COP 1 и COP 2 са двама души зад един запис в TMDb."""
    m = match_speakers(["COP 1", "COP 2"], CROWD)
    assert all(v.gender == "unknown" for v in m.values())


def test_bare_role_distrusted_when_numbered_siblings_exist():
    assert match_speakers(["COP", "COP 1", "COP 2"], CROWD)["COP"].gender == "unknown"


def test_bare_role_alone_is_still_used():
    assert match_speakers(["COP"], CROWD)["COP"].gender == "female"


def test_real_names_are_unaffected_by_the_role_rule():
    assert match_speakers(["NEO", "COP 1"], CROWD)["NEO"].gender == "male"


def test_conflicting_genders_for_one_character_give_unknown():
    cast = [
        {"character": "Twin", "name": "X", "gender": 1},
        {"character": "Twin", "name": "Y", "gender": 2},
    ]
    assert match_speakers(["TWIN"], cast)["TWIN"].gender == "unknown"


def test_numbered_generic_label_uses_the_label():
    assert match_speakers(["MAN 2"], CAST)["MAN 2"].gender == "male"


# --- раздаване на гласове ------------------------------------------------

def test_main_characters_get_distinct_voices():
    m = match_speakers(["NEO", "MORPHEUS", "TRINITY", "ORACLE"], CAST)
    weights = {"NEO": 500, "MORPHEUS": 400, "TRINITY": 300, "ORACLE": 20}
    got = assign_voices(m, POOL, weights)
    assert got["NEO"].id != got["MORPHEUS"].id
    assert got["TRINITY"].id != got["ORACLE"].id


def test_voice_gender_matches_speaker_gender():
    got = assign_voices(match_speakers(["NEO", "TRINITY"], CAST), POOL)
    assert got["NEO"].gender == "male"
    assert got["TRINITY"].gender == "female"


def test_unknown_speakers_get_no_voice_yet():
    got = assign_voices(match_speakers(["NEO", "NOBODY"], CAST), POOL)
    assert "NOBODY" not in got


def test_pool_needs_both_genders():
    with pytest.raises(ValueError):
        assign_voices(match_speakers(["NEO"], CAST), [Voice("m1", "male")])
