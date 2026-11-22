# CropFarm-AI restoration guide

This guide reflects the current repository. The Flask/Jinja application is the working backend. `frontend/` is a React/Vite dashboard preview and is not yet connected to the Flask API, authentication, or crop inference.

## Verified toolchain

- Python: 3.11.18 (`.python-version`)
- Node.js: 26.13.0 (`.nvmrc`)
- npm: 11.20.0
- Vite 8 requires Node `^20.19.0 || >=22.12.0`.
- Python package versions are pinned in `requirements.txt`; frontend package versions are pinned by `frontend/package-lock.json` (lockfile version 3).

The versions above were checked on the development Mac. Use the same versions to reproduce this environment. No FFmpeg dependency was found. Install PostgreSQL client tools only if using PostgreSQL.

## Clone the repository

```bash
git clone https://github.com/ahrar123-dev/cropfarmAI.git
cd cropfarmAI
```

This is a public repository, so anyone can read its contents. Keep credentials and private user data out of Git. In a clone of this repository, verify the remote before pushing:

```bash
git remote -v
```

## Flask backend

Install Python 3.11.18, then from the repository root:

```bash
python3.11 --version
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` locally. Leave `DATABASE_URL` blank for SQLite. The sample uses `AUTO_CREATE_DB=false` so the schema is created and versioned by migrations:

```bash
flask --app app db upgrade
python app.py
```

Open `http://127.0.0.1:5000`. The alternative Flask development command is:

```bash
flask --app app run --host 127.0.0.1 --port 5000
```

Do not run `flask --app app init-db` before `flask db upgrade` on a new database if you want Alembic migration history. `init-db` creates tables directly and does not stamp a migration revision.

To run the tests:

```bash
python -m unittest discover -s tests -v
```

## React/Vite preview

Install Node.js 26.13.0 and npm 11.20.0. With `nvm`, the root `.nvmrc` selects the Node version:

```bash
nvm install
nvm use
node --version
npm --version
npm ci --prefix frontend
npm --prefix frontend run dev
```

Open `http://localhost:5173`. To preview on another device on the same trusted Wi-Fi, run `npm --prefix frontend run dev:network` and open `http://<host-ip>:5173`. Restrict any firewall prompt to private networks. The preview has no configured API base URL; its Supabase/Groq references are placeholders, not working integrations.

Build the preview with:

```bash
npm --prefix frontend run build
```

## AI model and training data

Inference requires both checked-in files:

- `models/crop_disease_model.keras` (~39.7 MB)
- `models/class_indices.json`

`app.py` loads these fixed paths. Inference resizes images to 128×128, scales pixel values to 0–1, and selects among 15 classes. The included model is sufficient for inference; the PlantVillage training dataset is not included. `train_model.py` expects it at `static/dataset/PlantVillage`, so retraining requires separately obtaining authorized data.

The model is currently a normal Git blob, below GitHub's 50 MiB warning threshold and 100 MiB per-file limit. Git LFS is not installed and is not needed for this file at its current size. Reassess if the model grows.

## Environment variables

`.env.example` contains names and safe defaults only. Never commit `.env` or paste secret values into source control.

| Variable | Use |
| --- | --- |
| `DATABASE_URL` | Optional SQLAlchemy URL; blank selects `instance/cropfarm.db` (SQLite). |
| `SECRET_KEY` | Flask session/reset signing key; configure a strong random value in production. |
| `APP_ENV`, `FLASK_ENV` | Environment mode; `FLASK_ENV` is the fallback. |
| `AUTO_CREATE_DB` | Defaults to automatic table creation for SQLite if unset; the example disables it to use migrations. |
| `COOKIE_SECURE` | Set `true` when served over HTTPS. |
| `HOST`, `PORT`, `FLASK_DEBUG` | Direct `python app.py` server settings. |
| `RATELIMIT_STORAGE_URI` | Rate-limit backend; local default is in-memory. Use shared storage such as Redis for multi-worker hosting. |
| `WEATHER_LOCATION` | Optional default location for Open-Meteo weather. No API key is required. |
| `REQUESTS_CA_BUNDLE`, `CURL_CA_BUNDLE` | Optional custom CA bundle paths. |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `MAIL_FROM`, `SUPPORT_EMAIL` | Optional password-reset/contact email delivery. |
| `REPORT_FONT_PATH` | Optional font for localized PDF reports. |

Model paths, upload/report directories, and a React frontend API URL are not environment-variable settings in this codebase. Uploads and reports default to `instance/uploads` and `instance/reports`.

## Database backup and restore

The default database is SQLite at `instance/cropfarm.db`; PostgreSQL is optional through `DATABASE_URL`. Alembic migrations live under `migrations/versions/`.

### SQLite

Stop the application before copying a database file. For a live database, use SQLite's backup API:

```bash
python - <<'PY'
import sqlite3
source = sqlite3.connect("instance/cropfarm.db")
backup = sqlite3.connect("cropfarm-backup.sqlite3")
source.backup(backup)
backup.close()
source.close()
PY
```

To restore an authorized backup into a new local environment, create the destination directory and copy the backup into the database location while the app is stopped:

```bash
mkdir -p instance
python - <<'PY'
import sqlite3
source = sqlite3.connect("cropfarm-backup.sqlite3")
destination = sqlite3.connect("instance/cropfarm.db")
source.backup(destination)
destination.close()
source.close()
PY
flask --app app db upgrade
```

Restore only into a new or separately backed-up destination; restoring replaces its database contents. SQLite databases may contain personal account and crop records. Do not put database files, backups, uploaded images, or reports in GitHub. Transfer them separately through an approved encrypted channel only if you are authorized to move that data. Keep corresponding `instance/uploads/` files with the database only when that transfer is authorized.

### PostgreSQL

Use the PostgreSQL client tools and a separate, approved database:

```bash
pg_dump --format=custom --no-owner \
  --file=cropfarm-backup.dump \
  "postgresql://USER:PASSWORD@HOST:5432/DATABASE"
pg_restore --no-owner \
  --dbname="postgresql://USER:PASSWORD@HOST:5432/PERSONAL_DATABASE" \
  cropfarm-backup.dump
```

Replace placeholders locally; do not put credentials in this guide or commit them. Restore into a new or empty database, then configure the SQLAlchemy `DATABASE_URL` in `.env` using `postgresql+psycopg://...` and run `flask --app app db upgrade`.

## What is and is not transferred

- Preserve application source, static assets, templates, migrations, tests, `requirements.txt`, `frontend/package.json`, and `frontend/package-lock.json`.
- Keep `.env`, SQLite databases/backups, uploads, reports, local datasets, virtual environments, `node_modules`, build output, and editor state out of Git.
- The React dashboard currently displays placeholder states; the Flask/Jinja application is the real connected product.
- Confirm ownership/permission for the company-developed source, the model, and image assets before publishing to a personal public repository.
