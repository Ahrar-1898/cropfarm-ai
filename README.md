# CropFarmAI

CropFarmAI is a Flask application for crop-disease image screening and farm record keeping. It preserves the bundled TensorFlow classifier and adds user accounts, private detection history, farm records, operational logs, analytics, and a responsive workspace.

For exact Mac restoration steps, version pins, database backup guidance, and the current React/backend connection status, see [MIGRATION_GUIDE.md](MIGRATION_GUIDE.md).

## What is available

- Public long-scroll landing page with an English-first language picker, account registration, sign-in, sign-out, password reset, and profile updates. `/explore` redirects to the services section.
- Password hashing, CSRF protection, secure user sessions, route authorization, and rate limits on authentication forms.
- Farmer dashboard with counts derived from the signed-in user's records, a persisted day/night theme, and a profile menu.
- Farm, field, and crop records. The crop list is limited to the classifier's actual supported crop groups: bell pepper, potato, and tomato.
- Authenticated crop-image selection from a gallery or device camera, followed by inference using `models/crop_disease_model.keras` and `models/class_indices.json`.
- Private uploaded images, user-scoped detection history, detail views, notifications, and CSV/PDF reports.
- Manual crop-health observations, irrigation schedules, and soil readings.
- Analytics based on saved detections and user-entered crop health statuses.
- Open-Meteo current weather, seven-day forecast, location lookup, and weather context on irrigation planning; SMTP password-reset email.
- Admin aggregates and account enable/disable controls.
- Authenticated versioned JSON endpoints for summary, farms, fields, crops, detections, notifications, and admin aggregates.
- A searchable native-script language picker, saved language preferences, and honest English fallback labels for languages not translated yet.
- An optional welcome background video with reduced-motion and static-image fallbacks. No video asset is bundled.
- Public contact form, privacy information, and terms pages. Contact delivery is disabled until SMTP and `SUPPORT_EMAIL` are configured.

AI output is informational and is not a confirmed diagnosis. The classifier's confidence is its score for its selected class, not a guarantee of accuracy. Consult a local agricultural expert before treatment.

## Requirements

- Python 3.11.18 (the local project environment was verified with this version).
- PostgreSQL for a shared or production deployment. SQLite is the default for local development if `DATABASE_URL` is unset.
- The repository's trained model files in `models/`.

The training dataset is not included. Running the application does not retrain or overwrite the model.

## Local development

From the repository root:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
```

For local SQLite, leave `DATABASE_URL` blank. The sample `.env` sets `AUTO_CREATE_DB=false`; create the versioned schema through Flask-Migrate:

```bash
flask --app app db upgrade
```

To use PostgreSQL, create a database and set a connection URL in `.env`, for example:

```dotenv
SECRET_KEY=replace-with-a-long-random-value
DATABASE_URL=postgresql+psycopg://cropfarm:your-password@localhost:5432/cropfarm
AUTO_CREATE_DB=false
```

Keep API keys and passwords in `.env`, never in source code or chat, and do not commit `.env`. Open-Meteo does not require a key; set `WEATHER_LOCATION` for a default location, or set a location in your profile. Configure `DATABASE_URL` only when a PostgreSQL server is ready.

For PostgreSQL, apply the checked-in initial migration:

```bash
flask --app app db upgrade
```

For later model changes, create and review a migration before running `flask --app app db upgrade`. Migrations do not drop or recreate the database.
The language-onboarding change adds a column in migration `9f4b7c2d1a63`. For an existing database already managed by Flask-Migrate, back it up and run `flask --app app db upgrade` before starting the updated app. If a local SQLite database was created using `flask init-db` and has no `alembic_version` table, back it up first, then mark the existing schema at the initial revision and apply the new migration:

```bash
flask --app app db stamp 3cd3914451a0
flask --app app db upgrade
```

New local SQLite databases created by `flask --app app init-db` already include the onboarding column.
The per-account day/night theme preference adds migration `7a8c21e0f9b4`; back up an existing database and apply it with `flask --app app db upgrade` before starting the updated app. Newly initialized databases already include the theme column.

Start the application:

```bash
flask --app app run --host 127.0.0.1 --port 5000
```

Open [http://127.0.0.1:5000](http://127.0.0.1:5000). The consolidated public homepage is at `/`; `/explore` links to its services section. To run directly, use `python app.py`. Debug mode is off by default.

The welcome background is a static farm image until a permitted video is provided. See [`static/animations/README.md`](static/animations/README.md) to configure local video files or a supported HTTPS provider. The language picker lists English and 22 Indian languages; welcome, core account, navigation, dashboard labels, and the updated scanner, profile, settings, and notification controls are translated for English, Hindi, Assamese, and Bengali. Detailed analysis content and other locales retain an explicit English-fallback notice. This Flask application does not use Supabase or implement email/SMS OTP; account recovery remains the configured Flask password-reset flow.

The public homepage is assembled from ordered Jinja partials under `templates/home/`; section content is kept under `templates/home/sections/`. Its layout and interactions are in `static/css/home.css` and `static/js/home.js`, separate from the language/video behavior. The privacy and terms pages are deployment-specific drafts and must be reviewed by the operator before production use.

### React dashboard preview on other devices

The React dashboard lives in `frontend/`. From the repository root, install its dependencies and run the LAN-accessible Vite server:

```bash
nvm install
nvm use
npm ci --prefix frontend
npm --prefix frontend run dev:network
```

The checked development versions are Node.js 26.13.0 and npm 11.20.0; `.nvmrc` pins Node.js. Vite 8 requires Node.js `^20.19.0 || >=22.12.0`.

Open `http://<host-computer-ip>:5173` from a Windows computer or phone connected to the same trusted Wi-Fi. On Windows, find the host computer's IPv4 address with `ipconfig`; allow the development server through the firewall on private networks only if prompted. See [`frontend/README.md`](frontend/README.md) for details. This is a UI preview; the React frontend is not yet connected to the Flask API.

