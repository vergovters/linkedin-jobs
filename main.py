#!/usr/bin/env python3
"""
Parse xlsx file and return LinkedIn company URLs as an array.
Optionally visit each URL and save a screenshot.
"""

import argparse
import json
import os
import re
import sys
import time
from typing import Callable, List, Optional

import pandas as pd

# Match linkedin.com/company/<slug> with optional trailing path
LINKEDIN_COMPANY_PATTERN = re.compile(
    r"https?://(?:www\.)?linkedin\.com/company/([a-zA-Z0-9_-]+)",
    re.IGNORECASE,
)


def _column_letter_to_index(col: str) -> int:
    """Convert Excel column letter(s) to 0-based index: A->0, B->1, ..., Z->25, AA->26."""
    col = str(col).strip().upper()
    idx = 0
    for c in col:
        idx = idx * 26 + (ord(c) - ord("A") + 1)
    return idx - 1


def extract_linkedin_company_urls_from_xlsx(
    path: str,
    sheet_name: Optional[str] = None,
    url_column: Optional[str] = None,
) -> List[str]:
    """Read xlsx and return unique LinkedIn company URLs in order of first appearance.
    If url_column is set (e.g. 'B' or '2'), only that column is scanned; otherwise all cells are scanned.
    """
    df = pd.read_excel(path, sheet_name=sheet_name or 0, header=None)

    if url_column is not None:
        try:
            if url_column.upper().isalpha():
                col_idx = _column_letter_to_index(url_column)
            else:
                col_idx = int(url_column) - 1
            if col_idx < 0 or col_idx >= len(df.columns):
                sys.stderr.write(f"Invalid url_column '{url_column}'; scanning all columns.\n")
                col_idx = None
        except (ValueError, AttributeError):
            sys.stderr.write(f"Invalid url_column '{url_column}'; scanning all columns.\n")
            col_idx = None
    else:
        col_idx = None

    seen = set()
    urls_ordered = []

    if col_idx is not None:
        cells = df.iloc[:, col_idx]
    else:
        cells = df.values.flatten()

    for cell in cells:
        if pd.isna(cell):
            continue
        cell_str = str(cell).strip()
        for m in LINKEDIN_COMPANY_PATTERN.finditer(cell_str):
            slug = m.group(1)
            url = f"https://www.linkedin.com/company/{slug}/jobs"
            if url not in seen:
                seen.add(url)
                urls_ordered.append(url)
    return urls_ordered


def slug_from_url(url: str) -> Optional[str]:
    m = LINKEDIN_COMPANY_PATTERN.search(url)
    return m.group(1) if m else None


DEFAULT_AUTH_FILE = "linkedin-auth.json"
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

# Page text that means the company has no open jobs (any match, case-insensitive)
NO_JOBS_PHRASES = [
    "There are no jobs right now",
    "no jobs right now",
    "no open positions",
    "doesn't have any jobs",
    "don't have any jobs",
    "has no jobs",
    "have no jobs",
    "no positions at this time",
    "aren't any jobs",
    "are no jobs",
]

# Page missing / error / unavailable -> treat as no jobs
PAGE_MISSING_OR_ERROR_PHRASES = [
    "this linkedin page isn't available",
    "page not found",
    "page doesn't exist",
    "something went wrong",
    "this page is unavailable",
    "we can't find that page",
    "couldn't find that page",
]

# Positive signs that this is a valid jobs page with listings
HAS_JOBS_INDICATORS = [
    "open job",
    "open position",
    "see all jobs",
    "/jobs/view/",
]


