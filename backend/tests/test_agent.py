"""The agent loop, with a scripted fake LLM standing in for the model."""

from datetime import date

from app.agent.agent import MAX_STEPS, TOO_MANY_STEPS_ANSWER, answer_question
from app.llm import AssistantMessage, ToolCall, ToolResultMessage, UserMessage
from tests.factories import add_receipt, default_user

TODAY = date(2026, 10, 4)


def tool_call(name: str, **arguments) -> AssistantMessage:
    return AssistantMessage(tool_calls=[ToolCall(id="call-1", name=name, arguments=arguments)])


def ask(fake_llm, db, question: str, history=None):
    return answer_question(
        llm=fake_llm,
        db=db,
        user_id=default_user(db).id,
        question=question,
        history=history or [],
        today=TODAY,
    )


def test_calls_a_tool_then_answers_from_its_result(fake_llm, db_session):
    add_receipt(db_session, total="42.00", purchase_date=date(2026, 9, 5))
    fake_llm.chat_replies = [
        tool_call("spending_summary", start_date="2026-09-01", end_date="2026-09-30"),
        AssistantMessage(text="You spent $42.00 in September 2026."),
    ]

    result = ask(fake_llm, db_session, "How much did I spend in September?")

    assert result.answer == "You spent $42.00 in September 2026."
    assert [c.name for c in result.tool_calls] == ["spending_summary"]

    # The model's second turn saw the real tool result from the database.
    tool_result = fake_llm.chat_calls[1]["messages"][-1]
    assert isinstance(tool_result, ToolResultMessage)
    assert tool_result.result["groups"][0]["total"] == "42.00"


def test_system_prompt_includes_today_and_categories(fake_llm, db_session):
    fake_llm.chat_replies = [AssistantMessage(text="Hi!")]

    ask(fake_llm, db_session, "Hello")

    system = fake_llm.chat_calls[0]["system"]
    assert "Today's date is 2026-10-04 (Sunday)" in system
    assert "- groceries:" in system


def test_history_is_passed_to_the_model(fake_llm, db_session):
    fake_llm.chat_replies = [AssistantMessage(text="Same as before.")]
    history = [UserMessage("How much on dining?"), AssistantMessage(text="$20.")]

    ask(fake_llm, db_session, "And groceries?", history)

    assert fake_llm.chat_calls[0]["messages"] == [*history, UserMessage("And groceries?")]


def test_tool_error_goes_back_to_the_model_so_it_can_recover(fake_llm, db_session):
    fake_llm.chat_replies = [
        tool_call("spending_summary", categories=["snacks"]),
        tool_call("spending_summary", categories=["dining"]),
        AssistantMessage(text="You spent nothing on dining."),
    ]

    result = ask(fake_llm, db_session, "Snack spending?")

    first_result = fake_llm.chat_calls[1]["messages"][-1].result
    assert "Invalid arguments" in first_result["error"]
    assert result.answer == "You spent nothing on dining."


def test_stops_after_max_steps(fake_llm, db_session):
    fake_llm.chat_replies = [tool_call("spending_summary")] * MAX_STEPS

    result = ask(fake_llm, db_session, "Loop forever")

    assert result.answer == TOO_MANY_STEPS_ANSWER
    assert len(fake_llm.chat_calls) == MAX_STEPS
