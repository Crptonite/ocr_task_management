from flask import Flask, render_template, request, redirect, url_for, session, flash  # Flask framework components
import sqlite3  # The database module
import os  # Operating system operations for file/path handling
import re  # Regular expressions for quantity parsing
from datetime import datetime

LABOR_HOURLY_RATE = 60.0
DEFAULT_PART_PRICE = 45.0
PART_PRICE_CATALOG = {
    'engine oil': 65.0,
    'oil filter': 25.0,
    'air filter': 35.0,
    'brake pads': 90.0,
    'spark plugs': 28.0,
    'chain kit': 220.0,
    'sprocket': 95.0,
    'battery': 120.0,
    'coolant': 30.0
}


def get_available_parts_options():
    return [
        {'name': 'Engine Oil', 'example_price': PART_PRICE_CATALOG['engine oil']},
        {'name': 'Oil Filter', 'example_price': PART_PRICE_CATALOG['oil filter']},
        {'name': 'Air Filter', 'example_price': PART_PRICE_CATALOG['air filter']},
        {'name': 'Brake Pads', 'example_price': PART_PRICE_CATALOG['brake pads']},
        {'name': 'Spark Plugs', 'example_price': PART_PRICE_CATALOG['spark plugs']},
        {'name': 'Chain Kit', 'example_price': PART_PRICE_CATALOG['chain kit']},
        {'name': 'Sprocket', 'example_price': PART_PRICE_CATALOG['sprocket']},
        {'name': 'Battery', 'example_price': PART_PRICE_CATALOG['battery']},
    ]


def get_part_unit_price(part_name: str) -> float:
    if not part_name:
        return DEFAULT_PART_PRICE
    normalized = part_name.strip().lower()
    for key, value in PART_PRICE_CATALOG.items():
        if key in normalized:
            return value
    return DEFAULT_PART_PRICE


def generate_job_card_number(rfq_id: int) -> str:
    return f"#RFQ-{rfq_id:05d}"


def validate_labor_task_name(task_name: str):
    if not task_name:
        return False, 'Labour task name is required'

    normalized = task_name.strip().lower()
    disallowed_keywords = ['spray paint', 'spray painting', 'painting']
    if any(keyword in normalized for keyword in disallowed_keywords):
        return False, 'Use Parts for spray painting-type items; labour is for service work only.'

    return True, ''

# Helper function to parse quantity (e.g., "4L" for liters) - from Javier's RFQ Merging
def parse_quantity(quantity: str):
    if not quantity:
        return None, None

    q = quantity.strip().upper().replace(" ", "")
    m = re.match(r"^(\d+(\.\d+)?)(L)?$", q)
    if not m:
        return None, None

    qty_num = float(m.group(1))
    unit = "L" if m.group(3) == "L" else None

    if qty_num <= 0:
        return None, None

    # If no unit, enforce whole number (parts count)
    if unit is None and not qty_num.is_integer():
        return None, None

    return qty_num, unit

# Initialise the Flask application
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.join(os.path.dirname(BASE_DIR), 'frontend')

# Templates live in ../frontend so the app works from any working directory
app = Flask(__name__, template_folder=FRONTEND_DIR)
app.secret_key = os.environ.get('WORKSHOP_SECRET_KEY', 'wdpassignment_secret_key_2026')  # Secret key for session management
app.config['DATABASE'] = os.path.join(BASE_DIR, 'workshop_system.db')  # Absolute path so the DB is not created wherever you launch from
app.config['SESSION_PERMANENT'] = False  # Session expires when browser is closed
app.config['PERMANENT_SESSION_LIFETIME'] = 560  # Session timeout in seconds (8 minutes) if permanent

# Route for job history (placeholder)
@app.route('/job_history')
def job_history():
    if 'user_id' not in session:
        flash('Please login first', 'warning')
        return redirect(url_for('login'))
    
    search_query = request.args.get('search', '')
    
    conn = get_db()
    history_union_sql = '''
        SELECT
            ('quotation-' || q.id) AS id,
            q.customer_name AS customer_name,
            TRIM(COALESCE(q.vehicle_year, '') || ' ' || COALESCE(q.vehicle_make, '') || ' ' || COALESCE(q.vehicle_model, '')) AS vehicle_info,
            COALESCE(q.reported_issues, '') AS issues,
            COALESCE((
                SELECT GROUP_CONCAT(qp.part_name, ', ')
                FROM quotation_parts qp
                WHERE qp.quotation_id = q.id AND qp.item_type = 'part'
            ), '') AS parts_used,
            COALESCE(q.total_cost, 0) AS total_amount,
            COALESCE(NULLIF(q.created_date, ''), date(q.created_at), date('now')) AS job_date
        FROM quotations q

        UNION ALL

        SELECT
            ('rfq-' || r.id) AS id,
            r.customer_name AS customer_name,
            TRIM(COALESCE(r.motorcycle_brand, '') || ' ' || COALESCE(r.motorcycle_model, '')) AS vehicle_info,
            '' AS issues,
            COALESCE((
                SELECT GROUP_CONCAT(rp.part_description, ', ')
                FROM rfq_parts rp
                WHERE rp.rfq_id = r.id
            ), '') AS parts_used,
            COALESCE(r.total_price, 0) AS total_amount,
            COALESCE(NULLIF(r.created_date, ''), date('now')) AS job_date
        FROM rfq r

        UNION ALL

        SELECT
            ('job-' || j.id) AS id,
            j.customer_name AS customer_name,
            COALESCE(j.vehicle_info, '') AS vehicle_info,
            COALESCE(j.issues, '') AS issues,
            COALESCE(j.parts_used, '') AS parts_used,
            COALESCE(j.total_amount, 0) AS total_amount,
            COALESCE(NULLIF(j.job_date, ''), date('now')) AS job_date
        FROM job_history j
    '''

    total_jobs = conn.execute(f'SELECT COUNT(*) FROM ({history_union_sql}) AS history').fetchone()[0]

    if search_query:
        like_query = '%' + search_query + '%'
        jobs = conn.execute(f'''
            SELECT * FROM ({history_union_sql}) AS history
            WHERE customer_name LIKE ? OR vehicle_info LIKE ? OR issues LIKE ? OR parts_used LIKE ?
            ORDER BY job_date DESC, id DESC
        ''', (like_query, like_query, like_query, like_query)).fetchall()
    else:
        jobs = conn.execute(f'''
            SELECT * FROM ({history_union_sql}) AS history
            ORDER BY job_date DESC, id DESC
        ''').fetchall()
    
    conn.close()
    
    return render_template('job_history.html', 
                          jobs=jobs, 
                          total_jobs=total_jobs, 
                          search_query=search_query)

