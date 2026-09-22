"""
Database initialization and management for BC Court lists.
Maintains:
  - processed_files: tracks file sha256 checksums, court dates, report dates to avoid duplicates.
  - appearances: primary database of scheduled appearances and completed outcomes.
  - advanced_appearances: scheduled appearances for upcoming 5 days.
"""

import sqlite3
import os

DEFAULT_DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "court_data.db")

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS processed_files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT NOT NULL,          -- 'prov_daily', 'supreme_daily', 'prov_completed', 'supreme_completed', 'prov_advance'
    court_name TEXT NOT NULL,
    filename TEXT NOT NULL,
    file_url TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    report_id TEXT,
    report_date TEXT,
    court_date TEXT,
    processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    record_count INTEGER DEFAULT 0,
    UNIQUE(filename, sha256)
);

CREATE TABLE IF NOT EXISTS appearances (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    court_level TEXT NOT NULL,        -- 'Provincial' or 'Supreme'
    court_name TEXT NOT NULL,
    room TEXT,
    court_date TEXT,                  -- Appearance date (YYYY-MM-DD or text representation)
    session_time TEXT,
    item_no TEXT,
    file_number TEXT NOT NULL,
    name TEXT NOT NULL,
    proc TEXT,                        -- Bail process
    ic TEXT,                          -- In custody: Y / N
    counsel TEXT,
    plea TEXT,
    elec TEXT,
    age TEXT,                         -- Age of file
    rsn TEXT,                         -- Reason / purpose of appearance
    cnt TEXT,                         -- Count number
    charge_description TEXT,          -- Act / section and charge description
    lesser_included TEXT,
    vc TEXT,                          -- Videoconference flag
    location_of_offence TEXT,
    agency_file TEXT,                 -- For completed files
    result TEXT,                      -- For completed files (e.g. IBJ, END)
    next_appearance TEXT,             -- For completed files
    disposition TEXT,                 -- Final disposition (e.g. SOP, PNI, APG)
    status TEXT DEFAULT 'Scheduled',  -- 'Scheduled', 'Completed', 'Adjourned'
    source_category TEXT,             -- 'prov_daily', 'supreme_daily', 'prov_completed', 'supreme_completed'
    source_filename TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(court_level, court_name, court_date, file_number, cnt, rsn, room)
);

CREATE TABLE IF NOT EXISTS advanced_appearances (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    court_level TEXT NOT NULL,
    court_name TEXT NOT NULL,
    room TEXT,
    court_date TEXT,
    session_time TEXT,
    item_no TEXT,
    file_number TEXT NOT NULL,
    name TEXT NOT NULL,
    proc TEXT,
    ic TEXT,
    counsel TEXT,
    plea TEXT,
    elec TEXT,
    age TEXT,
    rsn TEXT,
    cnt TEXT,
    charge_description TEXT,
    lesser_included TEXT,
    vc TEXT,
    location_of_offence TEXT,
    source_filename TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(court_level, court_name, court_date, file_number, cnt, rsn, room)
);

CREATE INDEX IF NOT EXISTS idx_appearances_file_number ON appearances(file_number);
CREATE INDEX IF NOT EXISTS idx_appearances_name ON appearances(name);
CREATE INDEX IF NOT EXISTS idx_appearances_court_date ON appearances(court_date);
CREATE INDEX IF NOT EXISTS idx_appearances_court_name ON appearances(court_name);
CREATE INDEX IF NOT EXISTS idx_appearances_disposition ON appearances(disposition);
CREATE INDEX IF NOT EXISTS idx_appearances_status ON appearances(status);

CREATE INDEX IF NOT EXISTS idx_advanced_file_number ON advanced_appearances(file_number);
CREATE INDEX IF NOT EXISTS idx_advanced_name ON advanced_appearances(name);
CREATE INDEX IF NOT EXISTS idx_advanced_court_date ON advanced_appearances(court_date);
"""

def get_connection(db_path=DEFAULT_DB_PATH):
    os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

def init_db(db_path=DEFAULT_DB_PATH):
    conn = get_connection(db_path)
    with conn:
        conn.executescript(SCHEMA_SQL)
    conn.close()

def is_file_already_processed(conn, filename, sha256):
    cur = conn.cursor()
    cur.execute("SELECT id FROM processed_files WHERE filename = ? AND sha256 = ?", (filename, sha256))
    return cur.fetchone() is not None

def record_processed_file(conn, category, court_name, filename, file_url, sha256, report_id, report_date, court_date, count):
    cur = conn.cursor()
    cur.execute("""
        INSERT OR REPLACE INTO processed_files
        (category, court_name, filename, file_url, sha256, report_id, report_date, court_date, record_count)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (category, court_name, filename, file_url, sha256, report_id, report_date, court_date, count))
    conn.commit()

if __name__ == "__main__":
    init_db()
    print("Database initialized successfully at", DEFAULT_DB_PATH)
