import csv
import re
import sys
import tkinter as tk
import time
from tkinter import simpledialog
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError


CSV_PATH = Path("data/daten_template.csv")
LOG_PATH = Path("data/run_log.csv")
DEBUG = False
HEADLESS = True
DRY_RUN = False  # Set False to submit entries
TIMEOUT_MS = 120000

BASE_URL = "https://<opnsense-host>"
LOGIN_URL = "https://10.6.168.1:81"
DHCP_STATIC_URL = "https://10.6.168.1:81/ui/core/dashboard"
USERNAME: Optional[str] = None
PASSWORD: Optional[str] = None

# Replace these with stable selectors from your UI
SELECTORS: Dict[str, str] = {
    "username_input": "#usernamefld",
    "password_input": "#passwordfld",
    "login_button": ".btn",
    "dashboard_link": "#Lobby > a:nth-child(1) > div:nth-child(1) > div:nth-child(1) > div:nth-child(1)",
    "add_button": "#staticdhcpleases_opt3 > div > div > div:nth-child(1) > button",
    "mac_input": "#input-mac",
    "ip_input": "#input-ip",
    "hostname_input": "#input-hostname",
    "save_button": ".btnSaveLease",
    # Optional:
    "search_input": "input[placeholder='Search']",
    "apply_button": "button:has-text('Apply')",
    "static_leases_table": "#statifdhcpleases-if-lease-table-opt3",
}

MAC_RE = re.compile(r"^[0-9A-Fa-f]{2}([:-][0-9A-Fa-f]{2}){5}$")
IP_RE = re.compile(
    r"^(25[0-5]|2[0-4]\\d|1\\d\\d|[1-9]?\\d)(\\.(25[0-5]|2[0-4]\\d|1\\d\\d|[1-9]?\\d)){3}$"
)


@dataclass
class DhcpRow:
    hostname: str
    mac: str
    ip: str


def read_csv(path: Path) -> List[DhcpRow]:
    rows: List[DhcpRow] = []
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter=";")
        for idx, row in enumerate(reader, start=2):
            key_map = {k.lower(): k for k in row.keys() if k}
            hostname = (row.get(key_map.get("geraet", "")) or row.get(key_map.get("name", "")) or "").strip()
            mac = (row.get(key_map.get("mac", "")) or "").strip()
            ip = (row.get(key_map.get("ip", "")) or "").strip()
            if not hostname or not mac or not ip:
                print(f"Skip line {idx}: missing fields")
                continue
            rows.append(DhcpRow(hostname=hostname, mac=mac, ip=ip))
    return rows


def validate_rows(rows: List[DhcpRow]) -> List[DhcpRow]:
    valid: List[DhcpRow] = []
    for row in rows:
        if not MAC_RE.match(row.mac):
            print(f"Invalid MAC: {row.mac} ({row.hostname})")
            continue
        if not IP_RE.match(row.ip):
            print(f"Invalid IP: {row.ip} ({row.hostname})")
            continue
        valid.append(row)
    return valid


def safe_fill(page, selector: str, value: str) -> None:
    page.locator(selector).wait_for(timeout=TIMEOUT_MS)
    page.locator(selector).fill(value)


def optional_clear_search(page) -> None:
    search_selector = SELECTORS.get("search_input")
    if not search_selector:
        return
    try:
        locator = page.locator(search_selector)
        locator.wait_for(timeout=1000)
        locator.fill("")
    except PlaywrightTimeoutError:
        if DEBUG:
            print("DEBUG: search input not found, skipping clear")
        pass


def find_existing_by_mac(page, mac: str) -> bool:
    search_selector = SELECTORS.get("search_input")
    if not search_selector:
        return False
    try:
        locator = page.locator(search_selector)
        locator.wait_for(timeout=1000)
        locator.fill(mac)
        page.wait_for_timeout(500)
        return page.locator(f"text={mac}").first.is_visible()
    except PlaywrightTimeoutError:
        if DEBUG:
            print("DEBUG: search input not found, skipping existing check")
        return False


def prompt_credentials() -> tuple[str, str]:
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    username = simpledialog.askstring("OPNsense Login", "Username:")
    password = simpledialog.askstring("OPNsense Login", "Password:", show="*")
    root.destroy()

    if not username or not password:
        print("Login canceled.")
        sys.exit(1)
    return username, password


def login(page, username: str, password: str) -> None:
    page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=TIMEOUT_MS)
    safe_fill(page, SELECTORS["username_input"], username)
    safe_fill(page, SELECTORS["password_input"], password)
    page.locator(SELECTORS["login_button"]).click()
    page.wait_for_load_state("networkidle", timeout=TIMEOUT_MS * 4)


def open_dashboard(page) -> None:
    page.locator(SELECTORS["dashboard_link"]).click()
    page.wait_for_timeout(500)


def wait_for_add_button(page) -> None:
    add_selector = SELECTORS["add_button"]
    deadline = time.monotonic() + (TIMEOUT_MS * 6 / 1000)
    while time.monotonic() < deadline:
        try:
            if page.locator(add_selector).first.is_visible():
                if DEBUG:
                    print("DEBUG: add_button is visible")
                return
        except PlaywrightTimeoutError:
            pass
        time.sleep(1)
    raise PlaywrightTimeoutError(f"Add button not visible after {TIMEOUT_MS * 6}ms")


def find_frame_with_selector(page, selector: str):
    for frame in page.frames:
        try:
            if frame.locator(selector).count() > 0:
                return frame
        except PlaywrightTimeoutError:
            continue
    return None


