import os
import sqlite3
from dotenv import load_dotenv

def alter_db():
    load_dotenv('backend/.env')
    db_url = os.getenv('DATABASE_URL')
    
    if db_url:
        try:
            import psycopg2
            if db_url.startswith('postgres://'):
                db_url = db_url.replace('postgres://', 'postgresql://', 1)
            conn = psycopg2.connect(db_url)
            cur = conn.cursor()
            try:
                cur.execute("ALTER TABLE users ALTER COLUMN password TYPE VARCHAR(255);")
                conn.commit()
                print("Successfully updated PostgreSQL users password column to VARCHAR(255).")
            except Exception as e:
                conn.rollback()
                print("PostgreSQL users alter note:", e)

            try:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS notifications (
                        id SERIAL PRIMARY KEY,
                        title VARCHAR(200) NOT NULL,
                        message TEXT NOT NULL,
                        type VARCHAR(50) DEFAULT 'new_complaint',
                        complaint_id VARCHAR(50) REFERENCES complaints(complaint_id),
                        target_role VARCHAR(20) DEFAULT 'authority',
                        is_read BOOLEAN DEFAULT FALSE NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                """)
                conn.commit()
                print("Successfully verified/created PostgreSQL notifications table.")
            except Exception as e:
                conn.rollback()
                print("PostgreSQL notification table creation note:", e)
            finally:
                conn.close()
        except Exception as e:
            print("PostgreSQL migration note:", e)


    db_path = 'backend/smartcivic.db'
    if os.path.exists(db_path):
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        try:
            cursor.execute("ALTER TABLE users ADD COLUMN created_at DATETIME DEFAULT '2000-01-01 00:00:00';")
            conn.commit()
            print("Successfully added created_at column to SQLite users table.")
        except Exception as e:
            print("SQLite migration note:", e)

        try:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS notifications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title VARCHAR(200) NOT NULL,
                    message TEXT NOT NULL,
                    type VARCHAR(50) DEFAULT 'new_complaint',
                    complaint_id VARCHAR(50) REFERENCES complaints(complaint_id),
                    target_role VARCHAR(20) DEFAULT 'authority',
                    is_read BOOLEAN DEFAULT 0 NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                );
            """)
            conn.commit()
            print("Successfully verified/created SQLite notifications table.")
        except Exception as e:
            print("SQLite notification table creation note:", e)
        finally:
            conn.close()

if __name__ == '__main__':
    alter_db()

