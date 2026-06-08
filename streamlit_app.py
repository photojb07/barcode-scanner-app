import streamlit as st
import snowflake.connector
import tempfile
import os
from datetime import datetime
import hashlib

st.set_page_config(page_title="Upload Portal", layout="centered")

st.title("Photo & Video Upload")
st.write("Upload your photos or videos securely. No login required.")

MAX_FILE_SIZE_MB = 200
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".heic", ".mp4", ".mov", ".avi", ".mkv", ".webm"}


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


def upload_to_stage(conn, file_bytes, filename):
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError("File type " + ext + " not allowed.")
    if len(file_bytes) > MAX_FILE_SIZE_MB * 1024 * 1024:
        raise ValueError("File exceeds " + str(MAX_FILE_SIZE_MB) + "MB limit.")

    safe_filename = sanitize_filename(filename)

    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
        tmp.write(file_bytes)
        tmp_path = tmp.name

    try:
        cursor = conn.cursor()
        stage_path = "@BARCODE_UPLOADS.PUBLIC.IMAGE_STAGE/" + safe_filename
        cursor.execute(
            "PUT file://" + tmp_path + " " + stage_path + " AUTO_COMPRESS=FALSE OVERWRITE=FALSE"
        )
        cursor.close()
    finally:
        os.remove(tmp_path)


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
    filename = timestamp + "_" + sanitize_filename(original_filename)
    file_hash = hashlib.sha256(file_bytes).hexdigest()[:16]

    with st.spinner("Uploading..."):
        try:
            conn = get_snowflake_connection()
            upload_to_stage(conn, file_bytes, filename)
            log_upload(conn, filename, len(file_bytes), file_hash, notes)
            st.success("Uploaded **" + original_filename + "** successfully!")
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
            for uploaded_file in uploaded_files:
                process_upload(uploaded_file.getvalue(), uploaded_file.name, notes)

st.divider()
st.caption("Upload only. Files are securely stored and cannot be deleted from this app.")
