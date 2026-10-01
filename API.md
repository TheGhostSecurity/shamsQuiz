# ShamsQuiz Mobile API

REST + WebSocket backend for the Android app. It lives in the `mobileapi` Django
app and is mounted at `/api/v1/`. The server-rendered web app is untouched and
keeps using its own cookie-based pages — the two frontends only share the
database and the models in `quiz/`.

## Running it

```bash
pip install -r requirements.txt
python manage.py migrate
daphne -b 0.0.0.0 -p 8000 shamsquiz.asgi:application
```

`daphne` serves both the normal Django views and the WebSocket endpoint. The web
app also still runs fine under Apache + mod_wsgi via `shamsquiz.wsgi`; the ASGI
process is only required for WebSockets.

Settings can be overridden with environment variables:

| Variable | Default | Notes |
| --- | --- | --- |
| `DJANGO_SECRET_KEY` | insecure dev key | set in production |
| `DJANGO_DEBUG` | `True` | set `False` in production |
| `DJANGO_ALLOWED_HOSTS` | `localhost,127.0.0.1,testserver` | comma separated |
| `REDIS_HOST` / `REDIS_PORT` | `127.0.0.1` / `6379` | channel layer when `DEBUG=False` |

`DEBUG=True` uses an in-memory channel layer (fine for development and tests).
`DEBUG=False` uses `channels_redis`, so run Redis in production.

## Response shape

Every REST response has `ok` at the top level.

Success:

```json
{ "ok": true, "...": "endpoint specific fields" }
```

Failure:

```json
{
  "ok": false,
  "error": "nickname: That name is taken here. Pick another.",
  "fields": { "nickname": ["That name is taken here. Pick another."] }
}
```

`fields` maps a form field to its messages, so the app can highlight the right
input. `error` is a human-readable summary suitable for a snackbar.

Common status codes: `400` validation, `401` no/invalid JWT, `403` wrong role or
not joined, `404` unknown quiz code, `409` already answered.

## Authentication

Two independent mechanisms:

- **JWT** — for account-level endpoints. Send `Authorization: Bearer <access>`.
  Access tokens last 12 h, refresh tokens 30 days and rotate on refresh.
- **Quiz ticket** — for live play. After joining, the server returns an opaque
  `ticket`. Send it as `X-Quiz-Ticket: <ticket>`. Tickets identify a player
  inside one quiz, survive restarts, and let a phone reconnect mid-quiz without
  a valid JWT.

Both are accepted on the live-play endpoints, so a dropped connection can be
recovered from either.

## Endpoints

### `POST /api/v1/auth/register/`

Public. Creates a student account.

```bash
curl -X POST http://127.0.0.1:8000/api/v1/auth/register/ \
  -H 'Content-Type: application/json' \
  -d '{"username":"amina","password":"Quizpass123!","password_confirm":"Quizpass123!","first_name":"Amina","email":"amina@example.com"}'
```

```json
{
  "ok": true,
  "tokens": { "access": "...", "refresh": "..." },
  "user": {
    "id": 1, "username": "amina", "first_name": "Amina", "last_name": "",
    "email": "amina@example.com", "phone": "", "role": "student",
    "display_name": "Amina", "initials": "AM", "date_joined": "..."
  }
}
```

Usernames are unique and case-insensitive; emails are unique and case-insensitive
when set. Passwords go through Django's validators.

### `POST /api/v1/auth/login/`

Public. `username` accepts a username **or** an email.

```json
{ "username": "amina", "password": "Quizpass123!" }
```

Returns the same shape as `register`. Archived or deactivated accounts are
rejected.

### `POST /api/v1/auth/refresh/`

Public. Body `{"refresh": "..."}`, returns a fresh `access` (and `refresh`,
since rotation is on).

### `GET /api/v1/auth/me/` · `PATCH /api/v1/auth/me/`

`GET` returns `{"ok": true, "user": {...}}`. `PATCH` accepts any of
`first_name`, `last_name`, `email`, `phone`, `whatsapp`, `telegram`,
`facebook`, `instagram`, `youtube`, `tiktok`, `website`.

