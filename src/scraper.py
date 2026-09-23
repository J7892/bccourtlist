"""
Daily scraper & database pipeline for BC Criminal Court Lists.
Features:
- Crawls index pages for:
    * Provincial Daily Lists
    * Supreme Daily Lists
    * Provincial Completed Lists
    * Supreme Completed Lists
    * Provincial Advance Lists
- Concurrent downloading and parsing with a polite thread pool (default: 4 workers).
- Checks for file-level duplicates using SHA256 hashes against `processed_files`.
- Thread-safe batch writes to SQLite database `data/court_data.db`.
- Updates dispositions and results on completed cases.
- Exports advanced lists separately into JSON / CSV format (`data/advanced_lists.json` and `data/advanced_lists.csv`).
- Exports daily / completed records into `data/daily_court_lists.json` and `data/daily_court_lists.csv` for dashboard use.
"""

import os
import re
import csv
import json
import time
import shutil
import hashlib
import logging
import urllib.request
from urllib.parse import urljoin
from concurrent.futures import ThreadPoolExecutor, as_completed

from src.db import init_db, get_connection, is_file_already_processed, record_processed_file, purge_expired_advanced_appearances
from src.parser import parse_provincial_daily_or_advance, parse_supreme_daily, parse_completed_list

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

MAX_WORKERS = 4  # Gentle on BC government servers while speeding up execution ~4x

INDEX_CONFIGS = [
    {
        "category": "prov_daily",
        "court_level": "Provincial",
        "index_url": "https://justice.gov.bc.ca/courts/DAPCindex.html",
        "target_table": "appearances",
        "parser": parse_provincial_daily_or_advance,
        "is_completed": False
    },
    {
        "category": "supreme_daily",
        "court_level": "Supreme",
        "index_url": "https://justice.gov.bc.ca/courts/DASCindex.html",
        "target_table": "appearances",
        "parser": parse_supreme_daily,
        "is_completed": False
    },
    {
        "category": "prov_completed",
        "court_level": "Provincial",
        "index_url": "https://justice.gov.bc.ca/courts/DACCPindex.html",
        "target_table": "appearances",
        "parser": lambda data, fn: parse_completed_list(data, fn, court_level="Provincial"),
        "is_completed": True
    },
    {
        "category": "supreme_completed",
        "court_level": "Supreme",
        "index_url": "https://justice.gov.bc.ca/courts/DACCSindex.html",
        "target_table": "appearances",
        "parser": lambda data, fn: parse_completed_list(data, fn, court_level="Supreme"),
        "is_completed": True
    },
    {
        "category": "prov_advance",
        "court_level": "Provincial",
        "index_url": "https://justice.gov.bc.ca/courts/PCDCindex.html",
        "target_table": "advanced_appearances",
        "parser": parse_provincial_daily_or_advance,
        "is_completed": False
    }
]

def fetch_url(url, timeout=25):
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()

def get_pdf_links_from_index(index_url):
    html_content = fetch_url(index_url).decode("utf-8", errors="ignore")
    matches = re.findall(r'<a\s+href=[\"\']?([^\"\' >]+\.pdf)[\"\']?', html_content, re.IGNORECASE)
    links = []
    seen = set()
    for m in matches:
        full_url = urljoin(index_url, m.strip())
        fn = m.strip().split('/')[-1]
        if fn not in seen:
            seen.add(fn)
            links.append((fn, full_url))
    return links

