import json
from datetime import date
from pathlib import Path

import pytest

from frontdesk.intake import (
    Business,
    Lead,
    Service,
    extract_fields,
    extract_name,
    match_service,
    normalize_phone,
    parse_date,
    parse_time,
)

TODAY = date(2026, 9, 24)  # a Thursday

SERVICES = (
    Service("Full Interior Detail", 120, 120, ("interior", "inside")),
    Service("Exterior Wash & Wax", 80, 90, ("exterior", "wash", "wax")),
    Service("Full Detail Package", 180, 180, ("full detail", "the works")),
)


class TestPhone:
    def test_digit_string_with_punctuation(self):
        assert normalize_phone("call me at 555-214-8690") == "(555) 214-8690"

    def test_spoken_digits(self):
        assert normalize_phone(
            "it's five five five, two one four, eight six nine oh"
        ) == "(555) 214-8690"

    def test_country_code_stripped(self):
        assert normalize_phone("1 555 214 8690") == "(555) 214-8690"

    def test_too_short_returns_none(self):
        assert normalize_phone("my number is 555 1234") is None

    def test_no_digits(self):
        assert normalize_phone("no number here") is None


class TestDate:
    def test_tomorrow(self):
        assert parse_date("does tomorrow work?", TODAY) == "2026-09-25"

    def test_day_after_tomorrow(self):
        assert parse_date("the day after tomorrow", TODAY) == "2026-09-26"

    def test_today(self):
        assert parse_date("today if possible", TODAY) == "2026-09-24"

    def test_bare_weekday_this_week(self):
        assert parse_date("how about Friday?", TODAY) == "2026-09-25"

    def test_bare_weekday_next_week(self):
        assert parse_date("maybe Monday", TODAY) == "2026-09-28"

    def test_weekday_same_day_rolls_forward(self):
        assert parse_date("Thursday", TODAY) == "2026-10-01"

    def test_this_weekday_same_day_is_today(self):
        assert parse_date("this Thursday", TODAY) == "2026-09-24"

    def test_next_weekday(self):
        assert parse_date("next Friday", TODAY) == "2026-10-02"

    def test_month_day(self):
        assert parse_date("September 26th", TODAY) == "2026-09-26"

    def test_month_day_past_rolls_to_next_year(self):
        assert parse_date("march 3", TODAY) == "2027-03-03"

    def test_slash_date(self):
        assert parse_date("9/26", TODAY) == "2026-09-26"

    def test_invalid_date(self):
        assert parse_date("february 30", TODAY) is None

    def test_no_date(self):
        assert parse_date("whenever you're free", TODAY) is None


class TestTime:
    def test_pm(self):
        assert parse_time("around 2 pm") == "14:00"

    def test_am(self):
        assert parse_time("9:00 am") == "09:00"

    def test_24h(self):
        assert parse_time("14:30 works") == "14:30"

    def test_spoken_minutes(self):
        assert parse_time("two thirty pm") == "14:30"

    def test_noon(self):
        assert parse_time("at noon") == "12:00"

    def test_midnight(self):
        assert parse_time("midnight") == "00:00"

    def test_daypart(self):
        assert parse_time("2 in the afternoon") == "14:00"

    def test_oclock(self):
        assert parse_time("3 o'clock") == "03:00"

    def test_bare_hour_ambiguous(self):
        assert parse_time("let's do 5") is None

    def test_no_time(self):
        assert parse_time("sometime next week") is None


class TestServiceMatch:
    def test_exact_name(self):
        svc = match_service("I want the Full Interior Detail", SERVICES)
        assert svc and svc.name == "Full Interior Detail"

    def test_alias(self):
        svc = match_service("just a wash please", SERVICES)
        assert svc and svc.name == "Exterior Wash & Wax"

    def test_longest_alias_wins(self):
        svc = match_service("give me the full detail", SERVICES)
        assert svc and svc.name == "Full Detail Package"

    def test_no_match(self):
        assert match_service("do you do haircuts?", SERVICES) is None


class TestName:
    def test_my_name_is(self):
        assert extract_name("hi, my name is dana whitfield") == "Dana Whitfield"

    def test_this_is(self):
        assert extract_name("this is marcus") == "Marcus"

    def test_stopword_filtered(self):
        assert extract_name("i'm calling about a quote") is None

    def test_no_name(self):
        assert extract_name("what are your prices") is None


class TestExtractFields:
    def test_multi_field_utterance(self):
        found = extract_fields(
            "I'm Dana, book the interior detail tomorrow at 2 pm, "
            "my number is 555 214 8690",
            SERVICES,
            TODAY,
        )
        assert found["name"] == "Dana"
        assert found["phone"] == "(555) 214-8690"
        assert found["service"] == "Full Interior Detail"
        assert found["date"] == "2026-09-25"
        assert found["time"] == "14:00"


class TestLead:
    def test_missing_fields(self):
        lead = Lead(business="B", name="Dana")
        assert lead.missing_fields() == ["phone", "service", "date", "time"]
        assert not lead.is_complete()

    def test_complete(self):
        lead = Lead(
            business="B", name="D", phone="(555) 214-8690",
            service="Wash", date="2026-09-25", time="14:00",
        )
        assert lead.is_complete()
        row = lead.to_row("2026-09-24T00:00:00+00:00")
        assert row[0] == "2026-09-24T00:00:00+00:00"
        assert row[2] == "D"


class TestBusinessConfig:
    def test_load_repo_config(self):
        path = Path(__file__).parent.parent / "business.json"
        business = Business.from_json(path)
        assert business.services
        assert "from $" in business.service_menu()

    def test_empty_services_rejected(self, tmp_path):
        cfg = tmp_path / "bad.json"
        cfg.write_text(json.dumps({"name": "X", "services": []}))
        with pytest.raises(ValueError):
            Business.from_json(cfg)
