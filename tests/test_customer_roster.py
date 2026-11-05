"""The roster of valid customer ids must say so when it is empty.

`validate_customer_middleware` rejects an unknown customer_id only when it
has a roster to compare against. `data/customers.json` is generated, not
committed, so an image built from a clean checkout has none -- and the
loader used to swallow that and return an empty set, which turns the
check off without a word. Failing closed would 400 every request on such
an image, so the loader instead says loudly that validation is off, and
/health reports the roster size so a deploy check can see it.
"""

import json

from src.customer_roster import load_roster, roster_status


def test_a_roster_file_yields_its_customer_ids(tmp_path):
    path = tmp_path / "customers.json"
    path.write_text(json.dumps([{"customer_id": "CUST-0000"}, {"customer_id": "CUST-0001"}]))

    assert load_roster(path) == {"CUST-0000", "CUST-0001"}


def test_a_missing_roster_is_reported_not_silently_empty(tmp_path, capsys):
    path = tmp_path / "customers.json"

    roster = load_roster(path)

    assert roster == set()
    err = capsys.readouterr().err
    assert str(path) in err
    assert "customer_id validation is OFF" in err


def test_a_corrupt_roster_is_reported_with_its_cause(tmp_path, capsys):
    path = tmp_path / "customers.json"
    path.write_text("{not json")

    assert load_roster(path) == set()
    assert "JSONDecodeError" in capsys.readouterr().err


def test_an_empty_roster_reports_degraded_and_a_full_one_ok():
    assert roster_status(set()) == "degraded"
    assert roster_status({"CUST-0000"}) == "ok"


def test_an_empty_roster_file_is_reported_not_silently_empty(tmp_path, capsys):
    # `[]` parses fine, so nothing raises -- and an empty roster switches the
    # unknown-customer check off exactly as a missing file does.
    path = tmp_path / "customers.json"
    path.write_text("[]")

    assert load_roster(path) == set()
    assert "customer_id validation is OFF" in capsys.readouterr().err