def add_mapping(page, row: DhcpRow) -> None:
    if DEBUG:
        print("DEBUG: add_mapping start")
    add_selector = SELECTORS["add_button"]
    add_locator = page.locator(add_selector)
    if DEBUG:
        print(f"DEBUG: add_button visible={add_locator.is_visible()} enabled={add_locator.is_enabled()}")

    if DEBUG:
        try:
            add_locator.highlight()
            box = add_locator.bounding_box()
            print(f"DEBUG: add_button box={box}")
        except PlaywrightTimeoutError:
            pass

    add_locator.scroll_into_view_if_needed()

    add_frame = find_frame_with_selector(page, add_selector)
    target = page
    if add_frame and add_frame != page.main_frame:
        if DEBUG:
            print(f"DEBUG: add_button found in iframe: {add_frame.url}")
        add_frame.locator(add_selector).click(trial=True)
        add_frame.locator(add_selector).click(force=True)
        target = add_frame
    else:
        add_locator.click(trial=True)
        add_locator.click(force=True)

    if DEBUG:
        print("DEBUG: add_button clicked, waiting for hostname input")

    target.locator(SELECTORS["hostname_input"]).wait_for(state="visible", timeout=TIMEOUT_MS)
    target.locator(SELECTORS["mac_input"]).wait_for(state="visible", timeout=TIMEOUT_MS)
    target.locator(SELECTORS["ip_input"]).wait_for(state="visible", timeout=TIMEOUT_MS)
    safe_fill(target, SELECTORS["mac_input"], row.mac)
    safe_fill(target, SELECTORS["ip_input"], row.ip)
    safe_fill(target, SELECTORS["hostname_input"], row.hostname)

    if DRY_RUN:
        print(f"DRY RUN: would save {row.hostname}")
        if DEBUG:
            input("DEBUG: Press Enter to continue...")
        return

    page.locator(SELECTORS["save_button"]).click()
    page.wait_for_load_state("networkidle", timeout=TIMEOUT_MS)


def apply_changes(page) -> None:
    apply_selector = SELECTORS.get("apply_button")
    if not apply_selector:
        return
    try:
        page.locator(apply_selector).click()
        page.wait_for_load_state("networkidle", timeout=TIMEOUT_MS)
    except PlaywrightTimeoutError:
        pass


def in_static_leases_list(page, row: DhcpRow) -> bool:
    table_selector = SELECTORS.get("static_leases_table")
    if not table_selector:
        return False
    try:
        table = page.locator(table_selector)
        table.wait_for(timeout=2000)
        text = table.inner_text()
    except PlaywrightTimeoutError:
        if DEBUG:
            print("DEBUG: static leases table not found")
        return False

    if row.mac in text or row.ip in text or row.hostname in text:
        return True
    return False


def append_log(lines: List[str]) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8", newline="") as handle:
        for line in lines:
            handle.write(line + "\n")


def main() -> int:
    if not CSV_PATH.exists():
        print(f"CSV not found: {CSV_PATH}")
        return 1

    print(f"DEBUG: Using CSV at {CSV_PATH}") if DEBUG else None
    rows = validate_rows(read_csv(CSV_PATH))
    if not rows:
        print("No valid rows found.")
        return 1

    username = USERNAME
    password = PASSWORD
    if not username or not password:
        username, password = prompt_credentials()

    print(f"DEBUG: Starting browser (headless={HEADLESS})") if DEBUG else None
    log_lines: List[str] = ["hostname;mac;ip;status;message"]
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS, args=[
            "--disable-extensions",
            "--disable-dev-shm-usage",
            "--disable-gpu",
            "--no-sandbox",
        ])
        context = browser.new_context(ignore_https_errors=True)
        page = context.new_page()
        page.set_default_timeout(TIMEOUT_MS)
        page.set_default_navigation_timeout(TIMEOUT_MS)

        print("DEBUG: Logging in...") if DEBUG else None
        login(page, username, password)
        print("DEBUG: Opening dashboard...") if DEBUG else None
        open_dashboard(page)
        print("DEBUG: Waiting for DHCP widget...") if DEBUG else None
        try:
            wait_for_add_button(page)
        except PlaywrightTimeoutError:
            print("DEBUG: DHCP widget not visible yet, navigating to dashboard...") if DEBUG else None
            page.goto(DHCP_STATIC_URL, wait_until="domcontentloaded", timeout=TIMEOUT_MS)
            open_dashboard(page)
            wait_for_add_button(page)

        for row in rows:
            print(f"DEBUG: Processing {row.hostname} {row.mac} {row.ip}") if DEBUG else None
            optional_clear_search(page)
            if find_existing_by_mac(page, row.mac):
                print(f"Skip existing MAC: {row.mac} ({row.hostname})")
                log_lines.append(f"{row.hostname};{row.mac};{row.ip};skipped;mac exists")
                continue
            if in_static_leases_list(page, row):
                print(f"Skip existing in table: {row.mac} ({row.hostname})")
                log_lines.append(f"{row.hostname};{row.mac};{row.ip};skipped;already in static list")
                continue
            try:
                add_mapping(page, row)
                log_lines.append(f"{row.hostname};{row.mac};{row.ip};ok;added")
            except PlaywrightTimeoutError as exc:
                print(f"ERROR: add_mapping timeout for {row.hostname}: {exc}")
                log_lines.append(f"{row.hostname};{row.mac};{row.ip};fail;timeout")
                continue
            except Exception as exc:
                print(f"ERROR: add_mapping failed for {row.hostname}: {exc}")
                log_lines.append(f"{row.hostname};{row.mac};{row.ip};fail;{exc}")
                continue

        if not DRY_RUN:
            apply_changes(page)

        context.close()
        browser.close()

    append_log(log_lines)
    print(f"Log written to {LOG_PATH}")

    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
