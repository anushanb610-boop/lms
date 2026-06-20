import os
from dotenv import load_dotenv

# Load environment variables from backend/.env when present
load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))
from datetime import date, timedelta
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
import mysql.connector
from mysql.connector import pooling
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import time

app = Flask(__name__)
# Use a permissive CORS during development to avoid preflight issues from the frontend dev server
CORS(app, supports_credentials=True)

UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
ALLOWED_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "gif"}


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_IMAGE_EXTENSIONS


@app.after_request
def add_cors_headers(response):
    response.headers.setdefault("Access-Control-Allow-Origin", "*")
    response.headers.setdefault("Access-Control-Allow-Headers", "Content-Type, X-Auth-Role, X-Auth-User-Id")
    response.headers.setdefault("Access-Control-Allow-Methods", "GET,POST,PUT,PATCH,DELETE,OPTIONS")
    return response

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "127.0.0.1"),
    "user": os.getenv("DB_USER", "root"),
    "password": os.getenv("DB_PASSWORD") or "Anushanb@19",  # fallback default for dev
    "database": os.getenv("DB_NAME", "library_db"),
}

LOAN_DAYS = 15
SUBJECTS = ["Science", "Kannada", "English", "Mathematics",
            "Social Studies", "Sanskrit", "Hindi"]

pool = None


def init_db_pool():
    global pool
    if pool is None:
        pool = pooling.MySQLConnectionPool(pool_name="lms_pool", pool_size=5, **DB_CONFIG)
    return pool


def get_conn():
    return init_db_pool().get_connection()


def rows(cursor):
    cols = [c[0] for c in cursor.description]
    return [dict(zip(cols, r)) for r in cursor.fetchall()]


def get_auth():
    role = (request.headers.get("X-Auth-Role") or "").lower()
    user_id = request.headers.get("X-Auth-User-Id")
    if role not in ("user", "admin", "staff") or not user_id:
        return None
    try:
        user_id = int(user_id)
    except ValueError:
        return None
    return {"role": role, "id": user_id}


def build_photo_url(photo_path):
    if not photo_path:
        return None
    return f"{request.url_root.rstrip('/')}/uploads/{photo_path}"


def find_user_by_id(user_id):
    conn = get_conn(); cur = conn.cursor()
    cur.execute(
        "SELECT id, username, email, phone, status, role, profile_photo, permanent_address, temporary_address FROM users WHERE id=%s", (user_id,)
    )
    row = cur.fetchone()
    cur.close(); conn.close()
    if not row:
        return None
    return {
        "id": row[0], "username": row[1], "email": row[2],
        "phone": row[3], "status": row[4], "role": row[5],
        "profile_photo": row[6],
        "permanent_address": row[7],
        "temporary_address": row[8],
    }


def find_admin_by_id(admin_id):
    conn = get_conn(); cur = conn.cursor()
    cur.execute("SELECT id, username, email FROM users WHERE id=%s AND role='admin'", (admin_id,))
    row = cur.fetchone()
    cur.close(); conn.close()
    if not row:
        return None
    return {"id": row[0], "username": row[1], "email": row[2], "role": "admin"}


def get_user_by_username(username):
    conn = get_conn(); cur = conn.cursor()
    cur.execute(
        "SELECT id, username, email, phone, password, status, role, profile_photo, permanent_address, temporary_address FROM users WHERE username=%s", (username,)
    )
    row = cur.fetchone()
    cur.close(); conn.close()
    if not row:
        return None
    return {
        "id": row[0], "username": row[1], "email": row[2],
        "phone": row[3], "password": row[4], "status": row[5], "role": row[6],
        "profile_photo": row[7],
        "permanent_address": row[8],
        "temporary_address": row[9],
    }


def get_admin_by_username(username):
    conn = get_conn(); cur = conn.cursor()
    cur.execute(
        "SELECT id, username, email, password FROM users WHERE username=%s AND role='admin'", (username,)
    )
    row = cur.fetchone()
    cur.close(); conn.close()
    if not row:
        return None
    return {"id": row[0], "username": row[1], "email": row[2], "password": row[3]}


@app.route("/api/subjects", methods=["GET"])
def list_subjects():
    return jsonify(SUBJECTS)


@app.route("/api/books", methods=["GET"])
def list_books():
    subject = request.args.get("subject")
    conn = get_conn(); cur = conn.cursor()
    # Compute available copies dynamically to avoid DB drift: total_copies - borrowed_count
    if subject:
        cur.execute(
            "SELECT b.id, b.title, b.author, b.subject, b.total_copies, "
            "(b.total_copies - IFNULL((SELECT COUNT(*) FROM borrow_records r WHERE r.book_id=b.id AND r.status='borrowed'),0)) AS available_copies "
            "FROM books b WHERE b.subject=%s ORDER BY b.title",
            (subject,)
        )
    else:
        cur.execute(
            "SELECT b.id, b.title, b.author, b.subject, b.total_copies, "
            "(b.total_copies - IFNULL((SELECT COUNT(*) FROM borrow_records r WHERE r.book_id=b.id AND r.status='borrowed'),0)) AS available_copies "
            "FROM books b ORDER BY b.subject, b.title"
        )
    data = rows(cur)
    cur.close(); conn.close()
    return jsonify(data)


@app.route("/api/books", methods=["POST"])
def add_book():
    auth = get_auth()
    if not auth or auth["role"] != "admin":
        return jsonify({"error": "Forbidden"}), 403
    payload = request.get_json() or {}
    title = (payload.get("title") or "").strip()
    author = (payload.get("author") or "").strip()
    subject = (payload.get("subject") or "").strip()
    try:
        total_copies = int(payload.get("total_copies") or 1)
    except Exception:
        total_copies = 1
    if not title or not author or not subject:
        return jsonify({"error": "title, author and subject required"}), 400
    conn = get_conn(); cur = conn.cursor()
    try:
        cur.execute("INSERT INTO books (title, author, subject, total_copies, available_copies, created_by) VALUES (%s, %s, %s, %s, %s, %s)",
                    (title, author, subject, total_copies, total_copies, auth["id"]))
        book_id = cur.lastrowid
        conn.commit()
        cur.execute("SELECT * FROM books WHERE id=%s", (book_id,))
        row = cur.fetchone()
        cols = [c[0] for c in cur.description]
        cur.close(); conn.close()
        return jsonify(dict(zip(cols, row)))
    except Exception as e:
        conn.rollback()
        cur.close(); conn.close()
        return jsonify({"error": str(e)}), 500


