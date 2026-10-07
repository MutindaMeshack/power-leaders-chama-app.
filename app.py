import json
import os
import random
from datetime import datetime, timedelta
from flask import Flask, flash, redirect, render_template, request, session, url_for
from flask_mail import Mail, Message
from werkzeug.security import check_password_hash, generate_password_hash
from dotenv import load_dotenv
from flask import send_file
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from io import BytesIO
from werkzeug.utils import secure_filename

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY")

# --- Flask-Mail configuration ---
app.config["MAIL_SERVER"] = "smtp.gmail.com"
app.config["MAIL_PORT"] = 587
app.config["MAIL_USE_TLS"] = True
app.config["MAIL_USERNAME"] = os.getenv("MAIL_USERNAME")
app.config["MAIL_PASSWORD"] = os.getenv("MAIL_PASSWORD")
app.config["MAIL_DEFAULT_SENDER"] = os.getenv("MAIL_USERNAME")

mail = Mail(app)

ADMIN_EMAIL = os.getenv("ADMIN_EMAIL")
DATA_FILE = "chama_data.json"


import hmac
import threading
from flask import jsonify
from sms_parser import parse_bank_sms, find_member_by_name

BANK_ACCOUNT_NUMBER = os.getenv("BANK_ACCOUNT_NUMBER")
SMS_WEBHOOK_SECRET = os.getenv("SMS_WEBHOOK_SECRET")
SMS_ALLOWED_SENDER = os.getenv("SMS_ALLOWED_SENDER", "CoopBank")
data_lock = threading.Lock()


def load_data():
    if not os.path.exists(DATA_FILE) or os.path.getsize(DATA_FILE) == 0:
        return {
            "bank_balance": 0,
            "penalty_amount": 200,
            "contribution_due_day": 10,
            "reminder_day": 5,
            "tracking_start_date": "2026-10-01",
            "admin": {"email": ADMIN_EMAIL},
            "suspense_pool": [],
            "members": [],
            "feedback": [],
            "documents": [],
        }
    with open(DATA_FILE, "r") as f:
        return json.load(f)


def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)


# ============================================
# Routes: Member Registration
# ============================================
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        phone = request.form.get("phone", "").strip()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not phone or not password:
            flash("Phone number and password are required.", "danger")
            return redirect(url_for("register"))

        if password != confirm_password:
            flash("Passwords do not match.", "danger")
            return redirect(url_for("register"))

        if len(password) < 6:
            flash("Password must be at least 6 characters.", "danger")
            return redirect(url_for("register"))

        data = load_data()
        found_member = None
        for member in data["members"]:
            if member["phone"] == phone:
                found_member = member
                break

        if not found_member:
            flash("This phone number is not recognized. Contact the admin to be added.", "danger")
            return redirect(url_for("register"))

        if found_member.get("password_hash"):
            flash("An account already exists for this phone number. Please log in instead.", "danger")
            return redirect(url_for("member_login"))

        found_member["password_hash"] = generate_password_hash(password)
        save_data(data)

        flash("Account created successfully. You can now log in.", "success")
        return redirect(url_for("member_login"))

    return render_template("register.html")


# ============================================
# Routes: Member Login
# ============================================
@app.route("/login", methods=["GET", "POST"])
def member_login():
    if request.method == "POST":
        phone = request.form.get("phone", "").strip()
        password = request.form.get("password", "")

        data = load_data()
        found_member = None
        for member in data["members"]:
            if member["phone"] == phone:
                found_member = member
                break

        if not found_member:
            flash("Phone number not recognized. Contact the admin to be added.", "danger")
            return redirect(url_for("member_login"))

        if not found_member.get("password_hash"):
            flash("No account exists for this number yet. Please register first.", "danger")
            return redirect(url_for("register"))

        if not check_password_hash(found_member["password_hash"], password):
            flash("Incorrect password.", "danger")
            return redirect(url_for("member_login"))

        session["user_type"] = "member"
        session["member_phone"] = found_member["phone"]
        flash(f"Welcome back, {found_member['name']}!", "success")
        return redirect(url_for("member_dashboard"))

    return render_template("member_login.html")


