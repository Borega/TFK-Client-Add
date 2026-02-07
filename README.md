# OPNsense DHCP CSV Automation (Headless)

This project automates adding DHCP static mappings in the OPNsense UI without using the API. It uses Playwright for fast, headless browser automation.

## What you get
- Headless browser automation (no mouse/GUI)
- CSV-driven entries
- Safer interaction via selectors (not screen coordinates)

## Files
- CSV template: data/daten_template.csv (Name;Raum;IP;MAC;Besitzer;Inventarnummer;Beschreibung)
- Script: src/opnsense_dhcp_ui.py

## Setup
1. Create a virtual environment and install dependencies:
   - pip install -r requirements.txt
2. Install Playwright browsers:
   - python -m playwright install

## Configure
Edit src/opnsense_dhcp_ui.py and set:
- BASE_URL
- LOGIN_URL (if different)
- USERNAME/PASSWORD
- Selectors in SELECTORS dict (see below)

## Finding selectors
Option A (recommended):
- Run Playwright codegen while logged in:
  - python -m playwright codegen https://<your-opnsense-host>
- Click the Add button and the input fields to capture selectors.

Option B:
- Use browser DevTools (F12) and copy a stable selector (id/name/data-testid).

## Run
- python src/opnsense_dhcp_ui.py

## Notes
- The script supports dry-run mode for safety.
- Validation is applied to MAC and IP formats before submission.