@app.route("/api/books/<int:book_id>", methods=["PUT"])
def edit_book(book_id):
    auth = get_auth()
    if not auth or auth["role"] != "admin":
        return jsonify({"error": "Forbidden"}), 403
    
    payload = request.get_json() or {}
    title = (payload.get("title") or "").strip()
    author = (payload.get("author") or "").strip()
    subject = (payload.get("subject") or "").strip()
    
    try:
        available_copies = int(payload.get("available_copies") or 0)
        total_copies = int(payload.get("total_copies") or 0)
    except (ValueError, TypeError):
        return jsonify({"error": "available_copies and total_copies must be integers"}), 400
    
    if not title or not author or not subject:
        return jsonify({"error": "title, author and subject are required"}), 400
    
    if available_copies < 0 or total_copies < 0:
        return jsonify({"error": "Copies cannot be negative"}), 400
    
    if available_copies > total_copies:
        return jsonify({"error": "Available copies cannot exceed total copies"}), 400
    
    conn = get_conn(); cur = conn.cursor()
    try:
        # Check if book exists and get current borrowed copies
        cur.execute(
            "SELECT id, total_copies FROM books WHERE id=%s",
            (book_id,)
        )
        row = cur.fetchone()
        if not row:
            cur.close(); conn.close()
            return jsonify({"error": "Book not found"}), 404
        
        # Calculate borrowed copies: total_copies - available_copies
        borrowed_copies = row[1] - available_copies
        if total_copies < borrowed_copies:
            cur.close(); conn.close()
            return jsonify({"error": f"Total copies cannot be less than borrowed copies ({borrowed_copies})"}), 400
        
        # Update the book
        cur.execute(
            "UPDATE books SET title=%s, author=%s, subject=%s, total_copies=%s, available_copies=%s WHERE id=%s",
            (title, author, subject, total_copies, available_copies, book_id)
        )
        conn.commit()
        
        # Return updated book
        cur.execute("SELECT id, title, author, subject, total_copies, available_copies FROM books WHERE id=%s", (book_id,))
        row = cur.fetchone()
        updated_book = {
            "id": row[0],
            "title": row[1],
            "author": row[2],
            "subject": row[3],
            "total_copies": row[4],
            "available_copies": row[5]
        }
        cur.close(); conn.close()
        return jsonify(updated_book)
    except Exception as e:
        conn.rollback()
        cur.close(); conn.close()
        return jsonify({"error": str(e)}), 500


@app.route("/api/books/<int:book_id>", methods=["DELETE"])
def delete_book(book_id):
    auth = get_auth()
    if not auth or auth["role"] != "admin":
        return jsonify({"error": "Forbidden"}), 403
    conn = get_conn(); cur = conn.cursor()
    try:
        cur.execute("SELECT id FROM books WHERE id=%s", (book_id,))
        if not cur.fetchone():
            cur.close(); conn.close()
            return jsonify({"error": "Book not found"}), 404
        cur.execute("DELETE FROM books WHERE id=%s", (book_id,))
        conn.commit()
        cur.close(); conn.close()
        return jsonify({"message": "Book deleted"})
    except Exception as e:
        conn.rollback(); cur.close(); conn.close()
        return jsonify({"error": str(e)}), 500


@app.route("/api/admin/dashboard", methods=["GET"])
def admin_dashboard():
    auth = get_auth()
    if not auth or auth["role"] not in ("admin","staff"):
        return jsonify({"error": "Forbidden"}), 403
    conn = get_conn(); cur = conn.cursor()
    try:
        # basic metrics
        cur.execute("SELECT COUNT(*) FROM books")
        total_books = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM users WHERE role='user'")
        total_users = cur.fetchone()[0]
        
        # Active borrowed (returned_date IS NULL)
        cur.execute("SELECT COUNT(*) FROM borrow_records WHERE returned_date IS NULL")
        borrowed = cur.fetchone()[0]
        
        # Overdue (returned_date IS NULL AND due_date < today)
        cur.execute("SELECT COUNT(*) FROM borrow_records WHERE returned_date IS NULL AND due_date < %s", (date.today(),))
        overdue = cur.fetchone()[0]

        # upcoming due dates (next 7 days, not yet returned)
        cur.execute(
            "SELECT r.id, r.book_id, b.title, r.user_id, r.borrower_name, r.due_date FROM borrow_records r "
            "JOIN books b ON b.id=r.book_id "
            "WHERE r.returned_date IS NULL AND r.due_date BETWEEN %s AND %s "
            "ORDER BY r.due_date ASC LIMIT 50",
            (date.today(), date.today() + timedelta(days=7))
        )
        upcoming = rows(cur)

        # borrower statistics: books borrowed by each borrower (active only)
        cur.execute(
            "SELECT borrower_name, COUNT(*) FROM borrow_records WHERE returned_date IS NULL "
            "GROUP BY borrower_name ORDER BY COUNT(*) DESC LIMIT 20"
        )
        borrower_rows = cur.fetchall()
        borrower_stats = [{"name": r[0], "count": r[1]} for r in borrower_rows]

        # recent activity: borrows in last 7 days grouped by day
        cur.execute(
            "SELECT borrow_date, COUNT(*) FROM borrow_records WHERE borrow_date BETWEEN %s AND %s AND borrow_date IS NOT NULL "
            "GROUP BY borrow_date ORDER BY borrow_date ASC",
            (date.today() - timedelta(days=6), date.today())
        )
        activity_rows = cur.fetchall()
        activity = [{"date": str(r[0]), "count": r[1]} for r in activity_rows]

        cur.close(); conn.close()
        return jsonify({
            "total_books": total_books,
            "total_users": total_users,
            "borrowed": borrowed,
            "overdue": overdue,
            "upcoming": upcoming,
            "borrower_stats": borrower_stats,
            "activity": activity,
        })
    except Exception as e:
        cur.close(); conn.close()
        return jsonify({"error": str(e)}), 500


