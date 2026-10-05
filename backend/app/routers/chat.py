"""HTTP route for asking the Q&A agent questions."""

import logging
from datetime import date
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.agent.agent import answer_question
from app.db import DbSession, make_read_only
from app.llm import AssistantMessage, LLMDep, LLMError, UserMessage

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])


class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=4000)


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    # Earlier turns, so follow-ups like "and in October?" work. The server keeps no state.
    history: list[ChatTurn] = Field(default_factory=list, max_length=20)


class ToolCallOut(BaseModel):
    name: str
    arguments: dict[str, Any]


class ChatResponse(BaseModel):
    answer: str
    tool_calls: list[ToolCallOut]  # shown in the UI so users can see how an answer was found


@router.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest, db: DbSession, llm: LLMDep) -> ChatResponse:
    history = [
        UserMessage(turn.content) if turn.role == "user" else AssistantMessage(text=turn.content)
        for turn in request.history
    ]
    make_read_only(db)
    try:
        result = answer_question(
            llm=llm, db=db, question=request.question, history=history, today=date.today()
        )
    except LLMError as exc:
        logger.exception("Chat failed: the LLM call didn't succeed")
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "The assistant is unavailable right now. Please try again in a moment.",
        ) from exc
    finally:
        db.rollback()

    return ChatResponse(
        answer=result.answer,
        tool_calls=[ToolCallOut(name=c.name, arguments=c.arguments) for c in result.tool_calls],
    )
