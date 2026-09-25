# ShamsQuiz

A live classroom quiz game built with Django. Teachers create modules of multiple-choice questions and host real-time quizzes; students join from any device with a 6-character code and race against the clock to answer. Points are fixed at **1,000 per question** and decay the longer a student waits, a live **top-5 podium** keeps the momentum, and each game finishes on a full-screen live **scoreboard**.

## Aim

- Make classroom revision **live, social and competitive** — no long setup, no per-student accounts.
- Give teachers a **reusable question bank**, instant question editing, and per-session **PDF reports + charts** from hosted quizzes.
- Give administrators a **control panel** to manage users, modules, sessions, participants, answers and activity logs.
- Keep the game fair and exciting: fixed 1,000-mark questions that reward speed, with results shown instantly.

## Features

- **Teacher**
  - Sign up / log in, teacher dashboard
  - Create modules and add MCQs (choices A–D, per-question time limit — minimum **10 s**)
  - Question **bank**: save any question to it, import bank questions into other modules
  - Host a quiz live → students join with the code
  - Start question / force reveal / next question, live status
  - **Live top-5 podium** (ranked by current score, updates as students answer)
  - End quiz → full-screen live **scoreboard**
  - **History** with pagination + downloadable **PDF report** and **chart** per session
  - **Account page**: name, email, phone, WhatsApp, Telegram, Facebook, Instagram, YouTube, TikTok, website + change password
- **Student**
  - Join with code + nickname (no account needed)
  - Answer within the time limit — **1,000 points fixed** per question, decaying with time
  - Instant correct/wrong + points at reveal
  - Final score and rank, landing on the live scoreboard
- **Admin** (`/admin/`)
  - Users (create/edit/delete, roles), modules, sessions (force-end), participants, answers, teachers, activity logs
  - Paginated lists and recent-sessions dashboard

## Scoring rules

- Every question is worth a **fixed 1,000 points**.
- A correct answer earns `round(1000 × time-remaining / time-limit)` — answer instantly for the full 1,000, answer just before time runs out for near zero.
- No answer or a wrong answer earns **0**.
- Minimum time per question is **10 seconds** (enforced in the form and clamped on the model).

## Tech stack

- Python 3 · Django 6
- SQLite for local development, Apache2 + mod_wsgi for production
- Tailwind CSS (CDN) + Lucide icons · responsive, mobile-friendly
- reportlab (PDF reports) · matplotlib + numpy (score charts)
- No-account gameplay: participants stored per-session via cookies

## Installation (local development)

```bash
# 1. Clone and enter the project
git clone https://github.com/TheGhostSecurity/shamsQuiz.git
cd shamsQuiz

# 2. Create and activate a virtual environment
python -m venv venv
venv\Scripts\activate            # Windows
# source venv/bin/activate       # macOS / Linux

# 3. Install dependencies
pip install -r requirements.txt

# 4. Prepare the database
python manage.py migrate

# 5. Create your superuser / teacher account
python manage.py createsuperuser

# 6. Run the dev server
python manage.py runserver

# 7. Open http://127.0.0.1:8000
```

Run the test suite with:

```bash
python manage.py test quiz
```

## Installation (production — Apache2 + mod_wsgi)

Example server layout used by the live deployment:

```bash
sudo apt install apache2 libapache2-mod-wsgi-py3
sudo git clone https://github.com/TheGhostSecurity/shamsQuiz.git /opt/shamsquiz
cd /opt/shamsquiz
sudo python3 -m venv venv
sudo ./venv/bin/pip install -r requirements.txt
```

Create a server-only settings file `/opt/shamsquiz/shamsquiz/settings_prod.py`:

```python
from .settings import *   # noqa: F401,F403

DEBUG = False
ALLOWED_HOSTS = ["YOUR_SERVER_IP", "localhost", "127.0.0.1"]
CSRF_TRUSTED_ORIGINS = ["http://YOUR_SERVER_IP", "http://YOUR_SERVER_IP:9000"]
STATIC_ROOT = BASE_DIR / "staticfiles"
```

Apply migrations, collect static files and deploy behind mod_wsgi:

