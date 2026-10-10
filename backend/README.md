# Courses API + AI professors (FastAPI)

Read-only API over `../data/yale_som.db`, the Yale SOM Fall 2026 course catalog (234 sections), plus a chat
endpoint where every professor in the catalog is an AI agent.

## AI professors

`professors.py` builds each professor's system prompt from the catalog (bio, courses, descriptions, meeting
times) plus a speaking style from `STYLES`. They're pedantic, know their field's material, and use tools
(`search_courses`, `get_course_details`, `get_professor`, `list_categories`) to look anything up in the
catalog instead of making it up.

- Model: `gpt-5.6-luna` through Portkey (override with `PROFESSOR_MODEL`).
- Key: `PORTKEY_API_KEY` from the first `.env` found in `backend/`, the repo root, or the folder holding the
  repo. The `.env` value wins over the shell's.
- Add a style: add an entry to `STYLES` keyed by slug (`"Zaman, Tauhid"` → `tauhid-zaman`).
- In the 3D app, walk up to Prof. Zaman in room 2400 and press **E** (or tap **Talk**).

## Run it

```bash
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

Interactive docs: http://127.0.0.1:8000/docs

## Endpoints

| Route | What it returns |
|---|---|
| `GET /api/health` | `{"status": "ok", "courses": 234}` |
| `GET /api/courses` | Paged list. Filters: `q`, `category`, `session`, `room`, `day`, `faculty`, `limit`, `offset` |
| `GET /api/courses/{id}` | One section with description, bio, timings and syllabus links |
| `GET /api/categories` | Categories with section counts |
| `GET /api/rooms` | Rooms with section counts |
| `GET /api/rooms/{room}/courses` | Everything taught in a room; `2400` works as shorthand for `EVANS 2400` |
| `GET /api/faculty` | Each faculty member and the course numbers they teach |
| `GET /api/professors` | Every professor as a chat agent (slug, name, courses) |
| `GET /api/professors/{slug}` | Bio, courses and greeting |
| `POST /api/professors/{slug}/chat` | `{"messages": [{"role": "user", "content": "..."}]}` → `{"reply", "tools_used"}` |

Examples:

```bash
curl "http://127.0.0.1:8000/api/courses?category=Finance&day=Tu"
curl "http://127.0.0.1:8000/api/rooms/2400/courses"
```

CORS allows the Vite dev server (`localhost:5173`) and `aminebenyakoub.github.io`.

## Test

```bash
.venv/bin/python -m pytest -q
```
