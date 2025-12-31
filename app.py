from flask import Flask, render_template
import requests, json, os
from datetime import datetime
from playwright.sync_api import sync_playwright

app = Flask(__name__)

# ==============================
# CONFIG
# ==============================
LOGIN_URL = "https://ims.marvellousfiber.com/Account/Login"
API_URL = "https://ims.marvellousfiber.com/MISReport/UpcommingRenewal/GetData"
COOKIE_FILE = "cookies.json"

USERNAME = os.getenv("ISP_USERNAME")
PASSWORD = os.getenv("ISP_PASSWORD")

if not USERNAME or not PASSWORD:
    raise RuntimeError("ISP_USERNAME / ISP_PASSWORD not set in environment")

PAYLOAD = {
    "draw": 1,
    "start": 0,
    "length": 50,
    "From_Date": "2025/12/31",
    "To_Date": "2025/12/31",
    "ZoneId": ""
}

# ==============================
# LOGIN + COOKIE HANDLING
# ==============================
def auto_login():
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"]
        )
        context = browser.new_context()
        page = context.new_page()

        page.goto(LOGIN_URL)

        # VERIFY THESE IDs ONCE
        page.fill("#UserName", USERNAME)
        page.fill("#Password", PASSWORD)
        page.click("button[type=submit]")

        page.wait_for_load_state("networkidle")

        cookies = context.cookies()
        with open(COOKIE_FILE, "w") as f:
            json.dump(cookies, f)

        browser.close()


def load_cookie_header():
    if not os.path.exists(COOKIE_FILE):
        auto_login()

    with open(COOKIE_FILE) as f:
        cookies = json.load(f)

    return "; ".join(f"{c['name']}={c['value']}" for c in cookies)


def headers():
    return {
        "User-Agent": "Mozilla/5.0",
        "X-Requested-With": "XMLHttpRequest",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Cookie": load_cookie_header()
    }

# ==============================
# HELPERS
# ==============================
def dotnet_date(value):
    if not value:
        return ""
    ts = int(value.replace("/Date(", "").replace(")/", "")) / 1000
    return datetime.fromtimestamp(ts).strftime("%d-%m-%Y")

# ==============================
# ROUTES
# ==============================
@app.route("/")
def index():
    r = requests.post(API_URL, headers=headers(), data=PAYLOAD)

    # Session expired → auto re-login
    if r.status_code in (401, 302):
        auto_login()
        r = requests.post(API_URL, headers=headers(), data=PAYLOAD)

    r.raise_for_status()
    rows = r.json().get("data", [])

    for row in rows:
        row["PlanActivationDate"] = dotnet_date(row.get("PlanActivationDate"))
        row["PlanExpiryDate"] = dotnet_date(row.get("PlanExpiryDate"))

    return render_template("index.html", rows=rows)

# ==============================
# ENTRY POINT
# ==============================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
