from app.case_seed import load_cases
from app.cli import DEFAULT_CASES_CSV
from app.models import Case

HEADER = "case,type,low,high,second_low,second_high\n"


def _case(number):
    return Case.query.filter_by(case_number=number).one()


def test_adds_cases_with_one_or_two_ranges(db, instrument_type):
    result = load_cases(HEADER + "K1,Chimes,C4,D4,,\nK2,chimes,C4,D4,A5,C6\n")

    assert result.errors == []
    assert result.added == ["K1", "K2"]
    assert _case("K1").ranges() == [("C4", "D4")]
    assert _case("K2").ranges() == [("C4", "D4"), ("A5", "C6")]


def test_blank_high_note_is_a_single_bell(db, instrument_type):
    load_cases(HEADER + "K1,Chimes,G4,,,\n")

    assert _case("K1").ranges() == [("G4", "G4")]


def test_overwrites_existing_case_and_leaves_others_alone(db, instrument_type):
    db.session.add_all(
        [
            Case(
                instrument_type=instrument_type,
                case_number="K1",
                note_range_low="C4",
                note_range_high="C5",
                second_range_low="A5",
                second_range_high="C6",
            ),
            Case(
                instrument_type=instrument_type,
                case_number="KEEP",
                note_range_low="C4",
                note_range_high="C5",
            ),
        ]
    )
    db.session.commit()

    result = load_cases(HEADER + "K1,Chimes,E4,F4,,\n")

    assert result.updated == ["K1"]
    assert _case("K1").ranges() == [("E4", "F4")]
    assert _case("KEEP").ranges() == [("C4", "C5")]


def test_any_bad_row_loads_nothing(db, instrument_type):
    result = load_cases(
        HEADER
        + "K1,Chimes,C4,D4,,\n"
        + "K2,Gongs,C4,D4,,\n"
        + "K3,Chimes,C3,D4,,\n"
        + "K4,Chimes,H4,,,\n"
        + "K5,Chimes,C4,D4,A5,\n"
        + "K1,Chimes,C4,D4,,\n"
    )

    assert len(result.errors) == 5
    assert "no instrument type named 'Gongs'" in result.errors[0]
    assert "Chimes's range" in result.errors[1]
    assert "unknown pitch H4" in result.errors[2]
    assert "second range needs both" in result.errors[3]
    assert "more than once" in result.errors[4]
    assert Case.query.count() == 0


def test_dry_run_saves_nothing(db, instrument_type):
    result = load_cases(HEADER + "K1,Chimes,C4,D4,,\n", dry_run=True)

    assert result.added == ["K1"]
    assert Case.query.count() == 0


def test_missing_column_is_reported(db, instrument_type):
    result = load_cases("case,type,low\nK1,Chimes,C4\n")

    assert result.errors == ["Missing column(s): high, second_low, second_high."]


def test_cli_loads_a_given_file(app, instrument_type, tmp_path):
    csv_path = tmp_path / "cases.csv"
    csv_path.write_text(HEADER + "K1,Chimes,C4,D4,,\n")

    result = app.test_cli_runner().invoke(args=["load-cases", str(csv_path)])

    assert result.exit_code == 0, result.output
    assert "Added 1: K1" in result.output
    assert Case.query.count() == 1


def test_cli_fails_and_reports_errors(app, instrument_type, tmp_path):
    csv_path = tmp_path / "cases.csv"
    csv_path.write_text(HEADER + "K1,Gongs,C4,D4,,\n")

    result = app.test_cli_runner().invoke(args=["load-cases", str(csv_path)])

    assert result.exit_code != 0
    assert "Nothing was loaded" in result.output
    assert Case.query.count() == 0


def test_default_csv_ships_with_the_repo():
    assert DEFAULT_CASES_CSV.is_file()