@app.route("/api/auth/register", methods=["POST"])
def register():
    # Support both JSON and form-data (for file uploads)
    if request.is_json:
        payload = request.get_json() or {}
        username = (payload.get("username") or "").strip()
        email = (payload.get("email") or "").strip()
        phone = (payload.get("phone") or "").strip()
        password = (payload.get("password") or "").strip()
        permanent_address = (payload.get("permanent_address") or "").strip() or None
        temporary_address = (payload.get("temporary_address") or "").strip() or None
    else:
        username = (request.form.get("username") or "").strip()
        email = (request.form.get("email") or "").strip()
        phone = (request.form.get("phone") or "").strip()
        password = (request.form.get("password") or "").strip()
        permanent_address = (request.form.get("permanent_address") or "").strip() or None
        temporary_address = (request.form.get("temporary_address") or "").strip() or None

    if not username or not email or not phone or not password:
        return jsonify({"error": "username, email, phone, and password are required"}), 400

    # Validate phone number: must be exactly 10 digits
    phone_digits = ''.join(c for c in phone if c.isdigit())
    if len(phone_digits) != 10:
        return jsonify({"error": "Enter valid number"}), 400

    # Handle profile photo if provided
    profile_photo = None
    if "profile_photo" in request.files:
        photo = request.files["profile_photo"]
        if photo and allowed_file(photo.filename):
            filename = secure_filename(photo.filename)
            filename = f"{int(time.time())}_{filename}"
            save_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
            photo.save(save_path)
            profile_photo = filename
        else:
            return jsonify({"error": "Invalid image file"}), 400

    conn = get_conn(); cur = conn.cursor()
    try:
        cur.execute(
            "SELECT id FROM users WHERE username=%s OR email=%s OR phone=%s",
            (username, email, phone),
        )
        if cur.fetchone():
            return jsonify({"error": "Username, email, or phone already registered"}), 400
        hashed = generate_password_hash(password)
        cur.execute(
            "INSERT INTO users (username, email, phone, password, status, role, permanent_address, temporary_address, profile_photo) VALUES (%s, %s, %s, %s, 'pending', 'user', %s, %s, %s)",
            (username, email, phone, hashed, permanent_address, temporary_address, profile_photo),
        )
        user_id = cur.lastrowid
        cur.execute(
            "INSERT INTO user_status_history (user_id, status, comment) VALUES (%s, 'pending', 'Registered - awaiting admin approval')",
            (user_id,),
        )
        
        # Create notification for all admin users
        notification_message = f"New user {username} is waiting for approval"
        notification_title = f"User Registration: {username}"
        
        cur.execute("SELECT id FROM users WHERE role='admin'")
        admin_users = cur.fetchall()
        
        for admin_row in admin_users:
            admin_id = admin_row[0]
            cur.execute(
                "INSERT INTO notifications (user_id, recipient_role, title, message, type, related_id) VALUES (%s, %s, %s, %s, %s, %s)",
                (admin_id, 'admin', notification_title, notification_message, 'USER_REGISTRATION', user_id)
            )
        
        conn.commit()
        return jsonify({"message": "Registration complete. Your account is pending admin approval."}), 201
    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        cur.close(); conn.close()


@app.route("/api/auth/login", methods=["POST"])
def login():
    payload = request.get_json() or {}
    username = (payload.get("username") or "").strip()
    password = (payload.get("password") or "").strip()
    if not username or not password:
        return jsonify({"error": "username and password are required"}), 400
    user = get_user_by_username(username)
    if not user or not check_password_hash(user["password"], password):
        return jsonify({"error": "Invalid login credentials"}), 401

    if user["status"] == "pending":
        return jsonify({"error": "Account pending approval"}), 403
    if user["status"] == "rejected":
        return jsonify({"error": "Account rejected by admin"}), 403

    return jsonify({
        "user": {
            "id": user["id"],
            "username": user["username"],
            "email": user["email"],
            "phone": user["phone"],
            "status": user["status"],
            "role": user.get("role", "user"),
            "profile_photo": build_photo_url(user.get("profile_photo")),
            "permanent_address": user.get("permanent_address"),
            "temporary_address": user.get("temporary_address"),
        }
    })


@app.route("/api/auth/me", methods=["GET"])
def auth_me():
    auth = get_auth()
    if not auth:
        return jsonify({"error": "Unauthorized"}), 401
    if auth["role"] == "admin":
        admin = find_admin_by_id(auth["id"])
        if not admin:
            return jsonify({"error": "Unauthorized"}), 401
        return jsonify(admin)

    user = find_user_by_id(auth["id"])
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    user["role"] = user.get("role", "user")
    user["profile_photo"] = build_photo_url(user.get("profile_photo"))
    return jsonify(user)


@app.route("/api/auth/debug", methods=["GET"])
def auth_debug():
    """Debug endpoint - shows auth headers and auth object"""
    auth = get_auth()
    headers = {
        "X-Auth-Role": request.headers.get("X-Auth-Role"),
        "X-Auth-User-Id": request.headers.get("X-Auth-User-Id"),
    }
    return jsonify({
        "headers": headers,
        "auth": auth,
        "auth_computed_from_headers": get_auth() is not None
    })


