from datetime import datetime
from pydantic import BaseModel, Field, model_validator


class TeacherQuestionInput(BaseModel):
    subject_id: str = Field(min_length=1)
    class_id: str = Field(min_length=1)
    section_id: str = Field(min_length=1)
    question_text: str = Field(min_length=5, max_length=2000)
    options: list[str] = Field(min_length=2, max_length=5)
    correct_option: int = Field(ge=0, le=4)
    points: float = Field(default=1, gt=0, le=100)

    @model_validator(mode="after")
    def validate_options(self):
        if self.correct_option >= len(self.options):
            raise ValueError("correct_option must identify an existing option")
        if any(not option.strip() for option in self.options):
            raise ValueError("Options cannot be empty")
        self.options = [option.strip() for option in self.options]
        self.question_text = self.question_text.strip()
        return self


class TeacherExamInput(BaseModel):
    title: str = Field(min_length=3, max_length=160)
    subject_id: str = Field(min_length=1)
    class_id: str = Field(min_length=1)
    section_id: str = Field(min_length=1)
    question_ids: list[str] = Field(min_length=1, max_length=200)
    duration_minutes: int = Field(ge=1, le=300)
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    allow_retakes: bool = False

    @model_validator(mode="after")
    def validate_schedule(self):
        if self.starts_at and self.ends_at and self.ends_at <= self.starts_at:
            raise ValueError("ends_at must be later than starts_at")
        self.title = self.title.strip()
        if len(set(self.question_ids)) != len(self.question_ids):
            raise ValueError("Duplicate question IDs are not allowed")
        return self


class TeacherPublishExamsInput(BaseModel):
    exam_ids: list[str] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def validate_unique_exam_ids(self):
        if len(set(self.exam_ids)) != len(self.exam_ids):
            raise ValueError("Duplicate exam IDs are not allowed")
        return self


class QuestionGradeInput(BaseModel):
    question_id: str = Field(min_length=1)
    is_correct: bool


class SubmissionGradeInput(BaseModel):
    grades: list[QuestionGradeInput] = Field(min_length=1, max_length=200)
