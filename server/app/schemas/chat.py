from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: str  # "user" | "assistant"
    content: str


class ChatRequest(BaseModel):
    message: str = Field(..., description="the household's question")
    history: list[ChatMessage] = Field(
        default_factory=list, description="prior turns, oldest first"
    )


class ChatResponse(BaseModel):
    reply: str
