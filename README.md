# Power Leaders Investment Group Portal

A secure, web-based platform built to automate financial tracking, loan management, and ledger updates for self-help investment groups (chamas).

---

## 📌 The Problem
Traditionally, self-help investment groups track monthly contributions, loans, and penalties manually using spreadsheets. This creates major operational bottlenecks:
* The treasurer has to manually update every member's balance by hand.
* Bank or mobile money SMS alerts must be cross-checked line by line.
* Members lack visibility into their financial standing, constantly needing to reach out to leadership for updates.

---

## 💡 The Solution
**Power Leaders Investment Group** digitizes and streamlines group financial operations:
* **Member Portal:** Members can log in securely anytime via their phones to view real-time contribution balances, loan statuses, and payment histories.
* **Treasurer Portal:** A separate, OTP-secured dashboard allows treasurers to manage members, approve/disburse loans, and review records.
* **Automated SMS Ingestion:** Incoming deposit alert SMS messages are parsed automatically via a REST API endpoint, matched to the correct member, and applied instantly.
* **Suspense Pool:** Unmatched or ambiguous payments are safely routed to a suspense pool for manual review, preventing ledger discrepancies.

---

## 🛠️ Tech Stack & Tools

* **Backend:** Python, Flask, Werkzeug (Password Security), Flask-Mail
* **Frontend:** Jinja2, HTML5, CSS3, JavaScript
* **Data Storage:** JSON data storage architecture
* **Utilities & Automation:** Regex-based SMS parsing, ReportLab (PDF receipt generation)
* **Deployment:** PythonAnywhere

---

## ✨ Key Features

1. **Automated M-Pesa/Bank SMS Processing:** Real-time deposit ingestion that updates ledgers within seconds of a payment arriving.
2. **Automated Penalties:** Monthly group fines and penalties apply automatically based on group bylaws.
3. **Instant Financial Transparency:** Members check standing from their phones 24/7 without manual intervention from leadership.
4. **PDF Receipts:** Automated receipt generation for contributions and loan repayments using ReportLab.

---