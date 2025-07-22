import os
import gspread

from gspread.exceptions import SpreadsheetNotFound, WorksheetNotFound, APIError


CREDENTIALS_FILE = os.getenv('CREDENTIALS_FILE')
SPREADSHEET_KEY = os.getenv('SPREADSHEET_KEY')
WORKSHEET_NAME = os.getenv('SHEET_NAME')

_cached_worksheet = None

def _get_worksheet():
    """
    Establishes connection to Google Sheet and returns the worksheet object.
    Caches the worksheet object after the first successful connection.
    Returns the worksheet object or None on failure.
    """
    global _cached_worksheet
    if _cached_worksheet:
        return _cached_worksheet

    try:
        gc = gspread.service_account(filename=CREDENTIALS_FILE)
        print("[Sheets Manager] Gspread client initialized.")

        spreadsheet = gc.open_by_key(SPREADSHEET_KEY)
        print(f"[Sheets Manager] Spreadsheet '{SPREADSHEET_KEY}' opened.")

        worksheet = spreadsheet.worksheet(WORKSHEET_NAME)
        print(f"[Sheets Manager] Successfully connected to Google Sheet: '{WORKSHEET_NAME}'")
        _cached_worksheet = worksheet
        return worksheet

    except SpreadsheetNotFound:
        print(f"[Sheets Manager] CRITICAL ERROR: Spreadsheet with key '{SPREADSHEET_KEY}' not found. "
              "Please double-check the SPREADSHEET_KEY in sheets_manager.py.")
    except WorksheetNotFound:
        print(f"[Sheets Manager] CRITICAL ERROR: Worksheet '{WORKSHEET_NAME}' not found in the spreadsheet. "
              "Please double-check the WORKSHEET_NAME in sheets_manager.py (case-sensitive!).")
    except APIError as e:
        print(f"[Sheets Manager] CRITICAL ERROR: Google Sheets API error: {e}. "
              "This often means incorrect permissions or API not enabled. "
              "Ensure the service account has 'Editor' access to the sheet and "
              "Google Sheets API/Google Drive API are enabled in Google Cloud Console.")
    except Exception as e:
        print(f"[Sheets Manager] UNEXPECTED ERROR during connection: {type(e).__name__}: {e}. "
              "This might indicate a network issue, firewall, or a corrupted credentials file.")
    return None


def get_all_members_data():
    """
    Fetches all records from the worksheet and returns a list of dictionaries.
    """
    worksheet = _get_worksheet()
    if worksheet:
        try:
            return worksheet.get_all_records()
        except Exception as e:
            print(f"Error fetching records: {e}")
            return []
    else:
        print("Warning: Google Sheet connection not established. Cannot fetch records.")
    return []


def add_new_discord_user(username, discord_id):
    """
    Adds a new user to the Google Sheet if they are not already present.
    """
    worksheet = _get_worksheet()
    if not worksheet:
        return False, "Could not connect to Google Sheet."
    
    try:
        existing_discord_ids = [str(id_val) for id_val in worksheet.col_values(2)]

        if str(discord_id) in existing_discord_ids:
            return False, f"User '{username}' (ID: {discord_id}) already exists in the sheet."

        new_row = [username, str(discord_id), ""]
        worksheet.append_row(new_row)
        return True, f"User '{username}' (ID: {discord_id}) added successfully."

    except Exception as e:
        return False, f"Error adding user to sheet: {e}"


def get_steam_id_for_discord_id(discord_id):
    """
    Retrieves the Steam ID for a given Discord ID from the sheet.
    Assumes 'Discord ID' is column 2 and 'Steam ID' is column 3.
    Returns the Steam ID string or None if not found/error.
    """
    worksheet = _get_worksheet()
    if not worksheet:
        print("Warning: Google Sheet connection not established. Cannot get Steam ID.")
        return None

    try:
        cell = worksheet.find(str(discord_id), in_column=2)
        if cell:
            steam_id = worksheet.cell(cell.row, 3).value
            return steam_id if steam_id else None
    except gspread.exceptions.CellNotFound:
        print(f"Discord ID {discord_id} not found in sheet.")
        return None
    except Exception as e:
        print(f"ERROR: Failed to retrieve Steam ID for {discord_id}: {e}")
        return None
    return None


def update_user_steam_id(discord_id, new_steam_id):
    """
    Updates the Steam ID for a given Discord user in the Google Sheet.
    Returns (True, message) on success, (False, message) on failure.
    """
    worksheet = _get_worksheet()
    if not worksheet:
        return False, "Google Sheet connection not established."
    
    try:
        cell = worksheet.find(str(discord_id), in_column=2)
        if cell:
            worksheet.update_cell(cell.row, 3, new_steam_id)
            return True, f"Steam ID for Discord user {discord_id} updated successfully."
        else:
            return False, f"Discord ID {discord_id} not found in the sheet."
    except Exception as e:
        return False, f"Error updating Steam ID for user {discord_id}: {e}"