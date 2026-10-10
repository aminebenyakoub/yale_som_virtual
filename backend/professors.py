"""Professor agents: every faculty member in the catalog can be chatted with.

Each agent's system prompt is built from the database (bio, courses, descriptions, meeting times)
plus a speaking style from STYLES. Agents answer questions about their own material from the model's
own knowledge, and look up anything about the catalog (other courses, other professors, rooms, times)
with tools so they never make it up.

The model runs through Portkey's OpenAI-compatible gateway using the Responses API: Azure behind
Portkey rejects tool calls on /chat/completions for these models.
"""

import json
import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

import db

HERE = Path(__file__).resolve().parent
# Closest .env wins: backend/, then the repo root, then the class folder that holds the repo.
# override=True: a stale PORTKEY_API_KEY exported in the shell profile must not shadow the .env one.
for env in (HERE / ".env", HERE.parent / ".env", HERE.parent.parent / ".env"):
    if env.exists():
        load_dotenv(env, override=True)
        break

PORTKEY_BASE_URL = "https://api.portkey.ai/v1"
MODEL = os.getenv("PROFESSOR_MODEL", "gpt-5.6-luna")  # cheapest tier that handles tools well
MAX_TOOL_ROUNDS = 6

_client: OpenAI | None = None


def client() -> OpenAI:
    global _client
    if _client is None:
        key = os.environ.get("PORTKEY_API_KEY")
        if not key:
            raise RuntimeError("PORTKEY_API_KEY is missing. Put it in a .env next to the repo.")
        _client = OpenAI(base_url=PORTKEY_BASE_URL, api_key=key, default_headers={"x-portkey-api-key": key})
    return _client


# ---------- personalities

# Speaking styles keyed by slug. Professors without one get DEFAULT_STYLE.
STYLES = {
    "tauhid-zaman": {
        "style": (
            "You are the cool professor. You say \"yo\" all the time: open most replies with \"Yo\" and drop it "
            "in mid-sentence too. You wear hoodies, and you are a big Labubu fan; you reach for Labubus as "
            "examples when they fit (Labubu resale prices, blind-box odds, Labubu demand forecasting). You are "
            "Bangladeshi and proud of it, and it comes through now and then (cricket, food, Dhaka), never forced. "
            "Relaxed, hype, encouraging energy, but you are still a stickler for precise terms."
        ),
        "greeting": "Yo! Welcome to MGT 409. What's up, what do you wanna know?",
    },
}
DEFAULT_STYLE = "Warm, articulate, and professorial, with dry academic humor."

# Core topics per catalog category, so every agent knows the canon of its field even when the
# catalog description is thin.
CANON = {
    "Economics": "supply and demand, elasticity, marginal analysis, game theory, OLS regression and its "
    "assumptions, the central limit theorem, multivariate regression, omitted-variable bias, causal inference",
    "Core": "the core MBA toolkit for the course: frameworks, the key quantitative methods, and the "
    "managerial judgement for applying them",
    "Finance": "time value of money, NPV and IRR, CAPM and beta, the Modigliani-Miller theorems, WACC, "
    "options pricing, portfolio theory, market efficiency",
    "Accounting": "the three financial statements, accrual vs cash accounting, revenue recognition, "
    "ratio analysis, earnings quality",
    "Marketing": "segmentation, targeting and positioning, customer lifetime value, conjoint analysis, "
    "pricing, brand equity",
    "Operations": "queueing theory, Little's law, inventory models (EOQ, newsvendor), capacity, "
    "supply-chain coordination, optimization",
    "Organizational Behavior": "motivation, team dynamics, power and influence, decision biases, "
    "negotiation, organizational culture",
    "Artificial Intelligence": "machine learning basics, overfitting and validation, large language "
    "models, prompting, embeddings, agents and tool use, AI strategy",
    "Strategy": "Porter's five forces, competitive advantage, the resource-based view, platform strategy",
    "PhD": "the research methods and theory of the field at doctoral depth: identification, estimation, "
    "proofs and the canonical papers",
}


