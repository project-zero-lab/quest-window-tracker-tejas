# QUEST WINDOW — COMPLETE SINGLE-FILE VERSION
# All app pages are included in this one Python file.
#
# To run:
#   1. Install Python and Streamlit:  pip install streamlit
#   2. Run this file:                 streamlit run app.py
#
# Note: Streamlit must be installed on the device/server where the app runs.
# This file is the complete app code; it does not include the Streamlit library.
#
"""
QUEST WINDOW — Streamlit Edition
================================

A beginner-friendly quest and productivity tracker.

Features
--------
1. Player registration
2. Home dashboard with summary metrics and progress
3. One-time tasks
4. Daily quests
5. Mark tasks as complete / pending
6. Edit and delete quests
7. Quest filtering and search
8. Player profile editing
9. XP, levels, and streak-style daily completion statistics
10. Session-only storage by default
11. Optional SQLite persistence for quests and profile
12. Export quest data as JSON and CSV
13. Import a JSON backup
14. Responsive Streamlit layout
15. Helpful validation and clear messages

Important notes
---------------
- By default, data is stored in Streamlit session state. It is not guaranteed
  to survive a browser refresh, a lost session, or a server restart.
- To enable SQLite persistence, set QUEST_WINDOW_USE_SQLITE=1 in your
  environment before running the app. SQLite writes to quest_window.db in the
  current working directory. On Streamlit Community Cloud this file does not
  persist across reboots/redeploys, so leave this off for a hosted deploy.
- This is a personal starter app, not a secure multi-user production service.
  Do not use it to store sensitive information.
"""

from __future__ import annotations

import csv
import io
import json
import os
import sqlite3
from datetime import date, datetime
from typing import Any

import streamlit as st


# =============================================================================
# PAGE CONFIGURATION
# =============================================================================

st.set_page_config(
    page_title="Quest Window",
    page_icon="⚔️",
    layout="wide",
    initial_sidebar_state="expanded",
)


# =============================================================================
# CONSTANTS
# =============================================================================

APP_VERSION = "2.0.1"
DB_PATH = os.environ.get("QUEST_WINDOW_DB_PATH", "quest_window.db")
USE_SQLITE = os.environ.get("QUEST_WINDOW_USE_SQLITE", "0").strip() == "1"

QUEST_TYPES = {
    "one_time_tasks": "One-Time Task",
    "daily_quests": "Daily Quest",
}

NAVIGATION = [
    "🏠 Home",
    "📜 Make Quests",
    "📋 Quest List",
    "📊 Status Window",
    "👤 Profile",
    "💾 Backup & Data",
    "ℹ️ Help",
]


# =============================================================================
# GENERAL HELPERS
# =============================================================================

def now_iso() -> str:
    """Return the current local date/time in ISO format."""
    return datetime.now().isoformat(timespec="seconds")


def today_iso() -> str:
    """Return today's local date in ISO format."""
    return date.today().isoformat()


def clean_text(value: Any) -> str:
    """Convert a value to a trimmed string safely."""
    return str(value if value is not None else "").strip()


def make_quest_id() -> str:
    """Generate a unique-enough ID for a personal single-user app."""
    return datetime.now().strftime("%Y%m%d%H%M%S%f")


