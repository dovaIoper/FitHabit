import sqlite3
with open('schema.sql') as f:
    conn = sqlite3.connect('instance/habit_tracker.db')
    conn.executescript(f.read())
    conn.commit()
    conn.close()
