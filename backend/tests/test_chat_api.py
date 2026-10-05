from app.llm import AssistantMessage, LLMError, ToolCall, UserMessage


def test_chat_returns_answer_and_the_tools_used(client, fake_llm):
    fake_llm.chat_replies = [
        AssistantMessage(
            tool_calls=[ToolCall(id=None, name="spending_summary", arguments={"group_by": "month"})]
        ),
        AssistantMessage(text="You haven't spent anything yet."),
    ]

    response = client.post("/chat", json={"question": "How much did I spend per month?"})

    assert response.status_code == 200
    assert response.json() == {
        "answer": "You haven't spent anything yet.",
        "tool_calls": [{"name": "spending_summary", "arguments": {"group_by": "month"}}],
    }


def test_chat_history_is_converted_to_messages(client, fake_llm):
    fake_llm.chat_replies = [AssistantMessage(text="$5.")]

    client.post(
        "/chat",
        json={
            "question": "And in October?",
            "history": [
                {"role": "user", "content": "Dining in September?"},
                {"role": "assistant", "content": "$20."},
            ],
        },
    )

    assert fake_llm.chat_calls[0]["messages"] == [
        UserMessage("Dining in September?"),
        AssistantMessage(text="$20."),
        UserMessage("And in October?"),
    ]


def test_empty_question_is_rejected(client):
    assert client.post("/chat", json={"question": ""}).status_code == 422


def test_llm_outage_returns_503(client, fake_llm):
    fake_llm.chat_replies = [LLMError("model unavailable")]

    response = client.post("/chat", json={"question": "Hi"})

    assert response.status_code == 503
    assert "try again" in response.json()["detail"]