@app.route("/member/dashboard")
def member_dashboard():
    if session.get("user_type") != "member":
        return redirect(url_for("member_login"))

    data = load_data()
    data = sync_monthly_ledger(data)
    save_data(data)

    current_member = None
    for member in data["members"]:
        if member["phone"] == session.get("member_phone"):
            current_member = member
            break

    if not current_member:
        session.clear()
        return redirect(url_for("member_login"))

    total_balance = current_member["size_balance"] + current_member["loan_balance"]
    return render_template("member_dashboard.html", member=current_member, total_balance=total_balance, data=data)


@app.route("/member/receipt/<int:payment_index>")
def download_receipt(payment_index):
    if session.get("user_type") != "member":
        return redirect(url_for("member_login"))

    data = load_data()
    current_member = None
    for member in data["members"]:
        if member["phone"] == session.get("member_phone"):
            current_member = member
            break

    if not current_member:
        session.clear()
        return redirect(url_for("member_login"))

    history = current_member.get("payment_history", [])
    if payment_index < 0 or payment_index >= len(history):
        flash("Receipt not found.", "danger")
        return redirect(url_for("member_dashboard"))

    payment = history[payment_index]

    buffer = BytesIO()
    p = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    p.setFont("Helvetica-Bold", 18)
    p.drawString(50, height - 60, "Power Leaders Investment Group")

    p.setFont("Helvetica", 11)
    p.drawString(50, height - 90, "Official Payment Receipt")
    p.line(50, height - 100, width - 50, height - 100)

    p.setFont("Helvetica", 12)
    y = height - 140
    p.drawString(50, y, f"Member Name:")
    p.drawString(200, y, current_member["name"])
    y -= 25
    p.drawString(50, y, f"Membership ID:")
    p.drawString(200, y, current_member["member_id"])
    y -= 25
    p.drawString(50, y, f"Phone Number:")
    p.drawString(200, y, current_member["phone"])
    y -= 25
    p.drawString(50, y, f"Payment Date:")
    p.drawString(200, y, payment["date"])
    y -= 25
    p.setFont("Helvetica-Bold", 12)
    p.drawString(50, y, f"Amount Paid:")
    p.drawString(200, y, f"KES {payment['amount']:,.2f}")

    y -= 50
    p.setFont("Helvetica-Oblique", 10)
    p.drawString(50, y, "This receipt confirms the payment above was received and recorded by Power Leaders Investment Group.")

    p.showPage()
    p.save()
    buffer.seek(0)

    filename = f"receipt_{current_member['member_id'].replace(' ', '')}_{payment['date']}.pdf"
    return send_file(buffer, as_attachment=True, download_name=filename, mimetype="application/pdf")


# ============================================
# Routes: Member Feedback
# ============================================
@app.route("/member/feedback", methods=["POST"])
def submit_feedback():
    if session.get("user_type") != "member":
        return redirect(url_for("member_login"))

    category = request.form.get("category", "").strip()
    message = request.form.get("message", "").strip()

    if not category or not message:
        flash("Please select a category and enter a message.", "danger")
        return redirect(url_for("member_dashboard"))

    data = load_data()
    current_member = None
    for member in data["members"]:
        if member["phone"] == session.get("member_phone"):
            current_member = member
            break

    if not current_member:
        session.clear()
        return redirect(url_for("member_login"))

    data.setdefault("feedback", []).append({
        "member_name": current_member["name"],
        "member_phone": current_member["phone"],
        "category": category,
        "message": message,
        "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "resolved": False,
    })
    save_data(data)

    flash("Your feedback has been submitted. Thank you.", "success")
    return redirect(url_for("member_dashboard"))


# ============================================
# Routes: Staff Feedback Review
# ============================================
@app.route("/staff/resolve-feedback/<int:feedback_index>", methods=["POST"])
def staff_resolve_feedback(feedback_index):
    if session.get("user_type") != "staff":
        return redirect(url_for("staff_login"))

    data = load_data()
    feedback_list = data.get("feedback", [])

    if feedback_index < 0 or feedback_index >= len(feedback_list):
        flash("Feedback item not found.", "danger")
        return redirect(url_for("staff_dashboard"))

    feedback_list[feedback_index]["resolved"] = True
    save_data(data)

    flash("Feedback marked as resolved.", "success")
    return redirect(url_for("staff_dashboard"))


# ============================================
# Routes: Document Vault
# ============================================
ALLOWED_EXTENSIONS = {"pdf", "jpg", "jpeg", "png", "docx"}
UPLOAD_FOLDER = os.path.join("static", "uploads")


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


