"""
PDF Parsers for BC Court Lists:
- parse_provincial_daily_or_advance: Handles Provincial daily and advance court lists.
- parse_supreme_daily: Handles Supreme Court daily criminal lists.
- parse_completed_list: Handles both Provincial and Supreme completed court lists.
"""

import re
import io
import pdfplumber

def clean_court_name_from_filename(filename):
    base = filename.replace('.pdf', '')
    for suffix in ['_Provincial_Completed', '_Supreme_Completed', '_Provincial_Advance', '_Supreme_Advance', '_Provincial', '_Supreme']:
        if base.endswith(suffix):
            base = base[:-len(suffix)]
            break
    return base.replace('_', ' ')

def _group_words_by_line(words, y_tolerance=4.0):
    lines = []
    for w in sorted(words, key=lambda x: (x['top'], x['x0'])):
        if not lines or abs(lines[-1][0]['top'] - w['top']) > y_tolerance:
            lines.append([w])
        else:
            lines[-1].append(w)
    return lines

def _assign_words_to_columns(line_words, col_ranges):
    line_cols = {k: [] for k in col_ranges}
    for w in line_words:
        cx = (w['x0'] + w['x1']) / 2
        for cname, (x_min, x_max) in col_ranges.items():
            if x_min <= cx < x_max:
                line_cols[cname].append(w['text'])
                break
    return {k: " ".join(v).strip() for k, v in line_cols.items()}

