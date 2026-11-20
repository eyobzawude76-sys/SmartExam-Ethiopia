from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

Role = Literal["ADMIN", "TEACHER", "STUDENT"]


class LoginInput(BaseModel):
    username: str = Field(min_length=3, max_length=50, pattern=r"^[A-Za-z0-9._-]+$")
    password: str = Field(min_length=8, max_length=128)


class UserCreateInput(BaseModel):
    username: str = Field(min_length=3, max_length=50, pattern=r"^[A-Za-z0-9._-]+$")
    full_name: str = Field(min_length=2, max_length=120)
    temporary_password: str = Field(min_length=12, max_length=128)
    model_config = ConfigDict(str_strip_whitespace=True)


class TeacherAssignmentInput(BaseModel):
    subject_id: str
    class_id: str
    section_id: str


class TeacherCreateInput(UserCreateInput):
    assignments: list[TeacherAssignmentInput] = Field(min_length=1, max_length=30)


class StudentCreateInput(UserCreateInput):
    class_id: str = Field(min_length=1)
    section_id: str = Field(min_length=1)


class SubjectInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    name: str = Field(min_length=2, max_length=80)
    code: str = Field(min_length=2, max_length=20, pattern=r"^[A-Za-z0-9_-]+$")


class ClassInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    name: str = Field(min_length=2, max_length=40)


class SectionInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    class_id: str = Field(min_length=1)
    name: str = Field(min_length=1, max_length=20)


class UserStatusInput(BaseModel):
    is_active: bool


class PasswordChangeInput(BaseModel):
    current_password: str = Field(min_length=8, max_length=128)
    new_password: str = Field(min_length=12, max_length=128)
