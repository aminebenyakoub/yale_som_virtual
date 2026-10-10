"""API over the Yale SOM Fall 2026 course catalog in data/yale_som.db, plus chat with professor agents.

Run from this folder:  uvicorn main:app --reload   → docs at http://127.0.0.1:8000/docs
"""

import sqlite3
from collections.abc import Iterator
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

import db
import professors

app = FastAPI(
    title="Yale SOM Courses API",
    description="Fall 2026 course catalog behind the Evans Hall walkthrough, and its AI professors.",
    version="0.2.0",
)

# The React app runs on Vite's dev server locally and on GitHub Pages when deployed.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "https://aminebenyakoub.github.io",
    ],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


def get_db() -> Iterator[sqlite3.Connection]:
    conn = db.connect()
    try:
        yield conn
    finally:
        conn.close()


# ---------- response models


class CourseSummary(BaseModel):
    id: int
    course_number: str
    course_title: str
    course_category: str
    course_session: str
    section: str
    faculty: str
    daytimes: str
    room: str
    units: str


class Course(CourseSummary):
    course_id: str
    course_type: str
    course_description: str
    faculty_bio: str
    timings_day: str
    timings_start: str
    timings_end: str
    term_code: str
    syllabus: str
    old_syllabus: str


class CourseList(BaseModel):
    total: int
    limit: int
    offset: int
    courses: list[CourseSummary]


class Count(BaseModel):
    name: str
    count: int


class Faculty(BaseModel):
    name: str
    courses: list[str]


class ProfessorCard(BaseModel):
    slug: str
    name: str
    courses: list[str]
    has_style: bool


class Professor(BaseModel):
    slug: str
    name: str
    bio: str
    greeting: str
    courses: list[dict]


class Message(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)


class ChatRequest(BaseModel):
    messages: list[Message] = Field(min_length=1, max_length=40)


class ChatReply(BaseModel):
    reply: str
    tools_used: list[str]


# ---------- catalog routes


@app.get("/api/health")
def health(conn: sqlite3.Connection = Depends(get_db)):
    return {"status": "ok", "courses": db.count_courses(conn)}


@app.get("/api/courses", response_model=CourseList)
def list_courses(
    q: str | None = Query(None, description="Search title, number, description and faculty"),
    category: str | None = Query(None, description="e.g. Finance, Core, Artificial Intelligence"),
    session: str | None = Query(None, description="fall, fall-1 or fall-2"),
    room: str | None = Query(None, description='"EVANS 2400" or just "2400"'),
    day: str | None = Query(None, description="Mo, Tu, We, Th or Fr"),
    faculty: str | None = Query(None, description="Part of a faculty name"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    conn: sqlite3.Connection = Depends(get_db),
):
    total, rows = db.search_courses(conn, q, category, session, room, day, faculty, limit, offset)
    return {"total": total, "limit": limit, "offset": offset, "courses": rows}


@app.get("/api/courses/{course_pk}", response_model=Course)
def get_course(course_pk: int, conn: sqlite3.Connection = Depends(get_db)):
    course = db.get_course(conn, course_pk)
    if course is None:
        raise HTTPException(404, f"No course with id {course_pk}")
    return course


@app.get("/api/categories", response_model=list[Count])
def categories(conn: sqlite3.Connection = Depends(get_db)):
    return db.categories(conn)


@app.get("/api/rooms", response_model=list[Count])
def rooms(conn: sqlite3.Connection = Depends(get_db)):
    return db.rooms(conn)


@app.get("/api/rooms/{room}/courses", response_model=list[CourseSummary])
def room_courses(room: str, conn: sqlite3.Connection = Depends(get_db)):
    rows = db.room_courses(conn, room)
    if not rows:
        raise HTTPException(404, f"No courses scheduled in {db.room_name(room)}")
    return rows


@app.get("/api/faculty", response_model=list[Faculty])
def faculty(conn: sqlite3.Connection = Depends(get_db)):
    return db.faculty(conn)


# ---------- professor agents


def load_professor(slug: str, conn: sqlite3.Connection) -> dict:
    p = db.professor(conn, slug)
    if p is None:
        raise HTTPException(404, f"No professor {slug!r} in the catalog")
    return p


@app.get("/api/professors", response_model=list[ProfessorCard])
def list_professors(conn: sqlite3.Connection = Depends(get_db)):
    return [
        {
            "slug": db.slugify(f["name"]),
            "name": db.display_name(f["name"]),
            "courses": f["courses"],
            "has_style": db.slugify(f["name"]) in professors.STYLES,
        }
        for f in db.faculty(conn)
    ]


@app.get("/api/professors/{slug}", response_model=Professor)
def get_professor(slug: str, conn: sqlite3.Connection = Depends(get_db)):
    p = load_professor(slug, conn)
    greeting = professors.STYLES.get(slug, {}).get("greeting", f"Hello! I'm Professor {p['name'].split()[-1]}. How can I help?")
    return {**p, "greeting": greeting}


@app.post("/api/professors/{slug}/chat", response_model=ChatReply)
def chat(slug: str, body: ChatRequest, conn: sqlite3.Connection = Depends(get_db)):
    # plain def: FastAPI runs it in a worker thread, so a slow model call doesn't block other requests
    p = load_professor(slug, conn)
    if body.messages[-1].role != "user":
        raise HTTPException(422, "The last message must be from the user")
    try:
        return professors.chat(p, [m.model_dump() for m in body.messages])
    except RuntimeError as e:  # missing key
        raise HTTPException(503, str(e))
    except Exception as e:
        raise HTTPException(502, f"The model call failed: {e}")