@app.route("/staff/upload-document", methods=["POST"])
def staff_upload_document():
    if session.get("user_type") != "staff":
        return redirect(url_for("staff_login"))

    if "document" not in request.files:
        flash("No file selected.", "danger")
        return redirect(url_for("staff_dashboard"))

    file = request.files["document"]
    title = request.form.get("title", "").strip()

    if file.filename == "":
        flash("No file selected.", "danger")
        return redirect(url_for("staff_dashboard"))

    if not allowed_file(file.filename):
        flash("File type not allowed. Use PDF, JPG, PNG, or DOCX.", "danger")
        return redirect(url_for("staff_dashboard"))

    if not title:
        title = file.filename

    filename = secure_filename(file.filename)
    # Prevent overwriting an existing file with the same name
    save_path = os.path.join(UPLOAD_FOLDER, filename)
    counter = 1
    name_part, ext_part = os.path.splitext(filename)
    while os.path.exists(save_path):
        filename = f"{name_part}_{counter}{ext_part}"
        save_path = os.path.join(UPLOAD_FOLDER, filename)
        counter += 1

    file.save(save_path)

    data = load_data()
    data.setdefault("documents", []).append({
        "title": title,
        "filename": filename,
        "uploaded_date": datetime.now().strftime("%Y-%m-%d"),
    })
    save_data(data)

    flash(f"Document '{title}' uploaded successfully.", "success")
    return redirect(url_for("staff_dashboard"))


@app.route("/documents/download/<filename>")
def download_document(filename):
    if session.get("user_type") not in ("staff", "member"):
        return redirect(url_for("index"))

    safe_name = secure_filename(filename)
    file_path = os.path.join(UPLOAD_FOLDER, safe_name)

    if not os.path.exists(file_path):
        flash("Document not found.", "danger")
        return redirect(url_for("index"))

    return send_file(file_path, as_attachment=True)


@app.route("/staff/delete-document/<int:doc_index>", methods=["POST"])
def staff_delete_document(doc_index):
    if session.get("user_type") != "staff":
        return redirect(url_for("staff_login"))

    data = load_data()
    documents = data.get("documents", [])

    if doc_index < 0 or doc_index >= len(documents):
        flash("Document not found.", "danger")
        return redirect(url_for("staff_dashboard"))

    doc = documents[doc_index]
    file_path = os.path.join(UPLOAD_FOLDER, doc["filename"])
    if os.path.exists(file_path):
        os.remove(file_path)

    documents.pop(doc_index)
    save_data(data)

    flash(f"Document '{doc['title']}' removed.", "success")
    return redirect(url_for("staff_dashboard"))


# ============================================
# OTP Storage (temporary, in-memory)
# ============================================
otp_store = {}  # e.g. {"code": "483920", "expires_at": datetime, "email": "..."}


def generate_otp():
    return str(random.randint(100000, 999999))


def send_otp_email(to_email, otp_code):
    try:
        msg = Message(
            subject="Power Leaders App - Admin Login OTP",
            recipients=[to_email],
            body=f"Your one-time login code is: {otp_code}\n\nThis code expires in 5 minutes.",
        )
        mail.send(msg)
        return True
    except Exception as e:
        print(f"Failed to send OTP email: {e}")
        return False


# ============================================
# Routes: Admin OTP Login
# ============================================
@app.route("/staff/login", methods=["GET", "POST"])
def staff_login():
    admin_email = ADMIN_EMAIL

    if request.method == "POST":
        entered_email = request.form.get("email", "").strip().lower()

        if entered_email != admin_email.lower():
            flash("This email is not recognized for staff access.", "danger")
            return redirect(url_for("staff_login"))

        otp_code = generate_otp()
        otp_store["code"] = otp_code
        otp_store["expires_at"] = datetime.now() + timedelta(minutes=5)
        otp_store["email"] = entered_email

        sent = send_otp_email(entered_email, otp_code)
        if sent:
            flash("An OTP has been sent to the admin email.", "success")
            return redirect(url_for("staff_verify_otp"))
        else:
            flash("Failed to send OTP. Please try again.", "danger")
            return redirect(url_for("staff_login"))

    return render_template("staff_login.html")


