import csv
import io
import json

import pytest

from frontdesk.intake import CSV_HEADER, Lead
from frontdesk.sink import CsvSink, MultiSink, WebhookSink


def complete_lead() -> Lead:
    return Lead(
        business="Test Detailing",
        name="Dana Whitfield",
        phone="(555) 214-8690",
        service="Full Interior Detail",
        date="2026-09-25",
        time="14:00",
        notes="SUV with two car seats",
    )


class TestCsvSink:
    def test_writes_header_and_row(self, tmp_path):
        path = tmp_path / "out" / "leads.csv"
        CsvSink(path).save(complete_lead())
        with path.open() as fh:
            rows = list(csv.reader(fh))
        assert rows[0] == list(CSV_HEADER)
        assert len(rows) == 2
        assert rows[1][2] == "Dana Whitfield"
        assert rows[1][8] == "SUV with two car seats"

    def test_appends_without_duplicate_header(self, tmp_path):
        path = tmp_path / "leads.csv"
        sink = CsvSink(path)
        sink.save(complete_lead())
        sink.save(complete_lead())
        with path.open() as fh:
            rows = list(csv.reader(fh))
        assert len(rows) == 3
        assert [r for r in rows if r == list(CSV_HEADER)] == [list(CSV_HEADER)]

    def test_creates_parent_dirs(self, tmp_path):
        path = tmp_path / "deep" / "nested" / "leads.csv"
        CsvSink(path).save(complete_lead())
        assert path.exists()


class TestWebhookSink:
    def test_rejects_non_http_url(self):
        with pytest.raises(ValueError):
            WebhookSink("ftp://example.com/hook")

    def test_payload_shape(self):
        payload = WebhookSink.build_payload(complete_lead())
        assert set(payload) == set(CSV_HEADER)
        assert payload["phone"] == "(555) 214-8690"
        json.dumps(payload)  # must be JSON-serializable

    def test_posts_json(self, monkeypatch):
        captured = {}

        class FakeResp:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        def fake_urlopen(req, timeout=0):
            captured["url"] = req.full_url
            captured["body"] = json.loads(req.data.decode())
            captured["content_type"] = req.headers["Content-type"]
            return FakeResp()

        monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
        status = WebhookSink("https://example.com/hook").save(complete_lead())
        assert status == 200
        assert captured["url"] == "https://example.com/hook"
        assert captured["content_type"] == "application/json"
        assert captured["body"]["service"] == "Full Interior Detail"


class TestMultiSink:
    def test_all_sinks_called(self, tmp_path):
        path = tmp_path / "leads.csv"
        calls = []

        class Spy:
            def save(self, lead):
                calls.append(lead.name)

        multi = MultiSink(CsvSink(path), Spy())
        multi.save(complete_lead())
        assert path.exists()
        assert calls == ["Dana Whitfield"]
        assert multi.errors == []

    def test_failing_sink_does_not_block_others(self, tmp_path):
        path = tmp_path / "leads.csv"

        class Broken:
            def save(self, lead):
                raise ConnectionError("webhook down")

        multi = MultiSink(Broken(), CsvSink(path))
        multi.save(complete_lead())
        assert len(multi.errors) == 1
        assert path.exists()  # CSV still written