### `POST /api/v1/auth/password/`

`{"current_password": "...", "new_password": "..."}`.

### `GET /api/v1/home/`

The app's landing payload.

```json
{
  "ok": true,
  "user": { "...": "..." },
  "stats": {
    "quizzes_played": 3, "questions_answered": 30, "correct_answers": 21,
    "accuracy": 70, "best_score": 7420, "total_score": 15980
  },
  "live_quizzes": [
    { "code": "87IF87", "module_title": "Networking Basics", "host_name": "Mr Juma",
      "status": "waiting", "participant_count": 12 }
  ],
  "my_sessions": [
    { "code": "87IF87", "module_title": "Networking Basics", "host_name": "Mr Juma",
      "played_at": "...", "status": "ended", "score": 7420, "rank": 1,
      "total_players": 24, "answered": 10, "correct": 8, "accuracy": 80 }
  ]
}
```

### `GET /api/v1/modules/`

Student-only list of modules that have active questions.

### `GET /api/v1/progress/`

Student-only. Pure JSON — deliberately **no** matplotlib images, unlike the web
page which renders charts server-side.

```json
{
  "ok": true,
  "stats": {
    "quizzes_ended": 3, "quizzes_joined": 5, "total_points": 15980,
    "correct": 21, "answered": 30, "accuracy": 70,
    "best_score": 7420, "average_score": 5327
  },
  "modules": [ { "title": "Networking Basics", "quizzes": 2, "correct": 14,
                 "attempted": 20, "accuracy": 70 } ],
  "history": [ { "code": "87IF87", "module_title": "...", "host_name": "...",
                 "status": "ended", "score": 7420, "rank": 1, "total_players": 24,
                 "correct": 8, "attempted": 10, "accuracy": 80,
                 "played_at": "..." } ],
  "trend": [ { "label": "Sep 26", "score": 7420 } ]
}
```

### `GET /api/v1/utils/`

Student-only revision material uploaded by teachers. Optional `?teacher=<id>`.

```json
{
  "ok": true,
  "teachers": [ { "id": 2, "name": "Mr Juma", "file_count": 3 } ],
  "selected_teacher": { "id": 2, "name": "Mr Juma", "file_count": 3 },
  "files": [ { "id": 1, "title": "Chapter 1 Notes", "description": "",
               "category": "book", "category_label": "Book (PDF)",
               "filename": "chapter1.pdf",
               "file_url": "http://host/media/utils/2026/09/chapter1.pdf",
               "file_size": 245760, "teacher_name": "Mr Juma",
               "created_at": "..." } ]
}
```

### `POST /api/v1/quiz/join/`

```json
{ "code": "87IF87", "nickname": "Amina", "team": "red" }
```

`team` is only sent when the quiz has teams enabled. Rejects unknown codes,
ended quizzes, names already taken in that quiz, and names under 2 characters.
Joining twice with the same account reuses the existing participant.

```json
{
  "ok": true,
  "ticket": "Pi9WzLYNGZ...",
  "participant": { "id": 3, "name": "Amina", "team": "", "score": 0 },
  "state": { "...": "full session state, see below" }
}
```

### `GET /api/v1/quiz/<code>/state/`

Works with a JWT or a ticket, or with neither (anonymous viewer). This is the
same payload the WebSocket pushes, and is what you poll as a fallback.

```json
{
  "ok": true,
  "joined": true,
  "state": {
    "code": "87IF87", "module_title": "Networking Basics", "host_name": "Mr Juma",
    "status": "question", "paused": false, "teams_enabled": false,
    "current_index": 2, "total_questions": 10,
    "seconds_remaining": 14, "question_ends_at": "...", "ended_at": null,
    "question": {
      "id": 7, "index": 2, "text": "Which layer routes packets?",
      "time_limit": 20,
      "choices": [
        { "id": 31, "text": "Network", "letter": "A", "is_correct": null },
        { "id": 32, "text": "Data link", "letter": "B", "is_correct": null }
      ]
    },
    "participant": { "id": 3, "name": "Amina", "team": "", "score": 4820,
                     "has_answered": false },
    "my_answer": null,
    "leaderboard": [ { "id": 3, "name": "Amina", "team": "", "team_label": "",
                       "score": 4820, "rank": 1, "correct": 5, "answered": 6,
                       "accuracy": 83 } ],
    "teams": []
  }
}
```