def init_db():
    # Connect to SQLite database
    conn = sqlite3.connect(app.config['DATABASE'])
    cursor = conn.cursor()
    
    # Create users table if it doesn't exist
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            email TEXT NOT NULL,
            phone TEXT,
            role TEXT DEFAULT 'staff',
            is_admin_account INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Create quotations table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS quotations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_name TEXT NOT NULL,
            customer_email TEXT,
            phone_number TEXT,
            vehicle_make TEXT NOT NULL,
            vehicle_model TEXT NOT NULL,
            vehicle_year INTEGER NOT NULL,
            reported_issues TEXT,
            labor_cost REAL DEFAULT 0,
            parts_cost REAL DEFAULT 0,
            total_cost REAL DEFAULT 0,
            status TEXT DEFAULT 'draft',
            created_date TEXT DEFAULT (date('now')),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Create quotation_parts table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS quotation_parts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            quotation_id INTEGER NOT NULL,
            part_name TEXT NOT NULL,
            part_number TEXT,
            item_type TEXT DEFAULT 'part',
            labor_hours REAL DEFAULT 0,
            part_price REAL NOT NULL,
            quantity INTEGER DEFAULT 1,
            FOREIGN KEY (quotation_id) REFERENCES quotations (id)
        )
    ''')
    
    # Create job_history table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS job_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_name TEXT NOT NULL,
            vehicle_info TEXT NOT NULL,
            issues TEXT,
            parts_used TEXT,
            total_amount REAL DEFAULT 0,
            job_date TEXT DEFAULT (date('now'))
        )
    ''')
    
    # Create RFQ table (from Ryan)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS rfq (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_name TEXT NOT NULL,
            customer_email TEXT NOT NULL,
            phone_number TEXT NOT NULL,
            motorcycle_brand TEXT NOT NULL,
            motorcycle_model TEXT NOT NULL,
            total_price REAL DEFAULT 0,
            created_date TEXT DEFAULT (date('now'))
        )
    ''')
    
    # Create RFQ parts table (from Ryan)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS rfq_parts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rfq_id INTEGER NOT NULL,
            part_description TEXT NOT NULL,
            manufacturer_name TEXT,
            part_number TEXT,
            action TEXT,
            quantity INTEGER DEFAULT 1,
            price REAL DEFAULT 0,
            FOREIGN KEY (rfq_id) REFERENCES rfq (id)
        )
    ''')
    
    # Create Job Cards table (from Javier - for RFQ merge system)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS job_cards (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_card_number TEXT UNIQUE NOT NULL,
            customer_name TEXT NOT NULL,
            vehicle_model TEXT NOT NULL,
            issue_description TEXT,
            date_created TEXT NOT NULL,
            status TEXT DEFAULT 'Pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Create Mechanic RFQ - Labor Services table (from Javier)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS mechanic_labor (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_card_id INTEGER NOT NULL,
            quotation_part_id INTEGER,
            service_name TEXT NOT NULL,
            quantity INTEGER DEFAULT 1,
            price REAL NOT NULL,
            FOREIGN KEY (job_card_id) REFERENCES job_cards(id)
        )
    ''')
    
    # Create Mechanic RFQ - Non-Stockable Parts table (from Javier)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS mechanic_nonstockable (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_card_id INTEGER NOT NULL,
            quotation_part_id INTEGER,
            part_name TEXT NOT NULL,
            quantity INTEGER DEFAULT 1,
            price REAL NOT NULL,
            FOREIGN KEY (job_card_id) REFERENCES job_cards(id)
        )
    ''')
    
    # Create Spare Parts RFQ table (from Javier)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS spare_parts_rfq (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_card_id INTEGER NOT NULL,
            quotation_part_id INTEGER,
            part_name TEXT NOT NULL,
            quantity TEXT NOT NULL,
            unit_price REAL NOT NULL,
            total_price REAL NOT NULL,
            is_nonstockable INTEGER DEFAULT 0,
            FOREIGN KEY (job_card_id) REFERENCES job_cards(id)
        )
    ''')

    # Backwards-compatible migrations for older databases
    existing_quotation_part_cols = {
        row[1] for row in cursor.execute('PRAGMA table_info(quotation_parts)').fetchall()
    }
    if 'part_number' not in existing_quotation_part_cols:
        cursor.execute("ALTER TABLE quotation_parts ADD COLUMN part_number TEXT")
    if 'item_type' not in existing_quotation_part_cols:
        cursor.execute("ALTER TABLE quotation_parts ADD COLUMN item_type TEXT DEFAULT 'part'")
    if 'labor_hours' not in existing_quotation_part_cols:
        cursor.execute("ALTER TABLE quotation_parts ADD COLUMN labor_hours REAL DEFAULT 0")

    existing_quotation_cols = {row[1] for row in cursor.execute('PRAGMA table_info(quotations)').fetchall()}
    if 'customer_email' not in existing_quotation_cols:
        cursor.execute("ALTER TABLE quotations ADD COLUMN customer_email TEXT")
    if 'phone_number' not in existing_quotation_cols:
        cursor.execute("ALTER TABLE quotations ADD COLUMN phone_number TEXT")
    if 'job_card_id' not in existing_quotation_cols:
        cursor.execute("ALTER TABLE quotations ADD COLUMN job_card_id INTEGER")

    existing_labor_cols = {row[1] for row in cursor.execute('PRAGMA table_info(mechanic_labor)').fetchall()}
    if 'quotation_part_id' not in existing_labor_cols:
        cursor.execute("ALTER TABLE mechanic_labor ADD COLUMN quotation_part_id INTEGER")

    existing_nonstockable_cols = {row[1] for row in cursor.execute('PRAGMA table_info(mechanic_nonstockable)').fetchall()}
    if 'quotation_part_id' not in existing_nonstockable_cols:
        cursor.execute("ALTER TABLE mechanic_nonstockable ADD COLUMN quotation_part_id INTEGER")

    existing_spare_part_cols = {row[1] for row in cursor.execute('PRAGMA table_info(spare_parts_rfq)').fetchall()}
    if 'quotation_part_id' not in existing_spare_part_cols:
        cursor.execute("ALTER TABLE spare_parts_rfq ADD COLUMN quotation_part_id INTEGER")
    
    # Create Merged RFQ table (from Javier)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS merged_rfq (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_card_id INTEGER NOT NULL,
            item_type TEXT NOT NULL,
            item_name TEXT NOT NULL,
            quantity TEXT NOT NULL,
            unit_price REAL NOT NULL,
            total_price REAL NOT NULL,
            is_nonstockable INTEGER DEFAULT 0,
            merged_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (job_card_id) REFERENCES job_cards(id)
        )
    ''')
    
    # Checks if admin user accounts already exists to avoid duplicate accounts
    cursor.execute("SELECT COUNT(*) FROM users WHERE username = 'admin'")
    if cursor.fetchone()[0] == 0:
        # Insert default admin account
        cursor.execute(
            "INSERT INTO users (username, password, email, role, is_admin_account) VALUES (?, ?, ?, ?, ?)",
            ('admin', '@dmin123', 'admin@workshop.com', 'admin', 1)
        )
        # Insert default staff accounts
        cursor.execute(
            "INSERT INTO users (username, password, email, role, is_admin_account) VALUES (?, ?, ?, ?, ?)",
            ('StaffAcc1', 'st@ff1st', 'staff1@workshop.com', 'staff', 0)
        )
        cursor.execute(
            "INSERT INTO users (username, password, email, role, is_admin_account) VALUES (?, ?, ?, ?, ?)",
            ('StaffAcc2', 'st@ff2nd', 'staff2@workshop.com', 'staff', 0)
        )
        cursor.execute(
            "INSERT INTO users (username, password, email, role, is_admin_account) VALUES (?, ?, ?, ?, ?)",
            ('StaffAcc3', 'st@ff3rd', 'staff3@workshop.com', 'staff', 0)
        )
    
    # Sample data seeding disabled for proof-of-concept reset
    cursor.execute("SELECT COUNT(*) FROM quotations")
    if False and cursor.fetchone()[0] == 0:
        # Insert sample quotations
        sample_quotations = [
            ('John Tan', 'Toyota', 'Camry', 2020, 'Engine oil leak, brake pads worn', 150.00, 280.00, 430.00, 'pending', '2026-02-10'),
            ('Sarah Lim', 'Honda', 'Civic', 2019, 'Air conditioning not cooling, battery weak', 80.00, 350.00, 430.00, 'approved', '2026-02-12'),
            ('Michael Wong', 'BMW', '3 Series', 2021, 'Suspension noise, tire alignment needed', 200.00, 450.00, 650.00, 'draft', '2026-02-14'),
            ('Emily Chen', 'Mercedes', 'C200', 2018, 'Full service, spark plugs replacement', 180.00, 320.00, 500.00, 'completed', '2026-02-08'),
            ('David Lee', 'Mazda', 'CX-5', 2022, 'Brake fluid change, headlight bulb replacement', 60.00, 95.00, 155.00, 'pending', '2026-02-15'),
        ]
        
        for q in sample_quotations:
            cursor.execute('''
                INSERT INTO quotations (customer_name, vehicle_make, vehicle_model, vehicle_year, 
                                       reported_issues, labor_cost, parts_cost, total_cost, status, created_date)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', q)
        
        # Insert sample parts for quotations
        sample_parts = [
            # Parts for John Tan's quotation (id=1)
            (1, 'Engine Oil 5W-30', 65.00, 4),
            (1, 'Oil Filter', 15.00, 1),
            (1, 'Brake Pads (Front)', 45.00, 1),
            # Parts for Sarah Lim's quotation (id=2)
            (2, 'AC Compressor', 280.00, 1),
            (2, 'Car Battery 60AH', 70.00, 1),
            # Parts for Michael Wong's quotation (id=3)
            (3, 'Front Shock Absorber', 180.00, 2),
            (3, 'Wheel Alignment Service', 90.00, 1),
            # Parts for Emily Chen's quotation (id=4)
            (4, 'Engine Oil 5W-40', 75.00, 5),
            (4, 'Oil Filter Premium', 25.00, 1),
            (4, 'Air Filter', 40.00, 1),
            (4, 'Spark Plugs Iridium', 45.00, 4),
            # Parts for David Lee's quotation (id=5)
            (5, 'Brake Fluid DOT4', 25.00, 2),
            (5, 'Headlight Bulb H7', 45.00, 1),
        ]
        
        for p in sample_parts:
            cursor.execute('''
                INSERT INTO quotation_parts (quotation_id, part_name, part_price, quantity)
                VALUES (?, ?, ?, ?)
            ''', p)
    
    # Sample data seeding disabled for proof-of-concept reset
    cursor.execute("SELECT COUNT(*) FROM job_history")
    if False and cursor.fetchone()[0] == 0:
        # Insert sample job history
        sample_jobs = [
            ('Robert Ng', '2017 Nissan Qashqai', 'Transmission fluid change, air filter replacement', 'Transmission Fluid x2, Air Filter x1', 285.00, '2026-01-25'),
            ('Amanda Koh', '2019 Hyundai Tucson', 'Full brake service, battery replacement', 'Brake Pads x4, Brake Rotors x2, Battery 70AH x1', 520.00, '2026-02-01'),
        ]
        
        for job in sample_jobs:
            cursor.execute('''
                INSERT INTO job_history (customer_name, vehicle_info, issues, parts_used, total_amount, job_date)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', job)
    
    # Sample data seeding disabled for proof-of-concept reset
    cursor.execute("SELECT COUNT(*) FROM rfq")
    if False and cursor.fetchone()[0] == 0:
        # Insert sample RFQs
        sample_rfqs = [
            ('James Wong', 'james@email.com', '91234567', 'Yamaha', 'YZF-R15', 385.00, '2026-02-10'),
            ('Lisa Tan', 'lisa@email.com', '98765432', 'Honda', 'CBR150R', 520.00, '2026-02-12'),
        ]
        
        for rfq in sample_rfqs:
            cursor.execute('''
                INSERT INTO rfq (customer_name, customer_email, phone_number, motorcycle_brand, motorcycle_model, total_price, created_date)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', rfq)
        
        # Insert sample RFQ parts
        sample_rfq_parts = [
            (1, 'Engine Oil 10W-40', 'Yamaha', 'YAM-OIL-001', 'Replace', 4, 25.00),
            (1, 'Oil Filter', 'Yamaha', 'YAM-FIL-002', 'Replace', 1, 35.00),
            (1, 'Brake Pads Front', 'Brembo', 'BRM-PAD-001', 'Replace', 1, 150.00),
            (2, 'Chain Kit', 'RK', 'RK-CHN-001', 'Replace', 1, 280.00),
            (2, 'Sprocket Set', 'JT', 'JT-SPR-001', 'Replace', 1, 120.00),
            (2, 'Chain Lubricant', 'Motul', 'MOT-LUB-001', 'Service', 2, 30.00),
        ]
        
        for part in sample_rfq_parts:
            cursor.execute('''
                INSERT INTO rfq_parts (rfq_id, part_description, manufacturer_name, part_number, action, quantity, price)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', part)
    
    # Sample data seeding disabled for proof-of-concept reset
    cursor.execute("SELECT COUNT(*) FROM job_cards")
    if False and cursor.fetchone()[0] == 0:
        # Insert sample job cards
        cursor.execute('''
            INSERT INTO job_cards (job_card_number, customer_name, vehicle_model, issue_description, date_created, status)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', ('#2025-0111', 'Marcus Tan', 'Honda CBR150R', 'Oil Change + Brake Replacement', '15 Dec 2025', 'Pending'))
        job_card_1_id = cursor.lastrowid
        
        cursor.execute('''
            INSERT INTO job_cards (job_card_number, customer_name, vehicle_model, issue_description, date_created, status)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', ('#2025-0211', 'Adrian Lim', 'BMW S1000RR', 'Chain Replacement + Oil Change', '15 Dec 2025', 'Pending'))
        job_card_2_id = cursor.lastrowid
        
        # Insert mechanic labor services for job card 1
        for service in [('Engine Oil Change', 1, 50.00), ('Brake Pads Inspection', 1, 30.00), ('Brake Pads Replacement', 1, 80.00)]:
            cursor.execute('INSERT INTO mechanic_labor (job_card_id, service_name, quantity, price) VALUES (?, ?, ?, ?)',
                          (job_card_1_id, service[0], service[1], service[2]))
        
        # Insert mechanic non-stockable for job card 1
        cursor.execute('INSERT INTO mechanic_nonstockable (job_card_id, part_name, quantity, price) VALUES (?, ?, ?, ?)',
                      (job_card_1_id, 'Red Rear Brake Pad', 1, 85.00))
        
        # Insert spare parts for job card 1
        for part in [('Engine Oil (4L)', '4L', 65.00, 65.00, 0), ('Front Brake Pads', '1', 75.00, 75.00, 0), ('Rear Brake Pads (Non Stockable)', '1', 85.00, 85.00, 1)]:
            cursor.execute('INSERT INTO spare_parts_rfq (job_card_id, part_name, quantity, unit_price, total_price, is_nonstockable) VALUES (?, ?, ?, ?, ?, ?)',
                          (job_card_1_id, part[0], part[1], part[2], part[3], part[4]))
        
        # Insert mechanic labor services for job card 2
        for service in [('Chain Inspection', 1, 40.00), ('Chain Replacement Service', 1, 120.00), ('Engine Oil Change', 1, 50.00)]:
            cursor.execute('INSERT INTO mechanic_labor (job_card_id, service_name, quantity, price) VALUES (?, ?, ?, ?)',
                          (job_card_2_id, service[0], service[1], service[2]))
        
        # Insert spare parts for job card 2
        for part in [('Chain Kit', '1', 200.00, 200.00, 0), ('Engine Oil (4L)', '4L', 65.00, 65.00, 0), ('Oil Filter', '1', 25.00, 25.00, 0)]:
            cursor.execute('INSERT INTO spare_parts_rfq (job_card_id, part_name, quantity, unit_price, total_price, is_nonstockable) VALUES (?, ?, ?, ?, ?, ?)',
                          (job_card_2_id, part[0], part[1], part[2], part[3], part[4]))
    
    # Save changes and close connection
    conn.commit()
    conn.close()

# Function to get a database connection
def get_db():
    # Connect to the SQLite database with timeout to prevent lock issues
    conn = sqlite3.connect(app.config['DATABASE'], timeout=10)  # 10 second timeout for database locks
    # Enable returning rows as dictionary objects
    conn.row_factory = sqlite3.Row
    return conn


def get_or_create_job_card_for_rfq(conn, rfq_row):
    job_card_id = rfq_row['job_card_id'] if 'job_card_id' in rfq_row.keys() else None
    if job_card_id:
        existing = conn.execute('SELECT id FROM job_cards WHERE id = ?', (job_card_id,)).fetchone()
        if existing:
            return existing['id']

    job_card_number = generate_job_card_number(rfq_row['id'])
    existing_by_number = conn.execute(
        'SELECT id FROM job_cards WHERE job_card_number = ?', (job_card_number,)
    ).fetchone()
    if existing_by_number:
        conn.execute('UPDATE quotations SET job_card_id = ? WHERE id = ?', (existing_by_number['id'], rfq_row['id']))
        return existing_by_number['id']

    vehicle_text = f"{rfq_row['vehicle_year']} {rfq_row['vehicle_make']} {rfq_row['vehicle_model']}".strip()
    date_created = rfq_row['created_date'] if rfq_row['created_date'] else 'N/A'

    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO job_cards (job_card_number, customer_name, vehicle_model, issue_description, date_created, status)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (job_card_number, rfq_row['customer_name'], vehicle_text, rfq_row['reported_issues'], date_created, 'Pending'))
    new_job_card_id = cursor.lastrowid
    conn.execute('UPDATE quotations SET job_card_id = ? WHERE id = ?', (new_job_card_id, rfq_row['id']))
    return new_job_card_id


def sync_part_to_spare_parts_rfq(conn, job_card_id, quotation_part_id, part_name, quantity):
    unit_price = get_part_unit_price(part_name)
    total_price = unit_price * float(quantity)
    existing = conn.execute(
        'SELECT id FROM spare_parts_rfq WHERE quotation_part_id = ? AND job_card_id = ?',
        (quotation_part_id, job_card_id)
    ).fetchone()
    if existing:
        conn.execute('''
            UPDATE spare_parts_rfq
            SET part_name = ?, quantity = ?, unit_price = ?, total_price = ?, is_nonstockable = 0
            WHERE id = ?
        ''', (part_name, str(quantity), unit_price, total_price, existing['id']))
    else:
        conn.execute('''
            INSERT INTO spare_parts_rfq (job_card_id, quotation_part_id, part_name, quantity, unit_price, total_price, is_nonstockable)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (job_card_id, quotation_part_id, part_name, str(quantity), unit_price, total_price, 0))


def sync_labor_to_mechanic_rfq(conn, job_card_id, quotation_part_id, service_name, labor_hours):
    total_cost = float(labor_hours) * LABOR_HOURLY_RATE
    existing = conn.execute(
        'SELECT id FROM mechanic_labor WHERE quotation_part_id = ? AND job_card_id = ?',
        (quotation_part_id, job_card_id)
    ).fetchone()
    if existing:
        conn.execute('''
            UPDATE mechanic_labor
            SET service_name = ?, quantity = ?, price = ?
            WHERE id = ?
        ''', (service_name, labor_hours, LABOR_HOURLY_RATE, existing['id']))
    else:
        conn.execute('''
            INSERT INTO mechanic_labor (job_card_id, quotation_part_id, service_name, quantity, price)
            VALUES (?, ?, ?, ?, ?)
        ''', (job_card_id, quotation_part_id, service_name, labor_hours, LABOR_HOURLY_RATE))

    return total_cost

# Simple password validation function
def validate_password(password):
    # Check length
    if len(password) < 8:
        return False, "Password must be at least 8 characters"
    # Check for letter
    if not any(c.isalpha() for c in password):
        return False, "Password must contain at least one letter"
    # Check for number
    if not any(c.isdigit() for c in password):
        return False, "Password must contain at least one number"
    # Check for special character
    if not any(c in '!@#$%^&*' for c in password):
        return False, "Password must contain at least one special character (!@#$%^&*)"
    return True, "Valid"

# Route for home page redirects to home if logged in, otherwise to login page
@app.route('/')
def index():
    # Check if user is already logged in
    if 'user_id' in session:
        # Redirect to home if user is logged in
        return redirect(url_for('home'))
    # Redirect to login page if user is not logged in
    return redirect(url_for('login'))

# Route for login page handles both GET requests and POST requests
@app.route('/login', methods=['GET', 'POST'])
def login():
    # Process login form submission
    if request.method == 'POST':
        # Get username and password from the form
        username = request.form['username']
        password = request.form['password']
        
        # Query database for user with matching username and password
        conn = get_db()
        user = conn.execute(
            'SELECT * FROM users WHERE username = ? AND password = ?',
            (username, password)
        ).fetchone()
        conn.close()
        
        # If user found, create session and redirect to home
        if user:
            session.permanent = False  # Session expires when browser closes
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['role'] = user['role']
            flash(f'Welcome back, {username}!', 'success')
            return redirect(url_for('home'))
        # If user not found, show error message
        else:
            flash('Invalid username or password', 'danger')
    
    # Display login template for GET requests
    return render_template('login.html')

# Route to change admin role between admin and staff
@app.route('/switch_role', methods=['GET', 'POST'])
def switch_role():
    # Check if user is logged in
    if 'user_id' not in session:
        flash('Please login first', 'warning')
        return redirect(url_for('login'))
    
    # Check if user is an admin account (can switch roles)
    conn = get_db()
    user = conn.execute('SELECT is_admin_account FROM users WHERE id = ?', (session.get('user_id'),)).fetchone()
    conn.close()
    
    if not user or not user['is_admin_account']:
        flash('Only admin accounts can switch roles', 'danger')
        return redirect(url_for('home'))
    
    # Process role switch form submission
    if request.method == 'POST':
        # Get admin account's new role
        new_role = request.form.get('new_role', 'test_staff')
        
        # Validate role is either admin or test_staff
        if new_role not in ['admin', 'test_staff']:
            flash('Invalid role selected', 'danger')
            return redirect(url_for('switch_role'))
        
        # Update user role in database
        try:
            conn = get_db()
            conn.execute('UPDATE users SET role = ? WHERE id = ?', (new_role, session.get('user_id')))
            conn.commit()
            conn.close()
            # Update session role
            session['role'] = new_role
            flash(f'Role changed to {new_role} successfully', 'success')
            return redirect(url_for('home'))
        except Exception as e:
            flash('Database error occurred', 'danger')
            return redirect(url_for('switch_role'))
    
    # Display role switch template for GET requests
    return render_template('switch_role.html', current_role=session.get('role'))

# Route for home - displays main page for logged-in users
@app.route('/home')
@app.route('/dashboard')  # Keep for backwards compatibility
def home():
    # Check if user is logged in
    if 'user_id' not in session:
        flash('Please login first', 'warning')
        return redirect(url_for('login'))
    
    # Get database statistics for home display
    conn = get_db()
    # Count total number of users in system
    total_users = conn.execute('SELECT COUNT(*) FROM users').fetchone()[0]
    # Count total number of staff users
    total_staff = conn.execute("SELECT COUNT(*) FROM users WHERE role = 'staff'").fetchone()[0]
    # Get 5 most recently created users
    recent_users = conn.execute(
        'SELECT username, email, role, phone FROM users ORDER BY created_at DESC LIMIT 5'
    ).fetchall()
    conn.close()
    
    # Display home template with statistics and user information
    return render_template('home.html',
                         username=session.get('username'),
                         role=session.get('role'),
                         total_users=total_users,
                         total_staff=total_staff,
                         recent_users=recent_users)

# Route to display all users admin only access
@app.route('/users')
def users():
    # Check if user is logged in
    if 'user_id' not in session:
        flash('Please login first', 'warning')
        return redirect(url_for('login'))
    
    # Check if user has admin role
    if session.get('role') != 'admin':
        flash('Admin access required', 'danger')
        return redirect(url_for('home'))
    
    # Get all users from database, ordered by creation date
    conn = get_db()
    users_list = conn.execute('SELECT * FROM users ORDER BY created_at DESC').fetchall()
    conn.close()
    
    # Display users template with full user list
    return render_template('users.html', users=users_list)


# Route for creating a new mechanic RFQ
@app.route('/new_quotation', methods=['GET', 'POST'])
def new_quotation():
    if 'user_id' not in session:
        flash('Please login first', 'warning')
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        customer_name = (request.form.get('customer_name') or '').strip()
        customer_email = (request.form.get('customer_email') or '').strip()
        phone_number = (request.form.get('phone_number') or '').strip()
        vehicle_make = (request.form.get('vehicle_make') or '').strip()
        vehicle_model = (request.form.get('vehicle_model') or '').strip()
        vehicle_year = (request.form.get('vehicle_year') or '').strip()
        reported_issues = (request.form.get('reported_issues') or '').strip()

        if not customer_name or not customer_email or not phone_number or not vehicle_make or not vehicle_model or not vehicle_year or not reported_issues:
            flash('Please fill in all required fields before continuing.', 'danger')
            return render_template('new_quotation.html')

        if '@' not in customer_email or '.' not in customer_email.split('@')[-1]:
            flash('Please enter a valid customer email.', 'danger')
            return render_template('new_quotation.html')

        phone_digits = ''.join(char for char in phone_number if char.isdigit())
        if len(phone_digits) < 8:
            flash('Please enter a valid customer phone number.', 'danger')
            return render_template('new_quotation.html')

        session['pending_rfq'] = {
            'customer_name': customer_name,
            'customer_email': customer_email,
            'phone_number': phone_number,
            'vehicle_make': vehicle_make,
            'vehicle_model': vehicle_model,
            'vehicle_year': vehicle_year,
            'reported_issues': reported_issues,
            'parts': [],
            'labor': [],
        }
        session.modified = True
        return redirect(url_for('rfq_parts_builder'))
    
    return render_template('new_quotation.html')


@app.route('/rfq_parts', methods=['GET', 'POST'])
def rfq_parts_builder():
    if 'user_id' not in session:
        flash('Please login first', 'warning')
        return redirect(url_for('login'))

    pending_rfq = session.get('pending_rfq')
    if not pending_rfq:
        flash('Start RFQ creation from the dashboard first.', 'warning')
        return redirect(url_for('new_quotation'))

    pending_rfq.setdefault('parts', [])
    pending_rfq.setdefault('labor', [])
    available_parts = get_available_parts_options()
    allowed_part_names = {part['name'].lower(): part['name'] for part in available_parts}

    if request.method == 'POST':
        action = (request.form.get('action') or '').strip()

        if action == 'add_part':
            part_name = (request.form.get('part_name') or '').strip()
            part_number = (request.form.get('part_number') or '').strip()
            quantity_raw = (request.form.get('quantity') or '1').strip()
            try:
                quantity = int(quantity_raw)
            except (TypeError, ValueError):
                quantity = 0

            if not part_name:
                flash('Part name is required', 'danger')
            elif part_name.lower() not in allowed_part_names:
                flash('Please select a part from the preset list.', 'danger')
            elif quantity <= 0:
                flash('Quantity must be a positive whole number', 'danger')
            else:
                canonical_part_name = allowed_part_names[part_name.lower()]
                pending_rfq['parts'].append({
                    'part_name': canonical_part_name,
                    'part_number': part_number,
                    'quantity': quantity,
                })

        elif action == 'delete_part':
            try:
                part_index = int(request.form.get('part_index', '-1'))
            except (TypeError, ValueError):
                part_index = -1

            if 0 <= part_index < len(pending_rfq['parts']):
                pending_rfq['parts'].pop(part_index)

        elif action == 'add_labor':
            labor_name = (request.form.get('labor_name') or '').strip()
            labor_hours_raw = (request.form.get('labor_hours') or '').strip()
            try:
                labor_hours = float(labor_hours_raw)
            except (TypeError, ValueError):
                labor_hours = 0

            is_valid_task, labor_message = validate_labor_task_name(labor_name)
            if not is_valid_task:
                flash(labor_message, 'danger')
            elif labor_hours <= 0:
                flash('Labour hours must be a positive number', 'danger')
            else:
                pending_rfq['labor'].append({
                    'labor_name': labor_name,
                    'labor_hours': labor_hours,
                })

        elif action == 'delete_labor':
            try:
                labor_index = int(request.form.get('labor_index', '-1'))
            except (TypeError, ValueError):
                labor_index = -1

            if 0 <= labor_index < len(pending_rfq['labor']):
                pending_rfq['labor'].pop(labor_index)

        elif action == 'create_rfq':
            if not pending_rfq['parts'] and not pending_rfq['labor']:
                flash('Add at least one part or labour item before creating RFQ.', 'danger')
                session['pending_rfq'] = pending_rfq
                session.modified = True
                return redirect(url_for('rfq_parts_builder'))

            conn = get_db()
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO quotations (customer_name, customer_email, phone_number, vehicle_make, vehicle_model, vehicle_year, reported_issues, parts_cost, labor_cost, total_cost, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, 0, 0, 0, ?)
            ''', (
                pending_rfq['customer_name'],
                pending_rfq['customer_email'],
                pending_rfq['phone_number'],
                pending_rfq['vehicle_make'],
                pending_rfq['vehicle_model'],
                pending_rfq['vehicle_year'],
                pending_rfq['reported_issues'],
                'draft'
            ))
            quotation_id = cursor.lastrowid

            rfq_row = conn.execute('SELECT * FROM quotations WHERE id = ?', (quotation_id,)).fetchone()
            job_card_id = get_or_create_job_card_for_rfq(conn, rfq_row)

            for part in pending_rfq['parts']:
                cursor.execute('''
                    INSERT INTO quotation_parts (quotation_id, part_name, part_number, item_type, labor_hours, part_price, quantity)
                    VALUES (?, ?, ?, 'part', 0, 0, ?)
                ''', (quotation_id, part['part_name'], part['part_number'], part['quantity']))
                quotation_part_id = cursor.lastrowid
                sync_part_to_spare_parts_rfq(conn, job_card_id, quotation_part_id, part['part_name'], part['quantity'])

            for labor in pending_rfq['labor']:
                cursor.execute('''
                    INSERT INTO quotation_parts (quotation_id, part_name, part_number, item_type, labor_hours, part_price, quantity)
                    VALUES (?, ?, '', 'labor', ?, 0, ?)
                ''', (quotation_id, labor['labor_name'], labor['labor_hours'], labor['labor_hours']))
                quotation_part_id = cursor.lastrowid
                sync_labor_to_mechanic_rfq(conn, job_card_id, quotation_part_id, labor['labor_name'], labor['labor_hours'])

            parts_total = conn.execute('''
                SELECT COALESCE(SUM(total_price), 0) FROM spare_parts_rfq WHERE job_card_id = ?
            ''', (job_card_id,)).fetchone()[0] or 0
            labor_total = conn.execute('''
                SELECT COALESCE(SUM(quantity * price), 0) FROM mechanic_labor WHERE job_card_id = ?
            ''', (job_card_id,)).fetchone()[0] or 0
            conn.execute(
                'UPDATE quotations SET parts_cost = ?, labor_cost = ?, total_cost = ?, job_card_id = ? WHERE id = ?',
                (parts_total, labor_total, parts_total + labor_total, job_card_id, quotation_id)
            )

            part_names = [part.get('part_name', '').strip() for part in pending_rfq['parts'] if part.get('part_name')]
            labor_names = [labor.get('labor_name', '').strip() for labor in pending_rfq['labor'] if labor.get('labor_name')]
            parts_used_sections = []
            if part_names:
                parts_used_sections.append('Parts: ' + ', '.join(part_names))
            if labor_names:
                parts_used_sections.append('Labour: ' + ', '.join(labor_names))
            parts_used = ' | '.join(parts_used_sections)
            vehicle_info = f"{pending_rfq['vehicle_year']} {pending_rfq['vehicle_make']} {pending_rfq['vehicle_model']}"

            conn.execute('''
                INSERT INTO job_history (customer_name, vehicle_info, issues, parts_used, total_amount, job_date)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                pending_rfq['customer_name'],
                vehicle_info,
                pending_rfq['reported_issues'],
                parts_used,
                parts_total + labor_total,
                datetime.now().strftime('%Y-%m-%d')
            ))

            conn.commit()
            conn.close()

            session.pop('pending_rfq', None)
            session.modified = True
            flash('RFQ created successfully!', 'success')
            return redirect(url_for('edit_quotation', quotation_id=quotation_id))

        session['pending_rfq'] = pending_rfq
        session.modified = True
        return redirect(url_for('rfq_parts_builder'))

    return render_template(
        'rfq_parts_builder.html',
        draft=pending_rfq,
        parts=pending_rfq['parts'],
        labor_items=pending_rfq['labor'],
        available_parts=available_parts
    )

# Route for viewing all mechanic RFQs
@app.route('/rfqs')
def quotations():
    if 'user_id' not in session:
        flash('Please login first', 'warning')
        return redirect(url_for('login'))
    
    search_query = request.args.get('search', '')
    conn = get_db()
    query = 'SELECT * FROM quotations WHERE 1=1'
    params = []
    
    if search_query:
        query += ' AND (customer_name LIKE ? OR vehicle_make LIKE ? OR vehicle_model LIKE ? OR reported_issues LIKE ?)'
        params.extend(['%' + search_query + '%'] * 4)
    
    query += ' ORDER BY created_at DESC'
    quotations_list = conn.execute(query, params).fetchall()
    conn.close()
    
    return render_template('quotations.html', quotations=quotations_list, search_query=search_query)


@app.route('/quotations')
def quotations_legacy_redirect():
    return redirect(url_for('quotations'))

# Route for editing a mechanic RFQ
@app.route('/quotation/edit/<int:quotation_id>', methods=['GET', 'POST'])
def edit_quotation(quotation_id):
    if 'user_id' not in session:
        flash('Please login first', 'warning')
        return redirect(url_for('login'))
    
    conn = get_db()
    quotation = conn.execute('SELECT * FROM quotations WHERE id = ?', (quotation_id,)).fetchone()
    
    if not quotation:
        conn.close()
        flash('RFQ not found', 'danger')
        return redirect(url_for('quotations'))
    
    job_card_id = get_or_create_job_card_for_rfq(conn, quotation)

    if request.method == 'POST':
        entry_type = request.form.get('entry_type', 'part').strip().lower()

        if entry_type == 'part':
            part_name = request.form.get('part_name', '').strip()
            part_number = request.form.get('part_number', '').strip()
            quantity_raw = request.form.get('quantity', '1').strip()

            try:
                quantity = int(quantity_raw)
            except (TypeError, ValueError):
                quantity = 0

            if not part_name:
                flash('Part name is required', 'danger')
            elif quantity <= 0:
                flash('Quantity must be a positive whole number', 'danger')
            else:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO quotation_parts (quotation_id, part_name, part_number, item_type, labor_hours, part_price, quantity)
                    VALUES (?, ?, ?, 'part', 0, 0, ?)
                ''', (quotation_id, part_name, part_number, quantity))
                quotation_part_id = cursor.lastrowid
                sync_part_to_spare_parts_rfq(conn, job_card_id, quotation_part_id, part_name, quantity)
                conn.commit()
                flash('Part added to RFQ successfully!', 'success')

        elif entry_type == 'labor':
            labor_name = request.form.get('labor_name', '').strip()
            labor_hours_raw = request.form.get('labor_hours', '').strip()

            try:
                labor_hours = float(labor_hours_raw)
            except (TypeError, ValueError):
                labor_hours = 0

            is_valid_task, labor_message = validate_labor_task_name(labor_name)
            if not is_valid_task:
                flash(labor_message, 'danger')
            elif labor_hours <= 0:
                flash('Labour hours must be a positive number', 'danger')
            else:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO quotation_parts (quotation_id, part_name, part_number, item_type, labor_hours, part_price, quantity)
                    VALUES (?, ?, '', 'labor', ?, 0, ?)
                ''', (quotation_id, labor_name, labor_hours, labor_hours))
                quotation_part_id = cursor.lastrowid
                sync_labor_to_mechanic_rfq(conn, job_card_id, quotation_part_id, labor_name, labor_hours)
                conn.commit()
                flash('Labour hours added to RFQ successfully!', 'success')

        else:
            flash('Unsupported RFQ entry type', 'danger')

        # Keep totals synchronized for compatibility with existing reports
        parts_total = conn.execute('''
            SELECT COALESCE(SUM(total_price), 0) FROM spare_parts_rfq WHERE job_card_id = ?
        ''', (job_card_id,)).fetchone()[0] or 0
        labor_total = conn.execute('''
            SELECT COALESCE(SUM(quantity * price), 0) FROM mechanic_labor WHERE job_card_id = ?
        ''', (job_card_id,)).fetchone()[0] or 0
        conn.execute(
            'UPDATE quotations SET parts_cost = ?, labor_cost = ?, total_cost = ?, job_card_id = ? WHERE id = ?',
            (parts_total, labor_total, parts_total + labor_total, job_card_id, quotation_id)
        )
        conn.commit()
        
        conn.close()
        return redirect(url_for('edit_quotation', quotation_id=quotation_id))
    
    rfq_items = conn.execute('''
        SELECT * FROM quotation_parts
        WHERE quotation_id = ?
        ORDER BY item_type, id ASC
    ''', (quotation_id,)).fetchall()
    parts = [row for row in rfq_items if row['item_type'] == 'part']
    labor_items = [row for row in rfq_items if row['item_type'] == 'labor']
    conn.close()
    
    return render_template('edit_quotation.html', quotation=quotation, parts=parts, labor_items=labor_items)

# Route for updating labor cost (legacy endpoint kept for compatibility)
@app.route('/quotation/<int:quotation_id>/labor', methods=['POST'])
def update_labor(quotation_id):
    if 'user_id' not in session:
        flash('Please login first', 'warning')
        return redirect(url_for('login'))
    
    labor_cost = float(request.form.get('labor_cost', 0) or 0)
    
    conn = get_db()
    quotation = conn.execute('SELECT parts_cost FROM quotations WHERE id = ?', (quotation_id,)).fetchone()
    parts_cost = quotation['parts_cost'] or 0 if quotation else 0
    total_cost = parts_cost + labor_cost
    
    conn.execute('UPDATE quotations SET labor_cost = ?, total_cost = ? WHERE id = ?', (labor_cost, total_cost, quotation_id))
    conn.commit()
    conn.close()
    
    flash('Labour cost updated!', 'success')
    return redirect(url_for('edit_quotation', quotation_id=quotation_id))

# Route for deleting an RFQ line item
@app.route('/quotation/<int:quotation_id>/part/<int:part_id>/delete', methods=['POST'])
def delete_part(quotation_id, part_id):
    if 'user_id' not in session:
        flash('Please login first', 'warning')
        return redirect(url_for('login'))
    
    conn = get_db()
    part_row = conn.execute('SELECT * FROM quotation_parts WHERE id = ? AND quotation_id = ?', (part_id, quotation_id)).fetchone()
    if not part_row:
        conn.close()
        flash('RFQ item not found', 'danger')
        return redirect(url_for('edit_quotation', quotation_id=quotation_id))

    quotation = conn.execute('SELECT * FROM quotations WHERE id = ?', (quotation_id,)).fetchone()
    if quotation:
        job_card_id = get_or_create_job_card_for_rfq(conn, quotation)
        conn.execute('DELETE FROM mechanic_labor WHERE quotation_part_id = ? AND job_card_id = ?', (part_id, job_card_id))
        conn.execute('DELETE FROM mechanic_nonstockable WHERE quotation_part_id = ? AND job_card_id = ?', (part_id, job_card_id))
        conn.execute('DELETE FROM spare_parts_rfq WHERE quotation_part_id = ? AND job_card_id = ?', (part_id, job_card_id))

    conn.execute('DELETE FROM quotation_parts WHERE id = ?', (part_id,))

    # Recalculate totals from merge-source tables
    if quotation:
        parts_total = conn.execute('''
            SELECT COALESCE(SUM(total_price), 0) FROM spare_parts_rfq WHERE job_card_id = ?
        ''', (job_card_id,)).fetchone()[0] or 0
        labor_total = conn.execute('''
            SELECT COALESCE(SUM(quantity * price), 0) FROM mechanic_labor WHERE job_card_id = ?
        ''', (job_card_id,)).fetchone()[0] or 0
        conn.execute('UPDATE quotations SET parts_cost = ?, labor_cost = ?, total_cost = ? WHERE id = ?',
                     (parts_total, labor_total, parts_total + labor_total, quotation_id))

    conn.commit()
    conn.close()
    
    flash('RFQ item deleted!', 'success')
    return redirect(url_for('edit_quotation', quotation_id=quotation_id))

# Route for deleting a quotation
@app.route('/quotation/<int:quotation_id>/delete', methods=['POST'])
def delete_quotation(quotation_id):
    if 'user_id' not in session:
        flash('Please login first', 'warning')
        return redirect(url_for('login'))
    
    # Only admin can delete quotations
    if session.get('role') != 'admin':
        flash('Only administrators can delete quotations', 'danger')
        return redirect(url_for('quotations'))
    
    conn = get_db()
    quotation = conn.execute('SELECT job_card_id FROM quotations WHERE id = ?', (quotation_id,)).fetchone()
    if quotation and quotation['job_card_id']:
        job_card_id = quotation['job_card_id']
        conn.execute('DELETE FROM merged_rfq WHERE job_card_id = ?', (job_card_id,))
        conn.execute('DELETE FROM mechanic_labor WHERE job_card_id = ?', (job_card_id,))
        conn.execute('DELETE FROM mechanic_nonstockable WHERE job_card_id = ?', (job_card_id,))
        conn.execute('DELETE FROM spare_parts_rfq WHERE job_card_id = ?', (job_card_id,))
        conn.execute('DELETE FROM job_cards WHERE id = ?', (job_card_id,))
    conn.execute('DELETE FROM quotation_parts WHERE quotation_id = ?', (quotation_id,))
    conn.execute('DELETE FROM quotations WHERE id = ?', (quotation_id,))
    conn.commit()
    conn.close()
    
    flash('Quotation deleted!', 'success')
    return redirect(url_for('quotations'))

# Route to add new users admin only, handles both GET and POST
# Only one add_user route
@app.route('/users/add', methods=['GET', 'POST'])
def add_user():
    # Check if user is logged in
    if 'user_id' not in session:
        flash('Please login first', 'warning')
        return redirect(url_for('login'))
    
    # Check if user has admin role
    if session.get('role') != 'admin':
        flash('Admin access required', 'danger')
        return redirect(url_for('home'))
    
    # Process form submission to create new user
    if request.method == 'POST':
        # Get form data
        username = request.form['username']
        password = request.form['password']
        confirm_password = request.form['confirm_password']
        email = request.form['email']
        phone = request.form.get('phone', '')  # Phone is optional
        role = request.form.get('role', 'staff')  # Default role is staff
        
        # Validate passwords match
        if password != confirm_password:
            flash('Passwords do not match!', 'danger')
            return render_template('add_user.html', username=username, email=email, phone=phone, role=role)
        
        # Validate password strength
        is_valid, message = validate_password(password)
        if not is_valid:
            flash(message, 'danger')
            return render_template('add_user.html', username=username, email=email, phone=phone, role=role)
        
        # Try to insert new user into database
        try:
            conn = get_db()
            conn.execute(
                'INSERT INTO users (username, password, email, phone, role) VALUES (?, ?, ?, ?, ?)',
                (username, password, email, phone, role)
            )
            conn.commit()
            conn.close()
            flash(f'User {username} added successfully', 'success')
            return redirect(url_for('users'))
        except sqlite3.IntegrityError:
            # Username already exists in database
            conn.close()  # Close connection
            flash('Username already exists', 'danger')
            return render_template('add_user.html', username=username, email=email, phone=phone, role=role)
        except Exception as e:
            # Catch any other database errors
            conn.close()  # Close connection
            flash('Database error occurred. Please try again.', 'danger')
            return render_template('add_user.html', username=username, email=email, phone=phone, role=role)
    
    # Display add user template for GET requests
    return render_template('add_user.html')

# Route to delete users admin only, requires confirmation
@app.route('/users/delete/<int:user_id>', methods=['GET', 'POST'])
def delete_user(user_id):
    # Check if user is logged in
    if 'user_id' not in session:
        flash('Please login first', 'warning')
        return redirect(url_for('login'))
    
    # Check if user has admin role
    if session.get('role') != 'admin':
        flash('Admin access required', 'danger')
        return redirect(url_for('home'))
    
    # Process deletion when form is submitted via POST
    if request.method == 'POST':
        # Prevent admin from deleting their own account
        if user_id == session.get('user_id'):
            flash('Cannot delete your own account', 'danger')
            return redirect(url_for('users'))
        
        # Delete user from database
        conn = get_db()
        conn.execute('DELETE FROM users WHERE id = ?', (user_id,))
        conn.commit()
        conn.close()
        flash('User deleted successfully', 'success')
        return redirect(url_for('users'))
    
    # Display confirmation template for GET requests
    return render_template('delete_confirm.html', user_id=user_id)

# Route for user profile page allows logged in users to change their password
@app.route('/profile', methods=['GET', 'POST'])
def profile():
    # Check if user is logged in
    if 'user_id' not in session:
        flash('Please login first', 'warning')
        return redirect(url_for('login'))
    
    # Process password change form submission
    if request.method == 'POST':
        # Get password fields from form
        current_password = request.form.get('current_password')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')
        
        # Get current password from database
        conn = get_db()
        user = conn.execute(
            'SELECT password FROM users WHERE id = ?',
            (session.get('user_id'),)
        ).fetchone()
        conn.close()
        
        # Validate current password is correct
        if not user or current_password != user['password']:
            flash('Current password is incorrect', 'danger')
        # Validate that new passwords are provided and match
        elif not new_password or new_password != confirm_password:
            flash('New passwords do not match', 'danger')
        # Check if new password is same as current password
        elif new_password == user['password']:
            flash('New password cannot be the same as your current password', 'danger')
        else:
            # Validate password strength
            is_valid, message = validate_password(new_password)
            if not is_valid:
                flash(message, 'danger')
            else:
                # Update password in database
                conn = get_db()
                conn.execute(
                    'UPDATE users SET password = ? WHERE id = ?',
                    (new_password, session.get('user_id'))
                )
                conn.commit()
                conn.close()
                flash('Password changed successfully', 'success')
                return redirect(url_for('home'))
    
    # Display profile template for GET requests
    return render_template('change_password.html')

# Route to create new user account handles both GET and POST
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    # Process form submission to create new account
    if request.method == 'POST':
        # Get form data from signup form
        username = request.form['username']
        password = request.form['password']
        confirm_password = request.form['confirm_password']
        email = request.form['email']
        phone = request.form.get('phone', '')  # Phone is optional
        
        # Validate passwords match
        if password != confirm_password:
            flash('Passwords do not match!', 'danger')
            return render_template('signup.html', username=username, email=email, phone=phone)
        
        # Validate password strength
        is_valid, message = validate_password(password)
        if not is_valid:
            flash(message, 'danger')
            return render_template('signup.html', username=username, email=email, phone=phone)
        
        # Try to insert new user account into database
        try:
            conn = get_db()
            # Insert new user with staff role
            conn.execute(
                'INSERT INTO users (username, password, email, phone, role) VALUES (?, ?, ?, ?, ?)',
                (username, password, email, phone, 'staff')
            )
            conn.commit()
            conn.close()
            flash('Account created successfully! Please login.', 'success')
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            # Username already exists in database
            conn.close()  # Close connection
            flash('Username already exists', 'danger')
            return render_template('signup.html', username=username, email=email, phone=phone)
        except Exception as e:
            # Catch any other database errors
            conn.close()  # Close connection
            flash('Database error occurred. Please try again.', 'danger')
            return render_template('signup.html', username=username, email=email, phone=phone)
    
    # Display signup template for GET requests
    return render_template('signup.html')

# Route for account management allows users to update their account details
@app.route('/account', methods=['GET', 'POST'])
def account():
    # Check if user is logged in
    if 'user_id' not in session:
        flash('Please login first', 'warning')
        return redirect(url_for('login'))
    
    # Only admins can access account settings
    if session.get('role') != 'admin':
        flash('Admin access required', 'danger')
        return redirect(url_for('home'))
    
    # Get all staff users for dropdown
    conn = get_db()
    staff_users = conn.execute('SELECT id, username FROM users ORDER BY username').fetchall()
    conn.close()
    
    # Get user_id from form or default to current admin
    target_user_id = request.form.get('user_id') or request.args.get('user_id') or session.get('user_id')
    
    # Process account update form submission
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        phone = request.form.get('phone', '')
        
        # Validate that username and email are provided
        if not username or not email:
            flash('Username and email are required', 'danger')
        else:
            # Check if username or email already exists in another account
            conn = get_db()
            existing = conn.execute(
                'SELECT id FROM users WHERE (username = ? OR email = ?) AND id != ?',
                (username, email, target_user_id)
            ).fetchone()
            
            if existing:
                # Notify user that username or email is already taken
                conn.close()
                flash('Username or email already in use', 'danger')
            else:
                # Try to update user account in database
                try:
                    # Execute UPDATE query to modify user details
                    conn.execute('UPDATE users SET username = ?, email = ?, phone = ? WHERE id = ?',
                        (username, email, phone, target_user_id))
                    # Commit changes to database
                    conn.commit()
                    conn.close()
                    # Notify user of successful update
                    flash('Account details updated successfully', 'success')
                    # Redirect to account page with updated user ID parameter
                    return redirect(url_for('account', user_id=target_user_id))
                except Exception as e:
                    # Catch any other unexpected database errors
                    conn.close()
                    flash('Database error occurred', 'danger')
    
    # Get selected user details for display
    conn = get_db()
    user = conn.execute('SELECT id, username, email, phone FROM users WHERE id = ?', (target_user_id,)).fetchone()
    conn.close()
    
    if not user:
        flash('User not found', 'danger')
        return redirect(url_for('home'))
    
    return render_template('account.html', current_username=user['username'], current_email=user['email'], 
                         current_phone=user['phone'], staff_users=staff_users, target_user_id=user['id'])

# ==================== RFQ MANAGEMENT ROUTES (from Ryan) ====================

# Route to display all RFQs
@app.route('/rfqmanagement')
@app.route('/rfq_management')
def rfqmanagement():
    if 'user_id' not in session:
        flash('Please log in to access this page', 'warning')
        return redirect(url_for('login'))
    
    conn = get_db()
    rfqs = conn.execute('''
        SELECT id, customer_name, customer_email, phone_number, 
               motorcycle_brand, motorcycle_model, total_price, created_date 
        FROM rfq ORDER BY id DESC
    ''').fetchall()
    conn.close()
    
    return render_template('rfqmgmt.html', rfqs=rfqs)

# Alias for rfqmanagement route
rfq_mgmt = rfqmanagement
app.add_url_rule('/rfq_mgmt', 'rfq_mgmt', rfq_mgmt)

# Legacy route kept only for backwards compatibility.
# RFQ creation is now handled via the RFQ Dashboard flow (`new_quotation`).
@app.route('/rfqcreate', methods=['GET', 'POST'])
@app.route('/rfq_create', endpoint='rfq_create', methods=['GET', 'POST'])
def rfqcreate():
    if 'user_id' not in session:
        flash('Please log in to access this page', 'warning')
        return redirect(url_for('login'))

    flash('RFQ creation has moved to RFQ Dashboard.', 'info')
    return redirect(url_for('new_quotation'))

# Route to delete RFQ
@app.route('/rfqdelete/<int:rfq_id>', methods=['POST'])
def rfqdelete(rfq_id):
    if 'user_id' not in session:
        flash('Please log in to access this page', 'warning')
        return redirect(url_for('login'))
    
    if session.get('role') != 'admin':
        flash('Only administrators can delete RFQs', 'danger')
        return redirect(url_for('rfqmanagement'))
    
    conn = get_db()
    conn.execute('DELETE FROM rfq_parts WHERE rfq_id = ?', (rfq_id,))
    conn.execute('DELETE FROM rfq WHERE id = ?', (rfq_id,))
    conn.commit()
    conn.close()
    
    flash(f'RFQ #{rfq_id} deleted successfully', 'success')
    return redirect(url_for('rfqmanagement'))

# ==================== RFQ MERGING ROUTES (from Javier) ====================

# Route to display RFQ Merging dashboard
@app.route('/rfq_merging')
def rfq_merging():
    if 'user_id' not in session:
        flash('Please log in to access this page', 'warning')
        return redirect(url_for('login'))
    
    conn = get_db()
    job_cards = conn.execute('SELECT * FROM job_cards ORDER BY id ASC, date_created ASC').fetchall()
    
    pending_count = sum(1 for j in job_cards if j['status'] == 'Pending')
    ready_count = sum(1 for j in job_cards if j['status'] == 'Ready To Merge')
    finalized_count = sum(1 for j in job_cards if j['status'] == 'Finalized')
    
    conn.close()
    
    return render_template('rfq_merging.html', 
                         job_cards=job_cards,
                         pending_count=pending_count,
                         ready_count=ready_count,
                         finalized_count=finalized_count)

# Route to view mechanic RFQ
@app.route('/mechanic_rfq/<int:job_card_id>')
def mechanic_rfq(job_card_id):
    if 'user_id' not in session:
        flash('Please log in to access this page', 'warning')
        return redirect(url_for('login'))
    
    conn = get_db()
    job_card = conn.execute('SELECT * FROM job_cards WHERE id = ?', (job_card_id,)).fetchone()
    
    if not job_card:
        flash('Job Card not found', 'danger')
        return redirect(url_for('rfq_merging'))
    
    labor_services = conn.execute('SELECT * FROM mechanic_labor WHERE job_card_id = ?', (job_card_id,)).fetchall()
    nonstockable_parts = conn.execute('SELECT * FROM mechanic_nonstockable WHERE job_card_id = ?', (job_card_id,)).fetchall()
    conn.close()
    
    return render_template('mechanic_rfq.html', 
                         job_card=job_card, 
                         labor_services=labor_services,
                         nonstockable_parts=nonstockable_parts,
                         view_only=True)

# Route to view spare parts RFQ
@app.route('/spare_parts_rfq/<int:job_card_id>')
def spare_parts_rfq(job_card_id):
    if 'user_id' not in session:
        flash('Please log in to access this page', 'warning')
        return redirect(url_for('login'))
    
    conn = get_db()
    job_card = conn.execute('SELECT * FROM job_cards WHERE id = ?', (job_card_id,)).fetchone()
    
    if not job_card:
        flash('Job Card not found', 'danger')
        return redirect(url_for('rfq_merging'))
    
    spare_parts = conn.execute('SELECT * FROM spare_parts_rfq WHERE job_card_id = ?', (job_card_id,)).fetchall()
    conn.close()
    
    return render_template('spare_parts_rfq.html', 
                         job_card=job_card,
                         spare_parts=spare_parts,
                         view_only=True)

# Route to merge RFQs
@app.route('/merge_rfq/<int:job_card_id>', methods=['GET', 'POST'])
def merge_rfq(job_card_id):
    if 'user_id' not in session:
        flash('Please log in to access this page', 'warning')
        return redirect(url_for('login'))
    
    conn = get_db()
    job_card = conn.execute('SELECT * FROM job_cards WHERE id = ?', (job_card_id,)).fetchone()
    
    if not job_card:
        flash('Job Card not found', 'danger')
        return redirect(url_for('rfq_merging'))
    
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'perform_merge':
            conn.execute('DELETE FROM merged_rfq WHERE job_card_id = ?', (job_card_id,))
            
            labor_services = conn.execute('SELECT * FROM mechanic_labor WHERE job_card_id = ?', (job_card_id,)).fetchall()
            for service in labor_services:
                total = service['quantity'] * service['price']
                conn.execute('''INSERT INTO merged_rfq 
                               (job_card_id, item_type, item_name, quantity, unit_price, total_price, is_nonstockable)
                               VALUES (?, ?, ?, ?, ?, ?, ?)''',
                            (job_card_id, 'Labor', service['service_name'], str(service['quantity']), 
                             service['price'], total, 0))
            
            mech_nonstockable = conn.execute('SELECT * FROM mechanic_nonstockable WHERE job_card_id = ?', (job_card_id,)).fetchall()
            for part in mech_nonstockable:
                total = part['quantity'] * part['price']
                conn.execute('''INSERT INTO merged_rfq 
                               (job_card_id, item_type, item_name, quantity, unit_price, total_price, is_nonstockable)
                               VALUES (?, ?, ?, ?, ?, ?, ?)''',
                            (job_card_id, 'Part', part['part_name'], str(part['quantity']), 
                             part['price'], total, 1))
            
            spare_parts = conn.execute('SELECT * FROM spare_parts_rfq WHERE job_card_id = ?', (job_card_id,)).fetchall()
            for part in spare_parts:
                conn.execute('''INSERT INTO merged_rfq 
                               (job_card_id, item_type, item_name, quantity, unit_price, total_price, is_nonstockable)
                               VALUES (?, ?, ?, ?, ?, ?, ?)''',
                            (job_card_id, 'Part', part['part_name'], part['quantity'], 
                             part['unit_price'], part['total_price'], part['is_nonstockable']))
            
            conn.execute('UPDATE job_cards SET status = ? WHERE id = ?', ('Ready To Merge', job_card_id))
            conn.commit()
            flash('RFQs merged successfully! You can now review and edit the merged RFQ.', 'success')
            return redirect(url_for('view_merged_rfq', job_card_id=job_card_id))
    
    labor_services = conn.execute('SELECT * FROM mechanic_labor WHERE job_card_id = ?', (job_card_id,)).fetchall()
    mech_nonstockable = conn.execute('SELECT * FROM mechanic_nonstockable WHERE job_card_id = ?', (job_card_id,)).fetchall()
    spare_parts = conn.execute('SELECT * FROM spare_parts_rfq WHERE job_card_id = ?', (job_card_id,)).fetchall()

    labor_total = sum((service['quantity'] or 0) * (service['price'] or 0) for service in labor_services)
    mech_nonstockable_total = sum((part['quantity'] or 0) * (part['price'] or 0) for part in mech_nonstockable)
    mechanic_total = labor_total + mech_nonstockable_total
    spare_parts_total = sum(part['total_price'] or 0 for part in spare_parts)
    combined_total = mechanic_total + spare_parts_total

    conn.close()
    
    return render_template('merge_rfq.html', 
                         job_card=job_card,
                         labor_services=labor_services,
                         mech_nonstockable=mech_nonstockable,
                         spare_parts=spare_parts,
                         mechanic_total=mechanic_total,
                         spare_parts_total=spare_parts_total,
                         combined_total=combined_total)

# Route to view merged RFQ
@app.route('/view_merged_rfq/<int:job_card_id>', methods=['GET', 'POST'])
def view_merged_rfq(job_card_id):
    if 'user_id' not in session:
        flash('Please log in to access this page', 'warning')
        return redirect(url_for('login'))
    
    conn = get_db()
    job_card = conn.execute('SELECT * FROM job_cards WHERE id = ?', (job_card_id,)).fetchone()
    
    if not job_card:
        flash('Job Card not found', 'danger')
        return redirect(url_for('rfq_merging'))
    
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'add_item':
            # Add new item to merged RFQ
            item_type = request.form.get('item_type', '').strip()
            item_name = request.form.get('item_name', '').strip()
            quantity = request.form.get('quantity', '').strip()
            unit_price = request.form.get('unit_price', '').strip()
            is_nonstockable = request.form.get('is_nonstockable') == 'on'
            
            # Validation
            errors = []
            if not item_type:
                errors.append('Item type is required')
            if not item_name:
                errors.append('Item name is required')
            if not quantity:
                errors.append('Quantity is required')
            
            qty_num, unit = parse_quantity(quantity)
            if qty_num is None:
                errors.append('Quantity must be a positive number or format like "4L"')
            
            try:
                unit_price_float = float(unit_price)
                if unit_price_float <= 0:
                    errors.append('Unit price must be a positive number')
            except (ValueError, TypeError):
                errors.append('Unit price must be a valid number')
            
            if errors:
                for error in errors:
                    flash(error, 'danger')
            else:
                # Calculate total price
                total_price = qty_num * unit_price_float
                
                conn.execute('''INSERT INTO merged_rfq 
                               (job_card_id, item_type, item_name, quantity, unit_price, total_price, is_nonstockable)
                               VALUES (?, ?, ?, ?, ?, ?, ?)''',
                            (job_card_id, item_type, item_name, quantity, unit_price_float, total_price, is_nonstockable))
                conn.commit()
                flash('Item added successfully!', 'success')
            return redirect(url_for('view_merged_rfq', job_card_id=job_card_id))
        
        elif action == 'update_item':
            # Update existing item in merged RFQ
            item_id = request.form.get('item_id')
            quantity = request.form.get('quantity', '').strip()
            unit_price = request.form.get('unit_price', '').strip()
            
            # Validation
            errors = []
            if not quantity:
                errors.append('Quantity is required')
            
            qty_num, unit = parse_quantity(quantity)
            if qty_num is None:
                errors.append('Quantity must be a positive number or format like "4L"')
            
            try:
                unit_price_float = float(unit_price)
                if unit_price_float <= 0:
                    errors.append('Unit price must be a positive number')
            except (ValueError, TypeError):
                errors.append('Unit price must be a valid number')
            
            if errors:
                for error in errors:
                    flash(error, 'danger')
            else:
                # Calculate total price
                total_price = qty_num * unit_price_float
                
                conn.execute('''UPDATE merged_rfq 
                               SET quantity = ?, unit_price = ?, total_price = ?
                               WHERE id = ?''',
                            (quantity, unit_price_float, total_price, item_id))
                conn.commit()
                flash('Item updated successfully!', 'success')
            return redirect(url_for('view_merged_rfq', job_card_id=job_card_id))
        
        elif action == 'delete_item':
            item_id = request.form.get('item_id')
            conn.execute('DELETE FROM merged_rfq WHERE id = ?', (item_id,))
            conn.commit()
            flash('Item deleted successfully!', 'success')
            return redirect(url_for('view_merged_rfq', job_card_id=job_card_id))
        
        elif action == 'finalize':
            conn.execute('UPDATE job_cards SET status = ? WHERE id = ?', ('Finalized', job_card_id))
            conn.commit()
            flash('Merged RFQ finalized and sent to admin for quotation generation!', 'success')
            return redirect(url_for('rfq_merging'))
    
    merged_items = conn.execute('''SELECT * FROM merged_rfq 
                                   WHERE job_card_id = ?
                                   ORDER BY item_type, item_name''', (job_card_id,)).fetchall()
    
    total_amount = sum(item['total_price'] for item in merged_items)
    conn.close()
    
    return render_template('view_merged_rfq.html', 
                         job_card=job_card,
                         merged_items=merged_items,
                         total_amount=total_amount)

# ==================== QUOTATION MANAGEMENT ROUTES (from Ryan+Wesley) ====================

ADMIN_QUOTATIONS_TABLE = 'admin_quotations'
ADMIN_QUOTATION_PARTS_TABLE = 'admin_quotation_parts'

def _clean_text(value, fallback):
    text = str(value).strip() if value is not None else ''
    return text if text else fallback

def init_quotations_db():
    """Initialize quotation management tables in the main workshop database"""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute(f'''CREATE TABLE IF NOT EXISTS {ADMIN_QUOTATIONS_TABLE} (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        quotation_number TEXT,
                        customer_name TEXT,
                        customer_email TEXT,
                        phone_number TEXT,
                        motorcycle_brand TEXT,
                        motorcycle_model TEXT,
                        total_price REAL,
                        status TEXT DEFAULT 'Unsent',
                        created_date TEXT)''')
    
    cursor.execute(f'''CREATE TABLE IF NOT EXISTS {ADMIN_QUOTATION_PARTS_TABLE} (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        quotation_id INTEGER,
                        part_description TEXT,
                        manufacturer_name TEXT,
                        part_number TEXT,
                        action TEXT,
                        quantity INTEGER,
                        price REAL,
                        FOREIGN KEY (quotation_id) REFERENCES {ADMIN_QUOTATIONS_TABLE}(id))''')
    
    conn.commit()
    
    # Sample data seeding disabled for proof-of-concept reset
    cursor.execute(f"SELECT COUNT(*) FROM {ADMIN_QUOTATIONS_TABLE}")
    if False and cursor.fetchone()[0] == 0:
        # Insert sample quotations
        sample_quotations = [
            ('QT-1707900001', 'James Wong', 'james@email.com', '91234567', 'Yamaha', 'YZF-R15', 485.00, 'Sent', '10/02/2026 10:30:00'),
            ('QT-1707900002', 'Lisa Tan', 'lisa@email.com', '98765432', 'Honda', 'CBR150R', 620.00, 'Unsent', '12/02/2026 14:15:00'),
            ('QT-1707900003', 'Marcus Tan', 'marcus@email.com', '87654321', 'Honda', 'CBR150R', 385.00, 'Sent', '14/02/2026 09:45:00'),
            ('QT-1707900004', 'Sarah Lim', 'sarah@email.com', '92345678', 'Kawasaki', 'Ninja 250', 750.00, 'Unsent', '15/02/2026 16:20:00'),
            ('QT-1707900005', 'David Lee', 'david@email.com', '93456789', 'Suzuki', 'GSX-R150', 320.00, 'Sent', '16/02/2026 11:00:00'),
        ]
        
        for q in sample_quotations:
            cursor.execute('''
                INSERT INTO admin_quotations (quotation_number, customer_name, customer_email, phone_number, 
                                       motorcycle_brand, motorcycle_model, total_price, status, created_date)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', q)
        
        # Insert sample parts for quotations
        sample_parts = [
            # Parts for James Wong's quotation (id=1)
            (1, 'Engine Oil 10W-40 (4L)', 'Yamaha', 'YAM-OIL-001', 'Replace', 1, 65.00),
            (1, 'Oil Filter', 'Yamaha', 'YAM-FIL-002', 'Replace', 1, 35.00),
            (1, 'Brake Pads Front', 'Brembo', 'BRM-PAD-001', 'Replace', 1, 150.00),
            (1, 'Spark Plugs', 'NGK', 'NGK-SPK-001', 'Replace', 2, 45.00),
            (1, 'Labour - Oil Change', 'Workshop', 'LAB-001', 'Service', 1, 50.00),
            (1, 'Labour - Brake Service', 'Workshop', 'LAB-002', 'Service', 1, 50.00),
            # Parts for Lisa Tan's quotation (id=2)
            (2, 'Chain Kit', 'RK', 'RK-CHN-001', 'Replace', 1, 280.00),
            (2, 'Sprocket Set', 'JT', 'JT-SPR-001', 'Replace', 1, 120.00),
            (2, 'Chain Lubricant', 'Motul', 'MOT-LUB-001', 'Service', 2, 30.00),
            (2, 'Labour - Chain Replacement', 'Workshop', 'LAB-003', 'Service', 1, 80.00),
            (2, 'Labour - Wheel Alignment', 'Workshop', 'LAB-004', 'Service', 1, 50.00),
            # Parts for Marcus Tan's quotation (id=3)
            (3, 'Engine Oil 10W-40 (4L)', 'Honda', 'HON-OIL-001', 'Replace', 1, 70.00),
            (3, 'Oil Filter', 'Honda', 'HON-FIL-001', 'Replace', 1, 40.00),
            (3, 'Air Filter', 'K&N', 'KN-AIR-001', 'Replace', 1, 85.00),
            (3, 'Labour - Full Service', 'Workshop', 'LAB-005', 'Service', 1, 100.00),
            (3, 'Labour - Inspection', 'Workshop', 'LAB-006', 'Inspect', 1, 50.00),
            # Parts for Sarah Lim's quotation (id=4)
            (4, 'Front Tire', 'Michelin', 'MCH-TIR-F01', 'Replace', 1, 180.00),
            (4, 'Rear Tire', 'Michelin', 'MCH-TIR-R01', 'Replace', 1, 220.00),
            (4, 'Tube Front', 'Generic', 'TUB-F01', 'Replace', 1, 25.00),
            (4, 'Tube Rear', 'Generic', 'TUB-R01', 'Replace', 1, 25.00),
            (4, 'Labour - Tire Change', 'Workshop', 'LAB-007', 'Service', 2, 100.00),
            (4, 'Wheel Balancing', 'Workshop', 'LAB-008', 'Service', 2, 50.00),
            (4, 'Labour - Alignment', 'Workshop', 'LAB-009', 'Service', 1, 50.00),
            # Parts for David Lee's quotation (id=5)
            (5, 'Brake Fluid DOT4', 'Motul', 'MOT-BRK-001', 'Replace', 1, 35.00),
            (5, 'Coolant', 'Motul', 'MOT-COL-001', 'Replace', 2, 45.00),
            (5, 'Spark Plugs Iridium', 'NGK', 'NGK-SPK-IR1', 'Replace', 2, 60.00),
            (5, 'Labour - Fluid Change', 'Workshop', 'LAB-010', 'Service', 1, 50.00),
            (5, 'Labour - Spark Plug Change', 'Workshop', 'LAB-011', 'Service', 1, 40.00),
        ]
        
        for p in sample_parts:
            cursor.execute('''
                INSERT INTO admin_quotation_parts (quotation_id, part_description, manufacturer_name, 
                                             part_number, action, quantity, price)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', p)
        
        conn.commit()
    
    conn.close()

def fetch_all_quotations():
    """Fetch all quotations with their parts"""
    conn = get_db()
    quotations = conn.execute(f'SELECT * FROM {ADMIN_QUOTATIONS_TABLE} ORDER BY id DESC').fetchall()
    result = []
    for q in quotations:
        q_dict = dict(q)
        q_dict['quotation_number'] = _clean_text(q_dict.get('quotation_number'), f"QT-{q_dict.get('id', '')}".rstrip('-'))
        q_dict['customer_name'] = _clean_text(q_dict.get('customer_name'), 'Unknown Customer')
        q_dict['customer_email'] = _clean_text(q_dict.get('customer_email'), 'Not provided')
        q_dict['phone_number'] = _clean_text(q_dict.get('phone_number'), 'Not provided')
        q_dict['status'] = _clean_text(q_dict.get('status'), 'Unsent')
        q_dict['created_date'] = _clean_text(q_dict.get('created_date'), 'Not provided')
        parts = conn.execute(f'SELECT * FROM {ADMIN_QUOTATION_PARTS_TABLE} WHERE quotation_id = ?', (q['id'],)).fetchall()
        q_dict['parts'] = [dict(p) for p in parts]
        result.append(q_dict)
    conn.close()
    return result

def get_quotation_by_id(quotation_id):
    """Get a quotation by ID with its parts"""
    conn = get_db()
    q = conn.execute(f'SELECT * FROM {ADMIN_QUOTATIONS_TABLE} WHERE id = ?', (quotation_id,)).fetchone()
    if not q:
        conn.close()
        return None
    q_dict = dict(q)
    parts = conn.execute(f'SELECT * FROM {ADMIN_QUOTATION_PARTS_TABLE} WHERE quotation_id = ?', (quotation_id,)).fetchall()
    q_dict['parts'] = [dict(p) for p in parts]
    conn.close()
    return q_dict

# Route to display all quotations (Quotation Management)
@app.route('/quotemanagement')
def quote_mgmt():
    if 'user_id' not in session:
        flash('Please log in to access this page', 'warning')
        return redirect(url_for('login'))
    
    init_quotations_db()
    quotations = fetch_all_quotations()
    return render_template('quotemgmt.html', quotations=quotations)

# Route to create quotation
@app.route('/quotecreate')
def quote_create():
    if 'user_id' not in session:
        flash('Please log in to access this page', 'warning')
        return redirect(url_for('login'))
    
    return render_template('quotecreate.html')

# API to create quotation with JSON
@app.route('/api/create-quotation', methods=['POST'])
def api_create_quotation():
    try:
        from flask import jsonify
        data = request.get_json()
        if not isinstance(data, dict):
            return jsonify({'success': False, 'error': 'Invalid request payload'}), 400

        generated_number = f"QT-{int(datetime.now().timestamp())}"
        quotation_number = _clean_text(data.get('quotation_number'), generated_number)
        customer_name = _clean_text(data.get('customer_name'), 'Unknown Customer')
        customer_email_raw = (data.get('customer_email') or '').strip()
        phone_number_raw = (data.get('phone_number') or '').strip()
        if not customer_email_raw or not phone_number_raw:
            return jsonify({'success': False, 'error': 'Customer email and phone are required.'}), 400

        customer_email = customer_email_raw
        phone_number = phone_number_raw
        motorcycle_brand = _clean_text(data.get('motorcycle_brand'), 'Unknown')
        motorcycle_model = _clean_text(data.get('motorcycle_model'), 'Unknown')
        total_price = data.get('total_price')
        created_date = _clean_text(
            data.get('created_date'),
            datetime.now().strftime('%d/%m/%Y %H:%M:%S')
        )
        parts = data.get('parts', [])

        try:
            total_price = float(total_price)
        except (TypeError, ValueError):
            total_price = 0.0

        if not isinstance(parts, list):
            parts = []
        
        init_quotations_db()
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute(f'''INSERT INTO {ADMIN_QUOTATIONS_TABLE} 
                         (quotation_number, customer_name, customer_email, phone_number, 
                          motorcycle_brand, motorcycle_model, total_price, created_date)
                         VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
                      (quotation_number, customer_name, customer_email, phone_number,
                       motorcycle_brand, motorcycle_model, total_price, created_date))
        quotation_id = cursor.lastrowid
        
        for part in parts:
            description = _clean_text(part.get('description') if isinstance(part, dict) else '', 'N/A')
            manufacturer = _clean_text(part.get('manufacturer') if isinstance(part, dict) else '', 'N/A')
            part_number = _clean_text(part.get('number') if isinstance(part, dict) else '', 'N/A')
            action = _clean_text(part.get('action') if isinstance(part, dict) else '', 'N/A')
            quantity = part.get('quantity') if isinstance(part, dict) else 0
            price = part.get('price') if isinstance(part, dict) else 0
            try:
                quantity = int(float(quantity))
            except (TypeError, ValueError):
                quantity = 0
            try:
                price = float(price)
            except (TypeError, ValueError):
                price = 0.0

            cursor.execute(f'''INSERT INTO {ADMIN_QUOTATION_PARTS_TABLE} 
                             (quotation_id, part_description, manufacturer_name, part_number, action, quantity, price)
                             VALUES (?, ?, ?, ?, ?, ?, ?)''',
                          (quotation_id, description, manufacturer,
                           part_number, action, quantity, price))
        
        conn.commit()
        conn.close()
        
        from flask import jsonify
        return jsonify({'success': True, 'quotation_number': quotation_number})
    except Exception as e:
        print(f"Error creating quotation: {e}")
        from flask import jsonify
        return jsonify({'success': False, 'error': str(e)}), 500

# Route to edit quotation
@app.route('/quoteedit/<int:quotation_id>', methods=['GET', 'POST'])
def quote_edit(quotation_id):
    if 'user_id' not in session:
        flash('Please log in to access this page', 'warning')
        return redirect(url_for('login'))
    
    quotation = get_quotation_by_id(quotation_id)
    if not quotation:
        flash('Quotation not found', 'danger')
        return redirect(url_for('quote_mgmt'))
    
    if request.method == 'POST':
        try:
            customer_name = request.form.get('customer_name')
            customer_email = request.form.get('customer_email')
            phone_number = request.form.get('phone_number')
            motorcycle_brand = request.form.get('motorcycle_brand')
            motorcycle_model = request.form.get('motorcycle_model')

            parts = []
            row_indexes = []
            for form_key in request.form.keys():
                if form_key.startswith('description_'):
                    index_part = form_key.split('_', 1)[1]
                    if index_part.isdigit():
                        row_indexes.append(int(index_part))

            for i in sorted(set(row_indexes)):
                description_value = (request.form.get(f"description_{i}") or '').strip()
                if not description_value:
                    continue

                manufacturer_value = (request.form.get(f"manufacturer_{i}") or '').strip() or 'N/A'

                try:
                    quantity_value = int(request.form.get(f"quantity_{i}", 1))
                except (TypeError, ValueError):
                    quantity_value = 1

                try:
                    price_value = float(request.form.get(f"price_{i}", 0))
                except (TypeError, ValueError):
                    price_value = 0.0

                part = {
                    'description': description_value,
                    'manufacturer': manufacturer_value,
                    'number': request.form.get(f"number_{i}"),
                    'action': (request.form.get(f"action_{i}") or '').strip(),
                    'quantity': quantity_value,
                    'price': price_value
                }
                parts.append(part)
            
            total_price = sum(p['quantity'] * p['price'] for p in parts)

            conn = get_db()
            cursor = conn.cursor()
            
            cursor.execute(f"""UPDATE {ADMIN_QUOTATIONS_TABLE} 
                             SET customer_name=?, customer_email=?, phone_number=?,
                                 motorcycle_brand=?, motorcycle_model=?, total_price=?
                             WHERE id=?""",
                          (customer_name, customer_email, phone_number,
                           motorcycle_brand, motorcycle_model, total_price, quotation_id))
            
            cursor.execute(f"DELETE FROM {ADMIN_QUOTATION_PARTS_TABLE} WHERE quotation_id=?", (quotation_id,))
            
            for part in parts:
                cursor.execute(f"""INSERT INTO {ADMIN_QUOTATION_PARTS_TABLE} 
                                 (quotation_id, part_description, manufacturer_name, part_number, action, quantity, price)
                                 VALUES (?, ?, ?, ?, ?, ?, ?)""",
                              (quotation_id, part['description'], part['manufacturer'],
                               part['number'], part['action'], part['quantity'], part['price']))
            
            conn.commit()
            conn.close()
            flash('Quotation updated successfully!', 'success')
            return redirect(url_for('quote_mgmt'))
        
        except Exception as e:
            print(f"Error updating quotation: {e}")
            flash('Error updating quotation', 'danger')
            return redirect(url_for('quote_mgmt'))

    return render_template('quoteedit.html', quotation=quotation)

# Route to delete quotation
@app.route('/quotedelete/<int:quotation_id>', methods=['POST'])
def quotedelete(quotation_id):
    if 'user_id' not in session:
        flash('Please log in to access this page', 'warning')
        return redirect(url_for('login'))
    
    if session.get('role') != 'admin':
        flash('Only administrators can delete quotations', 'danger')
        return redirect(url_for('quote_mgmt'))
    
    try:
        conn = get_db()
        conn.execute(f'DELETE FROM {ADMIN_QUOTATION_PARTS_TABLE} WHERE quotation_id = ?', (quotation_id,))
        conn.execute(f'DELETE FROM {ADMIN_QUOTATIONS_TABLE} WHERE id = ?', (quotation_id,))
        conn.commit()
        conn.close()
        flash('Quotation deleted successfully!', 'success')
    except Exception as e:
        print(f"Error deleting quotation: {e}")
        flash('Error deleting quotation', 'danger')
    
    return redirect(url_for('quote_mgmt'))

# Route to toggle quotation status
@app.route('/toggle-status/<int:quotation_id>', methods=['POST'])
def toggle_status(quotation_id):
    if 'user_id' not in session:
        flash('Please log in to access this page', 'warning')
        return redirect(url_for('login'))
    
    try:
        conn = get_db()
        result = conn.execute(f"SELECT status FROM {ADMIN_QUOTATIONS_TABLE} WHERE id=?", (quotation_id,)).fetchone()
        
        if result:
            current_status = result['status']
            new_status = 'Sent' if current_status == 'Unsent' else 'Unsent'
            conn.execute(f"UPDATE {ADMIN_QUOTATIONS_TABLE} SET status=? WHERE id=?", (new_status, quotation_id))
            conn.commit()
        
        conn.close()
    except Exception as e:
        print(f"Error toggling status: {e}")
    
    return redirect(url_for('quote_mgmt'))

# Route to send quotation page
@app.route('/quotesend/<int:quotation_id>')
def quote_send(quotation_id):
    if 'user_id' not in session:
        flash('Please log in to access this page', 'warning')
        return redirect(url_for('login'))
    
    quotation = get_quotation_by_id(quotation_id)
    if not quotation:
        flash('Quotation not found', 'danger')
        return redirect(url_for('quote_mgmt'))
    
    if 'parts' not in quotation or quotation['parts'] is None:
        quotation['parts'] = []
    
    return render_template('quotesend.html', quotation=quotation)

# Route to send via WhatsApp
@app.route('/send-whatsapp/<int:quotation_id>')
def send_whatsapp(quotation_id):
    from urllib.parse import quote
    
    quotation = get_quotation_by_id(quotation_id)
    if not quotation:
        return redirect(url_for('quote_mgmt'))
    
    phone = quotation.get('phone_number', '').replace(' ', '').replace('-', '')
    phone = ''.join(c for c in phone if c.isdigit() or c == '+')
    
    if not phone.startswith('+') and not phone.startswith('65'):
        phone = '65' + phone
    elif phone.startswith('+65'):
        phone = phone[1:]
    
    message = f"""Hello {quotation.get('customer_name')},

Here is your quotation from Ban Hock Hin:

*Quotation Number:* {quotation.get('quotation_number')}
*Vehicle:* {quotation.get('motorcycle_brand')} {quotation.get('motorcycle_model')}

*Items & Services:*
"""
    
    subtotal = 0
    for i, part in enumerate(quotation.get('parts', []), 1):
        qty = part.get('quantity', 0)
        price = part.get('price', 0)
        line_total = qty * price
        subtotal += line_total
        desc = part.get('description') or part.get('part_description', '')
        message += f"{i}. {desc} - Qty: {qty} × SGD {price:.2f} = SGD {line_total:.2f}\n"
    
    message += f"""
*Total Amount:* SGD {subtotal:.2f}

Thank you for your business!

Best regards,
Ban Hock Hin Team"""
    
    encoded_message = quote(message)
    whatsapp_url = f"https://wa.me/{phone}?text={encoded_message}"
    
    return redirect(whatsapp_url)

# Route to send via Email
@app.route('/send-email/<int:quotation_id>')
def send_email(quotation_id):
    from urllib.parse import quote
    
    quotation = get_quotation_by_id(quotation_id)
    if not quotation:
        return redirect(url_for('quote_mgmt'))
    
    email = quotation.get('customer_email', '')
    subject = f"Quotation {quotation.get('quotation_number')} from Ban Hock Hin"
    
    body = f"""Dear {quotation.get('customer_name')},

Please find your quotation details below:

Quotation Number: {quotation.get('quotation_number')}
Vehicle: {quotation.get('motorcycle_brand')} {quotation.get('motorcycle_model')}

Items & Services:
"""
    
    subtotal = 0
    for i, part in enumerate(quotation.get('parts', []), 1):
        qty = part.get('quantity', 0)
        price = part.get('price', 0)
        line_total = qty * price
        subtotal += line_total
        desc = part.get('description') or part.get('part_description', '')
        body += f"{i}. {desc} - Qty: {qty} × SGD {price:.2f} = SGD {line_total:.2f}\n"
    
    body += f"""
Total Amount: SGD {subtotal:.2f}

Thank you for your business!

Best regards,
Ban Hock Hin Team"""
    
    encoded_subject = quote(subject)
    encoded_body = quote(body)
    mailto_url = f"mailto:{email}?subject={encoded_subject}&body={encoded_body}"
    
    return redirect(mailto_url)

# API to get RFQs in JSON format (for quotation creation modal)
@app.route('/api/rfqs')
def api_rfqs():
    from flask import jsonify
    
    conn = get_db()
    rfqs = conn.execute('''
        SELECT q.id AS quotation_id,
               q.customer_name,
               q.customer_email,
               q.phone_number,
               q.vehicle_make,
               q.created_date,
               q.job_card_id,
               jc.id AS job_card_id_actual,
               jc.job_card_number,
               jc.vehicle_model,
               jc.status,
               COALESCE(SUM(m.total_price), 0) AS merged_total
        FROM quotations q
        JOIN job_cards jc ON jc.id = q.job_card_id
        LEFT JOIN merged_rfq m ON m.job_card_id = jc.id
        WHERE jc.status IN ('Ready To Merge', 'Finalized')
        GROUP BY q.id, q.customer_name, q.customer_email, q.phone_number, q.vehicle_make, q.created_date, q.job_card_id, jc.id, jc.job_card_number, jc.vehicle_model, jc.status
        ORDER BY jc.id DESC
    ''').fetchall()
    
    result = []
    for rfq in rfqs:
        source_quotation_id = rfq['quotation_id']
        source_parts = conn.execute('''
            SELECT part_name, item_type, part_number
            FROM quotation_parts
            WHERE quotation_id = ?
        ''', (source_quotation_id,)).fetchall()

        part_number_by_name = {}
        part_number_by_name_and_type = {}
        for source_part in source_parts:
            source_name = (source_part['part_name'] or '').strip().lower()
            source_type = (source_part['item_type'] or '').strip().lower()
            source_number = (source_part['part_number'] or '').strip()
            if not source_name:
                continue
            if source_name not in part_number_by_name or (not part_number_by_name[source_name] and source_number):
                part_number_by_name[source_name] = source_number
            part_number_by_name_and_type[(source_name, source_type)] = source_number

        rfq_dict = {
            'id': rfq['job_card_id_actual'],
            'source_id': rfq['quotation_id'],
            'job_card_number': rfq['job_card_number'],
            'name': rfq['customer_name'],
            'email': rfq['customer_email'] or '',
            'phone': rfq['phone_number'] or '',
            'brand': rfq['vehicle_make'] or '',
            'model': rfq['vehicle_model'],
            'status': rfq['status'],
            'total': rfq['merged_total'],
            'created_date': rfq['created_date'],
            'parts': []
        }
        
        parts = conn.execute('''
            SELECT item_name, item_type, quantity, unit_price, total_price
            FROM merged_rfq
            WHERE job_card_id = ?
            ORDER BY id ASC
        ''', (rfq['job_card_id_actual'],)).fetchall()
        for part in parts:
            part_name_key = (part['item_name'] or '').strip().lower()
            part_type_key = (part['item_type'] or '').strip().lower()
            part_number = part_number_by_name_and_type.get((part_name_key, part_type_key), '')
            if not part_number:
                part_number = part_number_by_name.get(part_name_key, '')

            part_dict = {
                'description': part['item_name'],
                'manufacturer': part['item_type'],
                'number': part_number,
                'action': part['item_type'],
                'quantity': part['quantity'],
                'price': part['unit_price'],
                'line_total': part['total_price']
            }
            rfq_dict['parts'].append(part_dict)
        result.append(rfq_dict)
    
    conn.close()
    return jsonify(result)

# Route to logout clears session and redirects to login page
@app.route('/logout')
def logout():
    # Clear all session data
    session.clear()
    # Flash message informing user they've been logged out
    flash('You have been logged out', 'info')
    # Redirect to login page
    return redirect(url_for('login'))

# Runs the Flask application
# Always initialize database to ensure all tables exist (also when started with `flask run`)
init_db()  # Create tables and insert default users if not exist
init_quotations_db()  # Admin quotation table was only created lazily, so edit/send/delete crashed before /quotemanagement was visited

if __name__ == '__main__':
    # Start Flask development server with debug mode enabled (port 5000; the FastAPI app uses 8000)
    app.run(debug=True, port=5000)