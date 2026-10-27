import hashlib
import os
import sqlite3

db_path = os.path.abspath("toeic_agent.db")
print(f"Absolute DB Path: {db_path}")
print(f"DB Exists: {os.path.exists(db_path)}")
if os.path.exists(db_path):
    print(f"DB File Size: {os.path.getsize(db_path)} bytes")

    # Hash before
    h_before = hashlib.sha256()
    with open(db_path, "rb") as f:
        h_before.update(f.read())
    sha_before = h_before.hexdigest()
    print(f"SHA-256 (before): {sha_before}")

    # Read-only sqlite3 connection
    uri = f"file:{db_path}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    cursor = conn.cursor()

    # Query sqlite_master for actual tables
    cursor.execute("SELECT type, name FROM sqlite_master WHERE type IN ('table', 'view') ORDER BY name;")
    tables = cursor.fetchall()
    print(f"sqlite_master entries: {tables}")

    table_names = [t[1] for t in tables if t[0] == 'table']

    for name in table_names:
        cursor.execute(f"SELECT COUNT(*) FROM {name};")
        count = cursor.fetchone()[0]
        print(f"Table '{name}' row count: {count}")

    # Specifically check question_enrichments
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='question_enrichments';")
    qe = cursor.fetchone()
    if qe:
        print("Table 'question_enrichments': PRESENT")
    else:
        print("Table 'question_enrichments': ABSENT (table does not exist in sqlite_master)")

    conn.close()

    # Hash after
    h_after = hashlib.sha256()
    with open(db_path, "rb") as f:
        h_after.update(f.read())
    sha_after = h_after.hexdigest()
    print(f"SHA-256 (after): {sha_after}")
    print(f"Hashes Match: {sha_before == sha_after}")