def system_prompt(p: dict) -> str:
    style = STYLES.get(p["slug"], {}).get("style", DEFAULT_STYLE)
    courses = []
    categories = []
    for c in p["courses"]:
        categories.append(c["course_category"])
        meetings = "; ".join(m["when"] for m in c["meetings"] if m["when"]) or "time TBA"
        courses.append(
            f"- {c['course_number']} {c['course_title']} [{c['course_category'] or 'uncategorized'}]\n"
            f"  Meets: {meetings}\n"
            f"  Description: {c['course_description'] or '(none in catalog)'}"
        )
    canon = "\n".join(f"- {cat}: {CANON[cat]}" for cat in dict.fromkeys(categories) if cat in CANON)
    return f"""You are Professor {p['name']} of the Yale School of Management, a character in a 3D walk-through \
of Evans Hall. A student has walked up to you and is talking to you.

## Your bio (from the course catalog)
{p['bio'] or '(No bio in the catalog.)'}

## What you teach in Fall 2026
{chr(10).join(courses)}

## Your expertise
You know the material of your courses thoroughly: the theory, the math, the standard examples and the \
common mistakes. Teach it when asked, accurately and concretely.
{('Canon of your field:' + chr(10) + canon) if canon else ''}

## Personality
You are pedantic. When the student uses a term loosely, correct it precisely before you answer \
(correlation is not causation; a p-value is not the probability the null is true; revenue is not profit). \
You care about definitions and assumptions. Stay kind and helpful while doing it.

## Speaking style
{style}

## Facts about courses
You can search the Fall 2026 Yale SOM catalog with your tools: any course, professor, room, meeting time or \
category. Always use a tool before stating catalog facts (course numbers, titles, times, rooms, who teaches \
what) other than the ones listed above, and never invent them. If the catalog has no answer, say so.

## Format
Your words appear in a chat bubble and are read aloud, so talk like a person: 2 to 5 short sentences, no \
markdown, no bullet lists, no headings. Write math in plain words or simple inline notation. Go longer only \
when the student asks you to explain or derive something in detail.

## Boundaries
You are an AI portrayal of this professor, not the real person. Do not invent private details about their \
life, grading decisions or course policies beyond what is above; point the student to the syllabus or the \
real professor instead."""


# ---------- tools

TOOLS = [
    {
        "type": "function",
        "name": "search_courses",
        "description": "Search the Fall 2026 Yale SOM course catalog. All filters are optional and combine with AND. "
        "Returns matching course sections (number, title, category, faculty, meeting time, room).",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Words to match in title, course number, description or faculty"},
                "category": {"type": "string", "description": "Exact category, e.g. Finance, Economics, Core, Artificial Intelligence"},
                "faculty": {"type": "string", "description": "Part of a professor's name"},
                "day": {"type": "string", "description": "Mo, Tu, We, Th or Fr"},
                "room": {"type": "string", "description": "Room like 'EVANS 2400' or just '2400'"},
            },
        },
    },
    {
        "type": "function",
        "name": "get_course_details",
        "description": "Full catalog entry for one course section by its id (from search_courses): description, "
        "faculty bio, schedule and syllabus link.",
        "parameters": {
            "type": "object",
            "properties": {"course_id": {"type": "integer"}},
            "required": ["course_id"],
        },
    },
    {
        "type": "function",
        "name": "get_professor",
        "description": "Look up another professor by (part of) their name: their bio and every course they teach.",
        "parameters": {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        },
    },
    {
        "type": "function",
        "name": "list_categories",
        "description": "All course categories in the catalog with how many sections each has.",
        "parameters": {"type": "object", "properties": {}},
    },
]


def run_tool(name: str, args: dict) -> object:
    conn = db.connect()
    try:
        if name == "search_courses":
            total, rows = db.search_courses(
                conn,
                q=args.get("query") or None,
                category=args.get("category") or None,
                faculty=args.get("faculty") or None,
                day=args.get("day") or None,
                room=args.get("room") or None,
                limit=20,
            )
            return {"total_matches": total, "showing": len(rows), "sections": rows}
        if name == "get_course_details":
            return db.get_course(conn, int(args["course_id"])) or {"error": "No course with that id"}
        if name == "get_professor":
            needle = args["name"].lower()
            matches = [f for f in db.faculty(conn) if all(part in f["name"].lower() for part in needle.replace(",", " ").split())]
            if not matches:
                return {"error": f"No professor matching {args['name']!r} in the catalog"}
            if len(matches) > 1:
                return {"ambiguous": [m["name"] for m in matches]}
            info = db.professor(conn, db.slugify(matches[0]["name"]))
            for c in info["courses"]:  # keep tool output short; get_course_details has the full text
                c["course_description"] = c["course_description"][:400]
            return info
        if name == "list_categories":
            return db.categories(conn)
        return {"error": f"Unknown tool {name}"}
    except Exception as e:  # a bad argument should come back to the model, not crash the chat
        return {"error": str(e)}
    finally:
        conn.close()


# ---------- chat


def chat(p: dict, messages: list[dict]) -> dict:
    """One student turn. `messages` is the whole conversation so far as [{role, content}]."""
    items: list = [{"role": m["role"], "content": m["content"]} for m in messages]
    used: list[str] = []
    for _ in range(MAX_TOOL_ROUNDS):
        r = client().responses.create(
            model=MODEL,
            instructions=system_prompt(p),
            input=items,
            tools=TOOLS,
            store=False,
            include=["reasoning.encrypted_content"],  # lets reasoning carry across tool rounds without server state
        )
        calls = [o for o in r.output if o.type == "function_call"]
        if not calls:
            return {"reply": r.output_text.strip(), "tools_used": used}
        items += [o.model_dump(exclude_none=True) for o in r.output]
        for call in calls:
            result = run_tool(call.name, json.loads(call.arguments or "{}"))
            used.append(call.name)
            items.append({"type": "function_call_output", "call_id": call.call_id, "output": json.dumps(result)})
    return {"reply": "Hmm, I went down a rabbit hole in the catalog there. Ask me that again?", "tools_used": used}
