import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class RegisterIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)
    accept_terms: bool
    language: Literal["pt-BR", "en"] | None = None
    captcha_token: str | None = None


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)
    captcha_token: str | None = None
    # Code from the authenticator app (or a recovery code) when the account has 2FA.
    otp_code: str | None = Field(default=None, max_length=20)


class TokenIn(BaseModel):
    token: str = Field(min_length=10, max_length=200)


class EmailIn(BaseModel):
    email: EmailStr


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    email: str
    ui_language: str
    is_system_admin: bool
    email_verified_at: datetime | None
    two_factor: bool = False


class TokenOut(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"  # noqa: S105 - OAuth token type, not a secret
    expires_in: int
    user: UserOut


class UserUpdateIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    ui_language: Literal["pt-BR", "en"] | None = None


class ResetPasswordIn(BaseModel):
    token: str = Field(min_length=10, max_length=200)
    password: str = Field(min_length=1, max_length=256)


class ChangePasswordIn(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=1, max_length=256)