```bash
cd /opt/shamsquiz
sudo ./venv/bin/python manage.py migrate --noinput
sudo ./venv/bin/python manage.py collectstatic --noinput
sudo chown -R www-data:www-data /opt/shamsquiz
```

Apache virtual host (e.g. `/etc/apache2/sites-available/shamsquiz.conf`) listening on port 9000:

```apache
<VirtualHost *:9000>
    WSGIDaemonProcess shamsquiz python-home=/opt/shamsquiz/venv python-path=/opt/shamsquiz
    WSGIProcessGroup shamsquiz
    WSGIApplicationGroup %{GLOBAL}
    WSGIScriptAlias / /opt/shamsquiz/shamsquiz/wsgi.py

    Alias /static/ /opt/shamsquiz/staticfiles/

    <Directory /opt/shamsquiz/shamsquiz>
        Require all granted
    </Directory>
    <Directory /opt/shamsquiz/staticfiles>
        Require all granted
    </Directory>

    ErrorLog ${APACHE_LOG_DIR}/shamsquiz_error.log
    CustomLog ${APACHE_LOG_DIR}/shamsquiz_access.log combined
</VirtualHost>
```

Point Django at the production settings and restart:

```bash
echo 'export DJANGO_SETTINGS_MODULE=shamsquiz.settings_prod' | sudo tee -a /etc/apache2/envvars
sudo a2ensite shamsquiz
sudo systemctl restart apache2
```

On every code update: `git pull` (keep the repo marked safe with `git config --global --add safe.directory /opt/shamsquiz`), `migrate` if new migrations appeared, `chown -R www-data:www-data /opt/shamsquiz`, then restart Apache.

## Usage guide

### Teacher

1. **Sign up** (choose "Teacher") and log in.
2. Go to **Modules → New module**, then **Add question**: type the question, fill choices A–D, pick the correct one, set the time limit (**min 10 s**) — scoring is always the fixed 1,000-point decay, no points field to set.
3. **Save to bank** any question you want to reuse; import bank questions into other modules from the **Bank** page.
4. Click **Host** — a 6-character code is generated (e.g. `A1B2C3`).
5. Students open the site, pick **Student**, enter the code and their name.
6. Use the host screen: share the code, then **Start question**, **Reveal** (or let the timer run out), **Next question**. The **Live podium** panel shows the current top 5 by score at all times.
7. **End quiz** → everyone is sent to the full-screen **scoreboard**.
8. Later, open **Teacher → History** for per-session **PDF reports** and **score charts**.
9. Keep your public contact details up to date under **Account** (profile + password).

### Student

1. Open the site → **Student** → enter the 6-character quiz code.
2. Enter your name — that's it, no account.
3. When the question appears, the timer bar runs down; tap your answer. The faster you're right, the more you keep of the **1,000 points**.
4. After the reveal you see whether you were right and what you earned, then on to the next question.
5. When the quiz ends you're taken to the live **scoreboard** to see the final standings.

### Admin

Superusers get the `/admin/` panel: manage users and roles, browse modules and their questions, view/force-end sessions, inspect participants, per-question answers and teacher lists, and review the full activity log.

## Version history

- **1.1** (2026-09-25, `d163209`) — Game logic overhaul
  - Fixed **1,000-point** scoring degraded by time (per-question `points` field removed)
  - **Minimum 10 s** time limit enforced in the form, model and live start
  - **Live top-5 podium** in the host control panel (dynamic per performance)
  - End/results screens now point to the **live scoreboard** (host and student auto-redirect)
  - Bug fix: invalid choice IDs no longer 500 (missing `Choice` import in answer view)
- **1.0.1** (2026-09-24, `0d25fa7`) — Admin fix
  - Fixed `NameError` (missing `log_activity` import) on admin user/module/session mutations
- **1.0** (2026-09-24, `d008c25`) — Polished release
  - Teacher profile/account page with contact links and password change
  - Admin pagination fixed across all list pages + dashboard recent sessions
  - Student timer-fade bar, mobile-tuned answer buttons
  - Question bank (save/import/archive), full-screen scoreboard, home page polish
- **0.9 → 1.0 dev** (2026-09-22 → 2026-09-24, `0953655` … `d008c25`)
  - Day-1 working version: auth, modules, questions, live hosting flow, admin panel, activity logs, PDF reports + charts