Create an account through the registration page. Promote an existing account to administrator from the activated environment with:

```bash
flask --app app promote-admin
```

The command prompts for the account email and does not create a default administrator.

## JSON API

The session-authenticated API is versioned under `/api/v1`:

- `GET /api/v1/summary`
- `GET` and `POST /api/v1/farms`
- `GET /api/v1/fields`
- `GET /api/v1/crops`
- `GET /api/v1/detections?page=1&per_page=20&crop=Tomato&disease=blight`
- `GET /api/v1/notifications`
- `PATCH /api/v1/notifications/<id>` with `{"is_read": true}`
- `GET /api/v1/weather?location=Fresno`
- `GET /api/v1/irrigation/advisory?location=Fresno`
- `GET /api/v1/admin/summary` for administrator accounts only

JSON writes use the same session and CSRF protection as HTML forms; send the token in an `X-CSRFToken` header. API responses are scoped to the current account.
Weather and irrigation endpoints use the user's profile location, `WEATHER_LOCATION`, or an explicit `location` query parameter. They return provider errors rather than sample data when weather is unavailable. Requests are cached in-process for 15 minutes.

## Configuration

| Variable | Purpose |
| --- | --- |
| `SECRET_KEY` | Required in production; signs sessions and reset tokens. |
| `DATABASE_URL` | PostgreSQL URL (`postgresql+psycopg://...`) or a local SQLite URL. Unset defaults to `instance/cropfarm.db`. |
| `AUTO_CREATE_DB` | Safe `create_all` behavior; defaults on for SQLite and off when `DATABASE_URL` is set. Use migrations for PostgreSQL. |
| `COOKIE_SECURE` | Set `true` when the app is served over HTTPS. |
| `RATELIMIT_STORAGE_URI` | Flask-Limiter storage; use shared Redis in multi-worker deployments. Local development defaults to in-memory storage. |
| `WEATHER_LOCATION` | Optional default Open-Meteo location; a user's profile location is used otherwise. |
| `REQUESTS_CA_BUNDLE` | Optional path to a PEM CA bundle for networks that use a custom TLS certificate. TLS verification stays enabled. |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `MAIL_FROM` | Optional SMTP configuration for password-reset and contact email. |
| `SUPPORT_EMAIL` | Required with SMTP settings to enable the public contact form. |
| `REPORT_FONT_PATH` | Optional TrueType font with the needed script coverage for localized PDF reports. English reports use the built-in PDF font when it is unavailable. |

Weather shows provider-reported current conditions and a seven-day forecast from Open-Meteo. The irrigation advisory is weather context only, not a crop-specific watering recommendation; irrigation records do not control physical equipment. Soil readings remain manual until a sensor provider and device are selected.

## Storage and privacy

Local uploads and generated reports live under the ignored `instance/` directory. Image routes require authentication and verify record ownership. User-facing history, exports, farm records, and notifications are scoped to the signed-in account; admin views show aggregate activity and account administration, not farmer images or detection details.

Back up the configured database and `instance/uploads/` together. If a detection is intentionally deleted, its stored source image and generated report are removed as well.

## Tests

Run the focused application tests:

```bash
python -m unittest discover -s tests -v
```

The scanner test performs real inference with the bundled model; it does not substitute a mock prediction.

## Known configuration limits

- PostgreSQL support and Flask-Migrate are configured, but a PostgreSQL server must be provisioned separately.
- Open-Meteo weather/geocoding does not require a key; internet access is required. Other external services need a provider-specific integration and credentials before they can be enabled.
- SMTP email verification is not configured; password reset email works only when SMTP settings are supplied.
- The contact form requires working SMTP credentials and a valid `SUPPORT_EMAIL`; its rate limit is three submissions per hour per client address. Success is shown only after the SMTP transport accepts the message.
- Privacy and terms text is a project-specific draft, not legal advice. The deployment operator must review it and add organization-specific contact, retention and jurisdiction details.
- The application has no connected sensor or irrigation hardware integration.
- In-memory rate-limit storage is suitable only for local development. Use shared storage such as Redis when deploying multiple workers.
- Non-English PDF output requires a suitable font file; without one, generated PDF reports use English text.
