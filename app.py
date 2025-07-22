import gradio as gr
import os
import time
import base64
import jsonimport gradio as gr
import os
import time
import base64
import json
from datetime import datetime
import csv
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# ---------- CONFIG ----------

SCOPES = ['https://www.googleapis.com/auth/drive', 'https://www.googleapis.com/auth/spreadsheets']

# Read credentials from environment variable (base64-encoded)
SERVICE_ACCOUNT_BASE64 = os.getenv("SERVICE_ACCOUNT_BASE64")
if not SERVICE_ACCOUNT_BASE64:
    raise ValueError("Missing SERVICE_ACCOUNT_BASE64 environment variable")

service_account_info = json.loads(base64.b64decode(SERVICE_ACCOUNT_BASE64).decode("utf-8"))
credentials = service_account.Credentials.from_service_account_info(service_account_info, scopes=SCOPES)

drive_service = build('drive', 'v3', credentials=credentials)
sheets_service = build('sheets', 'v4', credentials=credentials)

SHARED_DRIVE_ID = "0AF1duv2II1XOUk9PVA"
PARENT_FOLDER_ID = "1sxFuBEyTKSdoqOYvzUoLOzjUHR0EJuax"
FOLDER_ID_AUDIO = "1XHyO-ic-ci91fLE3iM6_5i9f9WSifLCU"
FOLDER_ID_METADATA = "1BOa2ww75J5ijleNYgRx7fgIkYUe_Af6S"
SPREADSHEET_NAME = "metadata"

# ----------------------------

def upload_to_drive(filepath, parent_folder_id):
    filename = os.path.basename(filepath)
    file_metadata = {
        'name': filename,
        'parents': [parent_folder_id],
        'driveId': SHARED_DRIVE_ID,
    }
    media = MediaFileUpload(filepath, resumable=True)
    file = drive_service.files().create(
        body=file_metadata,
        media_body=media,
        supportsAllDrives=True,
        fields='id'
    ).execute()
    return file.get('id')

def get_or_create_spreadsheet():
    query = f"'{FOLDER_ID_METADATA}' in parents and name='{SPREADSHEET_NAME}' and mimeType='application/vnd.google-apps.spreadsheet' and trashed=false"
    results = drive_service.files().list(
        q=query,
        supportsAllDrives=True,
        includeItemsFromAllDrives=True,
        fields="files(id, name)"
    ).execute()
    files = results.get('files', [])
    if files:
        return files[0]['id']
    else:
        spreadsheet_body = {
            'properties': {'title': SPREADSHEET_NAME}
        }
        spreadsheet = sheets_service.spreadsheets().create(
            body=spreadsheet_body,
            fields='spreadsheetId'
        ).execute()
        spreadsheet_id = spreadsheet['spreadsheetId']
        drive_service.files().update(
            fileId=spreadsheet_id,
            addParents=FOLDER_ID_METADATA,
            supportsAllDrives=True
        ).execute()
        header = [['Timestamp', 'Nama', 'Gender', 'Nationality', 'Surah', 'Ayat', 'Jenis Tarannum', 'File ID Audio']] 
        sheets_service.spreadsheets().values().append(
            spreadsheetId=spreadsheet_id,
            range="Sheet1!A1",
            valueInputOption="RAW",
            body={"values": header}
        ).execute()
        return spreadsheet_id

def save_audio_with_metadata(audio_file, jenis_tarannum, nama, gender, nationality, surah, ayat):  
    try:
        if audio_file is None:
            return "Sila rakam atau muat naik fail audio dahulu."

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        jenis_tarannum_clean = jenis_tarannum.replace(" ", "_")
        filename_audio = f"{timestamp}_{jenis_tarannum_clean}.wav"
        temp_audio_path = os.path.join(os.getcwd(), filename_audio)

        with open(temp_audio_path, "wb") as f:
            f.write(open(audio_file, "rb").read())

        file_id_audio = upload_to_drive(temp_audio_path, FOLDER_ID_AUDIO)
        os.remove(temp_audio_path)

        spreadsheet_id = get_or_create_spreadsheet()
        row = [[timestamp, nama, gender, nationality, surah, ayat, jenis_tarannum, file_id_audio]] 
        sheets_service.spreadsheets().values().append(
            spreadsheetId=spreadsheet_id,
            range="Sheet1!A1",
            valueInputOption="RAW",
            insertDataOption="INSERT_ROWS",
            body={"values": row}
        ).execute()

        return f"Audio berjaya disimpan dengan ID: {file_id_audio}"

    except Exception as e:
        return f"Ralat semasa simpan: {str(e)}"

# GRADIO UI

jenis_tarannum_list = [
    "Bayati", "Hijaz", "Nahawand", "Rast", "Sobah", "Sika", "Jiharkah", "Ajam", "Kurd"
]

