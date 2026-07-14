import uuid
from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints

from atip_api.models.auth import UserRole

# light shape check only (real validation happened at account creation);
# avoids the optional email-validator dependency
_EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


class LoginRequest(BaseModel):
    email: Annotated[
        str,
        StringConstraints(strip_whitespace=True, max_length=320, pattern=_EMAIL_PATTERN),
    ]
    # bcrypt ignores bytes past 72; reject instead of silently truncating
    password: Annotated[str, StringConstraints(min_length=8, max_length=72)]


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