@app.route("/staff/verify-otp", methods=["GET", "POST"])
def staff_verify_otp():
    if request.method == "POST":
        entered_otp = request.form.get("otp", "").strip()

        if "code" not in otp_store:
            flash("No OTP was requested. Please start over.", "danger")
            return redirect(url_for("staff_login"))

        if datetime.now() > otp_store["expires_at"]:
            flash("OTP expired. Please request a new one.", "danger")
            otp_store.clear()
            return redirect(url_for("staff_login"))

        if entered_otp == otp_store["code"]:
            session["user_type"] = "staff"
            otp_store.clear()
            flash("Login successful.", "success")
            return redirect(url_for("staff_dashboard"))
        else:
            flash("Incorrect OTP. Please try again.", "danger")
            return redirect(url_for("staff_verify_otp"))

    return render_template("staff_verify_otp.html")


@app.route("/staff/dashboard")
def staff_dashboard():
    if session.get("user_type") != "staff":
        return redirect(url_for("staff_login"))
    data = load_data()
    data = sync_monthly_ledger(data)
    save_data(data)
    return render_template("staff_dashboard.html", data=data)


@app.route("/staff/reset-password/<phone>", methods=["POST"])
def staff_reset_password(phone):
    if session.get("user_type") != "staff":
        return redirect(url_for("staff_login"))

    data = load_data()
    found_member = None
    for member in data["members"]:
        if member["phone"] == phone:
            found_member = member
            break

    if found_member:
        found_member["password_hash"] = ""
        save_data(data)
        flash(f"Password reset for {found_member['name']}. They can now register a new password.", "success")
    else:
        flash("Member not found.", "danger")

    return redirect(url_for("staff_dashboard"))


@app.route("/staff/add-member", methods=["POST"])
def staff_add_member():
    if session.get("user_type") != "staff":
        return redirect(url_for("staff_login"))

    name = request.form.get("name", "").strip()
    phone = request.form.get("phone", "").strip()
    member_id = request.form.get("member_id", "").strip()
    initial_size = request.form.get("initial_size", "0").strip()
    initial_loan = request.form.get("initial_loan", "0").strip()

    if not name or not phone or not member_id:
        flash("Name, phone number, and membership ID are required.", "danger")
        return redirect(url_for("staff_dashboard"))

    try:
        initial_size = float(initial_size) if initial_size else 0
        initial_loan = float(initial_loan) if initial_loan else 0
    except ValueError:
        flash("Starting balances must be numbers.", "danger")
        return redirect(url_for("staff_dashboard"))

    data = load_data()

    for member in data["members"]:
        if member["phone"] == phone:
            flash("A member with this phone number already exists.", "danger")
            return redirect(url_for("staff_dashboard"))
        if member["member_id"].lower() == member_id.lower():
            flash("A member with this membership ID already exists.", "danger")
            return redirect(url_for("staff_dashboard"))

    new_member = {
        "name": name,
        "phone": phone,
        "member_id": member_id,
        "password_hash": "",
        "size_balance": initial_size,
        "loan_balance": initial_loan,
        "advance_balance": 0,
        "missed_months": [],
        "payment_history": [],
        "monthly_contributions": [],
    }
    data["members"].append(new_member)
    save_data(data)

    flash(f"Member {name} added successfully.", "success")
    return redirect(url_for("staff_dashboard"))


@app.route("/staff/disburse-loan", methods=["POST"])
def staff_disburse_loan():
    if session.get("user_type") != "staff":
        return redirect(url_for("staff_login"))

    phone = request.form.get("phone", "").strip()
    amount_str = request.form.get("amount", "").strip()
    note = request.form.get("note", "").strip()

    try:
        amount = float(amount_str)
    except (ValueError, TypeError):
        flash("Invalid loan amount.", "danger")
        return redirect(url_for("staff_dashboard"))

    if amount <= 0:
        flash("Loan amount must be greater than zero.", "danger")
        return redirect(url_for("staff_dashboard"))

    with data_lock:
        data = load_data()

        if amount > data.get("bank_balance", 0):
            flash(
                f"Cannot disburse KES {amount:,.2f}. Group account only has "
                f"KES {data.get('bank_balance', 0):,.2f} available.",
                "danger",
            )
            return redirect(url_for("staff_dashboard"))

        target_member = None
        for m in data["members"]:
            if m["phone"] == phone:
                target_member = m
                break

        if not target_member:
            flash("Member not found.", "danger")
            return redirect(url_for("staff_dashboard"))

        target_member["loan_balance"] = target_member.get("loan_balance", 0) + amount
        data["bank_balance"] -= amount

        target_member.setdefault("loan_history", []).append({
            "date": datetime.now().strftime("%Y-%m-%d"),
            "amount": amount,
            "note": note,
        })

        save_data(data)

    flash(
        f"Loan of KES {amount:,.2f} disbursed to {target_member['name']}. "
        f"Group balance is now KES {data['bank_balance']:,.2f}.",
        "success",
    )
    return redirect(url_for("staff_dashboard"))


