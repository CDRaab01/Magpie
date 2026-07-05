from pydantic import BaseModel


class SuiteLoginRequest(BaseModel):
    # A suite access token issued by the Dragonfly identity server.
    suite_token: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
