# LinkedIn URLs from XLSX

Parses an Excel (`.xlsx`) file and returns LinkedIn company URLs. Web app: upload a file, get a table with “Has open jobs” and screenshots for each company.

---

## Easy setup (no IDE, no Python install)

**On Mac:** copy this folder anywhere (e.g. Desktop). Then:

1. **Double-click `Setup.command`**  
   A terminal will open and install everything (first time it may download Python into this folder — no system install). Wait until it says *“Setup complete”*.

2. **Double-click `Run.command`**  
   The app starts and your browser opens. Use the page to upload an Excel file and run.

3. **Keep the Run window open** while you use the app. Close it when you’re done.

**From terminal (Mac/Linux):**  
`./setup.sh` once, then `./run.sh` to start.

**Windows:** install [Python](https://www.python.org/downloads/) (check “Add to PATH”), open Command Prompt in this folder, then:
`python -m venv .venv` → `.venv\Scripts\activate` → `pip install -r requirements.txt` → `playwright install chromium` → `python app.py`. Open http://127.0.0.1:5000 in your browser.

---

## Deploy (run it on the web)

You can host the app so it’s available at a URL. No IDE needed for users.

**Railway:** Push to GitHub → [railway.app](https://railway.app) → **New Project** → **Deploy from GitHub** → select repo. It uses the **Dockerfile** and gives you a public URL.

**Render:** Push to GitHub → [render.com](https://render.com) → **New** → **Web Service** → connect repo → set **Environment** to **Docker** → Deploy.

**Your server:** `docker build -t linkedin-jobs . && docker run -d -p 8080:8080 linkedin-jobs` then open `http://YOUR_IP:8080`.

**LinkedIn on the server:** The “Set up LinkedIn” button needs a browser, so it doesn’t work when deployed. To get screenshots without sign-in walls: (1) Run the app locally, complete “Set up LinkedIn”, then copy the contents of `linkedin-auth.json`. (2) In Railway/Render, add an env var **`LINKEDIN_AUTH_JSON`** with that contents (or base64, e.g. `base64:...`). The app writes it to disk at startup. Without it, runs still work but LinkedIn may show sign-in pages in screenshots.

---

## Setup (manual)

```bash
cd linkedin-jobs-from-xlsx
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium
```

## Web app

Run the website to upload an xlsx file and see results with screenshots:

```bash
python app.py
```

Open **http://127.0.0.1:5000** in your browser. Upload an Excel file, set the URL column (e.g. B), and click Run. You’ll get a results table with **Has open jobs** (Yes/No) and a **screenshot** for each company (click to open full size).

For logged-in LinkedIn screenshots, run `python main.py --login` once before using the web app.

## Usage (CLI)

```bash
# Print URLs array to stdout
python main.py companies.xlsx

# With URL column B (recommended for your layout)
python main.py companies.xlsx --url-column B

# Write to file
python main.py companies.xlsx -o urls.json --url-column B

# Screenshots as a logged-in LinkedIn user (recommended)
# 1) One-time: log in to LinkedIn in the browser (cookies/session saved to linkedin-auth.json)
python main.py --login

# 2) Take screenshots using that session
python main.py companies.xlsx --url-column B --screenshot

# Custom auth file or screenshot folder
python main.py companies.xlsx --url-column B --screenshot --auth-file my-auth.json --screenshot-dir my_screenshots
```

## XLSX format

- Column A = labels, Column B = LinkedIn URLs → use `--url-column B`
- Or any layout: the script scans all cells (or only the given column) for `linkedin.com/company/...` URLs and returns them in order of first appearance, deduplicated.

## Output

- **Default**: JSON array of company jobs URL strings (each ends with `/jobs`).
- **With `--screenshot`**: Same URL list (to stdout or `-o`), screenshots in `screenshots/`, and a **jobs result** JSON file with `has_open_jobs` for each URL (default: `screenshots/jobs-result.json`, or `--jobs-result FILE`).

Example URL list:

```json
[
  "https://www.linkedin.com/company/zerotomvp/jobs",
  "https://www.linkedin.com/company/villanueva-photo/jobs"
]
```

Example jobs result (`screenshots/jobs-result.json` or `--jobs-result`):

```json
[
  { "url": "https://www.linkedin.com/company/zerotomvp/jobs", "has_open_jobs": true,  "screenshot": "zerotomvp.png" },
  { "url": "https://www.linkedin.com/company/other/jobs",     "has_open_jobs": false, "screenshot": "other.png" }
]
```

`has_open_jobs` is `true` if the page shows job listings, `false` if it shows "no jobs" text, or `null` if the page failed to load.
