from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, SecretStr, computed_field


class Page[T](BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[T]
    total: int = Field(ge=0, strict=True)
    page: int = Field(ge=1, strict=True)
    page_size: int = Field(ge=1, le=100, strict=True)

    @computed_field
    @property
    def total_pages(self) -> int:
        return (self.total + self.page_size - 1) // self.page_size


class UserCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    login: str = Field(min_length=1)
    password: SecretStr = Field(min_length=1)


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    login: str
    role: Literal["user", "moderator"]


class UserSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    login: str


class ThreadCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1)
    text: str = Field(min_length=1)


class ThreadListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    author: UserSummary
    created_at: AwareDatetime


class ThreadRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    text: str
    created_by: int
    created_at: AwareDatetime


class CommentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1)


class CommentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    thread_id: int
    user_id: int
    text: str
    created_at: AwareDatetime
