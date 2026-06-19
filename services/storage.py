from pathlib import Path
import sqlite3


DB_PATH = Path(__file__).resolve().parents[1] / "chat_history.db"


def get_db_connection() -> sqlite3.Connection:
    """Create a SQLite connection for chat history."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Create the chat history table if needed."""
    with get_db_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                pinned INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                agent TEXT,
                provider TEXT,
                feedback TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (session_id) REFERENCES sessions (id)
            )
            """
        )
        session_columns = [
            row["name"]
            for row in conn.execute("PRAGMA table_info(sessions)").fetchall()
        ]
        if "pinned" not in session_columns:
            conn.execute("ALTER TABLE sessions ADD COLUMN pinned INTEGER DEFAULT 0")

        columns = [
            row["name"]
            for row in conn.execute("PRAGMA table_info(messages)").fetchall()
        ]
        if "session_id" not in columns:
            conn.execute("ALTER TABLE messages ADD COLUMN session_id INTEGER")
        if "feedback" not in columns:
            conn.execute("ALTER TABLE messages ADD COLUMN feedback TEXT")
        default_id = ensure_default_session(conn)
        conn.execute(
            "UPDATE messages SET session_id = ? WHERE session_id IS NULL",
            (default_id,),
        )


def ensure_default_session(conn: sqlite3.Connection | None = None) -> int:
    """Return the first session, creating it when the database is empty."""
    owns_connection = conn is None
    if conn is None:
        conn = get_db_connection()

    try:
        row = conn.execute("SELECT id FROM sessions ORDER BY id ASC LIMIT 1").fetchone()
        if row:
            return int(row["id"])

        cursor = conn.execute("INSERT INTO sessions (title) VALUES (?)", ("Chat 1",))
        return int(cursor.lastrowid)
    finally:
        if owns_connection:
            conn.close()


def list_sessions() -> list[dict[str, str]]:
    """Return all chat sessions for the session switcher."""
    with get_db_connection() as conn:
        rows = conn.execute(
            """
            SELECT
                sessions.id,
                sessions.title,
                sessions.pinned,
                sessions.created_at,
                sessions.updated_at,
                COUNT(messages.id) AS message_count
            FROM sessions
            LEFT JOIN messages ON messages.session_id = sessions.id
            GROUP BY sessions.id
            ORDER BY sessions.pinned DESC, sessions.updated_at DESC, sessions.id DESC
            """
        ).fetchall()

    return [
        {
            "id": row["id"],
            "title": row["title"],
            "pinned": bool(row["pinned"]),
            "created_at": row["created_at"] or "",
            "updated_at": row["updated_at"] or "",
            "message_count": row["message_count"],
        }
        for row in rows
    ]


def create_session(title: str | None = None) -> int:
    """Create a new chat session."""
    with get_db_connection() as conn:
        if not title:
            count = conn.execute("SELECT COUNT(*) AS total FROM sessions").fetchone()["total"]
            title = f"Chat {int(count) + 1}"

        cursor = conn.execute("INSERT INTO sessions (title) VALUES (?)", (title,))
        return int(cursor.lastrowid)


def touch_session(session_id: int) -> None:
    """Move a session to the top of the session list."""
    with get_db_connection() as conn:
        conn.execute(
            "UPDATE sessions SET updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (session_id,),
        )


def rename_session(session_id: int, title: str) -> bool:
    """Rename an existing chat session."""
    clean_title = title.strip()[:60]
    if not clean_title:
        return False

    with get_db_connection() as conn:
        cursor = conn.execute(
            """
            UPDATE sessions
            SET title = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (clean_title, session_id),
        )
        return cursor.rowcount > 0


def get_session(session_id: int) -> dict[str, str] | None:
    """Return one session row."""
    with get_db_connection() as conn:
        row = conn.execute(
            """
            SELECT id, title, pinned, created_at, updated_at
            FROM sessions
            WHERE id = ?
            """,
            (session_id,),
        ).fetchone()

    if not row:
        return None

    return {
        "id": row["id"],
        "title": row["title"],
        "pinned": bool(row["pinned"]),
        "created_at": row["created_at"] or "",
        "updated_at": row["updated_at"] or "",
    }