def download_and_parse_task(task_info):
    """
    Worker task: downloads a single PDF and parses it in memory.
    Returns: dict with metadata, parsed records, and status.
    """
    category = task_info["category"]
    filename = task_info["filename"]
    file_url = task_info["file_url"]
    parser_fn = task_info["parser"]
    existing_sha_set = task_info["existing_sha_set"]

    try:
        pdf_data = fetch_url(file_url)
        sha256 = hashlib.sha256(pdf_data).hexdigest()

        # Check if already processed in this version
        if (filename, sha256) in existing_sha_set:
            return {
                "status": "skipped",
                "filename": filename,
                "file_url": file_url,
                "category": category,
                "sha256": sha256,
                "records": [],
                "metadata": {}
            }

        metadata, records = parser_fn(pdf_data, filename)
        return {
            "status": "success",
            "filename": filename,
            "file_url": file_url,
            "category": category,
            "sha256": sha256,
            "records": records,
            "metadata": metadata
        }
    except Exception as e:
        return {
            "status": "error",
            "filename": filename,
            "file_url": file_url,
            "category": category,
            "error": str(e)
        }

def save_appearances_to_db(conn, table_name, records, is_completed=False, source_category=""):
    cur = conn.cursor()
    saved = 0
    updated = 0

    if table_name == "appearances":
        for r in records:
            # Match existing appearance on core primary keys (court_level, court_name, court_date, file_number, cnt)
            cur.execute("""
                SELECT id, room, rsn, result, disposition, status FROM appearances
                WHERE court_level = ? AND court_name = ? AND court_date = ? 
                  AND file_number = ? AND cnt = ?
            """, (r['court_level'], r['court_name'], r['court_date'], r['file_number'], r['cnt']))
            existing = cur.fetchone()

            if existing:
                if is_completed or r.get('disposition') or r.get('result'):
                    cur.execute("""
                        UPDATE appearances
                        SET result = COALESCE(NULLIF(?, ''), result),
                            next_appearance = COALESCE(NULLIF(?, ''), next_appearance),
                            disposition = COALESCE(NULLIF(?, ''), disposition),
                            agency_file = COALESCE(NULLIF(?, ''), agency_file),
                            status = CASE WHEN ? != '' THEN 'Completed' ELSE status END,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = ?
                    """, (
                        r.get('result', ''),
                        r.get('next_appearance', ''),
                        r.get('disposition', ''),
                        r.get('agency_file', ''),
                        r.get('disposition', ''),
                        existing['id']
                    ))
                    updated += 1
            else:
                cur.execute("""
                    INSERT OR IGNORE INTO appearances
                    (court_level, court_name, room, court_date, session_time, item_no, file_number, name,
                     proc, ic, counsel, plea, elec, age, rsn, cnt, charge_description, lesser_included,
                     vc, location_of_offence, agency_file, result, next_appearance, disposition, status,
                     source_category, source_filename)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    r['court_level'], r['court_name'], r['room'], r['court_date'], r['session_time'],
                    r['item_no'], r['file_number'], r['name'], r['proc'], r['ic'], r['counsel'],
                    r['plea'], r['elec'], r['age'], r['rsn'], r['cnt'], r['charge_description'],
                    r['lesser_included'], r['vc'], r['location_of_offence'], r.get('agency_file', ''),
                    r.get('result', ''), r.get('next_appearance', ''), r.get('disposition', ''),
                    r.get('status', 'Scheduled'), source_category, r['source_filename']
                ))
                saved += 1
    elif table_name == "advanced_appearances":
        for r in records:
            cur.execute("""
                INSERT OR REPLACE INTO advanced_appearances
                (court_level, court_name, room, court_date, session_time, item_no, file_number, name,
                 proc, ic, counsel, plea, elec, age, rsn, cnt, charge_description, lesser_included,
                 vc, location_of_offence, source_filename)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                r['court_level'], r['court_name'], r['room'], r['court_date'], r['session_time'],
                r['item_no'], r['file_number'], r['name'], r['proc'], r['ic'], r['counsel'],
                r['plea'], r['elec'], r['age'], r['rsn'], r['cnt'], r['charge_description'],
                r['lesser_included'], r['vc'], r['location_of_offence'], r['source_filename']
            ))
            saved += 1

    return saved, updated

