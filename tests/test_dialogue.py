from datetime import date

from frontdesk.dialogue import IntakeAgent, State
from frontdesk.intake import Business, Service

TODAY = date(2026, 9, 24)

BUSINESS = Business(
    name="Test Detailing",
    agent_name="Riley",
    services=(
        Service("Full Interior Detail", 120, 120, ("interior",)),
        Service("Exterior Wash & Wax", 80, 90, ("wash", "wax")),
    ),
)


def make_agent(**kwargs) -> IntakeAgent:
    return IntakeAgent(BUSINESS, today=TODAY, **kwargs)


def drive(agent: IntakeAgent, lines: list[str]) -> list[str]:
    replies = [agent.greeting()]
    replies.extend(agent.handle(line) for line in lines)
    return replies


class TestHappyPath:
    def test_full_call_one_field_per_turn(self):
        agent = make_agent()
        replies = drive(agent, [
            "My name is Dana Whitfield",
            "555 214 8690",
            "the interior detail",
            "tomorrow",
            "2 pm",
            "yes",
        ])
        assert agent.done
        assert agent.lead.is_complete()
        assert agent.lead.name == "Dana Whitfield"
        assert agent.lead.phone == "(555) 214-8690"
        assert agent.lead.service == "Full Interior Detail"
        assert agent.lead.date == "2026-09-25"
        assert agent.lead.time == "14:00"
        assert "confirm" in replies[-2].lower()
        assert "all set" in replies[-1].lower()

    def test_multi_field_first_turn(self):
        agent = make_agent()
        agent.greeting()
        reply = agent.handle(
            "Hi I'm Dana, I want the interior detail tomorrow at 2 pm, "
            "number is 555 214 8690"
        )
        # Everything captured at once -> straight to confirmation.
        assert "confirm" in reply.lower()
        agent.handle("yes")
        assert agent.done

    def test_notes_captured_from_vehicle_detail(self):
        agent = make_agent()
        drive(agent, [
            "Dana",
            "555 214 8690",
            "interior detail, it's an SUV with two car seats",
            "tomorrow at 2 pm",
            "yes",
        ])
        assert agent.lead.notes is not None
        assert "SUV" in agent.lead.notes


class TestCorrections:
    def test_change_time_at_confirmation(self):
        agent = make_agent()
        replies = drive(agent, [
            "Dana",
            "555 214 8690",
            "interior detail",
            "tomorrow at 2 pm",
            "actually make it three pm",
        ])
        assert agent.lead.time == "15:00"
        assert "Updated" in replies[-1]
        agent.handle("yes")
        assert agent.done

    def test_change_phone_by_name(self):
        agent = make_agent()
        replies = drive(agent, [
            "Dana",
            "555 214 8690",
            "interior detail",
            "tomorrow at 2 pm",
            "no, the phone number is wrong",
        ])
        assert agent.lead.phone is None  # cleared for re-entry
        assert "phone" in replies[-1].lower()
        agent.handle("it's 555 900 1111")
        assert agent.lead.phone == "(555) 900-1111"
        agent.handle("yes")
        assert agent.done

    def test_ambiguous_confirmation_reasked(self):
        agent = make_agent()
        drive(agent, [
            "Dana",
            "555 214 8690",
            "interior detail",
            "tomorrow at 2 pm",
        ])
        reply = agent.handle("hmm")
        assert "yes or a no" in reply
        assert not agent.done


class TestRobustness:
    def test_empty_utterance_reasked(self):
        agent = make_agent()
        agent.greeting()
        reply = agent.handle("   ")
        assert "didn't catch that" in reply
        assert agent.state is State.NAME

    def test_greeting_mentions_business(self):
        agent = make_agent()
        assert "Test Detailing" in agent.greeting()

    def test_llm_extractor_fills_gaps_only(self):
        # On an utterance where the deterministic parser finds a field, the
        # parser wins; where it finds nothing, the LLM fills the gap.
        def fake_llm(text):
            if "2 pm" in text:
                return {"time": "09:00"}  # conflicts with parser -> parser wins
            return {}

        agent = make_agent(extractor=fake_llm)
        drive(agent, [
            "Dana",
            "555 214 8690",
            "interior detail",
            "tomorrow at 2 pm",
        ])
        assert agent.lead.time == "14:00"

    def test_failing_llm_extractor_is_ignored(self):
        def boom(text):
            raise RuntimeError("LLM endpoint down")

        agent = make_agent(extractor=boom)
        drive(agent, [
            "Dana",
            "555 214 8690",
            "interior detail",
            "tomorrow at 2 pm",
            "yes",
        ])
        assert agent.done

    def test_history_recorded(self):
        agent = make_agent()
        drive(agent, ["Dana"])
        speakers = [s for s, _ in agent.history]
        assert speakers[0] == "agent"
        assert "caller" in speakers