Important details:

- `status` is one of `waiting`, `question`, `reveal`, `ended`.
- `question.choices[].is_correct` is `null` while answering and only filled in at
  `reveal`. The server decides when to reveal, not the client.
- Choice **order is shuffled per participant** using a stable seed, so it does
  not reshuffle between polls or reconnects, and the same player sees the same
  order every time.
- `leaderboard` is the top 5 while playing, the full list once `ended`.
- Requesting state after the timer expires advances the session to `reveal` and
  returns the updated status.

### `POST /api/v1/quiz/<code>/answer/`

Needs a ticket (or a JWT belonging to a joined participant).

```json
{ "choice_id": 31 }
```

```json
{
  "ok": true,
  "result": { "ok": true, "question_id": 7, "choice_id": 31, "correct": true,
              "points": 812, "total_score": 5632 },
  "score": 5632
}
```

Scoring is identical to the web app: a correct answer is worth
`round(1000 × (time_limit − elapsed) / time_limit)`, so answering instantly gives
the full 1,000 and answering late gives close to zero. A wrong answer gives 0.

Returns `409` if the question was already answered, `400` if the choice does not
belong to the current question or the quiz is not accepting answers.

### `GET /api/v1/quiz/<code>/scoreboard/`

```json
{
  "ok": true, "code": "87IF87", "module_title": "Networking Basics",
  "status": "ended",
  "leaderboard": [ { "id": 3, "name": "Amina", "team": "", "team_label": "",
                     "score": 7420, "rank": 1, "correct": 8, "answered": 10,
                     "accuracy": 80 } ],
  "teams": [ { "team": "red", "label": "Red", "score": 15200, "rank": 1 } ],
  "me": { "id": 3, "name": "Amina", "...": "..." }
}
```

`me` is the caller's own row, or `null` if they are not in this quiz.

## WebSocket

```
ws://<host>:8000/ws/quiz/<code>/?token=<jwt>&ticket=<ticket>
```

Both query params are optional and can be combined. Send the JWT so the player is
linked to their account; send the ticket to resume an existing play. A bad or
expired token is ignored rather than rejected, so the socket still opens as a
guest.

Client messages:

```json
{ "action": "join", "nickname": "Amina", "team": "red" }
{ "action": "answer", "choice_id": 31 }
{ "action": "state" }
{ "action": "ping" }
```

Server messages, all shaped `{"event": "...", ...}`:

| Event | Payload | When |
| --- | --- | --- |
| `state` | `state` (same shape as REST) | on connect, after join, on demand |
| `ticket` | `ticket` | after join — persist this |
| `tick` | `tick` (lightweight) | about once a second while connected |
| `answered` | `result` | your answer was accepted |
| `answer_rejected` | `error` | wrong question, already answered, too late |
| `leaderboard` | `leaderboard`, `teams` | after you answer |
| `reveal` | — | the timer ran out; fetch fresh state |
| `error` | `error` | bad action, name taken, not joined |
| `pong` | — | reply to `ping` |

`tick` is deliberately small:

```json
{ "event": "tick",
  "tick": { "status": "question", "paused": false, "current_index": 2,
            "total_questions": 10, "seconds_remaining": 14 } }
```

Drive the countdown from `tick.seconds_remaining` rather than trusting a local
timer, so the phone stays in sync with the server. Full question and leaderboard
payloads are only sent when they actually change.

One ticker task runs per quiz code and is shared by every connected player, so a
classroom of 40 costs one query per second, not 40. It stops when the last player
disconnects.

Close codes: `4404` unknown or already-ended quiz.

## Tests

```bash
python manage.py test              # whole project
python manage.py test mobileapi    # API + WebSocket only
```

91 tests: 28 pre-existing web tests (unchanged), 44 API tests, 19 WebSocket
tests.