def parse_provincial_daily_or_advance(pdf_bytes, filename=""):
    """
    Parses Provincial Court Daily or Advance list.
    Columns: No., File Number, Name, Proc, I/C, Counsel, Plea, Elec, Age, Rsn, Cnt, Description, Included, V/C, Location
    """
    col_ranges = {
        'item_no': (0, 42),
        'file_number': (42, 145),
        'name': (145, 335),
        'proc': (335, 375),
        'ic': (375, 398),
        'counsel': (398, 460),
        'plea': (460, 490),
        'elec': (490, 518),
        'age': (518, 542),
        'rsn': (542, 570),
        'cnt': (570, 595),
        'description': (595, 740),
        'included': (740, 815),
        'vc': (815, 845),
        'location': (845, 1008)
    }

    records = []
    metadata = {
        'court_name': '',
        'court_date': '',
        'report_id': '',
        'report_date': '',
        'total_pages': 0
    }

    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        metadata['total_pages'] = len(pdf.pages)
        for page in pdf.pages:
            raw_text = page.extract_text() or ""
            page_court_date = metadata['court_date']
            
            # Extract header metadata
            for line in raw_text.splitlines():
                if "Court Date:" in line:
                    m_date = re.search(r"Court Date:\s*([0-9A-Za-z-]+)", line)
                    if m_date:
                        page_court_date = m_date.group(1).strip()
                        if not metadata['court_date']:
                            metadata['court_date'] = page_court_date
                if "Report ID:" in line:
                    m_rep = re.search(r"Report ID:\s*([^\s]+)\s+Report Date:\s*(.+)", line)
                    if m_rep and not metadata['report_id']:
                        metadata['report_id'] = m_rep.group(1).strip()
                        metadata['report_date'] = m_rep.group(2).strip()

            words = page.extract_words()
            # Extract court title from top
            top_words = [w for w in words if w['top'] < 30]
            if top_words and not metadata['court_name']:
                title_line = " ".join(w['text'] for w in sorted(top_words, key=lambda x: x['x0']))
                # e.g. "Richmond Provincial Court-2025 Page: 1 of 12"
                title_clean = re.sub(r'-\d+\s+Page.*$', '', title_line)
                title_clean = re.sub(r'\s+Page.*$', '', title_clean).strip()
                if title_clean:
                    metadata['court_name'] = title_clean

            # Process body words (between top 30 and 560)
            current_room = ""
            current_session = ""
            current_rec = None

            body_words = [w for w in words if 25 <= w['top'] <= 560]
            lines = _group_words_by_line(body_words, y_tolerance=4.0)

            for l_words in lines:
                line_str = " ".join(w['text'] for w in sorted(l_words, key=lambda x: x['x0']))
                if "Room:" in line_str:
                    m_rm = re.search(r"Room:\s*(\S+)", line_str)
                    if m_rm:
                        current_room = m_rm.group(1).strip()
                if "For the Session Commencing at" in line_str:
                    m_sess = re.search(r"For the Session Commencing at\s*([0-9:AMPMapm ]+)", line_str)
                    if m_sess:
                        current_session = m_sess.group(1).strip()
                    continue

                # Check if it's the header row
                if "No." in line_str and "File Number" in line_str:
                    continue

                cols = _assign_words_to_columns(l_words, col_ranges)

                # Check if this row begins a new entry (item_no present or new file_number present)
                valid_file_no = bool(re.search(r'\d+-\d+', cols['file_number']))
                is_new_item = bool(cols['item_no'] and cols['item_no'].isdigit())
                is_new_count = bool(cols['cnt'] and (cols['cnt'].isdigit() or 'CCC' in cols['cnt']))

                if is_new_item or (valid_file_no and is_new_count) or (is_new_count and (cols['rsn'] or cols['proc'])):
                    if current_rec:
                        records.append(current_rec)

                    prev_name = current_rec['name'] if current_rec else ""
                    prev_file = current_rec['file_number'] if current_rec else ""
                    file_to_use = cols['file_number'] if valid_file_no else prev_file

                    # Clean count and charge if concatenated (e.g., '001CCC' -> cnt='001', charge='CCC ...')
                    cnt_val = cols['cnt']
                    desc_val = cols['description']
                    m_cnt = re.match(r'^(\d{3})(.*)$', cnt_val)
                    if m_cnt:
                        cnt_val = m_cnt.group(1)
                        if m_cnt.group(2):
                            desc_val = (m_cnt.group(2) + " " + desc_val).strip()

                    current_rec = {
                        'court_level': 'Provincial',
                        'court_name': clean_court_name_from_filename(filename) if filename else metadata['court_name'],
                        'room': current_room,
                        'court_date': page_court_date,
                        'session_time': current_session,
                        'item_no': cols['item_no'] or (current_rec['item_no'] if current_rec else ""),
                        'file_number': file_to_use,
                        'name': cols['name'] or prev_name,
                        'proc': cols['proc'],
                        'ic': cols['ic'],
                        'counsel': cols['counsel'],
                        'plea': cols['plea'],
                        'elec': cols['elec'],
                        'age': cols['age'],
                        'rsn': cols['rsn'],
                        'cnt': cnt_val,
                        'charge_description': desc_val,
                        'lesser_included': cols['included'],
                        'vc': cols['vc'],
                        'location_of_offence': cols['location'],
                        'source_filename': filename
                    }
                elif current_rec:
                    # Continuation line: append description, name, counsel, or location
                    if cols['name']:
                        current_rec['name'] += " " + cols['name']
                    if cols['counsel']:
                        current_rec['counsel'] += " " + cols['counsel']
                    if cols['description']:
                        current_rec['charge_description'] += " " + cols['description']
                    if cols['location']:
                        current_rec['location_of_offence'] += " " + cols['location']

            if current_rec:
                records.append(current_rec)

    return metadata, records


