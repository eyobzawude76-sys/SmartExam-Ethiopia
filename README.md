# SmartExam Ethiopia

A role-based online examination system for Ethiopian secondary schools (Grades 11 and 12).

## V1 scope

- **Admin:** create teacher and student accounts; manage subjects, classes, and sections; assign teachers to subject/class/section and students to class/section.
- **Teacher:** manage MCQ questions only within assigned teaching scopes; create and schedule exams; publish exams; review/grade submissions; release results.
- **Student:** access only published exams assigned to their class and section; submit an exam; view results only after the teacher releases them.

## Technology

- Frontend: Next.js + TypeScript
- Backend: FastAPI + Python
- Database: MongoDB
- Authentication and authorization: JWT + role-based access control (RBAC)
- Offline foundation: PWA + IndexedDB (implemented only where compatible with secure exam rules)

## Core rules

1. Admin manages system setup and accounts; Admin does not create or grade exam questions.
2. Teachers can access only their assigned subject/class/section combinations.
3. Students can access only exams published for their own class and section.
4. Results remain hidden from students until the teacher explicitly releases them.
5. V1 supports MCQ exams only. AI chat and unrelated features are out of scope.
6. Exam timing, single-attempt defaults, server-side authorization, and secure result visibility must be enforced by the backend, not only by the UI.

## Repository layout

- `backend/` — FastAPI application
- `frontend/` — Next.js application
- `docs/` — requirements, architecture, and implementation notes

## Development status

Project initialized. Implementation will proceed in small, tested phases, starting with architecture and the Admin foundation.

## Security

Never commit `.env` files, database credentials, JWT secrets, passwords, or real student data. Use `.env.example` with placeholders only.