@app.route("/staff/remove-member/<phone>", methods=["POST"])
def staff_remove_member(phone):
    if session.get("user_type") != "staff":
        return redirect(url_for("staff_login"))

    data = load_data()
    member_to_remove = None
    for member in data["members"]:
        if member["phone"] == phone:
            member_to_remove = member
            break

    if not member_to_remove:
        flash("Member not found.", "danger")
        return redirect(url_for("staff_dashboard"))

    data["members"] = [m for m in data["members"] if m["phone"] != phone]
    save_data(data)

    flash(f"Member {member_to_remove['name']} removed.", "success")
    return redirect(url_for("staff_dashboard"))


DUE_DAY = 10


def monthly_owed(member):
    """Total still owed across all monthly contribution records (dues + penalties)."""
    return sum(
        max(0, e["due"] + e["penalty"] - e["paid"])
        for e in member.get("monthly_contributions", [])
    )


def apply_payment(member, amount):
    """
    Waterfall: monthly contributions (oldest first) -> older SIZE balance
    -> Loan Balance -> advance credit.
    """
    remaining = amount

    # Older SIZE balance that is not tied to any specific month
    legacy = max(0, member["size_balance"] - monthly_owed(member))

    for entry in sorted(member.get("monthly_contributions", []), key=lambda e: e["month"]):
        owed = entry["due"] + entry["penalty"] - entry["paid"]
        if owed > 0 and remaining > 0:
            applied = min(owed, remaining)
            entry["paid"] += applied
            remaining -= applied
            entry["status"] = "Paid" if entry["paid"] >= entry["due"] else "Partial"

    if legacy > 0 and remaining > 0:
        applied = min(legacy, remaining)
        legacy -= applied
        remaining -= applied

    member["size_balance"] = monthly_owed(member) + legacy

    if member["loan_balance"] > 0 and remaining > 0:
        applied = min(member["loan_balance"], remaining)
        member["loan_balance"] -= applied
        remaining -= applied

    if remaining > 0:
        member["advance_balance"] = member.get("advance_balance", 0) + remaining

    return member


def apply_payment_dated(member, amount, paid_on):
    """
    Same as apply_payment, but uses the date the payment was actually made.
    If the payment was made on or before the due day and it cleared that month's
    contribution, a penalty that was added only because the SMS arrived late
    is cancelled.
    """
    paid_dt = datetime.strptime(paid_on, "%Y-%m-%d")
    month_key = paid_dt.strftime("%Y-%m")
    paid_before = {e["month"]: e["paid"] for e in member.get("monthly_contributions", [])}

    apply_payment(member, amount)

    if paid_dt.day > DUE_DAY:
        return member

    legacy = max(0, member["size_balance"] - monthly_owed(member))
    excess = 0
    for entry in member.get("monthly_contributions", []):
        if (
            entry["month"] == month_key
            and entry["penalty"] > 0
            and paid_before.get(month_key, 0) < entry["due"] <= entry["paid"]
        ):
            excess += max(0, entry["paid"] - entry["due"])
            entry["paid"] = min(entry["paid"], entry["due"])
            entry["penalty"] = 0
            entry["status"] = "Paid"

    member["size_balance"] = monthly_owed(member) + legacy
    if excess > 0:
        apply_payment(member, excess)
    return member


MONTHLY_DUE = 1000
PENALTY_AMOUNT = 200


def get_month_list(start_str, end_date):
    """Returns a list of 'YYYY-MM' strings from start_str up to end_date's month, inclusive."""
    start_year, start_month = map(int, start_str.split("-")[:2])
    months = []
    y, m = start_year, start_month
    while (y, m) <= (end_date.year, end_date.month):
        months.append(f"{y:04d}-{m:02d}")
        m += 1
        if m > 12:
            m = 1
            y += 1
    return months