def set_session_pinned(session_id: int, pinned: bool) -> bool:
    """Pin or unpin a session."""
    with get_db_connection() as conn:
        cursor = conn.execute(
            """
            UPDATE sessions
            SET pinned = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (1 if pinned else 0, session_id),
        )
        return cursor.rowcount > 0


def count_session_messages(session_id: int) -> int:
    """Return how many messages a session currently has."""
    with get_db_connection() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS total FROM messages WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        return int(row["total"])


def delete_session(session_id: int) -> int:
    """Delete a session and return the next active session id."""
    with get_db_connection() as conn:
        existing = conn.execute(
            "SELECT id FROM sessions WHERE id = ?",
            (session_id,),
        ).fetchone()
        if not existing:
            return ensure_default_session(conn)

        conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
        conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))

        next_row = conn.execute(
            "SELECT id FROM sessions ORDER BY pinned DESC, updated_at DESC, id DESC LIMIT 1"
        ).fetchone()
        if next_row:
            return int(next_row["id"])

        cursor = conn.execute("INSERT INTO sessions (title) VALUES (?)", ("Chat 1",))
        return int(cursor.lastrowid)


def load_chat_history(limit: int, session_id: int | None = None) -> list[dict[str, str]]:
    """Load recent messages from SQLite for agent context and page rendering."""
    if session_id is None:
        session_id = ensure_default_session()

    with get_db_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, role, content, agent, provider, feedback, created_at
            FROM messages
            WHERE session_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (session_id, limit),
        ).fetchall()

    return [
        {
            "id": row["id"],
            "role": row["role"],
            "content": row["content"],
            "agent": row["agent"] or "",
            "provider": row["provider"] or "",
            "feedback": row["feedback"] or "",
            "created_at": row["created_at"] or "",
        }
        for row in reversed(rows)
    ]


def load_all_chat_messages(session_id: int | None = None) -> list[sqlite3.Row]:
    """Load all persisted messages for export."""
    if session_id is None:
        session_id = ensure_default_session()

    with get_db_connection() as conn:
        return conn.execute(
            """
            SELECT role, content, agent, provider, created_at
            FROM messages
            WHERE session_id = ?
            ORDER BY id ASC
            """,
            (session_id,),
        ).fetchall()


def search_chat(query: str, limit: int = 12) -> list[dict[str, str]]:
    """Search session titles and message content."""
    clean_query = query.strip()
    if not clean_query:
        return []

    pattern = f"%{clean_query}%"
    with get_db_connection() as conn:
        rows = conn.execute(
            """
            SELECT
                sessions.id AS session_id,
                sessions.title AS session_title,
                sessions.pinned AS session_pinned,
                messages.role,
                messages.content,
                messages.created_at
            FROM messages
            JOIN sessions ON sessions.id = messages.session_id
            WHERE sessions.title LIKE ? OR messages.content LIKE ?
            ORDER BY messages.created_at DESC, messages.id DESC
            LIMIT ?
            """,
            (pattern, pattern, limit),
        ).fetchall()

        title_rows = conn.execute(
            """
            SELECT
                sessions.id AS session_id,
                sessions.title AS session_title,
                sessions.pinned AS session_pinned,
                '' AS role,
                '' AS content,
                sessions.updated_at AS created_at
            FROM sessions
            WHERE sessions.title LIKE ?
            ORDER BY sessions.pinned DESC, sessions.updated_at DESC, sessions.id DESC
            LIMIT ?
            """,
            (pattern, limit),
        ).fetchall()

    seen = set()
    results = []
    for row in [*title_rows, *rows]:
        key = (row["session_id"], row["role"], row["content"][:120])
        if key in seen:
            continue
        seen.add(key)

        content = row["content"] or "Session title match"
        preview = " ".join(content.split())[:180]
        results.append({
            "session_id": row["session_id"],
            "session_title": row["session_title"],
            "session_pinned": bool(row["session_pinned"]),
            "role": row["role"] or "session",
            "preview": preview,
            "created_at": row["created_at"] or "",
        })
        if len(results) >= limit:
            break

    return results


def save_message(
    role: str,
    content: str,
    agent: str = "",
    provider: str = "",
    session_id: int | None = None,
) -> int:
    """Persist one message in SQLite."""
    if session_id is None:
        session_id = ensure_default_session()

    with get_db_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO messages (session_id, role, content, agent, provider)
            VALUES (?, ?, ?, ?, ?)
            """,
            (session_id, role, content, agent, provider),
        )
    touch_session(session_id)
    return int(cursor.lastrowid)


def update_user_message(message_id: int, content: str) -> bool:
    """Update one user message in place."""
    clean_content = content.strip()
    if not clean_content:
        return False

    with get_db_connection() as conn:
        cursor = conn.execute(
            """
            UPDATE messages
            SET content = ?
            WHERE id = ? AND role = 'user'
            """,
            (clean_content, message_id),
        )
        row = conn.execute(
            "SELECT session_id FROM messages WHERE id = ?",
            (message_id,),
        ).fetchone()

    if row:
        touch_session(int(row["session_id"]))
    return cursor.rowcount > 0


def update_assistant_message(
    message_id: int,
    content: str,
    agent: str = "",
    provider: str = "",
) -> bool:
    """Update one assistant message in place and clear old feedback."""
    clean_content = content.strip()
    if not clean_content:
        return False

    with get_db_connection() as conn:
        cursor = conn.execute(
            """
            UPDATE messages
            SET content = ?, agent = ?, provider = ?, feedback = ''
            WHERE id = ? AND role = 'assistant'
            """,
            (clean_content, agent, provider, message_id),
        )
        row = conn.execute(
            "SELECT session_id FROM messages WHERE id = ?",
            (message_id,),
        ).fetchone()

    if row:
        touch_session(int(row["session_id"]))
    return cursor.rowcount > 0


def set_message_feedback(message_id: int, feedback: str) -> bool:
    """Save feedback for one assistant message."""
    clean_feedback = feedback if feedback in {"up", "down", ""} else ""
    with get_db_connection() as conn:
        cursor = conn.execute(
            """
            UPDATE messages
            SET feedback = ?
            WHERE id = ? AND role = 'assistant'
            """,
            (clean_feedback, message_id),
        )
        return cursor.rowcount > 0


def clear_messages(session_id: int | None = None) -> None:
    """Delete all persisted chat messages."""
    if session_id is None:
        session_id = ensure_default_session()

    with get_db_connection() as conn:
        conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
    touch_session(session_id)
