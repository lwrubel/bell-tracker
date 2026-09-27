from app import pitch


def test_pitch_index_orders_by_octave_then_note():
    assert pitch.pitch_index("C1") < pitch.pitch_index("C2")
    assert pitch.pitch_index("C4") < pitch.pitch_index("C#4") < pitch.pitch_index("D4")


def test_all_pitches_default_range_spans_lowest_to_highest():
    pitches = pitch.all_pitches()
    assert pitches[0] == pitch.LOWEST_PITCH
    assert pitches[-1] == pitch.HIGHEST_PITCH
    assert len(pitches) == pitch.pitch_index(pitch.HIGHEST_PITCH) - pitch.pitch_index(
        pitch.LOWEST_PITCH
    ) + 1


def test_pitches_in_range_is_inclusive_and_chromatic():
    assert pitch.pitches_in_range("C4", "E4") == ["C4", "C#4", "D4", "D#4", "E4"]


def test_pitches_in_range_single_note():
    assert pitch.pitches_in_range("C4", "C4") == ["C4"]


def test_in_range():
    assert pitch.in_range("D4", "C4", "E4") is True
    assert pitch.in_range("C4", "C4", "E4") is True
    assert pitch.in_range("E4", "C4", "E4") is True
    assert pitch.in_range("F4", "C4", "E4") is False
    assert pitch.in_range("B3", "C4", "E4") is False


def test_flat_name_converts_sharps():
    assert pitch.flat_name("C#4") == "Db4"
    assert pitch.flat_name("D#4") == "Eb4"
    assert pitch.flat_name("A#3") == "Bb3"


def test_flat_name_leaves_naturals_unchanged():
    for natural in ["C4", "D4", "E4", "F4", "G4", "A4", "B4"]:
        assert pitch.flat_name(natural) == natural


def test_lowest_selectable_pitch_is_c2():
    # Bass bells go down to C2, so the admin note-range dropdowns must too.
    assert pitch.all_pitches()[0] == "C2"