def sync_monthly_ledger(data):
    """
    Ensures every member has a monthly_contributions entry for every month
    from tracking_start_date up to today. Applies advance credit to newly
    due months automatically, and applies penalties for months that passed
    the 11th unpaid. Runs automatically on every load.
    """
    today = datetime.now()
    tracking_start = data.get("tracking_start_date", "2026-10-01")
    all_months = get_month_list(tracking_start, today)

    for member in data["members"]:
        member.setdefault("monthly_contributions", [])
        existing_months = {entry["month"] for entry in member["monthly_contributions"]}

        for month_str in sorted(all_months):
            if month_str not in existing_months:
                entry = {
                    "month": month_str,
                    "due": MONTHLY_DUE,
                    "paid": 0,
                    "penalty": 0,
                    "penalty_applied": False,
                    "status": "Pending",
                }
                # Auto-apply advance credit the moment a month becomes due
                advance = member.get("advance_balance", 0)
                if advance > 0:
                    applied = min(advance, MONTHLY_DUE)
                    entry["paid"] += applied
                    member["advance_balance"] = advance - applied
                    entry["status"] = "Paid" if entry["paid"] >= entry["due"] else "Partial"

                member["monthly_contributions"].append(entry)
                member["size_balance"] += MONTHLY_DUE - entry["paid"]

        for entry in member["monthly_contributions"]:
            year, month = map(int, entry["month"].split("-"))
            eleventh_of_month = datetime(year, month, 11)

            fully_paid = entry["paid"] >= entry["due"]

            if not fully_paid and not entry["penalty_applied"] and today >= eleventh_of_month:
                entry["penalty"] += PENALTY_AMOUNT
                entry["penalty_applied"] = True
                member["size_balance"] += PENALTY_AMOUNT

            if fully_paid:
                entry["status"] = "Paid"
            elif entry["paid"] > 0:
                entry["status"] = "Partial"
            elif today >= eleventh_of_month:
                entry["status"] = "Unpaid"
            else:
                entry["status"] = "Pending"

    return data

@app.route("/staff/record-payment", methods=["POST"])
def staff_record_payment():
    if session.get("user_type") != "staff":
        return redirect(url_for("staff_login"))

    phone = request.form.get("phone", "").strip()
    amount_str = request.form.get("amount", "").strip()

    try:
        amount = float(amount_str)
    except (ValueError, TypeError):
        flash("Invalid amount entered.", "danger")
        return redirect(url_for("staff_dashboard"))

    if amount <= 0:
        flash("Amount must be greater than zero.", "danger")
        return redirect(url_for("staff_dashboard"))

    data = load_data()
    data = sync_monthly_ledger(data)
    found_member = None
    for member in data["members"]:
        if member["phone"] == phone:
            found_member = member
            break

    if not found_member:
        flash("Member not found.", "danger")
        return redirect(url_for("staff_dashboard"))

    apply_payment(found_member, amount)

    found_member.setdefault("payment_history", []).append({
        "date": datetime.now().strftime("%Y-%m-%d"),
        "amount": amount,
    })

    data["bank_balance"] = data.get("bank_balance", 0) + amount
    save_data(data)

    flash(f"Payment of KES {amount:,.2f} recorded for {found_member['name']}.", "success")
    return redirect(url_for("staff_dashboard"))

def extract_sms_fields(payload):
    text = (
        payload.get("text")
        or payload.get("message")
        or payload.get("content")
        or payload.get("body")
        or ""
    )
    sender = payload.get("from") or payload.get("sender") or payload.get("address") or ""
    return str(sender), str(text)