def do_login(auth_file: str) -> None:
    """Open a visible browser, go to LinkedIn login. After you log in, session (cookies/storage) is saved to auth_file."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        sys.stderr.write("Playwright required. Run: pip install playwright && playwright install chromium\n")
        sys.exit(1)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(user_agent=USER_AGENT)
        page = context.new_page()
        page.goto("https://www.linkedin.com/login", wait_until="domcontentloaded")
        sys.stderr.write("Log in to LinkedIn in the browser. When you're done, press Enter here...\n")
        input()
        context.storage_state(path=auth_file)
        sys.stderr.write(f"Session saved to {auth_file}\n")
        context.close()
        browser.close()


def get_page_jobs_status(page) -> Optional[bool]:
    """
    Return True if page clearly has open jobs, False if no jobs / page missing / error, None if unclear.
    Only returns True when we see positive job content; otherwise False so missing/error pages are not treated as having jobs.
    """
    try:
        body_text = page.locator("body").inner_text()
        content = page.content()
        combined = (body_text + " " + content).lower()
        if any(phrase in combined for phrase in [p.lower() for p in PAGE_MISSING_OR_ERROR_PHRASES]):
            return False
        if any(phrase.lower() in combined for phrase in NO_JOBS_PHRASES):
            return False
        if any(ind in combined for ind in HAS_JOBS_INDICATORS):
            return True
        return False
    except Exception:
        return None


def run_screenshots(
    urls: List[str],
    screenshot_dir: str,
    auth_file: Optional[str],
    on_progress: Optional[Callable[[int, int], None]] = None,
) -> List[dict]:
    """Visit each URL, save a screenshot, and detect if page has open jobs. Returns list of {url, has_open_jobs, screenshot}.
    If on_progress is provided, it is called after each URL as on_progress(current_index_1based, total)."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        sys.stderr.write("Playwright required. Run: pip install playwright && playwright install chromium\n")
        return []
    results = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            if auth_file and os.path.isfile(auth_file):
                context = browser.new_context(user_agent=USER_AGENT, storage_state=auth_file)
            else:
                context = browser.new_context(user_agent=USER_AGENT)
            for i, url in enumerate(urls):
                slug = slug_from_url(url) or f"page_{i + 1}"
                safe_slug = re.sub(r"[^\w\-]", "_", slug)
                filepath = os.path.join(screenshot_dir, f"{safe_slug}.png")
                rel_path = f"{safe_slug}.png"
                page = context.new_page()
                page.set_default_timeout(25000)
                has_open_jobs = None
                try:
                    page.goto(url, wait_until="domcontentloaded")
                    page.wait_for_timeout(4000)
                    has_open_jobs = get_page_jobs_status(page)
                    if has_open_jobs is None:
                        has_open_jobs = False
                    page.screenshot(path=filepath)
                    sys.stderr.write(f"[{i + 1}/{len(urls)}] {slug} -> {filepath} has_open_jobs={has_open_jobs} OK\n")
                except Exception as e:
                    sys.stderr.write(f"[{i + 1}/{len(urls)}] {slug} -> FAILED: {e}\n")
                finally:
                    page.close()
                results.append({
                    "url": url,
                    "has_open_jobs": has_open_jobs,
                    "screenshot": rel_path,
                })
                if on_progress:
                    on_progress(i + 1, len(urls))
                if i < len(urls) - 1:
                    time.sleep(1)
            context.close()
    except Exception as e:
        sys.stderr.write(f"Screenshots failed: {e}\n")
    return results


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Parse xlsx and return LinkedIn company URLs. Optionally take a screenshot of each.",
    )
    parser.add_argument("xlsx", nargs="?", help="Path to .xlsx file (not needed for --login)")
    parser.add_argument("-o", "--output", help="Output file path for URL list (default: stdout)")
    parser.add_argument("--sheet", default=None, help="Sheet name or index (default: first sheet)")
    parser.add_argument("--url-column", default=None, metavar="COL", help="Only read URLs from this column, e.g. B or 2")
    parser.add_argument("--screenshot", action="store_true", help="Visit each URL and save a screenshot (use saved session from --login)")
    parser.add_argument("--screenshot-dir", default="screenshots", metavar="DIR", help="Folder to save screenshots (default: screenshots)")
    parser.add_argument("--auth-file", default=DEFAULT_AUTH_FILE, metavar="FILE", help="File to save/load LinkedIn session (default: linkedin-auth.json)")
    parser.add_argument("--login", action="store_true", help="Log in to LinkedIn once; session is saved to --auth-file for future --screenshot runs")
    parser.add_argument("--jobs-result", metavar="FILE", help="Write JSON with has_open_jobs for each URL (default: <screenshot-dir>/jobs-result.json when using --screenshot)")
    args = parser.parse_args()

    if args.login:
        do_login(args.auth_file)
        return

    if not args.xlsx:
        sys.stderr.write("Missing xlsx file. Usage: python main.py <file.xlsx> [options]\n")
        sys.exit(1)
    if not os.path.isfile(args.xlsx):
        sys.stderr.write(f"File not found: {args.xlsx}\n")
        sys.exit(1)

    urls = extract_linkedin_company_urls_from_xlsx(
        args.xlsx,
        sheet_name=args.sheet,
        url_column=args.url_column,
    )

    if args.screenshot:
        os.makedirs(args.screenshot_dir, exist_ok=True)
        jobs_results = run_screenshots(urls, args.screenshot_dir, args.auth_file)
        jobs_file = args.jobs_result or os.path.join(args.screenshot_dir, "jobs-result.json")
        if jobs_results:
            with open(jobs_file, "w") as f:
                json.dump(jobs_results, f, indent=2)
            sys.stderr.write(f"Wrote jobs result to {jobs_file}\n")

    out = json.dumps(urls, indent=2)
    if args.output:
        with open(args.output, "w") as f:
            f.write(out)
        sys.stderr.write(f"Wrote {len(urls)} URLs to {args.output}\n")
    else:
        print(out)


if __name__ == "__main__":
    main()