with gr.Blocks() as iface:
    gr.Markdown("# **Tarannum Recording App**<br><span style='font-size:12px;'>Aplikasi Rakaman Tarannum</span>")


    nama = gr.Textbox(label="Name | Nama", interactive=True)
    gender = gr.Dropdown(label="Gender | Jantina", choices=["Male | Lelaki", "Female | Perempuan"], interactive=True)  
    nationality = gr.Textbox(label="Nationality | Warganegara", interactive=True)
    surah = gr.Textbox(label="Surah | Surah", interactive=True)
    ayat = gr.Textbox(label="Verse | Ayat", interactive=True)
    jenis_tarannum = gr.Dropdown(label="Tarannum Type | Jenis Tarannum", choices=jenis_tarannum_list, interactive=True)
    audio_input = gr.Audio(sources=["microphone", "upload"], type="filepath", label="Record or Upload Audio File | Rakam atau Muat Naik Fail Audio", interactive=True)

    submit_btn = gr.Button("Submit | Hantar", interactive=False)
    tambah_baru_btn = gr.Button("Add new Audio | Tambah Audio Baru", visible=False)
    output = gr.Textbox(label="Status")

    def check_inputs(nama, gender, nationality, surah, ayat, jenis_tarannum, audio_file):
        return all([nama, gender,nationality, surah, ayat, jenis_tarannum, audio_file])

    def update_button(nama, gender, nationality, surah, ayat, jenis_tarannum, audio_file):
        if check_inputs(nama, gender,nationality, surah, ayat, jenis_tarannum, audio_file):
            return gr.update(interactive=True)
        else:
            return gr.update(interactive=False)

    def reset_all():
        return "", "", "", "", None, None, None, gr.update(value="Hantar", interactive=False), gr.update(visible=False)  


    submit_btn.click(
        fn=save_audio_with_metadata,
        inputs=[audio_input, jenis_tarannum, nama, gender, nationality, surah, ayat], 
        outputs=output
    ).then(
        lambda: (gr.update(interactive=False), gr.update(visible=True)),
        outputs=[submit_btn, tambah_baru_btn]
    )

    tambah_baru_btn.click(
        fn=reset_all,
        outputs=[nama, nationality, surah, ayat, jenis_tarannum, audio_input, submit_btn, tambah_baru_btn]
    )

    inputs = [nama, gender, nationality, surah, ayat, jenis_tarannum, audio_input] 
    for inp in inputs:
        inp.change(fn=update_button, inputs=inputs, outputs=submit_btn)


iface.launch(server_name="0.0.0.0", server_port=int(os.environ.get("PORT", 7860)), share=False)

from datetime import datetime
import csv
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# ---------- CONFIG ----------

SCOPES = ['https://www.googleapis.com/auth/drive', 'https://www.googleapis.com/auth/spreadsheets']

# Read credentials from environment variable (base64-encoded)
SERVICE_ACCOUNT_BASE64 = os.getenv("SERVICE_ACCOUNT_BASE64")
if not SERVICE_ACCOUNT_BASE64:
    raise ValueError("Missing SERVICE_ACCOUNT_BASE64 environment variable")

service_account_info = json.loads(base64.b64decode(SERVICE_ACCOUNT_BASE64).decode("utf-8"))
credentials = service_account.Credentials.from_service_account_info(service_account_info, scopes=SCOPES)

drive_service = build('drive', 'v3', credentials=credentials)
sheets_service = build('sheets', 'v4', credentials=credentials)

SHARED_DRIVE_ID = "0AF1duv2II1XOUk9PVA"
PARENT_FOLDER_ID = "1sxFuBEyTKSdoqOYvzUoLOzjUHR0EJuax"
FOLDER_ID_AUDIO = "1XHyO-ic-ci91fLE3iM6_5i9f9WSifLCU"
FOLDER_ID_METADATA = "1BOa2ww75J5ijleNYgRx7fgIkYUe_Af6S"
SPREADSHEET_NAME = "metadata"

# ----------------------------

def upload_to_drive(filepath, parent_folder_id):
    filename = os.path.basename(filepath)
    file_metadata = {
        'name': filename,
        'parents': [parent_folder_id],
        'driveId': SHARED_DRIVE_ID,
    }
    media = MediaFileUpload(filepath, resumable=True)
    file = drive_service.files().create(
        body=file_metadata,
        media_body=media,
        supportsAllDrives=True,
        fields='id'
    ).execute()
    return file.get('id')

