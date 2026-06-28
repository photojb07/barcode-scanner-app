# Barcode scanner app with chunked file upload for large video support
# Co-authored with CoCo
import streamlit as st
import snowflake.connector
import os
from datetime import datetime
import hashlib
import uuid
from cryptography.hazmat.primitives import serialization

st.set_page_config(page_title="Upload Portal", layout="centered")

st.title("Photo & Video Upload")
st.write("Upload your photos or videos securely. No login required.")

MAX_FILE_SIZE_MB = 200
CHUNK_SIZE = 2 * 1024 * 1024  # 2 MB per chunk — safe for BINARY(8388608) with hex overhead
ALLOWED_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".heic",
    ".mp4", ".mov", ".avi", ".mkv", ".webm"
}


@st.cache_resource
def get_snowflake_connection():
    private_key_pem = st.secrets["snowflake"]["private_key"].encode()
    private_key = serialization.load_pem_private_key(private_key_pem, password=None)
    private_key_bytes = private_key.private_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return snowflake.connector.connect(
        account=st.secrets["snowflake"]["account"],
        user=st.secrets["snowflake"]["user"],
        private_key=private_key_bytes,
        warehouse=st.secrets["snowflake"]["warehouse"],
        database=st.secrets["snowflake"]["database"],
        schema=st.secrets["snowflake"]["schema"],
        role=st.secrets["snowflake"]["role"],
    )


def sanitize_filename(name):
    safe = "".join(c if c.isalnum() or c in "._-" else "_" for c in name)
    return safe[:100]


def upload_in_chunks(conn, file_bytes, filename, notes=""):
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError(f"File type {ext} not allowed.")
    if len(file_bytes) > MAX_FILE_SIZE_MB * 1024 * 1024:
        raise ValueError(f"File exceeds {MAX_FILE_SIZE_MB}MB limit.")

    safe_filename = sanitize_filename(filename)
    upload_id = uuid.uuid4().hex[:16]
    total_chunks = (len(file_bytes) + CHUNK_SIZE - 1) // CHUNK_SIZE

    cursor = conn.cursor()
    progress_bar = st.progress(0, text=f"Uploading {safe_filename}...")
    try:
        for i in range(total_chunks):
            chunk = file_bytes[i * CHUNK_SIZE : (i + 1) * CHUNK_SIZE]
            cursor.execute(
                "INSERT INTO BARCODE_UPLOADS.PUBLIC.FILE_CHUNKS "
                "(UPLOAD_ID, CHUNK_INDEX, TOTAL_CHUNKS, FILENAME, FILE_EXT, "
                "TOTAL_FILE_SIZE, CHUNK_DATA, NOTES) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                (upload_id, i, total_chunks, safe_filename, ext,
                 len(file_bytes), chunk, notes),
            )
            progress_bar.progress((i + 1) / total_chunks, text=f"Chunk {i+1}/{total_chunks}")
        progress_bar.empty()
    finally:
        cursor.close()

    return upload_id


def log_upload(conn, filename, file_size, file_hash, notes=""):
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO BARCODE_UPLOADS.PUBLIC.UPLOAD_LOG "
        "(BARCODE_VALUE, FILENAME, FILE_SIZE, FILE_HASH, NOTES) "
        "VALUES (%s, %s, %s, %s, %s)",
        ("UPLOAD", sanitize_filename(filename), file_size, file_hash, notes),
    )
    cursor.close()


def process_upload(file_bytes, original_filename, notes):
    ext = os.path.splitext(original_filename)[1].lower() if original_filename else ".jpg"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{timestamp}_{sanitize_filename(original_filename)}"
    file_hash = hashlib.sha256(file_bytes).hexdigest()[:16]

    with st.spinner("Uploading..."):
        try:
            conn = get_snowflake_connection()
            upload_in_chunks(conn, file_bytes, filename, notes)
            log_upload(conn, filename, len(file_bytes), file_hash, notes)
            st.success(f"Uploaded **{original_filename}** successfully!")
        except ValueError as e:
            st.error(str(e))
        except Exception as e:
            st.error(f"Upload failed: {e}")


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
            for uploaded_file in uploaded_files:
                process_upload(uploaded_file.getvalue(), uploaded_file.name, notes)

st.divider()
st.caption("Upload only. Files are securely stored and cannot be deleted from this app.")