def parse_supreme_daily(pdf_bytes, filename=""):
    """
    Parses Supreme Court Daily Criminal List.
    Columns: Justice, Case No., Name, Cnt, Main Charge / Application, Included, Rsn, Rm, Time, V/C, Location of Offence
    """
    col_ranges = {
        'justice': (0, 140),
        'case_no': (140, 250),
        'name': (250, 410),
        'cnt': (410, 440),
        'description': (440, 605),
        'included': (605, 670),
        'rsn': (670, 715),
        'rm': (715, 750),
        'time': (750, 810),
        'vc': (810, 840),
        'location': (840, 1008)
    }

    records = []
    metadata = {
        'court_name': '',
        'court_date': '',
        'report_id': '',
        'report_date': '',
        'total_pages': 0
    }

    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        metadata['total_pages'] = len(pdf.pages)
        for page in pdf.pages:
            raw_text = page.extract_text() or ""
            for line in raw_text.splitlines():
                if "Date:" in line:
                    m_date = re.search(r"Date:\s*([0-9A-Za-z-]+)", line)
                    if m_date and not metadata['court_date']:
                        metadata['court_date'] = m_date.group(1).strip()

            words = page.extract_words()
            top_words = [w for w in words if w['top'] < 50]
            if top_words and not metadata['court_name']:
                title_lines = [w['text'] for w in sorted(top_words, key=lambda x: (x['top'], x['x0'])) if 'Page:' not in w['text']]
                metadata['court_name'] = " ".join(title_lines[:4]).strip()

            body_words = [w for w in words if 70 <= w['top'] <= 560]
            lines = _group_words_by_line(body_words, y_tolerance=4.0)
            current_rec = None

            for l_words in lines:
                line_str = " ".join(w['text'] for w in sorted(l_words, key=lambda x: x['x0']))
                if "Case No." in line_str and "Main Charge" in line_str:
                    continue

                cols = _assign_words_to_columns(l_words, col_ranges)
                is_new_case = bool(cols['case_no'] and '-' in cols['case_no'])
                is_new_count = bool(cols['cnt'] and cols['cnt'].isdigit())

                if is_new_case or is_new_count:
                    if current_rec:
                        records.append(current_rec)

                    prev_case = current_rec['file_number'] if current_rec else ""
                    prev_name = current_rec['name'] if current_rec else ""
                    prev_rm = current_rec['room'] if current_rec else ""
                    prev_time = current_rec['session_time'] if current_rec else ""

                    current_rec = {
                        'court_level': 'Supreme',
                        'court_name': clean_court_name_from_filename(filename) if filename else metadata['court_name'],
                        'room': cols['rm'] or prev_rm,
                        'court_date': metadata['court_date'],
                        'session_time': cols['time'] or prev_time,
                        'item_no': '',
                        'file_number': cols['case_no'] or prev_case,
                        'name': cols['name'] or prev_name,
                        'proc': '',
                        'ic': '',
                        'counsel': cols['justice'],
                        'plea': '',
                        'elec': '',
                        'age': '',
                        'rsn': cols['rsn'],
                        'cnt': cols['cnt'],
                        'charge_description': cols['description'],
                        'lesser_included': cols['included'],
                        'vc': cols['vc'],
                        'location_of_offence': cols['location'],
                        'source_filename': filename
                    }
                elif current_rec:
                    if cols['name']:
                        current_rec['name'] += " " + cols['name']
                    if cols['description']:
                        current_rec['charge_description'] += " " + cols['description']
                    if cols['location']:
                        current_rec['location_of_offence'] += " " + cols['location']

            if current_rec:
                records.append(current_rec)

    return metadata, records


