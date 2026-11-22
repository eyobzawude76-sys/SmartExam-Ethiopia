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

### MongoDB Atlas connection (SmartExam V1)

1. In Atlas, create a dedicated database user for this application. Grant only the database permissions it needs; do not reuse your Atlas account login.
2. In **Network Access**, allow the backend host's outbound IP addresses. Avoid a permanent `0.0.0.0/0` rule; if the host has changing outbound IPs, use its documented outbound ranges or an appropriate private networking option.
3. In **Connect → Drivers**, copy the Python `mongodb+srv://` connection string. If the database-user password contains special characters, URL-encode them before inserting the password into the URI.
4. In the backend hosting dashboard (Render), add these private environment variables:
   - `MONGODB_URI` = the Atlas connection string (keep it secret; never commit it or put it in a `NEXT_PUBLIC_*` variable).
   - `MONGODB_DATABASE=smart_exam_ethiopia` = the V1 database name. The backend selects this configured database explicitly, even if the URI path contains a different database name.
   - Keep `APP_ENV=production`, `JWT_SECRET_KEY`, and `FRONTEND_ORIGIN` configured as described above.
5. Redeploy/restart the backend. Application startup runs MongoDB `ping` and creates the required indexes; if Atlas authentication, DNS, TLS, network access, or index creation fails, startup fails rather than silently using a disconnected database.

The `/health` endpoint reports whether the application has initialized its database handle; the definitive initial connectivity check is the MongoDB ping during startup. Do not share Atlas passwords or full connection strings in chat, screenshots, GitHub, or frontend variables. If a credential has been exposed, rotate it in Atlas before using the connection.

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

The pytest suite covers Admin APIs, Teacher assignment-scoped question/exam workflows, CSV import, manual per-student grading and result publication, Student exam access, timed attempts, auto-submit, and result visibility. CI compiles Python and runs the complete pytest suite, then lints, type-checks, and builds the Next.js frontend. Use the repository's **Actions** tab to see the actual run result; a committed workflow or test file alone is not evidence that tests passed.
