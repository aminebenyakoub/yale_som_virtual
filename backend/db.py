"""Queries over data/yale_som.db, shared by the HTTP routes and the professor agents' tools."""

import re
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "yale_som.db"

SUMMARY_COLS = (
    "id, course_number, course_title, course_category, course_session, section, "
    "faculty_1 AS faculty, daytimes, room, units"
)
DETAIL_COLS = SUMMARY_COLS + (
    ", course_id, course_type, course_description, faculty_bio, timings_day, "
    "timings_start, timings_end, term_code, syllabus, old_syllabus"
)


def connect() -> sqlite3.Connection:
    # mode=ro: nothing in this app can change the catalog
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def clean(row: sqlite3.Row) -> dict:
    # the export has NULLs and stray whitespace; callers always get trimmed strings
    return {k: (v.strip() if isinstance(v, str) else ("" if v is None else v)) for k, v in dict(row).items()}


def room_name(room: str) -> str:
    """Accept "2400" as shorthand for "EVANS 2400", the walkthrough's room ids."""
    room = room.strip().upper()
    return f"EVANS {room}" if room.isdigit() else room


def slugify(faculty: str) -> str:
    """"Zaman, Tauhid" -> "tauhid-zaman"."""
    last, _, first = faculty.partition(",")
    return re.sub(r"[^a-z0-9]+", "-", f"{first} {last}".lower()).strip("-")


def display_name(faculty: str) -> str:
    """"Zaman, Tauhid" -> "Tauhid Zaman"."""
    last, _, first = faculty.partition(",")
    return f"{first.strip()} {last.strip()}".strip()


def count_courses(db: sqlite3.Connection) -> int:
    return db.execute("SELECT count(*) FROM courses").fetchone()[0]


def search_courses(
    db: sqlite3.Connection,
    q: str | None = None,
    category: str | None = None,
    session: str | None = None,
    room: str | None = None,
    day: str | None = None,
    faculty: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[int, list[dict]]:
    where, args = [], []
    if q:
        where.append(
            "(course_title LIKE ? OR course_number LIKE ? OR course_description LIKE ? OR faculty_1 LIKE ?)"
        )
        args += [f"%{q}%"] * 4
    if category:
        where.append("trim(course_category) = ? COLLATE NOCASE")
        args.append(category.strip())
    if session:
        where.append("course_session = ? COLLATE NOCASE")
        args.append(session)
    if room:
        where.append("room = ? COLLATE NOCASE")
        args.append(room_name(room))
    if day:
        where.append("timings_day LIKE ?")
        args.append(f"%{day[:2].title()}%")
    if faculty:
        where.append("faculty_1 LIKE ?")
        args.append(f"%{faculty}%")
    sql_where = f"WHERE {' AND '.join(where)}" if where else ""

    total = db.execute(f"SELECT count(*) FROM courses {sql_where}", args).fetchone()[0]
    rows = db.execute(
        f"SELECT {SUMMARY_COLS} FROM courses {sql_where} "
        "ORDER BY course_number, section, id LIMIT ? OFFSET ?",
        [*args, limit, offset],
    ).fetchall()
    return total, [clean(r) for r in rows]


def get_course(db: sqlite3.Connection, course_pk: int) -> dict | None:
    row = db.execute(f"SELECT {DETAIL_COLS} FROM courses WHERE id = ?", [course_pk]).fetchone()
    return clean(row) if row else None


def categories(db: sqlite3.Connection) -> list[dict]:
    rows = db.execute(
        "SELECT trim(course_category) AS name, count(*) AS count FROM courses "
        "WHERE trim(coalesce(course_category, '')) <> '' GROUP BY 1 ORDER BY count DESC, name"
    ).fetchall()
    return [dict(r) for r in rows]


def rooms(db: sqlite3.Connection) -> list[dict]:
    rows = db.execute(
        "SELECT trim(room) AS name, count(*) AS count FROM courses "
        "WHERE trim(coalesce(room, '')) <> '' GROUP BY 1 ORDER BY name"
    ).fetchall()
    return [dict(r) for r in rows]


def room_courses(db: sqlite3.Connection, room: str) -> list[dict]:
    rows = db.execute(
        f"SELECT {SUMMARY_COLS} FROM courses WHERE room = ? COLLATE NOCASE "
        "ORDER BY timings_day, timings_start, course_number",
        [room_name(room)],
    ).fetchall()
    return [clean(r) for r in rows]


def faculty(db: sqlite3.Connection) -> list[dict]:
    rows = db.execute(
        "SELECT trim(faculty_1) AS name, group_concat(DISTINCT course_number) AS courses FROM courses "
        "WHERE trim(coalesce(faculty_1, '')) <> '' GROUP BY 1 ORDER BY name"
    ).fetchall()
    return [{"name": r["name"], "courses": sorted(r["courses"].split(","))} for r in rows]


def professor(db: sqlite3.Connection, slug: str) -> dict | None:
    """Everything the catalog knows about one faculty member, looked up by slug."""
    for f in faculty(db):
        if slugify(f["name"]) == slug:
            break
    else:
        return None
    rows = db.execute(
        "SELECT id, course_number, course_title, course_category, course_description, faculty_bio, "
        "daytimes, room, course_session, syllabus FROM courses WHERE trim(faculty_1) = ? ORDER BY course_number, id",
        [f["name"]],
    ).fetchall()
    sections = [clean(r) for r in rows]
    courses: dict[str, dict] = {}
    for s in sections:
        c = courses.setdefault(
            s["course_number"],
            {
                "course_number": s["course_number"],
                "course_title": s["course_title"],
                "course_category": s["course_category"],
                "course_description": s["course_description"],
                "syllabus": s["syllabus"],
                "meetings": [],
            },
        )
        when = " ".join(x for x in (s["daytimes"], s["room"], f"({s['course_session']})") if x)
        c["meetings"].append({"id": s["id"], "when": when})
    bio = next((s["faculty_bio"] for s in sections if s["faculty_bio"]), "")
    return {
        "slug": slug,
        "name": display_name(f["name"]),
        "catalog_name": f["name"],
        "bio": bio,
        "courses": list(courses.values()),
    }