@app.route("/api/admin/init-db", methods=["POST"])
def init_db():
    """Initialize/reset database schema - admin only"""
    auth = get_auth()
    if not auth or auth["role"] != "admin":
        return jsonify({"error": "Forbidden"}), 403
    
    try:
        conn = get_conn()
        cur = conn.cursor()
        
        # Read and execute schema
        with open("../database/schema.sql", "r") as f:
            schema = f.read()
        
        # Split by semicolons and execute each statement
        for statement in schema.split(";"):
            statement = statement.strip()
            if statement:
                cur.execute(statement)
        
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({"message": "Database initialized successfully"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/users/pending", methods=["GET"])
def pending_users():
    auth = get_auth()
    if not auth or auth["role"] != "admin":
        return jsonify({"error": "Forbidden"}), 403

    conn = get_conn(); cur = conn.cursor()
    cur.execute(
        "SELECT id, username, email, phone, status, updated_at FROM users WHERE status='pending' ORDER BY updated_at"
    )
    data = rows(cur)
    cur.close(); conn.close()
    return jsonify(data)


@app.route("/api/users", methods=["GET"])
def list_users():
    auth = get_auth()
    if not auth or auth["role"] not in ("admin", "staff"):
        return jsonify({"error": "Forbidden"}), 403

    status = (request.args.get("status") or "").strip().lower()
    role = (request.args.get("role") or "").strip().lower()
    q = (request.args.get("q") or "").strip()
    sort_by = (request.args.get("sort_by") or "updated_at").strip().lower()
    sort_dir = (request.args.get("sort_dir") or "desc").strip().lower()
    try:
        page = max(int(request.args.get("page", 1)), 1)
    except ValueError:
        page = 1
    try:
        page_size = min(max(int(request.args.get("page_size", 10)), 1), 100)
    except ValueError:
        page_size = 10

    sort_columns = {
        "name": "username",
            "date_joined": "updated_at",
            "created_at": "updated_at",
        "status": "status",
        "role": "role",
    }
    sort_col = sort_columns.get(sort_by, "updated_at")
    sort_dir = "asc" if sort_dir == "asc" else "desc"

    filters = []
    params = []
    if status in ("pending", "approved", "rejected"):
        filters.append("status=%s")
        params.append(status)
    if role in ("admin", "staff", "user"):
        filters.append("role=%s")
        params.append(role)
    if q:
        filters.append("(username LIKE %s OR email LIKE %s OR phone LIKE %s)")
        wildcard = f"%{q}%"
        params.extend([wildcard, wildcard, wildcard])

    where_sql = ""
    if filters:
        where_sql = "WHERE " + " AND ".join(filters)

    offset = (page - 1) * page_size

    conn = get_conn(); cur = conn.cursor()
    count_sql = f"SELECT COUNT(*) FROM users {where_sql}"
    cur.execute(count_sql, tuple(params))
    total = cur.fetchone()[0]

    query = f"SELECT id, username, email, phone, role, status, updated_at FROM users {where_sql} ORDER BY {sort_col} {sort_dir} LIMIT %s OFFSET %s"
    cur.execute(query, (*params, page_size, offset))
    data = rows(cur)
    cur.close(); conn.close()

    return jsonify({
        "data": data,
        "page": page,
        "page_size": page_size,
        "total": total,
    })


@app.route("/api/users/<int:user_id>/review", methods=["POST"])
def review_user(user_id):
    auth = get_auth()
    if not auth or auth["role"] != "admin":
        return jsonify({"error": "Forbidden"}), 403

    payload = request.get_json() or {}
    action = (payload.get("action") or "").strip().lower()
    comment = (payload.get("comment") or "").strip()
    if action not in ("approve", "reject"):
        return jsonify({"error": "Action must be approve or reject"}), 400

    target_status = "approved" if action == "approve" else "rejected"
    conn = get_conn(); cur = conn.cursor()
    try:
        cur.execute("SELECT status FROM users WHERE id=%s", (user_id,))
        row = cur.fetchone()
        if not row:
            return jsonify({"error": "User not found"}), 404

        cur.execute("UPDATE users SET status=%s WHERE id=%s", (target_status, user_id))
        cur.execute(
            "INSERT INTO user_status_history (user_id, status, comment) VALUES (%s, %s, %s)",
            (user_id, target_status, comment or f"{action.capitalize()}ed by admin"),
        )
        # Notify the user about their review status
        if action == "approve":
            title = "User Approved"
            msg = "Your account has been approved. You can now log in and access the library."
            cur.execute(
                "INSERT INTO notifications (user_id, recipient_role, title, message, type, related_id) VALUES (%s, %s, %s, %s, %s, %s)",
                (user_id, 'user', title, msg, 'OTHER', user_id)
            )
        else:
            # rejection message may include the comment if provided
            title = "User Rejected"
            reason = comment or "Your registration was rejected by admin."
            msg = f"Registration update: {reason}"
            cur.execute(
                "INSERT INTO notifications (user_id, recipient_role, title, message, type, related_id) VALUES (%s, %s, %s, %s, %s, %s)",
                (user_id, 'user', title, msg, 'OTHER', user_id)
            )
        conn.commit()
        return jsonify({"message": f"User {target_status}."})
    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        cur.close(); conn.close()


@app.route("/api/users/me/status-history", methods=["GET"])
def my_status_history():
    auth = get_auth()
    if not auth or auth["role"] != "user":
        return jsonify({"error": "Forbidden"}), 403

    conn = get_conn(); cur = conn.cursor()
    cur.execute(
        "SELECT status, comment, updated_at FROM user_status_history WHERE user_id=%s ORDER BY updated_at DESC",
        (auth["id"],),
    )
    data = rows(cur)
    cur.close(); conn.close()
    return jsonify(data)


def _records(auth=None, base_where="", params=()):
    where_sql = base_where
    if auth and auth["role"] == "user":
        if base_where.strip():
            where_sql = f"{base_where} AND r.user_id=%s"
        else:
            where_sql = "WHERE r.user_id=%s"
        params = (*params, auth["id"])

    conn = get_conn(); cur = conn.cursor()
    sql = f"""SELECT r.id, r.book_id, b.title, b.subject, b.author,
                     r.user_id, r.borrower_name, r.borrow_date, r.due_date,
                     r.returned_date, r.status
              FROM borrow_records r
              JOIN books b ON b.id = r.book_id
              {where_sql}
              AND r.borrow_date IS NOT NULL
              AND r.due_date IS NOT NULL
              ORDER BY r.borrow_date DESC, r.id DESC"""
    cur.execute(sql, params)
    data = rows(cur)
    cur.close(); conn.close()
    for d in data:
        for k in ("borrow_date", "due_date", "returned_date"):
            if d.get(k) is not None:
                d[k] = str(d[k])
    return data



@app.route("/api/records", methods=["GET"])
def all_records():
    auth = get_auth()
    if not auth:
        return jsonify({"error": "Unauthorized"}), 401
    return jsonify(_records(auth))


@app.route("/api/records/active", methods=["GET"])
def active_records():
    auth = get_auth()
    if not auth:
        return jsonify({"error": "Unauthorized"}), 401
    
    conn = get_conn(); cur = conn.cursor()
    try:
        where_clause = ""
        params = ()
        
        # For regular users, filter by their user_id
        if auth["role"] == "user":
            where_clause = "WHERE bb.user_id=%s"
            params = (auth["id"],)
        elif auth["role"] in ("admin", "staff"):
            where_clause = ""
        else:
            return jsonify({"error": "Unauthorized"}), 401
        
        sql = f"""SELECT bb.id, bb.book_id, b.title, b.subject, b.author,
                         bb.user_id, br.borrower_name, bb.borrowed_date, bb.due_date,
                         bb.status, bb.request_id
                  FROM borrowed_books bb
                  JOIN books b ON b.id = bb.book_id
                  JOIN borrow_records br ON br.id = bb.request_id
                  {where_clause}
                  ORDER BY bb.borrowed_date DESC, bb.id DESC"""
        
        cur.execute(sql, params)
        data = rows(cur)
        
        # Format dates
        for d in data:
            if d.get("borrowed_date"):
                d["borrow_date"] = str(d["borrowed_date"])
                del d["borrowed_date"]
            if d.get("due_date") is not None:
                d["due_date"] = str(d["due_date"])
        
        return jsonify(data)
    finally:
        cur.close(); conn.close()


@app.route("/api/records/history", methods=["GET"])
def history_records():
    auth = get_auth()
    if not auth:
        return jsonify({"error": "Unauthorized"}), 401
    return jsonify(_records(auth, "WHERE r.status='returned'"))


@app.route("/api/records/overdue", methods=["GET"])
def overdue_records():
    auth = get_auth()
    if not auth or auth["role"] not in ("admin", "staff"):
        return jsonify({"error": "Forbidden"}), 403
    
    conn = get_conn(); cur = conn.cursor()
    try:
        today = date.today()
        sql = f"""SELECT bb.id, bb.book_id, b.title, b.subject, b.author,
                         bb.user_id, br.borrower_name, bb.borrowed_date, bb.due_date,
                         bb.status, bb.request_id
                  FROM borrowed_books bb
                  JOIN books b ON b.id = bb.book_id
                  JOIN borrow_records br ON br.id = bb.request_id
                  WHERE (bb.status='overdue' OR (bb.status='borrowed' AND bb.due_date < %s))
                  ORDER BY bb.due_date ASC, bb.id DESC"""
        
        cur.execute(sql, (today,))
        data = rows(cur)
        
        # Format dates and mark overdue
        for d in data:
            if d.get("borrowed_date"):
                d["borrow_date"] = str(d["borrowed_date"])
                del d["borrowed_date"]
            if d.get("due_date") is not None:
                d["due_date"] = str(d["due_date"])
            # Mark as overdue if past due
            if d["status"] == "borrowed" and date.fromisoformat(d["due_date"]) < today:
                d["status"] = "overdue"
        
        return jsonify(data)
    finally:
        cur.close(); conn.close()


@app.route("/api/borrow", methods=["POST"])
def borrow():
    auth = get_auth()
    if not auth or auth["role"] != "user":
        return jsonify({"error": "Only approved users can borrow books"}), 403

    user = find_user_by_id(auth["id"])
    if not user:
        return jsonify({"error": "User not found"}), 401
    if user["status"] == "rejected":
        return jsonify({"error": "Account rejected"}), 403

    payload = request.get_json() or {}
    book_id = payload.get("book_id")
    if not book_id:
        return jsonify({"error": "book_id required"}), 400

    conn = get_conn(); cur = conn.cursor()
    try:
        # Get book title for notification
        cur.execute("SELECT title FROM books WHERE id=%s", (book_id,))
        book_row = cur.fetchone()
        book_title = book_row[0] if book_row else "Unknown Book"
        
        # Create a borrow request; staff/admin will approve and convert to 'borrowed'
        cur.execute(
            "INSERT INTO borrow_records (book_id, user_id, borrower_name, status) VALUES (%s, %s, %s, 'requested')",
            (book_id, auth["id"], user["username"]),
        )
        record_id = cur.lastrowid
        
        # Create notification for all staff members
        notification_message = f"{user['username']} requested to borrow {book_title}"
        notification_title = f"Borrow Request: {book_title}"
         
        # Get all staff and admin users
        cur.execute("SELECT id FROM users WHERE role IN ('staff', 'admin')")
        staff_users = cur.fetchall()
         
        for staff_row in staff_users:
            staff_id = staff_row[0]
            # Check if notification already exists for this request
            cur.execute(
                "SELECT id FROM notifications WHERE user_id=%s AND related_id=%s AND type='BORROW_REQUEST'",
                (staff_id, record_id)
            )
            if not cur.fetchone():  # Only insert if not already exists
                cur.execute(
                    "INSERT INTO notifications (user_id, recipient_role, title, message, type, related_id) VALUES (%s, %s, %s, %s, %s, %s)",
                    (staff_id, 'staff', notification_title, notification_message, 'BORROW_REQUEST', record_id)
                )
         
        conn.commit()
        return jsonify({
            "id": record_id,
            "book_id": book_id,
            "borrower_name": user["username"],
            "status": "requested"
        }), 201
    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        cur.close(); conn.close()


@app.route("/api/users/me/profile", methods=["POST"])
def update_user_profile_with_photo():
    auth = get_auth()
    if not auth or auth["role"] not in ("user", "staff", "admin"):
        return jsonify({"error": "Unauthorized"}), 401

    if request.is_json:
        payload = request.get_json() or {}
        username = (payload.get("username") or "").strip()
        email = (payload.get("email") or "").strip()
        phone = (payload.get("phone") or "").strip()
        password = (payload.get("password") or "").strip() or None
        permanent_address = (payload.get("permanent_address") or "").strip() or None
        temporary_address = (payload.get("temporary_address") or "").strip() or None
    else:
        username = (request.form.get("username") or "").strip()
        email = (request.form.get("email") or "").strip()
        phone = (request.form.get("phone") or "").strip()
        password = (request.form.get("password") or "").strip() or None
        permanent_address = (request.form.get("permanent_address") or "").strip() or None
        temporary_address = (request.form.get("temporary_address") or "").strip() or None

    profile_photo = None
    if "profile_photo" in request.files:
        photo = request.files["profile_photo"]
        if photo and allowed_file(photo.filename):
            filename = secure_filename(photo.filename)
            filename = f"{int(time.time())}_{filename}"
            save_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
            photo.save(save_path)
            profile_photo = filename
        else:
            return jsonify({"error": "Invalid image file"}), 400

    if not username or not email or not phone:
        return jsonify({"error": "Username, email, and phone are required."}), 400

    # Validate phone number: must be exactly 10 digits
    phone_digits = ''.join(c for c in phone if c.isdigit())
    if len(phone_digits) != 10:
        return jsonify({"error": "Enter valid number"}), 400

    conn = get_conn(); cur = conn.cursor()
    try:
        cur.execute("SELECT COUNT(*) FROM users WHERE username=%s AND id<>%s", (username, auth["id"]))
        if cur.fetchone()[0] > 0:
            return jsonify({"error": "Username already taken."}), 400
        cur.execute("SELECT COUNT(*) FROM users WHERE email=%s AND id<>%s", (email, auth["id"]))
        if cur.fetchone()[0] > 0:
            return jsonify({"error": "Email already in use."}), 400
        cur.execute("SELECT COUNT(*) FROM users WHERE phone=%s AND id<>%s", (phone, auth["id"]))
        if cur.fetchone()[0] > 0:
            return jsonify({"error": "Phone number already in use."}), 400

        updates = ["username=%s", "email=%s", "phone=%s", "permanent_address=%s", "temporary_address=%s"]
        params = [username, email, phone, permanent_address, temporary_address]

        if password:
            hashed = generate_password_hash(password)
            updates.append("password=%s")
            params.append(hashed)
        if profile_photo is not None:
            updates.append("profile_photo=%s")
            params.append(profile_photo)

        params.append(auth["id"])
        cur.execute(f"UPDATE users SET {', '.join(updates)} WHERE id=%s", tuple(params))
        conn.commit()
        updated_user = find_user_by_id(auth["id"])
        updated_user["profile_photo"] = build_photo_url(updated_user.get("profile_photo"))
        return jsonify(updated_user)
    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        cur.close(); conn.close()


@app.route("/api/return/<int:record_id>", methods=["POST"])
def return_book(record_id):
    auth = get_auth()
    if not auth or auth["role"] != "user":
        return jsonify({"error": "Only borrowers can return books"}), 403

    conn = get_conn(); cur = conn.cursor()
    try:
        cur.execute("SELECT book_id, status, user_id FROM borrow_records WHERE id=%s FOR UPDATE", (record_id,))
        row = cur.fetchone()
        if not row:
            return jsonify({"error": "Record not found"}), 404
        book_id, status, record_user_id = row
        if record_user_id != auth["id"]:
            return jsonify({"error": "You may only return your own borrowed books"}), 403
        if status == "returned":
            return jsonify({"error": "Already returned"}), 400

        # Update borrow_records
        cur.execute(
            "UPDATE borrow_records SET status='returned', returned_date=%s WHERE id=%s",
            (date.today(), record_id),
        )
        # Update borrowed_books (mark as returned)
        cur.execute(
            "UPDATE borrowed_books SET status='returned' WHERE request_id=%s",
            (record_id,)
        )
        # Increment available copies
        cur.execute("UPDATE books SET available_copies = available_copies + 1 WHERE id=%s", (book_id,))
        conn.commit()
        return jsonify({"message": "Book returned", "record_id": record_id})
    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        cur.close(); conn.close()


@app.route("/", methods=["GET"])
def index():
    return jsonify({"service": "Library Management API", "status": "ok"})




@app.route("/api/records/requests", methods=["GET"])
def request_records():
    auth = get_auth()
    if not auth or auth["role"] not in ("admin","staff"):
        return jsonify({"error":"Forbidden"}),403
    
    # Fetch all pending requests (status='requested') without the borrow_date/due_date constraint
    # because these are NULL until the request is approved
    conn = get_conn(); cur = conn.cursor()
    sql = """SELECT r.id, r.book_id, b.title, b.subject, b.author,
                     r.user_id, r.borrower_name, r.borrow_date, r.due_date,
                     r.returned_date, r.status
              FROM borrow_records r
              JOIN books b ON b.id = r.book_id
              WHERE r.status='requested'
              ORDER BY r.id DESC"""
    cur.execute(sql)
    data = rows(cur)
    cur.close(); conn.close()
    for d in data:
        for k in ("borrow_date", "due_date", "returned_date"):
            if d.get(k) is not None:
                d[k] = str(d[k])
    return jsonify(data)


@app.route("/api/records/<int:record_id>/approve", methods=["POST"])
def approve_request(record_id):
    auth = get_auth()
    if not auth or auth["role"] not in ("admin","staff"):
        return jsonify({"error":"Forbidden"}),403
    conn = get_conn(); cur = conn.cursor()
    try:
        cur.execute("SELECT book_id, status, user_id FROM borrow_records WHERE id=%s FOR UPDATE", (record_id,))
        row = cur.fetchone()
        if not row:
            return jsonify({"error":"Record not found"}),404
        book_id, status, user_id = row
        if status != "requested":
            return jsonify({"error":"Record not in requested state"}),400
        cur.execute("SELECT b.title, b.available_copies FROM books b WHERE b.id=%s FOR UPDATE", (book_id,))
        br = cur.fetchone()
        if not br:
            return jsonify({"error":"Book not found"}),404
        book_title, available_copies = br
        # Check if any copies are available
        if available_copies <= 0:
            msg = f"Staff has rejected your borrow request for \"{book_title}\" because no copies are available."
            cur.execute("UPDATE borrow_records SET status='rejected' WHERE id=%s", (record_id,))
            cur.execute(
                "INSERT INTO notifications (user_id, recipient_role, title, message, type, related_id) VALUES (%s, %s, %s, %s, %s, %s)",
                (user_id, 'user', f"Request Rejected: {book_title}", msg, 'OTHER', record_id)
            )
            conn.commit()
            return jsonify({"message":"Request rejected (no copies)", "record_id":record_id, "reason": msg}), 200
        borrow_date = date.today()
        due_date = borrow_date + timedelta(days=LOAN_DAYS)
        # Update borrow_records with borrowed status and dates
        cur.execute("UPDATE borrow_records SET status='borrowed', borrow_date=%s, due_date=%s WHERE id=%s", (borrow_date, due_date, record_id))
        # Insert into borrowed_books table to track active borrowing
        cur.execute(
            "INSERT INTO borrowed_books (request_id, book_id, user_id, borrowed_date, due_date, status) VALUES (%s, %s, %s, %s, %s, %s)",
            (record_id, book_id, user_id, borrow_date, due_date, 'borrowed')
        )
        # Decrement available copies
        cur.execute("UPDATE books SET available_copies = available_copies - 1 WHERE id=%s", (book_id,))
        msg = f"Staff has approved your borrow request for \"{book_title}\". Please collect the book and return by {str(due_date)}."
        cur.execute(
            "INSERT INTO notifications (user_id, recipient_role, title, message, type, related_id) VALUES (%s, %s, %s, %s, %s, %s)",
            (user_id, 'user', f"Request Approved: {book_title}", msg, 'OTHER', record_id)
        )
        conn.commit()
        return jsonify({"message":"Request approved", "record_id":record_id})
    except Exception as e:
        conn.rollback()
        return jsonify({"error":str(e)}),500
    finally:
        cur.close(); conn.close()


@app.route("/api/records/<int:record_id>/reject", methods=["POST"])
def reject_request(record_id):
    auth = get_auth()
    if not auth or auth["role"] not in ("admin","staff"):
        return jsonify({"error":"Forbidden"}),403
    conn = get_conn(); cur = conn.cursor()
    try:
        cur.execute("SELECT book_id, status, user_id FROM borrow_records WHERE id=%s FOR UPDATE", (record_id,))
        row = cur.fetchone()
        if not row:
            return jsonify({"error":"Record not found"}),404
        book_id, status, user_id = row
        if status != "requested":
            return jsonify({"error":"Record not in requested state"}),400

        cur.execute("SELECT title FROM books WHERE id=%s", (book_id,))
        br = cur.fetchone()
        book_title = br[0] if br else "requested book"
        cur.execute("UPDATE borrow_records SET status='rejected' WHERE id=%s", (record_id,))
        msg = f"Your borrow request for \"{book_title}\" has been rejected by staff."
        cur.execute(
            "INSERT INTO notifications (user_id, recipient_role, title, message, type, related_id) VALUES (%s, %s, %s, %s, %s, %s)",
            (user_id, 'user', f"Request Rejected: {book_title}", msg, 'OTHER', record_id)
        )
        conn.commit()
        return jsonify({"message":"Request rejected", "record_id":record_id})
    except Exception as e:
        conn.rollback()
        return jsonify({"error":str(e)}),500
    finally:
        cur.close(); conn.close()


@app.route("/uploads/<path:filename>", methods=["GET"])
def serve_upload(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)


@app.route("/api/notifications", methods=["GET"])
def get_notifications():
    auth = get_auth()
    if not auth:
        return jsonify({"error":"Unauthorized"}),401
    
    conn = get_conn(); cur = conn.cursor()
    
    # Mark any past-due borrowed records as overdue (if not already marked)
    try:
        cur.execute(
            "SELECT r.id, r.user_id, b.title, r.due_date FROM borrow_records r "
            "JOIN books b ON b.id = r.book_id "
            "WHERE r.status = 'borrowed' AND r.due_date < %s",
            (date.today(),)
        )
        overdue_rows = cur.fetchall()
        for orow in overdue_rows:
            rec_id, uid, title, due_date = orow
            try:
                # Check if we already have an OVERDUE_BOOK notification for this record
                cur.execute("SELECT id FROM notifications WHERE type='OVERDUE_BOOK' AND related_id=%s", (rec_id,))
                if not cur.fetchone():
                    # Mark as overdue
                    cur.execute("UPDATE borrow_records SET status='overdue' WHERE id=%s", (rec_id,))
                    
                    # Create notification for the user who borrowed it
                    late_days = (date.today() - due_date).days
                    msg = f"Your borrow '{title}' is {late_days} day{'s' if late_days != 1 else ''} late. Please return it."
                    cur.execute(
                        "INSERT INTO notifications (user_id, recipient_role, title, message, type, related_id) "
                        "VALUES (%s, %s, %s, %s, %s, %s)",
                        (uid, 'user', f"Overdue: {title}", msg, 'OVERDUE_BOOK', rec_id)
                    )
                    
                    # Create notification for admin about the overdue
                    cur.execute("SELECT username FROM users WHERE id=%s", (uid,))
                    user_row = cur.fetchone()
                    borrower_name = user_row[0] if user_row else "Unknown"
                    admin_msg = f"{borrower_name} has overdue book: {title}, due on {due_date}"
                    
                    cur.execute("SELECT id FROM users WHERE role='admin'")
                    admin_users = cur.fetchall()
                    for admin_row in admin_users:
                        admin_id = admin_row[0]
                        cur.execute(
                            "INSERT INTO notifications (user_id, recipient_role, title, message, type, related_id) "
                            "VALUES (%s, %s, %s, %s, %s, %s)",
                            (admin_id, 'admin', f"Overdue: {title}", admin_msg, 'OVERDUE_BOOK', rec_id)
                        )
            except Exception as e:
                # ignore per-record errors and continue
                conn.rollback()
                continue
        
        if overdue_rows:
            conn.commit()
    except Exception:
        # best-effort only; don't block notifications retrieval
        conn.rollback()
    
    # Get notifications based on user role
    if auth["role"] == "user":
        # Users see only their own notifications
        cur.execute(
            "SELECT id, title, message, type, is_read, created_at FROM notifications "
            "WHERE user_id=%s ORDER BY created_at DESC LIMIT 50",
            (auth["id"],)
        )
    elif auth["role"] == "staff":
        # Staff see BORROW_REQUEST notifications (for their role)
        cur.execute(
            "SELECT id, title, message, type, is_read, created_at FROM notifications "
            "WHERE recipient_role='staff' AND type='BORROW_REQUEST' ORDER BY created_at DESC LIMIT 50"
        )
    elif auth["role"] == "admin":
        # Admin see USER_REGISTRATION and OVERDUE_BOOK notifications (for their role)
        cur.execute(
            "SELECT id, title, message, type, is_read, created_at FROM notifications "
            "WHERE (recipient_role='admin') AND (type='USER_REGISTRATION' OR type='OVERDUE_BOOK') "
            "ORDER BY created_at DESC LIMIT 50"
        )
    else:
        return jsonify({"error":"Invalid role"}),400
    
    data = rows(cur)
    cur.close(); conn.close()
    return jsonify(data)


@app.route("/api/notifications/overdue-count", methods=["GET"])
def overdue_count():
    auth = get_auth()
    if not auth:
        return jsonify({"error":"Unauthorized"}),401
    
    conn = get_conn(); cur = conn.cursor()
    
    if auth["role"] == "admin":
        # Admin sees unread OVERDUE_BOOK notifications
        cur.execute(
            "SELECT COUNT(*) FROM notifications WHERE recipient_role='admin' AND type='OVERDUE_BOOK' AND is_read=0"
        )
        cnt = cur.fetchone()[0]
    elif auth["role"] == "staff":
        # Staff sees unread BORROW_REQUEST notifications
        cur.execute(
            "SELECT COUNT(*) FROM notifications WHERE recipient_role='staff' AND type='BORROW_REQUEST' AND is_read=0"
        )
        cnt = cur.fetchone()[0]
    elif auth["role"] == "user":
        # Users see unread notifications (all types)
        cur.execute(
            "SELECT COUNT(*) FROM notifications WHERE user_id=%s AND is_read=0",
            (auth["id"],)
        )
        cnt = cur.fetchone()[0]
    else:
        cnt = 0
    
    cur.close(); conn.close()
    return jsonify({"count": cnt})


@app.route("/api/profile", methods=["GET"])
def get_profile():
    """Get current logged-in user profile (works for all roles)"""
    auth = get_auth()
    if not auth:
        return jsonify({"error": "Unauthorized"}), 401
    
    conn = get_conn(); cur = conn.cursor()
    try:
        cur.execute(
            "SELECT id, username, email, phone, role, status, profile_photo, permanent_address, temporary_address FROM users WHERE id=%s",
            (auth["id"],)
        )
        row = cur.fetchone()
        if not row:
            return jsonify({"error": "User not found"}), 404
        
        cols = ["id", "username", "email", "phone", "role", "status", "profile_photo", "permanent_address", "temporary_address"]
        profile = dict(zip(cols, row))
        profile["profile_photo"] = build_photo_url(profile.get("profile_photo"))
        
        cur.close(); conn.close()
        return jsonify(profile)
    except Exception as e:
        cur.close(); conn.close()
        return jsonify({"error": str(e)}), 500


@app.route("/api/profile", methods=["PATCH"])
def update_profile():
    """Update current logged-in user profile"""
    auth = get_auth()
    if not auth:
        return jsonify({"error": "Unauthorized"}), 401
    
    payload = request.get_json() or {}
    
    # Allowed fields to update
    updates = {}
    fields = {
        "username": str,
        "email": str,
        "phone": str,
        "permanent_address": str,
        "temporary_address": str,
        "password": str,
    }
    
    conn = get_conn(); cur = conn.cursor()
    try:
        # Get current user
        cur.execute("SELECT id, username, email, phone FROM users WHERE id=%s", (auth["id"],))
        current = cur.fetchone()
        if not current:
            return jsonify({"error": "User not found"}), 404
        
        current_id, current_username, current_email, current_phone = current
        
        # Build updates
        for field, field_type in fields.items():
            if field in payload and payload[field] is not None:
                value = str(payload[field]).strip() if field != "password" else payload[field]
                if value:
                    updates[field] = value
        
        if not updates:
            cur.close(); conn.close()
            return jsonify({"error": "No updates provided"}), 400
        
        # Validate phone format
        if "phone" in updates:
            phone_digits = ''.join(c for c in updates["phone"] if c.isdigit())
            if len(phone_digits) != 10:
                cur.close(); conn.close()
                return jsonify({"error": "Enter valid number"}), 400
        
        # Check for duplicate email/phone (only if changed)
        if "email" in updates and updates["email"] != current_email:
            cur.execute("SELECT id FROM users WHERE email=%s", (updates["email"],))
            if cur.fetchone():
                cur.close(); conn.close()
                return jsonify({"error": "Email already in use"}), 400
        
        if "phone" in updates and updates["phone"] != current_phone:
            cur.execute("SELECT id FROM users WHERE phone=%s", (updates["phone"],))
            if cur.fetchone():
                cur.close(); conn.close()
                return jsonify({"error": "Phone already in use"}), 400
        
        # Hash password if provided
        if "password" in updates:
            updates["password"] = generate_password_hash(updates["password"])
        
        # Build SQL update
        set_clause = ", ".join([f"{k}=%s" for k in updates.keys()])
        sql = f"UPDATE users SET {set_clause} WHERE id=%s"
        values = list(updates.values()) + [auth["id"]]
        
        cur.execute(sql, tuple(values))
        conn.commit()
        
        # Return updated profile
        cur.execute(
            "SELECT id, username, email, phone, role, status, profile_photo, permanent_address, temporary_address FROM users WHERE id=%s",
            (auth["id"],)
        )
        row = cur.fetchone()
        cols = ["id", "username", "email", "phone", "role", "status", "profile_photo", "permanent_address", "temporary_address"]
        profile = dict(zip(cols, row))
        profile["profile_photo"] = build_photo_url(profile.get("profile_photo"))
        
        cur.close(); conn.close()
        return jsonify({"message": "Profile updated", "profile": profile})
    except Exception as e:
        conn.rollback()
        cur.close(); conn.close()
        return jsonify({"error": str(e)}), 500


@app.route("/api/notifications/<int:notification_id>/read", methods=["POST"])
def mark_notification_read(notification_id):
    """Mark a single notification as read"""
    auth = get_auth()
    if not auth:
        return jsonify({"error": "Unauthorized"}), 401
    
    conn = get_conn(); cur = conn.cursor()
    try:
        # Verify notification belongs to current user
        cur.execute("SELECT user_id FROM notifications WHERE id=%s", (notification_id,))
        row = cur.fetchone()
        if not row or row[0] != auth["id"]:
            cur.close(); conn.close()
            return jsonify({"error": "Not found"}), 404
        
        cur.execute("UPDATE notifications SET is_read=1 WHERE id=%s", (notification_id,))
        conn.commit()
        cur.close(); conn.close()
        return jsonify({"message": "Marked as read"})
    except Exception as e:
        conn.rollback()
        cur.close(); conn.close()
        return jsonify({"error": str(e)}), 500


@app.route("/api/notifications/mark-all-read", methods=["POST"])
def mark_all_notifications_read():
    """Mark all notifications as read for current user"""
    auth = get_auth()
    if not auth:
        return jsonify({"error": "Unauthorized"}), 401
    
    conn = get_conn(); cur = conn.cursor()
    try:
        cur.execute("UPDATE notifications SET is_read=1 WHERE user_id=%s AND is_read=0", (auth["id"],))
        updated = cur.rowcount
        conn.commit()
        cur.close(); conn.close()
        return jsonify({"message": "All marked as read", "count": updated})
    except Exception as e:
        conn.rollback()
        cur.close(); conn.close()
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    debug_mode = os.getenv("FLASK_DEBUG", "False").lower() in ("true", "1", "yes")
    app.run(host="0.0.0.0", port=5000, debug=debug_mode)
