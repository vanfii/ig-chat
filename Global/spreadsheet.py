from datetime import datetime
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from .config import get_spreadsheet_id_by_ig_id
import os
def get_sheet(spreadsheet_id):
    SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
    creds = Credentials.from_service_account_file(
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"], scopes=SCOPES
    )
    service = build("sheets", "v4", credentials=creds)
    sheet = service.spreadsheets()
    return sheet, spreadsheet_id

def count_orders_from_sheet(spreadsheet_id):
    SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
    creds = Credentials.from_service_account_file(
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"], scopes=SCOPES
    )
    service = build("sheets", "v4", credentials=creds)

    # 1. Ambil nama sheet pertama
    metadata = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    sheet_name = metadata["sheets"][0]["properties"]["title"]

    # 2. Ambil data dari kolom A (misalnya kolom A adalah penanda setiap order)
    range_name = f"{sheet_name}!A2:A"
    result = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range=range_name
    ).execute()

    values = result.get("values", [])
    return len(values)

def count_orders_by_ig_id(ig_id):
    spreadsheet_id = get_spreadsheet_id_by_ig_id(ig_id)
    if not spreadsheet_id:
        return 0  # atau bisa raise error jika mau

    return count_orders_from_sheet(spreadsheet_id)

def log_to_sheet(sender_id: str, username: str, final_order: str, ig_id: str):
    spreadsheet_id = get_spreadsheet_id_by_ig_id(ig_id)
    sheet, sid = get_sheet(spreadsheet_id)

    values = [[
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        sender_id,
        username,
        final_order
    ]]

    sheet.values().append(
        spreadsheetId=sid,
        range="Sheet1!A1",
        valueInputOption="USER_ENTERED",
        body={"values": values}
    ).execute()

    print(f"✅ Logged to sheet: {spreadsheet_id} | IG ID: {ig_id}")
