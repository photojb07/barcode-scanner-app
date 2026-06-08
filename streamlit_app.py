import streamlit as st
import snowflake.connector
import os
from datetime import datetime
import hashlib
import binascii

st.set_page_config(page_title="Upload Portal", layout="centered")
st.title("Photo & Video Upload")
st.write("Upload your photos or videos securely. No login required.")

MAX_FILE_SIZE_MB = 16
ALLOWED_EXTENSIONS = [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".heic", ".mp4", ".mov", ".avi", ".mkv", ".webm"]

@st.cache_resource
def get_snowflake_connection():
    return snowflake.connector.connect(
        account=st.secrets["snowflake"]["account"],
        user=st.secrets["snowflake"]["user"],
        password=st.secrets["snowflake"]["password"],
        warehouse=st.secrets["snowflake"]["warehouse"],
        database=st.secrets["snowflake"]["database"],
        schema=st.secrets["snowflake"]["schema"],
        role=st.secrets["snowflake"]["role"],
    )

def sanitize_filename(name):
    safe = "".join(c if c.isalnum() or c in "._-" else "_" for c in name)
    return safe[:100]

def upload_file(conn, file_bytes, filename, notes=""):
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError("File type not allowed: " + ext)
    if len(file_bytes) > MAX_FILE_SIZE_MB * 1024 * 1024:
        raise ValueError("File exceeds 16MB limit.")
    safe_filename = sanitize_filename(filename)
    hex_data = binascii.hexlify(file_bytes).decode("ascii")
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO BARCODE_UPLOADS.PUBLIC.FILE_UPLOADS (FILENAME, FILE_EXT, FILE_SIZE, FILE_DATA, NOTES) "
        "SELECT %s, %s, %s, TO_BINARY(%s, 'HEX'), %s",
        (safe_filename, ext, len(file_bytes), hex_data, notes),
    )
    cursor.close()

def process_upload(file_bytes, original_filename, notes):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = timestamp + "_" + original_filename
    with st.spinner("Uploading..."):
        try:
            conn = get_snowflake_connection()
            upload_file(conn, file_bytes, filename, notes)
            st.success("Uploaded " + original_filename + " successfully!")
        except ValueError as e:
            st.error(str(e))
        except Exception as e:
            st.error("Upload failed: " + str(e))

tab1, tab2 = st.tabs(["Take Photo", "Upload File"])

with tab1:
    camera_photo = st.camera_input("Take a photo")
    if camera_photo is not None:
        st.image(camera_photo, caption="Captured Photo", use_container_width=True)
        notes = st.text_input("Add a note (optional)", key="camera_notes")
        if st.button("Upload Photo", key="camera_upload"):
            process_upload(camera_photo.getvalue(), "camera_photo.jpg", notes)

with tab2:
    uploaded_files = st.file_uploader(
        "Choose photos or videos",
        type=["jpg", "jpeg", "png", "gif", "bmp", "heic", "mp4", "mov", "avi", "mkv", "webm"],
        accept_multiple_files=True,
    )
    if uploaded_files:
        notes = st.text_input("Add a note (optional)", key="file_notes")
        if st.button("Upload All", key="file_upload"):
            for uf in uploaded_files:
                process_upload(uf.getvalue(), uf.name, notes)

st.divider()
st.caption("Upload only. Files are securely stored and cannot be deleted from this app.")
