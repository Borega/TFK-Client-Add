# OPNsense DHCP CSV Automation (Headless)

This project automates adding DHCP static mappings in the OPNsense UI without using the API. It uses Playwright for fast, headless browser automation.

## What you get
- Headless browser automation (no mouse/GUI)
- CSV-driven entries
- Safer interaction via selectors (not screen coordinates)
- Run log for each CSV row
- Pre-checks for duplicates and existing leases
- Clean temp CSV for rows to add

## Files
- CSV template: data/daten_template.csv (Name;Raum;IP;MAC;Besitzer;Inventarnummer;Beschreibung)
- Script: src/opnsense_dhcp_ui.py
- Log output: data/run_log.csv
- Temp CSV (auto-deleted): data/to_add.csv

## Setup
1. Create a virtual environment and install dependencies:
   - pip install -r requirements.txt
2. Install Playwright browsers:
   - python -m playwright install

## Configure
Edit src/opnsense_dhcp_ui.py and set:
- BASE_URL
- LOGIN_URL (if different)
- Selectors in SELECTORS dict (see below)

Credentials are requested with a popup if `USERNAME` and `PASSWORD` are not set.

## Finding selectors
Option A (recommended):
- Run Playwright codegen while logged in:
   - python -m playwright codegen https://your-opnsense-host
- Click the Add button and the input fields to capture selectors.

Option B:
- Use browser DevTools (F12) and copy a stable selector (id/name/data-testid).

## Run
- python src/opnsense_dhcp_ui.py

## Notes
- The script supports dry-run mode for safety.
- Validation is applied to MAC and IP formats before submission.
- The CSV parser reads only Name/Geraet, MAC, and IP columns (case-insensitive) and ignores the rest.
- The script skips rows if any of MAC/IP/Name already exist in the static lease table.
- Set `HEADLESS = False` if you want a visible browser window.
