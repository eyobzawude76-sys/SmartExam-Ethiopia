# SmartExam Ethiopia V1 — Functional Requirements

## Admin — setup and user management
- Create teacher accounts and assign subject + class + section combinations.
- Manage subjects, classes, and sections.
- Create student accounts and assign each student to a class and section.
- Admin does not create questions, publish exams, grade submissions, or release results.

## Teacher — questions, exams, grading, and release
- A teacher can operate only within assignments granted by Admin.
- Create MCQ questions only for assigned subject/class/section scopes.
- Create exams, set start/end times and duration, and publish them.
- Review submissions and grade them. MCQ auto-scoring may calculate a suggested score, but teacher confirms/finalizes grades.
- Explicitly release results. Before release, students must not receive marks, answer keys, or grading details.

## Student — exam taking and results
- Sign in with an assigned student account.
- See only exams published for the student's class and section, during the allowed exam window.
- Submit answers within the permitted exam window.
- Default to one attempt per exam; retakes require explicit teacher authorization.
- Enforce exam deadlines and automatic submission server-side.
- See marks and feedback only after the teacher releases the result.

## V1 constraints
- MCQ only; roles are ADMIN, TEACHER, STUDENT.
- JWT authentication and backend-enforced RBAC.
- MongoDB; Next.js + TypeScript frontend; FastAPI + Python backend.
- PWA/IndexedDB foundation, without weakening server-side exam timing and submission rules.
- AI chat and unrelated features are out of scope.

## Security requirements
- Enforce every role and assignment boundary on the backend, not only in the UI.
- Store password hashes only; never store or display plaintext passwords after account creation.
- Never commit secrets or real student information.
- Validate inputs and test authorization boundaries.
