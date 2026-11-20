from app.schemas import UserCreateInput


def test_user_creation_trims_name_but_preserves_temporary_password_exactly():
    password = "  Exact-Temporary-Password-123!  "
    payload = UserCreateInput(
        username="student_123",
        full_name="  Example Student  ",
        temporary_password=password,
    )

    assert payload.full_name == "Example Student"
    assert payload.temporary_password == password
