import sqlite3

def alter_db():
    conn = sqlite3.connect('backend/smartcivic.db')
    cursor = conn.cursor()
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN created_at DATETIME DEFAULT '2000-01-01 00:00:00';")
        conn.commit()
        print("Successfully added created_at column to users table.")
    except Exception as e:
        print("Error or already exists:", e)
    finally:
        conn.close()

if __name__ == '__main__':
    alter_db()
