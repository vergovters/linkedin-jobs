#!/usr/bin/env python3
"""
Web app: upload xlsx, run LinkedIn jobs check, show results and screenshots.
"""

import json
import os
import threading
import time
import uuid
from pathlib import Path

from flask import Flask, jsonify, redirect, render_template, request, send_from_directory, url_for

import main as pipeline

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16 MB
RUNS_DIR = Path(__file__).resolve().parent / "runs"
RUNS_DIR.mkdir(exist_ok=True)
AUTH_FILE = str(Path(__file__).resolve().parent / pipeline.DEFAULT_AUTH_FILE)
SETUP_SAVE_TRIGGER = Path(__file__).resolve().parent / ".setup-save-requested"
SETUP_TIMEOUT = 300  # 5 min to log in

# When deployed: write LinkedIn auth from env so Railway/Render can inject the secret
_env_auth = os.environ.get("LINKEDIN_AUTH_JSON")
if _env_auth:
    try:
        raw = _env_auth
        if raw.startswith("base64:"):
            import base64
            raw = base64.b64decode(raw.split(":", 1)[1]).decode("utf-8")
        with open(AUTH_FILE, "w") as f:
            f.write(raw)
    except Exception:
        pass


def linkedin_configured() -> bool:
    if not os.path.isfile(AUTH_FILE):
        return False
    try:
        return os.path.getsize(AUTH_FILE) > 100
    except Exception:
        return False


def _is_logged_in_url(url: str) -> bool:
    u = url.lower()
    if "/login" in u or "/auth" in u or "/uas/" in u:
        return False
    if "linkedin.com" not in u:
        return False
    return (
        "/feed" in u
        or "/mynetwork" in u
        or "/in/" in u
        or "/home" in u
        or "linkedin.com/?trk=" in u
        or u.rstrip("/").endswith("linkedin.com")
        or "/checkpoint" in u
        or "/challenge" in u
    )


def _run_linkedin_setup() -> None:
    """Open browser at LinkedIn login. Save when URL looks logged-in OR when user clicks 'Save' on the website."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False)
            context = browser.new_context(user_agent=pipeline.USER_AGENT)
            page = context.new_page()
            page.goto("https://www.linkedin.com/login", wait_until="domcontentloaded")
            start = time.time()
            while time.time() - start < SETUP_TIMEOUT:
                time.sleep(0.8)
                if SETUP_SAVE_TRIGGER.exists():
                    try:
                        SETUP_SAVE_TRIGGER.unlink()
                    except Exception:
                        pass
                    time.sleep(0.5)
                    context.storage_state(path=AUTH_FILE)
                    break
                try:
                    url = page.url
                except Exception:
                    break
                if _is_logged_in_url(url):
                    time.sleep(0.5)
                    context.storage_state(path=AUTH_FILE)
                    break
            try:
                context.close()
                browser.close()
            except Exception:
                pass
    except Exception:
        pass


def run_pipeline(run_id: str, xlsx_path: str, url_column: str) -> None:
    run_dir = RUNS_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    screenshot_dir = str(run_dir / "screenshots")
    os.makedirs(screenshot_dir, exist_ok=True)
    status_path = run_dir / "status.json"
    results_path = run_dir / "results.json"

    def write_status(s: str, error: str = None, current: int = None, total: int = None):
        with open(status_path, "w") as f:
            json.dump({"status": s, "error": error, "current": current, "total": total}, f)

    try:
        write_status("running", total=0)
        urls = pipeline.extract_linkedin_company_urls_from_xlsx(
            xlsx_path, url_column=url_column or "B"
        )
        if not urls:
            write_status("done", error="No LinkedIn company URLs found in the file.")
            return
        write_status("running", current=0, total=len(urls))

        def on_progress(current: int, total: int):
            write_status("running", current=current, total=total)

        results = pipeline.run_screenshots(urls, screenshot_dir, AUTH_FILE, on_progress=on_progress)
        with open(results_path, "w") as f:
            json.dump(results, f, indent=2)
        write_status("done")
    except Exception as e:
        write_status("done", error=str(e))


@app.route("/")
def index():
    return render_template("index.html", linkedin_configured=linkedin_configured())


@app.route("/api/linkedin-status")
def api_linkedin_status():
    return jsonify({"configured": linkedin_configured()})


@app.route("/api/setup-linkedin", methods=["POST"])
def api_setup_linkedin():
    thread = threading.Thread(target=_run_linkedin_setup, daemon=True)
    thread.start()
    return jsonify({"started": True})


@app.route("/api/setup-linkedin-save", methods=["POST"])
def api_setup_linkedin_save():
    """Ask the running setup browser to save session now (user clicked 'I've logged in')."""
    try:
        SETUP_SAVE_TRIGGER.touch()
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/run", methods=["POST"])
def start_run():
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400
    f = request.files["file"]
    if not f or not f.filename or not f.filename.lower().endswith((".xlsx", ".xls")):
        return jsonify({"error": "Please upload an Excel file (.xlsx)"}), 400
    run_id = str(uuid.uuid4())[:8]
    run_dir = RUNS_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    xlsx_path = run_dir / "upload.xlsx"
    f.save(str(xlsx_path))
    url_column = (request.form.get("url_column") or "B").strip().upper() or "B"
    thread = threading.Thread(
        target=run_pipeline,
        args=(run_id, str(xlsx_path), url_column),
        daemon=True,
    )
    thread.start()
    return redirect(url_for("run_status", run_id=run_id))


@app.route("/run/<run_id>")
def run_status(run_id):
    return render_template("results.html", run_id=run_id)


@app.route("/run/<run_id>/status")
def get_status(run_id):
    run_dir = RUNS_DIR / run_id
    status_path = run_dir / "status.json"
    if not run_dir.exists() or not status_path.exists():
        return jsonify({"status": "pending"})
    with open(status_path) as f:
        return jsonify(json.load(f))


@app.route("/run/<run_id>/results")
def get_results(run_id):
    run_dir = RUNS_DIR / run_id
    results_path = run_dir / "results.json"
    if not results_path.exists():
        return jsonify([])
    with open(results_path) as f:
        return jsonify(json.load(f))


@app.route("/run/<run_id>/screenshots/<path:filename>")
def get_screenshot(run_id, filename):
    run_dir = RUNS_DIR / run_id / "screenshots"
    if not run_dir.exists():
        return "", 404
    return send_from_directory(run_dir, filename)


if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "false").lower() in ("1", "true", "yes")
    app.run(host="0.0.0.0", port=port, debug=debug)