def parse_completed_list(pdf_bytes, filename="", court_level="Provincial"):
    """
    Parses Completed Court Lists (Provincial or Supreme).
    Columns: Rm, File Number, Name, Proc, I/C, Cnt, Description, Included, Agency File, Rslt, Next Appearance, Disposition
    """
    col_ranges = {
        'rm': (0, 38),
        'file_number': (38, 145),
        'name': (145, 280),
        'proc': (280, 318),
        'ic': (318, 345),
        'cnt': (345, 375),
        'description': (375, 470),
        'included': (470, 530),
        'agency_file': (530, 650),
        'rslt': (650, 690),
        'next_appearance': (690, 850),
        'disposition': (850, 1008)
    }

    records = []
    metadata = {
        'court_name': '',
        'court_date': '',
        'report_id': '',
        'report_date': '',
        'total_pages': 0
    }

    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        metadata['total_pages'] = len(pdf.pages)
        for page in pdf.pages:
            raw_text = page.extract_text() or ""
            for line in raw_text.splitlines():
                if "For Files Appearing on" in line:
                    m_date = re.search(r"For Files Appearing on\s*([0-9A-Za-z-]+)", line)
                    if m_date and not metadata['court_date']:
                        metadata['court_date'] = m_date.group(1).strip()
                if "Report Id:" in line or "Report ID:" in line:
                    m_rep = re.search(r"Report Id:\s*([^\s]+)\s+Report Date:\s*(.+)", line, re.IGNORECASE)
                    if m_rep:
                        metadata['report_id'] = m_rep.group(1).strip()
                        metadata['report_date'] = m_rep.group(2).strip()

            words = page.extract_words()
            top_words = [w for w in words if w['top'] < 30]
            if top_words and not metadata['court_name']:
                title_line = " ".join(w['text'] for w in sorted(top_words, key=lambda x: x['x0']))
                title_clean = re.sub(r'\s+Page.*$', '', title_line).strip()
                if title_clean:
                    metadata['court_name'] = title_clean

            body_words = [w for w in words if 70 <= w['top'] <= 560]
            lines = _group_words_by_line(body_words, y_tolerance=4.0)

            current_rm = ""
            current_rec = None

            for l_words in lines:
                line_str = " ".join(w['text'] for w in sorted(l_words, key=lambda x: x['x0']))
                if "File Number" in line_str and "Description" in line_str:
                    continue

                cols = _assign_words_to_columns(l_words, col_ranges)

                if cols['rm']:
                    current_rm = cols['rm']

                is_new_file = bool(cols['file_number'] and '-' in cols['file_number'])
                is_new_count = bool(cols['cnt'] and cols['cnt'].isdigit())

                if is_new_file or is_new_count:
                    if current_rec:
                        records.append(current_rec)

                    prev_file = current_rec['file_number'] if current_rec else ""
                    prev_name = current_rec['name'] if current_rec else ""

                    current_rec = {
                        'court_level': court_level,
                        'court_name': clean_court_name_from_filename(filename) if filename else metadata['court_name'],
                        'room': current_rm,
                        'court_date': metadata['court_date'],
                        'session_time': '',
                        'item_no': '',
                        'file_number': cols['file_number'] or prev_file,
                        'name': cols['name'] or prev_name,
                        'proc': cols['proc'],
                        'ic': cols['ic'],
                        'counsel': '',
                        'plea': '',
                        'elec': '',
                        'age': '',
                        'rsn': '',
                        'cnt': cols['cnt'],
                        'charge_description': cols['description'],
                        'lesser_included': cols['included'],
                        'vc': '',
                        'location_of_offence': '',
                        'agency_file': cols['agency_file'],
                        'result': cols['rslt'],
                        'next_appearance': cols['next_appearance'],
                        'disposition': cols['disposition'],
                        'status': 'Completed' if cols['disposition'] else ('Adjourned' if cols['rslt'] == 'IBJ' else 'Concluded'),
                        'source_filename': filename
                    }
                elif current_rec:
                    # Continuation lines
                    if cols['name']:
                        current_rec['name'] += " " + cols['name']
                    if cols['description']:
                        # May contain location like "Richmond BC"
                        if "BC" in cols['description']:
                            current_rec['location_of_offence'] = (current_rec['location_of_offence'] + " " + cols['description']).strip()
                        else:
                            current_rec['charge_description'] += " " + cols['description']
                    if cols['agency_file']:
                        current_rec['agency_file'] += " " + cols['agency_file']
                    if cols['next_appearance']:
                        current_rec['next_appearance'] += " " + cols['next_appearance']
                    if cols['disposition']:
                        current_rec['disposition'] += " " + cols['disposition']

            if current_rec:
                records.append(current_rec)

    return metadata, records
