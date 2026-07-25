import re
import uuid
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, StringConstraints, model_validator

from atip_api.models.auth import UserRole

# light shape check only (real validation happened at account creation);
# avoids the optional email-validator dependency
_EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"

_HAS_LETTER = re.compile(r"[A-Za-z]")
_HAS_DIGIT = re.compile(r"\d")

# bcrypt hashes only the first 72 *bytes* and (bcrypt >= 4) raises ValueError on
# longer input. max_length below counts characters, so a multibyte password can
# be <= 72 chars yet exceed 72 bytes; validate the byte length here so such a
# password is rejected as 422 instead of blowing up hash_password into a 500.
_BCRYPT_MAX_BYTES = 72


def _within_bcrypt_byte_limit(value: str) -> str:
    if len(value.encode("utf-8")) > _BCRYPT_MAX_BYTES:
        raise ValueError(f"Password must be at most {_BCRYPT_MAX_BYTES} bytes long.")
    return value


_PasswordStr = Annotated[
    str,
    StringConstraints(min_length=8, max_length=_BCRYPT_MAX_BYTES),
    AfterValidator(_within_bcrypt_byte_limit),
]
_EmailStr = Annotated[
    str, StringConstraints(strip_whitespace=True, max_length=320, pattern=_EMAIL_PATTERN)
]


class LoginRequest(BaseModel):
    email: _EmailStr
    password: _PasswordStr


class RegisterRequest(BaseModel):
    """Public self-service signup. The registrant names their organization and
    becomes its ORG_ADMIN (see atip_api.services.auth)."""

    display_name: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
    ]
    email: _EmailStr
    organization_name: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
    ]
    password: _PasswordStr

    @model_validator(mode="after")
    def _enforce_password_policy(self) -> "RegisterRequest":
        # Kept in lock-step with the web registerSchema (apps/web/src/lib/validation.ts).
        # NB: the error messages are safe to surface; they never echo the password.
        if not _HAS_LETTER.search(self.password) or not _HAS_DIGIT.search(self.password):
            raise ValueError("Password must contain at least one letter and one digit.")
        if self.password.strip().lower() == self.email.strip().lower():
            raise ValueError("Password must not be the same as your email address.")
        return self


class OrganizationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    display_name: str
    role: UserRole
    organization: OrganizationRead