def safe_int(value: Any, default: int = 0) -> int:
    """Convert a value to an integer, falling back to default."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def init_session_state() -> None:
    """Initialize all app state keys if they do not already exist."""
    defaults = {
        "registered": False,
        "information": {"name": "", "age": 16, "created_at": now_iso()},
        "one_time_tasks": [],
        "daily_quests": [],
        "selected_page": "🏠 Home",
        "last_daily_reset": today_iso(),
        "notice": None,
        "xp": 0,
        "completion_log": [],
        "sqlite_loaded": False,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            # Use JSON round-trip to avoid sharing mutable nested defaults.
            st.session_state[key] = json.loads(json.dumps(value))


def all_quests() -> list[dict[str, Any]]:
    """Return all tasks and daily quests as a single list."""
    combined = []
    for item in st.session_state.one_time_tasks:
        combined.append({**item, "quest_type": "one_time_tasks"})
    for item in st.session_state.daily_quests:
        combined.append({**item, "quest_type": "daily_quests"})
    return combined


def count_completed(quests: list[dict[str, Any]]) -> int:
    return sum(1 for quest in quests if bool(quest.get("completed", False)))


def completion_percent(quests: list[dict[str, Any]]) -> float:
    if not quests:
        return 0.0
    return count_completed(quests) / len(quests)


def get_level(xp: int) -> int:
    """A simple progression system: each level costs 100 XP."""
    return max(1, (max(0, xp) // 100) + 1)


def xp_to_next_level(xp: int) -> int:
    next_threshold = get_level(xp) * 100
    return max(0, next_threshold - max(0, xp))


def set_notice(kind: str, message: str) -> None:
    st.session_state.notice = {"kind": kind, "message": message}


def show_notice() -> None:
    notice = st.session_state.get("notice")
    if not notice:
        return
    kind = notice.get("kind", "info")
    message = notice.get("message", "")
    if kind == "success":
        st.success(message)
    elif kind == "error":
        st.error(message)
    elif kind == "warning":
        st.warning(message)
    else:
        st.info(message)
    st.session_state.notice = None


# =============================================================================
# OPTIONAL SQLITE STORAGE
# =============================================================================

def get_db_connection() -> sqlite3.Connection:
    """Open a SQLite database and ensure the schema exists."""
    connection = sqlite3.connect(DB_PATH, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS profile (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            name TEXT NOT NULL,
            age INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            xp INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS quests (
            id TEXT PRIMARY KEY,
            quest_type TEXT NOT NULL,
            name TEXT NOT NULL,
            completed INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            completed_at TEXT,
            notes TEXT NOT NULL DEFAULT ''
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS completion_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            quest_id TEXT NOT NULL,
            quest_name TEXT NOT NULL,
            completed_at TEXT NOT NULL,
            xp_awarded INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    connection.commit()
    return connection


def load_sqlite_data() -> None:
    """Load profile, quests, and XP from SQLite once per Streamlit session."""
    if not USE_SQLITE or st.session_state.sqlite_loaded:
        return

    connection = get_db_connection()
    try:
        profile = connection.execute(
            "SELECT name, age, created_at, xp FROM profile WHERE id = 1"
        ).fetchone()

        if profile:
            st.session_state.information = {
                "name": profile["name"],
                "age": profile["age"],
                "created_at": profile["created_at"],
            }
            st.session_state.registered = bool(profile["name"])
            st.session_state.xp = safe_int(profile["xp"])

        rows = connection.execute(
            "SELECT id, quest_type, name, completed, created_at, completed_at, notes "
            "FROM quests ORDER BY created_at"
        ).fetchall()

        one_time = []
        daily = []
        for row in rows:
            quest = {
                "id": row["id"],
                "name": row["name"],
                "completed": bool(row["completed"]),
                "created_at": row["created_at"],
                "completed_at": row["completed_at"],
                "notes": row["notes"] or "",
            }
            if row["quest_type"] == "daily_quests":
                daily.append(quest)
            else:
                one_time.append(quest)

        st.session_state.one_time_tasks = one_time
        st.session_state.daily_quests = daily

        log_rows = connection.execute(
            "SELECT quest_id, quest_name, completed_at, xp_awarded "
            "FROM completion_log ORDER BY completed_at"
        ).fetchall()
        st.session_state.completion_log = [
            {
                "quest_id": row["quest_id"],
                "quest_name": row["quest_name"],
                "completed_at": row["completed_at"],
                "xp_awarded": row["xp_awarded"],
            }
            for row in log_rows
        ]
    finally:
        connection.close()

    st.session_state.sqlite_loaded = True


def save_profile_to_sqlite() -> None:
    if not USE_SQLITE:
        return
    info = st.session_state.information
    connection = get_db_connection()
    try:
        connection.execute(
            """
            INSERT INTO profile (id, name, age, created_at, xp)
            VALUES (1, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name = excluded.name,
                age = excluded.age,
                created_at = excluded.created_at,
                xp = excluded.xp
            """,
            (
                info.get("name", ""),
                safe_int(info.get("age", 16)),
                info.get("created_at", now_iso()),
                safe_int(st.session_state.xp),
            ),
        )
        connection.commit()
    finally:
        connection.close()


def save_quest_to_sqlite(quest: dict[str, Any], quest_type: str) -> None:
    if not USE_SQLITE:
        return
    connection = get_db_connection()
    try:
        connection.execute(
            """
            INSERT INTO quests
                (id, quest_type, name, completed, created_at, completed_at, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                quest_type = excluded.quest_type,
                name = excluded.name,
                completed = excluded.completed,
                created_at = excluded.created_at,
                completed_at = excluded.completed_at,
                notes = excluded.notes
            """,
            (
                quest["id"],
                quest_type,
                quest["name"],
                int(bool(quest.get("completed", False))),
                quest.get("created_at", now_iso()),
                quest.get("completed_at"),
                quest.get("notes", ""),
            ),
        )
        connection.commit()
    finally:
        connection.close()


def delete_quest_from_sqlite(quest_id: str) -> None:
    if not USE_SQLITE:
        return
    connection = get_db_connection()
    try:
        connection.execute("DELETE FROM quests WHERE id = ?", (quest_id,))
        connection.commit()
    finally:
        connection.close()


def log_completion_to_sqlite(
    quest_id: str, quest_name: str, completed_at: str, xp_awarded: int
) -> None:
    if not USE_SQLITE:
        return
    connection = get_db_connection()
    try:
        connection.execute(
            """
            INSERT INTO completion_log
                (quest_id, quest_name, completed_at, xp_awarded)
            VALUES (?, ?, ?, ?)
            """,
            (quest_id, quest_name, completed_at, xp_awarded),
        )
        connection.commit()
    finally:
        connection.close()


def clear_sqlite_data() -> None:
    if not USE_SQLITE:
        return
    connection = get_db_connection()
    try:
        connection.execute("DELETE FROM quests")
        connection.execute("DELETE FROM completion_log")
        connection.execute("DELETE FROM profile")
        connection.commit()
    finally:
        connection.close()


# =============================================================================
# QUEST MANAGEMENT
# =============================================================================

def add_quest(quest_type: str, name: str, notes: str = "") -> bool:
    """Validate and add a task/quest."""
    name = clean_text(name)
    if not name:
        return False

    quest = {
        "id": make_quest_id(),
        "name": name,
        "completed": False,
        "created_at": now_iso(),
        "completed_at": None,
        "notes": clean_text(notes),
    }

    if quest_type == "daily_quests":
        st.session_state.daily_quests.append(quest)
    else:
        st.session_state.one_time_tasks.append(quest)

    save_quest_to_sqlite(quest, quest_type)
    return True


def find_quest(quest_id: str) -> tuple[dict[str, Any] | None, str | None]:
    for collection_name in ("one_time_tasks", "daily_quests"):
        for quest in st.session_state[collection_name]:
            if quest.get("id") == quest_id:
                return quest, collection_name
    return None, None


def update_quest_completion(quest_id: str, completed: bool) -> None:
    quest, collection_name = find_quest(quest_id)
    if quest is None or collection_name is None:
        return

    previous = bool(quest.get("completed", False))
    if previous == completed:
        return

    quest["completed"] = completed
    quest["completed_at"] = now_iso() if completed else None

    if completed:
        # Award 10 XP only when changing from pending to completed.
        xp_awarded = 10
        st.session_state.xp = safe_int(st.session_state.xp) + xp_awarded
        entry = {
            "quest_id": quest_id,
            "quest_name": quest["name"],
            "completed_at": quest["completed_at"],
            "xp_awarded": xp_awarded,
        }
        st.session_state.completion_log.append(entry)
        log_completion_to_sqlite(
            quest_id,
            quest["name"],
            quest["completed_at"],
            xp_awarded,
        )
        set_notice("success", f"Quest completed! +{xp_awarded} XP earned.")
    else:
        # XP already earned is not removed if a quest is unchecked.
        set_notice("info", "Quest marked as pending. Previously earned XP remains.")

    save_quest_to_sqlite(quest, collection_name)
    save_profile_to_sqlite()


def delete_quest(quest_id: str) -> None:
    for collection_name in ("one_time_tasks", "daily_quests"):
        original = st.session_state[collection_name]
        st.session_state[collection_name] = [
            quest for quest in original if quest.get("id") != quest_id
        ]
    delete_quest_from_sqlite(quest_id)


def edit_quest(
    quest_id: str, new_name: str, new_notes: str
) -> bool:
    quest, collection_name = find_quest(quest_id)
    if quest is None or collection_name is None:
        return False
    new_name = clean_text(new_name)
    if not new_name:
        return False

    quest["name"] = new_name
    quest["notes"] = clean_text(new_notes)
    save_quest_to_sqlite(quest, collection_name)
    return True


def reset_daily_quests() -> None:
    """
    Reset all daily quests to pending when the app is opened on a new date.

    This is a simple local-date reset. It does not preserve a separate completion
    history for every day, but the completion log retains completion events.
    """
    today = today_iso()
    previous_day = st.session_state.get("last_daily_reset", today)
    if previous_day == today:
        return

    for quest in st.session_state.daily_quests:
        quest["completed"] = False
        quest["completed_at"] = None
        save_quest_to_sqlite(quest, "daily_quests")

    st.session_state.last_daily_reset = today


# =============================================================================
# DATA EXPORT / IMPORT
# =============================================================================

def export_payload() -> dict[str, Any]:
    return {
        "app": "Quest Window",
        "version": APP_VERSION,
        "exported_at": now_iso(),
        "information": st.session_state.information,
        "xp": st.session_state.xp,
        "one_time_tasks": st.session_state.one_time_tasks,
        "daily_quests": st.session_state.daily_quests,
        "completion_log": st.session_state.completion_log,
    }


def to_csv(quests: list[dict[str, Any]]) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(
        buffer,
        fieldnames=[
            "quest_type",
            "id",
            "name",
            "completed",
            "created_at",
            "completed_at",
            "notes",
        ],
    )
    writer.writeheader()
    for collection_name in ("one_time_tasks", "daily_quests"):
        for quest in st.session_state[collection_name]:
            writer.writerow(
                {
                    "quest_type": QUEST_TYPES[collection_name],
                    "id": quest.get("id", ""),
                    "name": quest.get("name", ""),
                    "completed": bool(quest.get("completed", False)),
                    "created_at": quest.get("created_at", ""),
                    "completed_at": quest.get("completed_at") or "",
                    "notes": quest.get("notes", ""),
                }
            )
    return buffer.getvalue()


def import_payload(payload: dict[str, Any]) -> tuple[bool, str]:
    """Validate a JSON backup and load its profile and quests."""
    if not isinstance(payload, dict):
        return False, "The backup must contain a JSON object."

    information = payload.get("information", {})
    one_time = payload.get("one_time_tasks", [])
    daily = payload.get("daily_quests", [])
    log = payload.get("completion_log", [])

    if not isinstance(information, dict):
        return False, "Profile data is invalid."
    if not isinstance(one_time, list) or not isinstance(daily, list):
        return False, "Quest lists are invalid."
    if not isinstance(log, list):
        return False, "Completion log is invalid."

    name = clean_text(information.get("name", ""))
    age = safe_int(information.get("age", 16), 16)
    if not name:
        return False, "The backup has no valid player name."
    if age < 1 or age > 120:
        return False, "The age in the backup is outside the allowed range."

    def validate_quests(items: list[Any]) -> list[dict[str, Any]]:
        validated = []
        for item in items:
            if not isinstance(item, dict):
                continue
            quest_name = clean_text(item.get("name", ""))
            if not quest_name:
                continue
            validated.append(
                {
                    "id": clean_text(item.get("id")) or make_quest_id(),
                    "name": quest_name,
                    "completed": bool(item.get("completed", False)),
                    "created_at": clean_text(item.get("created_at")) or now_iso(),
                    "completed_at": clean_text(item.get("completed_at")) or None,
                    "notes": clean_text(item.get("notes", "")),
                }
            )
        return validated

    st.session_state.information = {
        "name": name,
        "age": age,
        "created_at": clean_text(information.get("created_at")) or now_iso(),
    }
    st.session_state.one_time_tasks = validate_quests(one_time)
    st.session_state.daily_quests = validate_quests(daily)
    st.session_state.completion_log = [
        item for item in log if isinstance(item, dict)
    ]
    st.session_state.xp = max(0, safe_int(payload.get("xp", 0)))
    st.session_state.registered = True

    if USE_SQLITE:
        clear_sqlite_data()
        save_profile_to_sqlite()
        for quest in st.session_state.one_time_tasks:
            save_quest_to_sqlite(quest, "one_time_tasks")
        for quest in st.session_state.daily_quests:
            save_quest_to_sqlite(quest, "daily_quests")
        # Completion log entries are retained in session; insert them into DB.
        for item in st.session_state.completion_log:
            log_completion_to_sqlite(
                clean_text(item.get("quest_id")),
                clean_text(item.get("quest_name")),
                clean_text(item.get("completed_at")) or now_iso(),
                safe_int(item.get("xp_awarded")),
            )

    return True, "Backup imported successfully."


# =============================================================================
# INITIALIZATION
# =============================================================================

init_session_state()
load_sqlite_data()

# Reset daily quests at the first visit on a new local date.
reset_daily_quests()

# Save any profile edits/updates when SQLite mode is active.
if USE_SQLITE and st.session_state.registered:
    save_profile_to_sqlite()


# =============================================================================
# APP STYLING
# =============================================================================

st.markdown(
    """
    <style>
        .block-container {
            padding-top: 1.8rem;
            padding-bottom: 3rem;
            max-width: 1200px;
        }
        div[data-testid="stMetric"] {
            border: 1px solid rgba(128, 128, 128, 0.22);
            padding: 14px 16px;
            border-radius: 14px;
        }
        .quest-caption {
            color: #777;
            font-size: 0.9rem;
        }
    </style>
    """,
    unsafe_allow_html=True,
)


# =============================================================================
# REGISTRATION
# =============================================================================

if not st.session_state.registered:
    st.title("⚔️ Quest Window")
    st.caption(f"Personal Quest Tracker · Version {APP_VERSION}")
    st.markdown(
        """
        Welcome, player! Create your profile to begin your journey.

        Your quests will help you organize tasks, build consistency, and see
        your progress over time.
        """
    )

    with st.form("registration_form", clear_on_submit=False):
        player_name = st.text_input(
            "Player name",
            placeholder="Enter your name",
            max_chars=60,
        )
        player_age = st.number_input(
            "Age",
            min_value=1,
            max_value=120,
            value=16,
            step=1,
        )
        confirm = st.checkbox("I have checked that my information is correct.")
        register = st.form_submit_button(
            "Create Player Profile",
            type="primary",
            use_container_width=True,
        )

        if register:
            if not clean_text(player_name):
                st.error("Please enter your name.")
            elif not confirm:
                st.warning("Please confirm your information before registering.")
            else:
                st.session_state.information = {
                    "name": clean_text(player_name),
                    "age": int(player_age),
                    "created_at": now_iso(),
                }
                st.session_state.registered = True
                save_profile_to_sqlite()
                st.rerun()

    st.stop()


# =============================================================================
# SIDEBAR
# =============================================================================

profile = st.session_state.information
quests = all_quests()
total_quests = len(quests)
completed_quests = count_completed(quests)
pending_quests = total_quests - completed_quests
xp = safe_int(st.session_state.xp)
level = get_level(xp)

with st.sidebar:
    st.title("⚔️ Quest Window")
    st.caption(f"Version {APP_VERSION}")
    st.write(f"**Player:** {profile.get('name', 'Player')}")
    st.write(f"**Level:** {level} · **XP:** {xp}")
    st.progress((xp % 100) / 100)
    st.caption(f"{xp_to_next_level(xp)} XP until next level")

    st.divider()

    page = st.radio(
        "Navigation",
        NAVIGATION,
        key="navigation_radio",
        label_visibility="collapsed",
    )

    st.divider()

    st.caption("Quick statistics")
    st.metric("Total quests", total_quests)
    st.metric("Completed", completed_quests)
    st.metric("Pending", pending_quests)

    if USE_SQLITE:
        st.success("SQLite persistence is ON")
    else:
        st.info("Session-only storage is ON")


# =============================================================================
# HOME PAGE
# =============================================================================

if page == "🏠 Home":
    st.title(f"Welcome back, {profile.get('name', 'Player')}! 👋")
    st.write(
        "Every completed quest is a step forward. "
        "Plan your day, complete your tasks, and keep moving."
    )

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("All Quests", total_quests)
    c2.metric("Completed", completed_quests)
    c3.metric("Pending", pending_quests)
    c4.metric("Player XP", xp)

    st.subheader("Overall Progress")
    overall = completion_percent(quests)
    st.progress(overall)
    st.caption(f"{overall * 100:.1f}% of your current quests are completed.")

    st.divider()

    left, right = st.columns(2)

    with left:
        st.subheader("📌 One-Time Tasks")
        tasks = st.session_state.one_time_tasks
        if not tasks:
            st.info("No one-time tasks yet. Add your first task in Make Quests.")
        else:
            for task in tasks[:5]:
                status = "✅" if task.get("completed") else "⏳"
                st.write(f"{status} {task['name']}")
            if len(tasks) > 5:
                st.caption(f"And {len(tasks) - 5} more task(s).")

    with right:
        st.subheader("🌞 Daily Quests")
        daily = st.session_state.daily_quests
        if not daily:
            st.info("No daily quests yet. Add your first daily quest in Make Quests.")
        else:
            for quest in daily[:5]:
                status = "✅" if quest.get("completed") else "⏳"
                st.write(f"{status} {quest['name']}")
            if len(daily) > 5:
                st.caption(f"And {len(daily) - 5} more quest(s).")

    st.divider()

    st.subheader("🎮 Player Progress")
    p1, p2, p3 = st.columns(3)
    p1.metric("Current Level", level)
    p2.metric("XP earned", xp)
    p3.metric("Completions logged", len(st.session_state.completion_log))

    if total_quests == 0:
        st.info("Your adventure starts with one quest. Open Make Quests to begin.")
    elif pending_quests == 0:
        st.success("Excellent! Every current quest is completed.")
    else:
        st.warning(f"You have {pending_quests} quest(s) waiting for you.")


# =============================================================================
# MAKE QUESTS PAGE
# =============================================================================

elif page == "📜 Make Quests":
    st.title("📜 Make Quests")
    st.write("Create tasks for one-time work or activities you want to repeat daily.")

    task_tab, daily_tab = st.tabs(
        ["➕ One-Time Task", "🌞 Daily Quest"]
    )

    with task_tab:
        st.subheader("Add a One-Time Task")
        st.caption(
            "Use this for assignments, projects, errands, or anything you only "
            "need to finish once."
        )
        with st.form("add_one_time_task", clear_on_submit=True):
            task_name = st.text_input(
                "Task name",
                placeholder="Example: Finish my physics homework",
                max_chars=200,
            )
            task_notes = st.text_area(
                "Notes (optional)",
                placeholder="Add details, a reminder, or a small plan...",
                max_chars=2000,
            )
            task_submit = st.form_submit_button(
                "Add One-Time Task",
                type="primary",
                use_container_width=True,
            )

            if task_submit:
                if add_quest("one_time_tasks", task_name, task_notes):
                    st.success("One-time task added!")
                    st.rerun()
                else:
                    st.error("Please enter a task name.")

    with daily_tab:
        st.subheader("Add a Daily Quest")
        st.caption(
            "Use this for habits and activities you want to work on every day."
        )
        with st.form("add_daily_quest", clear_on_submit=True):
            daily_name = st.text_input(
                "Quest name",
                placeholder="Example: Read for 20 minutes",
                max_chars=200,
            )
            daily_notes = st.text_area(
                "Notes (optional)",
                placeholder="What will help you complete this quest?",
                max_chars=2000,
            )
            daily_submit = st.form_submit_button(
                "Add Daily Quest",
                type="primary",
                use_container_width=True,
            )

            if daily_submit:
                if add_quest("daily_quests", daily_name, daily_notes):
                    st.success("Daily quest added!")
                    st.rerun()
                else:
                    st.error("Please enter a quest name.")


# =============================================================================
# QUEST LIST PAGE
# =============================================================================

elif page == "📋 Quest List":
    st.title("📋 Quest List")
    st.write("Search, complete, edit, and delete your quests.")

    filter_choice = st.selectbox(
        "Show",
        [
            "All quests",
            "One-time tasks",
            "Daily quests",
            "Pending only",
            "Completed only",
        ],
    )
    search_text = st.text_input(
        "Search quests",
        placeholder="Type part of a quest name or its notes...",
    )

    visible = []
    for collection_name in ("one_time_tasks", "daily_quests"):
        for quest in st.session_state[collection_name]:
            is_daily = collection_name == "daily_quests"
            if filter_choice == "One-time tasks" and is_daily:
                continue
            if filter_choice == "Daily quests" and not is_daily:
                continue
            if filter_choice == "Pending only" and quest.get("completed"):
                continue
            if filter_choice == "Completed only" and not quest.get("completed"):
                continue

            combined_text = (
                clean_text(quest.get("name", "")) + " " +
                clean_text(quest.get("notes", ""))
            ).lower()
            if clean_text(search_text).lower() not in combined_text:
                continue

            visible.append((collection_name, quest))

    if not visible:
        st.info("No quests match these filters.")
    else:
        st.caption(f"Showing {len(visible)} quest(s).")

    for collection_name, quest in visible:
        quest_id = quest["id"]
        is_daily = collection_name == "daily_quests"
        label = "Daily Quest" if is_daily else "One-Time Task"

        with st.container(border=True):
            top_left, top_right = st.columns([5, 1])

            with top_left:
                st.markdown(f"**{quest['name']}**")
                st.caption(
                    f"{label} · Added {quest.get('created_at', 'date unknown')}"
                )
                if quest.get("notes"):
                    st.write(quest["notes"])
                if quest.get("completed"):
                    st.success("Completed")
                else:
                    st.warning("Pending")

            with top_right:
                completed_now = st.checkbox(
                    "Done",
                    value=bool(quest.get("completed", False)),
                    key=f"complete_{quest_id}",
                )
                if completed_now != bool(quest.get("completed", False)):
                    update_quest_completion(quest_id, completed_now)
                    st.rerun()

            with st.expander("Edit or delete"):
                with st.form(f"edit_form_{quest_id}"):
                    edited_name = st.text_input(
                        "Quest name",
                        value=quest.get("name", ""),
                        key=f"edit_name_{quest_id}",
                        max_chars=200,
                    )
                    edited_notes = st.text_area(
                        "Notes",
                        value=quest.get("notes", ""),
                        key=f"edit_notes_{quest_id}",
                        max_chars=2000,
                    )
                    save_edit = st.form_submit_button("Save Changes")

                    if save_edit:
                        if edit_quest(quest_id, edited_name, edited_notes):
                            set_notice("success", "Quest updated successfully.")
                            st.rerun()
                        else:
                            st.error("Quest name cannot be empty.")

                delete_confirm_key = f"confirm_delete_{quest_id}"
                confirm_delete = st.checkbox(
                    "I really want to delete this quest",
                    key=delete_confirm_key,
                )
                if st.button(
                    "Delete Quest",
                    key=f"delete_{quest_id}",
                    type="secondary",
                    disabled=not confirm_delete,
                ):
                    delete_quest(quest_id)
                    set_notice("success", "Quest deleted.")
                    st.rerun()


# =============================================================================
# STATUS WINDOW
# =============================================================================

elif page == "📊 Status Window":
    st.title("📊 Status Window")
    st.write("A detailed overview of your current quests and player progress.")

    quests = all_quests()
    total = len(quests)
    completed = count_completed(quests)
    pending = total - completed

    st.subheader("Player Information")
    a, b, c = st.columns(3)
    a.metric("Player", profile.get("name", "Player"))
    b.metric("Age", profile.get("age", "—"))
    c.metric("Level", get_level(safe_int(st.session_state.xp)))

    st.divider()
    st.subheader("Quest Summary")

    a, b, c = st.columns(3)
    a.metric("Total Quests", total)
    b.metric("Completed Quests", completed)
    c.metric("Pending Quests", pending)

    percent = completion_percent(quests)
    st.write("Overall completion")
    st.progress(percent)
    st.write(f"{percent * 100:.1f}%")

    tasks = st.session_state.one_time_tasks
    daily = st.session_state.daily_quests

    st.divider()
    st.subheader("One-Time Task Statistics")
    a, b, c = st.columns(3)
    a.metric("Total Tasks", len(tasks))
    b.metric("Completed Tasks", count_completed(tasks))
    c.metric("Pending Tasks", len(tasks) - count_completed(tasks))

    st.subheader("Daily Quest Statistics")
    a, b, c = st.columns(3)
    a.metric("Total Daily Quests", len(daily))
    b.metric("Completed Daily Quests", count_completed(daily))
    c.metric("Pending Daily Quests", len(daily) - count_completed(daily))

    st.divider()
    st.subheader("Experience Points")
    xp = safe_int(st.session_state.xp)
    level = get_level(xp)
    current_level_start = (level - 1) * 100
    xp_in_level = xp - current_level_start

    x1, x2, x3 = st.columns(3)
    x1.metric("Total XP", xp)
    x2.metric("Current Level", level)
    x3.metric("XP to Next Level", xp_to_next_level(xp))

    st.progress(min(1.0, xp_in_level / 100))
    st.caption(f"{xp_in_level}/100 XP toward level {level + 1}.")

    st.divider()
    st.subheader("Recent Completion Activity")
    completion_log = st.session_state.completion_log
    if not completion_log:
        st.info("Your completed quests will appear here.")
    else:
        for entry in reversed(completion_log[-10:]):
            st.write(
                f"✅ **{entry.get('quest_name', 'Quest')}** — "
                f"{entry.get('completed_at', 'Unknown date')} "
                f"(+{safe_int(entry.get('xp_awarded'))} XP)"
            )


# =============================================================================
# PROFILE PAGE
# =============================================================================

elif page == "👤 Profile":
    st.title("👤 Player Profile")
    st.write("View or update your player information.")

    st.markdown(f"**Registered since:** {profile.get('created_at', 'Unknown')}")

    with st.form("profile_update_form"):
        new_name = st.text_input(
            "Player name",
            value=profile.get("name", ""),
            max_chars=60,
        )
        new_age = st.number_input(
            "Age",
            min_value=1,
            max_value=120,
            value=safe_int(profile.get("age", 16), 16),
            step=1,
        )
        update_profile = st.form_submit_button(
            "Save Profile",
            type="primary",
            use_container_width=True,
        )

        if update_profile:
            if not clean_text(new_name):
                st.error("Player name cannot be empty.")
            else:
                st.session_state.information["name"] = clean_text(new_name)
                st.session_state.information["age"] = int(new_age)
                save_profile_to_sqlite()
                set_notice("success", "Profile updated successfully.")
                st.rerun()

    st.divider()
    st.subheader("Player Progress")
    xp = safe_int(st.session_state.xp)
    st.metric("Level", get_level(xp))
    st.metric("XP", xp)
    st.caption("You earn 10 XP when you change a quest from pending to completed.")

    st.divider()
    st.subheader("Reset or Exit")

    with st.expander("Reset profile and all quests"):
        st.warning(
            "This removes the current profile and all quests. "
            "If SQLite storage is enabled, it also deletes the saved database records."
        )
        confirm_reset = st.checkbox(
            "I understand that this action deletes my data.",
            key="confirm_full_reset",
        )

        if st.button(
            "Reset All Data",
            type="primary",
            disabled=not confirm_reset,
        ):
            clear_sqlite_data()
            st.session_state.registered = False
            st.session_state.information = {
                "name": "",
                "age": 16,
                "created_at": now_iso(),
            }
            st.session_state.one_time_tasks = []
            st.session_state.daily_quests = []
            st.session_state.xp = 0
            st.session_state.completion_log = []
            st.session_state.sqlite_loaded = True
            st.session_state.last_daily_reset = today_iso()
            for key in list(st.session_state.keys()):
                if key.startswith(("complete_", "edit_name_", "edit_notes_", "confirm_delete_")):
                    del st.session_state[key]
            st.rerun()


# =============================================================================
# BACKUP & DATA PAGE
# =============================================================================

elif page == "💾 Backup & Data":
    st.title("💾 Backup & Data")
    st.write(
        "Export your data so you can keep a backup. Importing a backup replaces "
        "the profile and quest lists currently in this session."
    )

    payload = export_payload()
    json_bytes = json.dumps(payload, indent=2, ensure_ascii=False).encode("utf-8")
    csv_text = to_csv(all_quests())

    st.download_button(
        "⬇️ Download JSON Backup",
        data=json_bytes,
        file_name="quest_window_backup.json",
        mime="application/json",
        use_container_width=True,
    )

    st.download_button(
        "⬇️ Download Quests as CSV",
        data=csv_text,
        file_name="quest_window_quests.csv",
        mime="text/csv",
        use_container_width=True,
    )

    st.divider()
    st.subheader("Import a JSON Backup")

    uploaded_file = st.file_uploader(
        "Choose a Quest Window JSON backup",
        type=["json"],
        help="Use a JSON file exported by Quest Window.",
    )

    if uploaded_file is not None:
        if st.button("Import Backup", type="primary"):
            try:
                incoming = json.load(uploaded_file)
                success, message = import_payload(incoming)
                if success:
                    set_notice("success", message)
                    st.rerun()
                else:
                    st.error(message)
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                st.error(f"Could not read the JSON file: {exc}")
            except Exception as exc:
                st.error(f"Import failed: {exc}")

    st.divider()
    st.subheader("Storage Mode")

    if USE_SQLITE:
        st.success(
            f"SQLite storage is enabled. Database path: `{os.path.abspath(DB_PATH)}`"
        )
        st.write(
            "Profile and quest changes are saved to a local SQLite database. "
            "Keep the database file safe and make regular JSON backups."
        )
    else:
        st.info(
            "Session-only mode is enabled. For local SQLite persistence, set "
            "`QUEST_WINDOW_USE_SQLITE=1` before starting Streamlit."
        )


# =============================================================================
# HELP PAGE
# =============================================================================

elif page == "ℹ️ Help":
    st.title("ℹ️ Help & Instructions")

    st.subheader("How to use Quest Window")
    st.markdown(
        """
        1. **Create your profile** on the registration page.
        2. Open **Make Quests** to add a one-time task or a daily quest.
        3. Open **Quest List** to search, mark quests done, edit them, or delete them.
        4. Open **Status Window** to see totals, completion percentage, XP, and level.
        5. Open **Profile** to update your name or age.
        6. Open **Backup & Data** to export or import a backup.
        """
    )

    st.divider()
    st.subheader("How XP and levels work")
    st.markdown(
        """
        - Completing a quest earns **10 XP**.
        - Every **100 XP** advances you by one level.
        - Unchecking a completed quest marks it pending but does not remove XP
          already earned.
        - Deleting a quest does not remove XP already earned from completing it.
        """
    )

    st.divider()
    st.subheader("How daily quests work")
    st.markdown(
        """
        Daily quests are reset to pending when the app detects a new local date
        during a new app run/session. In a long-running app, the reset check is
        performed when Streamlit reruns the script; the app does not run a
        background midnight scheduler.
        """
    )

    st.divider()
    st.subheader("Data and privacy")
    st.markdown(
        """
        - Session-only mode is the default.
        - SQLite mode saves data locally on the machine running Streamlit.
        - This starter app does not provide account passwords or secure,
          multi-user isolation.
        - Do not expose a personal SQLite-backed instance publicly without
          adding authentication and appropriate security controls.
        """
    )

    st.caption(f"Quest Window version {APP_VERSION}")


# =============================================================================
# FOOTER
# =============================================================================

st.divider()
st.caption(
    f"Quest Window v{APP_VERSION} · Built with Streamlit · "
    f"{'SQLite persistence enabled' if USE_SQLITE else 'Session storage'}"
)

show_notice()