def export_data_files(conn, output_dir, days_window=30):
    from datetime import datetime, timedelta
    os.makedirs(output_dir, exist_ok=True)
    cur = conn.cursor()

    # 1. Purge expired dates from advanced_appearances so it stays a 5-day snapshot
    purge_expired_advanced_appearances(conn)

    # 2. Export Advanced appearances (compact JSON + CSV)
    cur.execute("SELECT * FROM advanced_appearances ORDER BY court_date, court_name, file_number")
    adv_rows = [dict(row) for row in cur.fetchall()]
    
    adv_json_path = os.path.join(output_dir, "advanced_lists.json")
    with open(adv_json_path, "w", encoding="utf-8") as f:
        # Minified JSON eliminates ~30-40% unnecessary whitespace
        json.dump(adv_rows, f, separators=(',', ':'))
    
    adv_csv_path = os.path.join(output_dir, "advanced_lists.csv")
    if adv_rows:
        with open(adv_csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=adv_rows[0].keys())
            writer.writeheader()
            writer.writerows(adv_rows)

    # 3. Export Centralized Appearances
    # Full export into CSV for bulk analysis / records
    cur.execute("SELECT * FROM appearances ORDER BY court_date DESC, court_name, file_number")
    all_app_rows = [dict(row) for row in cur.fetchall()]

    app_csv_path = os.path.join(output_dir, "daily_court_lists.csv")
    if all_app_rows:
        with open(app_csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=all_app_rows[0].keys())
            writer.writeheader()
            writer.writerows(all_app_rows)

    # For JSON (used directly by the browser dashboard):
    # Keep rolling window (last 30 days of court dates) to keep browser load lightning fast
    recent_app_rows = []
    if all_app_rows:
        parsed_dates = []
        for r in all_app_rows:
            d_str = r.get('court_date') or ''
            try:
                dt = datetime.strptime(d_str.strip().upper(), "%d-%b-%Y")
                parsed_dates.append(dt)
            except Exception:
                pass
        
        if parsed_dates:
            max_dt = max(parsed_dates)
            cutoff_dt = max_dt - timedelta(days=days_window)
            
            for r in all_app_rows:
                d_str = r.get('court_date') or ''
                try:
                    dt = datetime.strptime(d_str.strip().upper(), "%d-%b-%Y")
                    if dt >= cutoff_dt:
                        recent_app_rows.append(r)
                except Exception:
                    recent_app_rows.append(r)
        else:
            recent_app_rows = all_app_rows
    else:
        recent_app_rows = []

    app_json_path = os.path.join(output_dir, "daily_court_lists.json")
    with open(app_json_path, "w", encoding="utf-8") as f:
        json.dump(recent_app_rows, f, separators=(',', ':'))

    # 4. Generate Complete Historical Archive Search Index
    # Stored compactly for on-demand search across ALL past records
    archive_rows = []
    for r in all_app_rows:
        archive_rows.append({
            'fn': r['file_number'],
            'nm': r['name'],
            'cd': r['court_date'] or '',
            'cn': r['court_name'],
            'cl': r['court_level'],
            'rm': r['room'] or '',
            'tm': r['session_time'] or '',
            'cnt': r['cnt'] or '',
            'ch': r['charge_description'] or '',
            'rs': r['result'] or '',
            'dp': r['disposition'] or '',
            'st': r['status'] or 'Scheduled',
            'pr': r['proc'] or '',
            'ic': r['ic'] or '',
            'na': r['next_appearance'] or ''
        })
    archive_json_path = os.path.join(output_dir, "archive_index.json")
    with open(archive_json_path, "w", encoding="utf-8") as f:
        json.dump(archive_rows, f, separators=(',', ':'))

    # 5. Sync to docs/data for GitHub Pages hosting
    docs_data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs", "data")
    if os.path.exists(docs_data_dir):
        shutil.copy2(adv_json_path, os.path.join(docs_data_dir, "advanced_lists.json"))
        if adv_rows:
            shutil.copy2(adv_csv_path, os.path.join(docs_data_dir, "advanced_lists.csv"))
        shutil.copy2(app_json_path, os.path.join(docs_data_dir, "daily_court_lists.json"))
        shutil.copy2(archive_json_path, os.path.join(docs_data_dir, "archive_index.json"))
        if all_app_rows:
            shutil.copy2(app_csv_path, os.path.join(docs_data_dir, "daily_court_lists.csv"))

    logging.info(f"Exported {len(adv_rows)} advanced rows (compact JSON) to {adv_json_path}")
    logging.info(f"Exported {len(recent_app_rows)} recent appearances ({days_window}-day window) to {app_json_path}")
    logging.info(f"Exported {len(archive_rows)} total appearances to archive search index: {archive_json_path}")



