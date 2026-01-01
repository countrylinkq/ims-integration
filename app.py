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

        page.goto(LOGIN_URL, timeout=30000)
        page.wait_for_load_state("domcontentloaded")

        # ---------- detect iframe if login form is inside ----------
        login_frame = page
        for frame in page.frames:
            if "login" in frame.url.lower() or "account" in frame.url.lower():
                login_frame = frame
                break

        # ---------- flexible selectors ----------
        username_selectors = [
            "input[name='UserName']",
            "input[name='Username']",
            "input[name='LoginId']",
            "input[name='Email']",
            "input[type='text']"
        ]

        password_selectors = [
            "input[name='Password']",
            "input[name='PassWord']",
            "input[type='password']"
        ]

        # ---------- fill username ----------
        for sel in username_selectors:
            try:
                login_frame.wait_for_selector(sel, timeout=5000)
                login_frame.fill(sel, USERNAME)
                break
            except:
                continue
        else:
            browser.close()
            raise RuntimeError("Username field not found on login page")

        # ---------- fill password ----------
        for sel in password_selectors:
            try:
                login_frame.wait_for_selector(sel, timeout=5000)
                login_frame.fill(sel, PASSWORD)
                break
            except:
                continue
        else:
            browser.close()
            raise RuntimeError("Password field not found on login page")

        # ---------- submit ----------
        try:
            login_frame.click("button[type='submit']")
        except:
            login_frame.click("input[type='submit']")

        page.wait_for_load_state("networkidle", timeout=30000)

        # ---------- save cookies ----------
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
    r = requests.post(API_URL, headers=headers(), data=PAYLOAD, timeout=20)

    # Session expired → re-login ONCE
    if r.status_code in (401, 302):
        if os.path.exists(COOKIE_FILE):
            os.remove(COOKIE_FILE)
        auto_login()
        r = requests.post(API_URL, headers=headers(), data=PAYLOAD, timeout=20)

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
