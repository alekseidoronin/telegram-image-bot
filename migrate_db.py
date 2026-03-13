import sqlite3
import os

DB_PATH = 'bot_database.db'

def migrate():
    if not os.path.exists(DB_PATH):
        print(f"Database {DB_PATH} not found.")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Add email to invite_tokens if not exists
    cursor.execute("PRAGMA table_info(invite_tokens)")
    cols = [row[1] for row in cursor.fetchall()]
    if 'email' not in cols:
        print("Adding 'email' column to invite_tokens...")
        try:
            cursor.execute("ALTER TABLE invite_tokens ADD COLUMN email TEXT")
            conn.commit()
        except Exception as e:
            print(f"Error adding email to invite_tokens: {e}")

    # Add email to WebAccessRequests if not exists
    cursor.execute("PRAGMA table_info(WebAccessRequests)")
    cols = [row[1] for row in cursor.fetchall()]
    if 'email' not in cols:
        print("Adding 'email' column to WebAccessRequests...")
        try:
            cursor.execute("ALTER TABLE WebAccessRequests ADD COLUMN email TEXT")
            conn.commit()
        except Exception as e:
            print(f"Error adding email to WebAccessRequests: {e}")

    conn.close()
    print("Migration finished.")

if __name__ == "__main__":
    migrate()