def run_pipeline(limit_per_category=None, max_workers=MAX_WORKERS):
    """
    Executes the ingestion pipeline with parallel downloads and safe single-threaded DB writes.
    """
    start_time = time.time()
    init_db()
    conn = get_connection()
    data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")

    # Load existing (filename, sha256) pairs into memory for instant lookup
    cur = conn.cursor()
    cur.execute("SELECT filename, sha256 FROM processed_files")
    existing_sha_set = {(row['filename'], row['sha256']) for row in cur.fetchall()}

    total_downloaded = 0
    total_skipped = 0
    total_records = 0

    for cfg in INDEX_CONFIGS:
        category = cfg["category"]
        logging.info(f"--- Fetching index for {category} ({cfg['index_url']}) ---")
        try:
            pdf_links = get_pdf_links_from_index(cfg["index_url"])
            logging.info(f"Found {len(pdf_links)} PDF files for {category}")
        except Exception as e:
            logging.error(f"Failed to fetch index for {category}: {e}")
            continue

        if limit_per_category:
            pdf_links = pdf_links[:limit_per_category]

        tasks = []
        for filename, file_url in pdf_links:
            tasks.append({
                "category": category,
                "filename": filename,
                "file_url": file_url,
                "parser": cfg["parser"],
                "existing_sha_set": existing_sha_set
            })

        # Process downloads and parsing concurrently
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_file = {executor.submit(download_and_parse_task, t): t["filename"] for t in tasks}

            for future in as_completed(future_to_file):
                res = future.result()
                status = res["status"]
                filename = res["filename"]

                if status == "skipped":
                    logging.info(f"Skipping unmodified file (duplicate SHA256): {filename}")
                    total_skipped += 1
                elif status == "error":
                    logging.error(f"Error processing {filename}: {res.get('error')}")
                elif status == "success":
                    total_downloaded += 1
                    records = res["records"]
                    metadata = res["metadata"]

                    # Safe single-threaded DB write
                    saved, updated = save_appearances_to_db(
                        conn,
                        cfg["target_table"],
                        records,
                        is_completed=cfg["is_completed"],
                        source_category=category
                    )

                    record_processed_file(
                        conn,
                        category,
                        records[0]['court_name'] if records else filename,
                        filename,
                        res["file_url"],
                        res["sha256"],
                        metadata.get('report_id', ''),
                        metadata.get('report_date', ''),
                        metadata.get('court_date', ''),
                        len(records)
                    )
                    existing_sha_set.add((filename, res["sha256"]))
                    conn.commit()

                    total_records += len(records)
                    logging.info(f"Processed {filename}: {len(records)} records (Saved: {saved}, Updated: {updated})")

    # Export latest dataset for dashboard
    export_data_files(conn, data_dir)
    conn.close()

    elapsed = time.time() - start_time
    logging.info(f"Pipeline complete in {elapsed:.1f}s! Downloaded: {total_downloaded}, Skipped (duplicate): {total_skipped}, Total Records Extracted: {total_records}")

if __name__ == "__main__":
    import sys
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else None
    run_pipeline(limit_per_category=limit)
