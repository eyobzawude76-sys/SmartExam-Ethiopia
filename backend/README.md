# Backend setup — Admin phase

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
- Set a unique `JWT_SECRET_KEY` with at least 32 characters.
- Set the correct private `MONGODB_URI` and database name.
- Set `ADMIN_USERNAME`, `ADMIN_FULL_NAME`, and a strong `ADMIN_PASSWORD` (12+ characters).
- Never commit `.env` or share its values.

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
- `GET /admin/dashboard`
- `GET|POST /admin/subjects`
- `GET|POST /admin/classes`
- `GET|POST /admin/sections`
- `POST /admin/teachers`
- `GET /admin/teachers`
- `GET /admin/teachers/{teacher_id}/assignments`
- `POST /admin/students`
- `GET /admin/students`
- `PATCH /admin/users/{user_id}/status`

The temporary password is returned only in the successful create-account response. The database stores only the Argon2 hash; existing passwords cannot be viewed.
