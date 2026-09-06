import os
import sqlite3
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), 'backend', '.env'))

def alter_sqlite():
    db_paths = [
        os.path.join(os.path.dirname(__file__), 'backend', 'smartcivic.db'),
        os.path.join(os.path.dirname(__file__), 'backend', 'test_smartcivic.db')
    ]
    for db_path in db_paths:
        if not os.path.exists(db_path):
            continue
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        queries = [
            ("users", "ALTER TABLE users ADD COLUMN created_at DATETIME DEFAULT '2000-01-01 00:00:00';"),
            ("users", "ALTER TABLE users ADD COLUMN approval_status VARCHAR(30) DEFAULT 'approved';"),
            ("users", "ALTER TABLE users ADD COLUMN secret_key VARCHAR(100);"),
            ("users", "ALTER TABLE users ADD COLUMN approved_at DATETIME;"),
            ("complaints", "ALTER TABLE complaints ADD COLUMN citizen_gmail VARCHAR(100);")
        ]
        for tbl, q in queries:
            try:
                cursor.execute(q)
                conn.commit()
                print(f"[SQLite {os.path.basename(db_path)}] Executed: {q}")
            except Exception as e:
                # Column already exists
                pass
        conn.close()

def alter_postgres():
    db_url = os.getenv('DATABASE_URL')
    if not db_url:
        return
    try:
        import psycopg2
        conn = psycopg2.connect(db_url)
        cursor = conn.cursor()
        queries = [
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS approval_status VARCHAR(30) DEFAULT 'approved';",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS secret_key VARCHAR(100);",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS approved_at TIMESTAMP;",
            "ALTER TABLE complaints ADD COLUMN IF NOT EXISTS citizen_gmail VARCHAR(100);"
        ]
        for q in queries:
            try:
                cursor.execute(q)
                conn.commit()
                print(f"[PostgreSQL] Executed: {q}")
            except Exception as e:
                conn.rollback()
                print(f"[PostgreSQL Warning] {e}")
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"[PostgreSQL Connect Note] {e}")

if __name__ == '__main__':
    alter_sqlite()
    alter_postgres()
