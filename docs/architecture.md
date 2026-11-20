# Initial Architecture

## Application boundaries
- `frontend/`: Next.js application; role-specific screens and API client.
- `backend/`: FastAPI application; authentication, authorization, exam lifecycle, grading, and result visibility.
- MongoDB: persistent storage accessed only by the backend.

## Planned collections
- `users`: identity, password hash, role, status.
- `subjects`, `classes`, `sections`: academic structure.
- `teacher_assignments`: teacher + subject + class + section scope.
- `student_enrollments`: student + class + section scope.
- `questions`: MCQ content; correct answer excluded from student-facing payloads.
- `exams`: scope, schedule, duration, publication state, attempt policy.
- `exam_attempts`: student attempt, timestamps, submitted answers, state.
- `grades`: teacher-confirmed score and release state/timestamp.

## Critical authorization rules
1. Every teacher query and mutation is constrained by the authenticated teacher's assignments.
2. Every student exam query is constrained by the student's enrollment and published/available exam state.
3. Correct answers are never included in student exam payloads.
4. Grades and feedback remain inaccessible until explicitly released.
5. Attempt count and deadlines are enforced server-side and atomically.
6. Admin endpoints never expose password hashes or existing passwords.

## Implementation sequence
1. Repository and application skeleton.
2. Configuration, database connection, health checks, and test setup.
3. Authentication and RBAC.
4. Admin setup APIs and UI.
5. Teacher question/exam workflows.
6. Student exam-taking workflow.
7. Grading, result release, and end-to-end security tests.
8. PWA/offline refinements compatible with exam integrity.
