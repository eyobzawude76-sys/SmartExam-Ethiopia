from pydantic import BaseModel, Field, model_validator


class StudentAnswerInput(BaseModel):
    question_id: str = Field(min_length=1)
    selected_option: int = Field(ge=0, le=4)


class StudentSaveAnswersInput(BaseModel):
    answers: list[StudentAnswerInput] = Field(max_length=200)

    @model_validator(mode="after")
    def unique_question_answers(self):
        ids = [item.question_id for item in self.answers]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate answers for a question are not allowed")
        return self
