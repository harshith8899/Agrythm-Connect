"""Simple local API server streaming Gate Zero SQLite call logs and farmer directory to the React dashboard."""
import json
import os
import sqlite3
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

# Points to gate0/gate0.db or the path set in GATE0_DB
DEFAULT_DB = Path(__file__).resolve().parent.parent / "database" / "agrythm_connect.db"
DB_PATH = os.environ.get("GATE0_DB", str(DEFAULT_DB))


def init_farmers_table(conn):
    """Ensures farmers table exists and has default demo records in SQLite."""
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS farmers (
        farmer_id TEXT PRIMARY KEY,
        farmer_name TEXT,
        phone_number TEXT,
        village TEXT,
        district TEXT,
        state TEXT,
        primary_language TEXT,
        call_consent TEXT,
        active TEXT
    );
    """)
    count = cur.execute("SELECT COUNT(*) FROM farmers").fetchone()[0]
    if count == 0:
        demo_data = [
            ("F001", "Ramesh", "+91 98450 12001", "Mandya", "Mandya", "Karnataka", "Hindi", "Yes", "Yes"),
            ("F002", "Lakshmi", "+91 98450 12002", "Mysuru", "Mysuru", "Karnataka", "English", "Yes", "Yes"),
            ("F003", "Suresh", "+91 98450 12003", "Hassan", "Hassan", "Karnataka", "Hindi", "Yes", "Yes"),
            ("F004", "Anita", "+91 98450 12004", "Mandya", "Mandya", "Karnataka", "Hindi", "Yes", "Yes"),
            ("F005", "Manjunath", "+91 98450 12005", "Hassan", "Hassan", "Karnataka", "Hindi", "Yes", "Yes"),
            ("F006", "Geeta", "+91 98450 12006", "Mysuru", "Mysuru", "Karnataka", "English", "Yes", "Yes"),
            ("F007", "Prakash", "+91 98450 12007", "Nowhere", "Bidar", "Karnataka", "Hindi", "Yes", "Yes"),
            ("F008", "Savitha", "+91 98450 12008", "Mandya", "Mandya", "Karnataka", "Hindi", "No", "Yes"),
            ("F009", "Basavaraj", "+91 98450 12009", "Mysuru", "Mysuru", "Karnataka", "Hindi", "Yes", "No"),
            ("F010", "Kavya", "+91 98450 12010", "Hassan", "Hassan", "Karnataka", "English", "Yes", "Yes"),
        ]
        cur.executemany("INSERT INTO farmers VALUES (?,?,?,?,?,?,?,?,?)", demo_data)
        conn.commit()


class TelemetryHandler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.end_headers()

    def do_GET(self):
        if self.path.startswith("/api/calls"):
            if not os.path.exists(DB_PATH):
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(b"[]")
                return

            try:
                conn = sqlite3.connect(DB_PATH)
                conn.row_factory = sqlite3.Row
                cur = conn.cursor()

                # Joined query: day_results joined with the latest attempt record
                query = """
                SELECT 
                    COALESCE(a.provider_call_id, d.farmer_id || '-' || d.call_date || '-' || COALESCE(a.attempt_no, 1)) AS call_id,
                    d.farmer_id,
                    d.call_date,
                    COALESCE(a.attempt_no, d.attempts) AS attempt_no,
                    a.status AS attempt_status,
                    d.result AS call_status,
                    d.skip_reason,
                    a.language,
                    COALESCE(a.duration_s, 0) AS duration_sec,
                    COALESCE(a.message_text, '') AS message_text,
                    COALESCE(a.error, '') AS error,
                    a.weather_source
                FROM day_results d
                LEFT JOIN attempts a 
                    ON d.farmer_id = a.farmer_id 
                    AND d.call_date = a.call_date
                ORDER BY d.call_date DESC, a.attempt_no DESC;
                """
                rows = [dict(r) for r in cur.execute(query).fetchall()]
                conn.close()

                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps(rows).encode("utf-8"))
            except Exception as e:
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))

        elif self.path.startswith("/api/farmers"):
            try:
                conn = sqlite3.connect(DB_PATH)
                conn.row_factory = sqlite3.Row
                init_farmers_table(conn)
                cur = conn.cursor()
                rows = [dict(r) for r in cur.execute("SELECT * FROM farmers ORDER BY farmer_id ASC").fetchall()]
                conn.close()

                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps(rows).encode("utf-8"))
            except Exception as e:
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()


def run(port=8000):
    server = HTTPServer(("0.0.0.0", port), TelemetryHandler)
    print(f"Gate Zero SQLite Telemetry API live on http://localhost:{port}/api/calls & /api/farmers")
    server.serve_forever()


if __name__ == "__main__":
    run()
