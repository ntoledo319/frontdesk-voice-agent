import pytest

from frontdesk.llm import LLMExtractor, parse_extraction_response


class TestParseExtractionResponse:
    def test_clean_json(self):
        out = parse_extraction_response(
            '{"name": "Dana", "phone": "(555) 214-8690", "service": null,'
            ' "date": null, "time": "14:00", "address": null, "notes": null}'
        )
        assert out == {"name": "Dana", "phone": "(555) 214-8690", "time": "14:00"}

    def test_markdown_fences(self):
        out = parse_extraction_response(
            '```json\n{"name": "Dana", "time": null}\n```'
        )
        assert out == {"name": "Dana"}

    def test_prose_around_json(self):
        out = parse_extraction_response(
            'Here is the extraction: {"name": "Dana"} hope that helps'
        )
        assert out == {"name": "Dana"}

    def test_unknown_keys_dropped(self):
        out = parse_extraction_response('{"name": "Dana", "evil": "x"}')
        assert out == {"name": "Dana"}

    def test_non_object_rejected(self):
        with pytest.raises((ValueError, Exception)):
            parse_extraction_response('["not", "an", "object"]')

    def test_no_json_rejected(self):
        with pytest.raises(ValueError):
            parse_extraction_response("I could not extract anything.")

    def test_non_string_values_dropped(self):
        out = parse_extraction_response('{"name": 42, "time": "14:00"}')
        assert out == {"time": "14:00"}


class TestLLMExtractor:
    def test_disabled_without_key(self, monkeypatch):
        monkeypatch.delenv("LLM_API_KEY", raising=False)
        extractor = LLMExtractor("Biz", ["Wash"], api_key="")
        assert not extractor.enabled
        assert extractor("some utterance") == {}

    def test_prompt_includes_business_context(self):
        extractor = LLMExtractor(
            "Test Detailing", ["Full Interior Detail", "Wash"], api_key="k"
        )
        assert "Test Detailing" in extractor.system_prompt
        assert "Full Interior Detail" in extractor.system_prompt