@app.route("/api/receive-sms", methods=["POST"])
def receive_sms():
    # 1. Secret key check (fails closed if no secret is configured)
    supplied_key = request.args.get("key", "")
    if not SMS_WEBHOOK_SECRET or not hmac.compare_digest(
        supplied_key.encode(), SMS_WEBHOOK_SECRET.encode()
    ):
        return jsonify({"status": "unauthorized"}), 401

    payload = request.get_json(silent=True) or request.form.to_dict()
    sender, text = extract_sms_fields(payload)

    # 2. Only the bank's sender name is accepted
    if sender.strip().lower() != SMS_ALLOWED_SENDER.lower():
        return jsonify({"status": "ignored", "reason": "sender not allowed"}), 200

    # 3. Must be a deposit notification for OUR account
    parsed = parse_bank_sms(text, expected_account=BANK_ACCOUNT_NUMBER)
    if not parsed:
        return jsonify({"status": "ignored", "reason": "not a valid deposit notification"}), 200

    # 4. Everything below reads and writes the data file, so only one
    #    request at a time is allowed in (prevents double-crediting).
    with data_lock:
        data = load_data()
        processed = data.setdefault("processed_refs", [])

        if parsed["mpesa_ref"] in processed:
            return jsonify({"status": "duplicate", "mpesa_ref": parsed["mpesa_ref"]}), 200

        data = sync_monthly_ledger(data)
        member = find_member_by_name(data["members"], parsed["payer_name"])

        if member:
            apply_payment_dated(member, parsed["amount"], parsed["date"])
            member.setdefault("payment_history", []).append({
                "date": parsed["date"],
                "amount": parsed["amount"],
                "mpesa_ref": parsed["mpesa_ref"],
                "source": "bank_sms",
            })
            outcome = "allocated"
            allocated_to = member["name"]
        else:
            data.setdefault("suspense_pool", []).append({
                "payer_name": parsed["payer_name"],
                "amount": parsed["amount"],
                "date": parsed["date"],
                "time": parsed["time"],
                "mpesa_ref": parsed["mpesa_ref"],
                "status": "Pending Treasurer Review",
            })
            outcome = "suspense"
            allocated_to = None

        # The money reached the bank either way
        data["bank_balance"] = data.get("bank_balance", 0) + parsed["amount"]
        processed.append(parsed["mpesa_ref"])
        save_data(data)

    return jsonify({
        "status": outcome,
        "member": allocated_to,
        "amount": parsed["amount"],
        "mpesa_ref": parsed["mpesa_ref"],
    }), 200

# ===== Suspense pool review =====
@app.route("/staff/allocate-suspense/<int:index>", methods=["POST"])
def staff_allocate_suspense(index):
    if session.get("user_type") != "staff":
        return redirect(url_for("staff_login"))

    phone = request.form.get("phone", "").strip()
    save_alias = request.form.get("save_alias") == "on"

    with data_lock:
        data = load_data()
        pool = data.get("suspense_pool", [])
        if index < 0 or index >= len(pool):
            flash("Suspense item not found.", "danger")
            return redirect(url_for("staff_dashboard"))

        target_member = None
        for m in data["members"]:
            if m["phone"] == phone:
                target_member = m
                break
        if not target_member:
            flash("Select a member to allocate this payment to.", "danger")
            return redirect(url_for("staff_dashboard"))

        entry = pool.pop(index)
        data = sync_monthly_ledger(data)
        apply_payment_dated(target_member, entry["amount"], entry["date"])
        target_member.setdefault("payment_history", []).append({
            "date": entry["date"],
            "amount": entry["amount"],
            "mpesa_ref": entry.get("mpesa_ref", ""),
            "source": "suspense_allocated",
        })

        if save_alias:
            aliases = target_member.setdefault("aliases", [])
            if entry["payer_name"] not in aliases:
                aliases.append(entry["payer_name"])

        # Money was already added to bank_balance when the SMS first arrived.
        save_data(data)

    flash(f"KES {entry['amount']:,.2f} from {entry['payer_name']} allocated to {target_member['name']}.", "success")
    return redirect(url_for("staff_dashboard"))


@app.route("/staff/discard-suspense/<int:index>", methods=["POST"])
def staff_discard_suspense(index):
    if session.get("user_type") != "staff":
        return redirect(url_for("staff_login"))

    with data_lock:
        data = load_data()
        pool = data.get("suspense_pool", [])
        if index < 0 or index >= len(pool):
            flash("Suspense item not found.", "danger")
            return redirect(url_for("staff_dashboard"))
        entry = pool.pop(index)
        save_data(data)

    flash(f"Suspense entry from {entry['payer_name']} discarded (kept in bank balance, unallocated).", "success")
    return redirect(url_for("staff_dashboard"))

# ============================================
# Shared Routes
# ============================================
@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


@app.route("/")
def index():
    return render_template("index.html")

if __name__ == "__main__":
    app.run(debug=True)