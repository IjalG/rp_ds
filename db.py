import sqlite3
import os
import sys
from datetime import datetime
from typing import Optional
from models import Template, Conversation, Message


def _data_dir() -> str:
    if getattr(sys, "frozen", False):
        base = os.path.dirname(sys.executable)
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return base


DB_PATH = os.path.join(_data_dir(), "data.db")


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS templates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            system_prompt TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            template_id INTEGER REFERENCES templates(id),
            mode TEXT NOT NULL DEFAULT 'inner_os',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id INTEGER NOT NULL REFERENCES conversations(id),
            parent_id INTEGER REFERENCES messages(id),
            role TEXT NOT NULL,
            content TEXT NOT NULL DEFAULT '',
            think_content TEXT NOT NULL DEFAULT '',
            branch_order INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
    """)
    conn.commit()
    conn.close()


# ---- Settings ----

def get_setting(key: str, default: str = "") -> str:
    conn = get_conn()
    row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    conn.close()
    return row["value"] if row else default


def set_setting(key: str, value: str):
    conn = get_conn()
    conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
    conn.commit()
    conn.close()


# ---- Templates ----

def list_templates() -> list[Template]:
    conn = get_conn()
    rows = conn.execute("SELECT * FROM templates ORDER BY updated_at DESC").fetchall()
    conn.close()
    return [Template(**dict(r)) for r in rows]


def get_template(tid: int) -> Optional[Template]:
    conn = get_conn()
    row = conn.execute("SELECT * FROM templates WHERE id=?", (tid,)).fetchone()
    conn.close()
    return Template(**dict(row)) if row else None


def save_template(t: Template):
    now = datetime.now().isoformat()
    conn = get_conn()
    if t.id:
        conn.execute(
            "UPDATE templates SET name=?, system_prompt=?, updated_at=? WHERE id=?",
            (t.name, t.system_prompt, now, t.id),
        )
    else:
        conn.execute(
            "INSERT INTO templates (name, system_prompt, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (t.name, t.system_prompt, now, now),
        )
        t.id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.commit()
    conn.close()


def delete_template(tid: int):
    conn = get_conn()
    conn.execute("DELETE FROM templates WHERE id=?", (tid,))
    conn.commit()
    conn.close()


# ---- Conversations ----

def list_conversations() -> list[Conversation]:
    conn = get_conn()
    rows = conn.execute("""
        SELECT c.*, t.name AS template_name
        FROM conversations c
        LEFT JOIN templates t ON c.template_id = t.id
        ORDER BY c.updated_at DESC
    """).fetchall()
    conn.close()
    return [Conversation(**dict(r)) for r in rows]


def get_conversation(cid: int) -> Optional[Conversation]:
    conn = get_conn()
    row = conn.execute("""
        SELECT c.*, t.name AS template_name
        FROM conversations c
        LEFT JOIN templates t ON c.template_id = t.id
        WHERE c.id=?
    """, (cid,)).fetchall()
    conn.close()
    return Conversation(**dict(row[0])) if row else None


def save_conversation(c: Conversation):
    now = datetime.now().isoformat()
    conn = get_conn()
    if c.id:
        conn.execute(
            "UPDATE conversations SET name=?, template_id=?, mode=?, updated_at=? WHERE id=?",
            (c.name, c.template_id, c.mode, now, c.id),
        )
    else:
        conn.execute(
            "INSERT INTO conversations (name, template_id, mode, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (c.name, c.template_id, c.mode, now, now),
        )
        c.id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.commit()
    conn.close()


def delete_conversation(cid: int):
    conn = get_conn()
    conn.execute("DELETE FROM messages WHERE conversation_id=?", (cid,))
    conn.execute("DELETE FROM conversations WHERE id=?", (cid,))
    conn.commit()
    conn.close()


# ---- Messages ----

def list_messages(conversation_id: int) -> list[Message]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM messages WHERE conversation_id=? ORDER BY branch_order, id",
        (conversation_id,),
    ).fetchall()
    conn.close()
    return [Message(**dict(r)) for r in rows]


def get_message(mid: int) -> Optional[Message]:
    conn = get_conn()
    row = conn.execute("SELECT * FROM messages WHERE id=?", (mid,)).fetchone()
    conn.close()
    return Message(**dict(row)) if row else None


def save_message(m: Message):
    now = datetime.now().isoformat()
    conn = get_conn()
    if m.id:
        conn.execute(
            "UPDATE messages SET content=?, think_content=? WHERE id=?",
            (m.content, m.think_content, m.id),
        )
    else:
        max_order = conn.execute(
            "SELECT COALESCE(MAX(branch_order)+1, 0) FROM messages WHERE conversation_id=? AND parent_id IS ?",
            (m.conversation_id, m.parent_id),
        ).fetchone()[0]
        m.branch_order = max_order
        conn.execute(
            "INSERT INTO messages (conversation_id, parent_id, role, content, think_content, branch_order, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (m.conversation_id, m.parent_id, m.role, m.content, m.think_content, m.branch_order, now),
        )
        m.id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        # update conversation timestamp
        conn.execute("UPDATE conversations SET updated_at=? WHERE id=?", (now, m.conversation_id))
    conn.commit()
    conn.close()


def delete_message(mid: int):
    conn = get_conn()
    conn.execute("DELETE FROM messages WHERE id=?", (mid,))
    conn.commit()
    conn.close()


def get_active_branch(conversation_id: int) -> list[Message]:
    """Get the current active message chain (root -> latest)."""
    all_msgs = list_messages(conversation_id)
    if not all_msgs:
        return []
    # build tree
    children_of: dict[int | None, list[Message]] = {}
    for m in all_msgs:
        pid: int | None = m.parent_id
        if pid not in children_of:
            children_of[pid] = []
        children_of[pid].append(m)
    # walk the highest branch_order path
    chain: list[Message] = []
    cur_pid: int | None = None
    while cur_pid in children_of:
        siblings = children_of[cur_pid]
        if not siblings:
            break
        best = max(siblings, key=lambda x: x.branch_order)
        chain.append(best)
        cur_pid = best.id
    return chain