def get_or_create_spreadsheet():
    query = f"'{FOLDER_ID_METADATA}' in parents and name='{SPREADSHEET_NAME}' and mimeType='application/vnd.google-apps.spreadsheet' and trashed=false"
    results = drive_service.files().list(
        q=query,
        supportsAllDrives=True,
        includeItemsFromAllDrives=True,
        fields="files(id, name)"
    ).execute()
    files = results.get('files', [])
    if files:
        return files[0]['id']
    else:
        spreadsheet_body = {
            'properties': {'title': SPREADSHEET_NAME}
        }
        spreadsheet = sheets_service.spreadsheets().create(
            body=spreadsheet_body,
            fields='spreadsheetId'
        ).execute()
        spreadsheet_id = spreadsheet['spreadsheetId']
        drive_service.files().update(
            fileId=spreadsheet_id,
            addParents=FOLDER_ID_METADATA,
            supportsAllDrives=True
        ).execute()
        header = [['Timestamp', 'Nama', 'Gender', 'Nationality', 'Surah', 'Ayat', 'Jenis Tarannum', 'File ID Audio']] 
        sheets_service.spreadsheets().values().append(
            spreadsheetId=spreadsheet_id,
            range="Sheet1!A1",
            valueInputOption="RAW",
            body={"values": header}
        ).execute()
        return spreadsheet_id

def save_audio_with_metadata(audio_file, jenis_tarannum, nama, gender, nationality, surah, ayat):  
    try:
        if audio_file is None:
            return "Sila rakam atau muat naik fail audio dahulu."

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        jenis_tarannum_clean = jenis_tarannum.replace(" ", "_")
        filename_audio = f"{timestamp}_{jenis_tarannum_clean}.wav"
        temp_audio_path = os.path.join(os.getcwd(), filename_audio)

        with open(temp_audio_path, "wb") as f:
            f.write(open(audio_file, "rb").read())

        file_id_audio = upload_to_drive(temp_audio_path, FOLDER_ID_AUDIO)
        os.remove(temp_audio_path)

        spreadsheet_id = get_or_create_spreadsheet()
        row = [[timestamp, nama, gender, nationality, surah, ayat, jenis_tarannum, file_id_audio]] 
        sheets_service.spreadsheets().values().append(
            spreadsheetId=spreadsheet_id,
            range="Sheet1!A1",
            valueInputOption="RAW",
            insertDataOption="INSERT_ROWS",
            body={"values": row}
        ).execute()

        return f"Audio berjaya disimpan dengan ID: {file_id_audio}"

    except Exception as e:
        return f"Ralat semasa simpan: {str(e)}"

# GRADIO UI

jenis_tarannum_list = [
    "Bayati", "Hijaz", "Nahawand", "Rast", "Sobah", "Sika", "Jiharkah", "Ajam", "Kurd"
]

with gr.Blocks() as iface:
    gr.Markdown("# **Tarannum Recording App**<br><span style='font-size:12px;'>Aplikasi Rakaman Tarannum</span>")


    nama = gr.Textbox(label="Name | Nama", interactive=True)
    gender = gr.Dropdown(label="Gender | Jantina", choices=["Male | Lelaki", "Female | Perempuan"], interactive=True)  
    nationality = gr.Textbox(label="Nationality | Warganegara", interactive=True)
    surah = gr.Textbox(label="Surah | Surah", interactive=True)
    ayat = gr.Textbox(label="Verse | Ayat", interactive=True)
    jenis_tarannum = gr.Dropdown(label="Tarannum Type | Jenis Tarannum", choices=jenis_tarannum_list, interactive=True)
    audio_input = gr.Audio(sources=["microphone", "upload"], type="filepath", label="Record or Upload Audio File | Rakam atau Muat Naik Fail Audio", interactive=True)

    submit_btn = gr.Button("Submit | Hantar", interactive=False)
    tambah_baru_btn = gr.Button("Add new Audio | Tambah Audio Baru", visible=False)
    output = gr.Textbox(label="Status")

    def check_inputs(nama, nationality, surah, ayat, jenis_tarannum, audio_file):
        return all([nama, nationality, surah, ayat, jenis_tarannum, audio_file])

    def update_button(nama, nationality, surah, ayat, jenis_tarannum, audio_file):
        if check_inputs(nama, nationality, surah, ayat, jenis_tarannum, audio_file):
            return gr.update(interactive=True)
        else:
            return gr.update(interactive=False)

    def reset_all():
        return "", "", "", "", None, None, None, gr.update(value="Hantar", interactive=False), gr.update(visible=False)  


    submit_btn.click(
        fn=save_audio_with_metadata,
        inputs=[audio_input, jenis_tarannum, nama, gender, nationality, surah, ayat], 
        outputs=output
    ).then(
        lambda: (gr.update(interactive=False), gr.update(visible=True)),
        outputs=[submit_btn, tambah_baru_btn]
    )

    tambah_baru_btn.click(
        fn=reset_all,
        outputs=[nama, nationality, surah, ayat, jenis_tarannum, audio_input, submit_btn, tambah_baru_btn]
    )

    inputs = [nama, gender, nationality, surah, ayat, jenis_tarannum, audio_input] 
    for inp in inputs:
        inp.change(fn=update_button, inputs=inputs, outputs=submit_btn)


iface.launch(server_name="0.0.0.0", server_port=int(os.environ.get("PORT", 7860)), share=False)
