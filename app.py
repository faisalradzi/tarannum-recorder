import gradio as gr
import os
import time
import json
from datetime import datetime
import csv
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# ---------- CONFIG CONFIG CONFIG ----------

# Membaca kredensial peribadi dari Environment Variables di Render
CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
REFRESH_TOKEN = os.getenv("GOOGLE_REFRESH_TOKEN")

if not all([CLIENT_ID, CLIENT_SECRET, REFRESH_TOKEN]):
    raise ValueError("Missing OAuth2 environment variables (CLIENT_ID, CLIENT_SECRET, or REFRESH_TOKEN)")

# Membina kredensial menggunakan Refresh Token peribadi anda
creds = Credentials(
    token=None,  # Google API Client akan menjana access token baharu secara automatik
    refresh_token=REFRESH_TOKEN,
    token_uri="https://oauth2.googleapis.com/token",
    client_id=CLIENT_ID,
    client_secret=CLIENT_SECRET,
    scopes=['https://www.googleapis.com/auth/drive', 'https://www.googleapis.com/auth/spreadsheets']
)

# Segarkan token secara automatik jika tamat tempoh
if not creds.valid:
    creds.refresh(Request())

drive_service = build('drive', 'v3', credentials=creds)
sheets_service = build('sheets', 'v4', credentials=creds)

# === MASUKKAN ID FOLDER GOOGLE DRIVE PERIBADI ANDA DI SINI ===
FOLDER_ID_AUDIO = "1GaZQADrKiIo8t6PdsKJwQob9CWZ0LJT3"   # Folder untuk simpan .wav
FOLDER_ID_METADATA = "15jGILIc3T0uwCFdru5qucevShFDQimTu" # Folder untuk simpan Google Sheets
SPREADSHEET_NAME = "metadata"

# ------------------------------------------

def upload_to_drive(filepath, parent_folder_id):
    filename = os.path.basename(filepath)
    file_metadata = {
        'name': filename,
        'parents': [parent_folder_id],
    }
    
    # Muat naik biasa (resumable=False) lebih stabil untuk fail saiz kecil
    media = MediaFileUpload(filepath, mimetype='audio/wav', resumable=False)
    
    file = drive_service.files().create(
        body=file_metadata,
        media_body=media,
        fields='id'
    ).execute()
    
    return file.get('id')

def get_or_create_spreadsheet():
    query = f"'{FOLDER_ID_METADATA}' in parents and name='{SPREADSHEET_NAME}' and mimeType='application/vnd.google-apps.spreadsheet' and trashed=false"
    results = drive_service.files().list(
        q=query,
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
            addParents=FOLDER_ID_METADATA
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
    "Bayati", "Hijaz", "Nahawand", "Rast", "Soba", "Sikah", "Jiharkah"
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
        return (
            "",  # nama
            None,  # gender
            "",  # nationality
            "",  # surah
            "",  # ayat
            None,  # jenis_tarannum
            None,  # audio_input
            gr.update(interactive=False),  # submit_btn
            gr.update(visible=False)  # tambah_baru_btn
        )

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
        outputs=[nama, gender, nationality, surah, ayat, jenis_tarannum, audio_input, submit_btn, tambah_baru_btn]
    )

    inputs = [nama, gender, nationality, surah, ayat, jenis_tarannum, audio_input] 
    for inp in inputs:
        inp.change(fn=update_button, inputs=inputs, outputs=submit_btn)


iface.launch(server_name="0.0.0.0", server_port=int(os.environ.get("PORT", 7860)), share=False)
