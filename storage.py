import sqlite3
from pathlib import Path
from models import Candidate

DB_PATH = Path(__file__).parent / "candidates.db"


def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS candidates (
                enbek_id    TEXT PRIMARY KEY,
                position    TEXT,
                full_name   TEXT,
                phone       TEXT,
                name        TEXT,
                city        TEXT,
                salary       TEXT,
                experience   TEXT,
                work_history TEXT,
                education    TEXT,
                skills      TEXT,
                languages   TEXT,
                profile_url TEXT,
                scraped_at  TEXT
            )
        """)
        # Миграция: добавляем новые колонки если их нет
        cols = {r[1] for r in conn.execute("PRAGMA table_info(candidates)")}
        if "full_name" not in cols:
            conn.execute("ALTER TABLE candidates ADD COLUMN full_name TEXT")
        if "phone" not in cols:
            conn.execute("ALTER TABLE candidates ADD COLUMN phone TEXT")
        if "work_history" not in cols:
            conn.execute("ALTER TABLE candidates ADD COLUMN work_history TEXT")


def save_candidate(c: Candidate) -> bool:
    with sqlite3.connect(DB_PATH) as conn:
        if conn.execute("SELECT 1 FROM candidates WHERE enbek_id=?", (c.enbek_id,)).fetchone():
            # Обновляем контакты если они появились
            if c.phone or c.full_name:
                conn.execute(
                    "UPDATE candidates SET full_name=?, phone=? WHERE enbek_id=?",
                    (c.full_name, c.phone, c.enbek_id),
                )
            return False
        conn.execute(
            """INSERT INTO candidates
               (enbek_id, position, full_name, phone, name, city, salary,
                experience, work_history, education, skills, languages,
                profile_url, scraped_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (c.enbek_id, c.position, c.full_name, c.phone, c.name,
             c.city, c.salary, c.experience, c.work_history, c.education,
             c.skills, c.languages, c.profile_url, c.scraped_at),
        )
        return True


def get_all_candidates() -> list[dict]:
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        return [dict(r) for r in conn.execute(
            "SELECT * FROM candidates ORDER BY scraped_at DESC"
        ).fetchall()]


def count_candidates() -> int:
    with sqlite3.connect(DB_PATH) as conn:
        return conn.execute("SELECT COUNT(*) FROM candidates").fetchone()[0]
