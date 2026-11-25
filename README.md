# BroShare

BroShare manages household bills, flatmates, and group trip expenses in a shared workspace. React 19, Vite, TypeScript, Tailwind CSS, Django 5.2, and Django REST Framework connect to a persistent SQLite or PostgreSQL database.

## Start locally on Windows

Install Python 3.11+ and Node.js 22.12+. Extract the ZIP and open the `broshare` folder in VS Code.

Run these commands from the project root in a PowerShell terminal:

```powershell
Set-Location backend
py -3 -m venv .venv
Copy-Item .env.example .env
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py seed_broshare
.\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000
```

Open a second PowerShell terminal at the project root:

```powershell
Set-Location frontend
Copy-Item .env.example .env
npm.cmd ci
npm.cmd run dev
```

Open [http://localhost:5173](http://localhost:5173). Use **Vinay** and **Test@123** for the development demo. The demo flat starts with Vinay Penta, Tharun, Sai, and Ashwin. Demo seeding is disabled when either `DEBUG` or `DEMO_ENABLED` is false and repeated seeding leaves the existing roster intact.

Run the worker in a third terminal to generate due recurring bills and in-app reminders:

```powershell
Set-Location backend
.\.venv\Scripts\python.exe manage.py tick_broshare --watch
```

Run the command without `--watch` for a single scheduler pass. SQLite creates `backend/db.sqlite3` automatically. To use PostgreSQL, create an empty database and set `DATABASE_URL` in `backend/.env` before migrating.

To try cross-device access locally, sign in using two independent browser profiles. To try distinct accounts in one flat, copy the invitation from Settings, register a second user, and join the flat with that code. Changes are fetched on a five-second timestamp poll.

## What the app does

- Tracks monthly cycles and expenses in separate household and trip ledgers. Trips support guests, budgets, dates, and their own settlement history.
- Allocates integer paise with equal, exact, percentage, and shares splits. Largest-remainder rounding distributes all paise. Suggested transfers use deterministic greedy cash flow.
- Closing a month creates pending settlements dated the first of the following month and opens that month. Only confirmed payments affect net balances. Reversal retains the original entry. A lead can reopen and edit a cycle.
- UPI intents and QR codes use the receiver and exact amount. Complete the transfer in your UPI app and record it in BroShare.
- Archives flatmates and trips to retain historical references. Uses flat-level JWT authorization, lead controls, atomic write operations, and settlement idempotency keys.
- Tracks rotating chores, completion history, fairness points, maintenance, expense conversion, in-app reminders, and reports.
- JSON export covers workspace records. Confirmed import creates a separate workspace, preserving the current one and omitting original account links. Archive and settlement history are included.

## Checks and project layout

`frontend/src` contains the React app, API client, Zustand session store, reusable components, finance and workflow screens, and responsive styles. `backend/core` contains models, serializers, views, calculations, management commands, and API tests. `backend/core/migrations` contains the initial migration and constraints. The API reference is [docs/API.md](docs/API.md).

```powershell
# From backend
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
.\.venv\Scripts\python.exe manage.py test --noinput

# From frontend
npm.cmd run build
```

Django admin is available at [http://localhost:8000/admin/](http://localhost:8000/admin/). Use `manage.py createsuperuser` for admin access.

## Docker and public deployment

Copy the root `.env.example` to `.env` and choose a URL-safe PostgreSQL password and a long random Django secret. Run `docker compose up --build -d`, then open `http://localhost:8080`. Compose starts PostgreSQL, the Django API under Gunicorn, the worker, and Nginx serving the production React build.

For a public deployment, terminate TLS on a reverse proxy that forwards the original hostname and sets `X-Forwarded-Proto` itself. Set the production hostname in `ALLOWED_HOSTS`, the HTTPS origin in `CSRF_TRUSTED_ORIGINS`, and enable `TRUST_HTTPS_PROXY`, `SECURE_SSL_REDIRECT`, and HSTS. Keep `DEBUG=false` and `DEMO_ENABLED=false`. Set `CORS_ALLOWED_ORIGINS` only if you deploy the frontend on a different origin, and build the frontend with the corresponding `VITE_API_BASE_URL`. The Compose config uses one origin by default.

Run migrations before starting a new release, run one reminder worker, arrange regular PostgreSQL backups, and run `manage.py check --deploy` against your final settings. Periodically remove expired JWT blacklist records with `manage.py flushexpiredtokens`. Run Docker and PostgreSQL verification in the deployment environment before exposing the instance publicly.

