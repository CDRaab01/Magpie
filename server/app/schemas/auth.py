from pydantic import BaseModel


class SuiteLoginRequest(BaseModel):
    # A suite access token issued by the Dragonfly identity server.
    suite_token: str


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    # The signed-in account, for the app's Settings header. Read-only projection of the SSO
    # identity linked at /auth/suite; Magpie owns no password of its own.
    name: str
    email: str
