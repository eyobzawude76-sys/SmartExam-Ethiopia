# SmartExam Ethiopia V1 — Backend setup

## 1. Requirements
- Python 3.11+
- MongoDB running locally or a private MongoDB Atlas connection
- PowerShell or a terminal

## 2. Install
From the repository root:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

Edit `.env` before starting:
- Set `APP_ENV=development` for local development (the environment setting is required).
- Set a unique `JWT_SECRET_KEY` with at least 32 characters.
- Set the correct private `MONGODB_URI` and database name.
- Set `ADMIN_USERNAME`, `ADMIN_FULL_NAME`, and a strong `ADMIN_PASSWORD` (12+ characters).
- Never commit `.env` or share its values.

### Hosted production environment

Configure these as private backend environment variables in the hosting provider (never in frontend/public variables):
- `APP_ENV=production` — required; the API will not start if the environment is omitted.
- `JWT_SECRET_KEY` — generate a unique random secret of at least 32 characters; do not use the example value.
- `MONGODB_URI` and `MONGODB_DATABASE` — use the production database and a private connection string.
- `FRONTEND_ORIGIN` — the exact HTTPS origin of the deployed Next.js frontend (for example, `https://your-app.example`, with no path).
- Set `ACCESS_TOKEN_EXPIRE_MINUTES` to the session lifetime you intend to use.

The API rejects a placeholder JWT secret and non-HTTPS frontend origin in production. **Before exposing the login endpoint publicly, configure shared rate limiting at the hosting/WAF layer or add a shared Redis-backed limiter.** Login rate limiting is not yet implemented in this V1 API; do not rely on an in-process memory counter for a multi-worker deployment. For the Next.js hosting provider, set `NEXT_PUBLIC_API_BASE_URL=https://your-api.example/api/v1` to the deployed HTTPS API URL. This value is public frontend configuration; never place JWT or MongoDB secrets in a `NEXT_PUBLIC_*` variable. The repository does not contain or verify the hosting provider's live environment variables; verify these settings in both provider dashboards before deployment.

## 3. Create the first Admin
Run once from the `backend/` directory:

```powershell
python -m scripts.create_admin
```

The script refuses to create another bootstrap Admin if one already exists. It stores only an Argon2 password hash.

## 4. Start the API

```powershell
uvicorn app.main:app --reload
```

- Health: `http://localhost:8000/health`
- OpenAPI docs: `http://localhost:8000/docs`
- Admin UI (Next.js): `http://localhost:3000/admin`

Set `NEXT_PUBLIC_API_BASE_URL=http://localhost:8000/api/v1` in the frontend environment if the API is hosted elsewhere.

## Admin API endpoints
All `/api/v1/admin/*` routes require a valid Admin JWT:
- `POST /auth/login` and `POST /auth/change-password`
- `GET /admin/dashboard`
- `GET|POST /admin/subjects`
- `GET|POST /admin/classes`
- `GET|POST /admin/sections`
- `POST /admin/teachers`
- `GET /admin/teachers`
- `GET /admin/teachers/{teacher_id}/assignments`
- `POST /admin/teachers/{teacher_id}/assignments` (add another subject/class/section assignment)
- `POST /admin/students`
- `GET /admin/students`
- `PATCH /admin/users/{user_id}/status`

The temporary password is returned only in the successful create-account response. The database stores only the Argon2 hash; existing passwords cannot be viewed.


## Automated Admin verification

The repository includes an Admin integration test suite and GitHub Actions workflow at `.github/workflows/admin-ci.yml`.

Local test commands (MongoDB must be running):

```powershell
cd backend
pip install -r requirements.txt
pip install pytest httpx
$env:APP_ENV="test"
$env:MONGODB_URI="mongodb://127.0.0.1:27017"
$env:MONGODB_DATABASE="smart_exam_admin_test"
$env:JWT_SECRET_KEY="test-only-secret-key-at-least-32-characters-long"
pytest -q
```

The tests cover unauthenticated access, Admin login, academic structure creation, Teacher and Student creation, assignment validation, password hashing, and Teacher role denial. CI also compiles Python and type-checks/builds the Next.js frontend. Use the repository's **Actions** tab to see the actual run result; a committed workflow or test file alone is not evidence that tests passed.
