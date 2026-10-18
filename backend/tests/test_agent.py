"""The agent loop, with a scripted fake LLM standing in for the model."""

from datetime import date

from app.agent.agent import (
    FINAL_STEP_INSTRUCTION,
    MAX_STEPS,
    TOO_MANY_STEPS_ANSWER,
    answer_question,
)
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


def test_question_on_an_empty_account_is_answered_in_one_tool_call(fake_llm, db_session):
    food_last_month = tool_call(
        "spending_summary",
        categories=["groceries", "dining"],
        start_date="2026-09-01",
        end_date="2026-09-30",
    )
    fake_llm.chat_replies = [
        food_last_month,
        AssistantMessage(text="$0, no receipts in that period (September 1-30, 2026)."),
    ]

    result = ask(fake_llm, db_session, "How much did I spend on food last month?")

    assert result.answer == "$0, no receipts in that period (September 1-30, 2026)."
    assert len(result.tool_calls) == 1
    # What the model saw: a valid, empty result that tells it not to keep searching.
    tool_result = fake_llm.chat_calls[1]["messages"][-1].result
    assert tool_result["groups"] == []
    assert "no receipts yet" in tool_result["result"]


def test_system_prompt_says_empty_results_are_final_and_food_is_groceries_and_dining(
    fake_llm, db_session
):
    fake_llm.chat_replies = [AssistantMessage(text="Hi!")]

    ask(fake_llm, db_session, "Hello")

    system = fake_llm.chat_calls[0]["system"]
    assert "always exist, even with no receipts" in system
    assert '"Food" means the\n  groceries and dining categories' in system
    assert "An empty tool result is a complete, correct answer" in system


def test_last_step_must_answer_without_tools(fake_llm, db_session):
    fake_llm.chat_replies = [tool_call("spending_summary")] * (MAX_STEPS - 1) + [
        AssistantMessage(text="You have no spending on record.")
    ]

    result = ask(fake_llm, db_session, "Keep checking")

    assert result.answer == "You have no spending on record."
    allowed = [c["allow_tool_calls"] for c in fake_llm.chat_calls]
    assert allowed == [True] * (MAX_STEPS - 1) + [False]
    assert fake_llm.chat_calls[-1]["messages"][-1] == UserMessage(FINAL_STEP_INSTRUCTION)


def test_stops_after_max_steps_if_the_model_still_calls_tools(fake_llm, db_session):
    fake_llm.chat_replies = [tool_call("spending_summary")] * MAX_STEPS

    result = ask(fake_llm, db_session, "Loop forever")

    assert result.answer == TOO_MANY_STEPS_ANSWER
    assert len(fake_llm.chat_calls) == MAX_STEPS
    assert len(result.tool_calls) == MAX_STEPS - 1  # the last step's calls never ran
