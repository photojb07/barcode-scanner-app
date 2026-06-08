import streamlit as st
import snowflake.connector
from PIL import Image
from pyzbar.pyzbar import decode
import tempfile
import os
from datetime import datetime
import hashlib

st.set_page_config(page_title="Barcode Scanner", layout="centered")

st.title("Barcode Scanner")
st.write("Scan a barcode or upload an image. Photos are securely stored.")

MAX_FILE_SIZE_MB = 10
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".bmp"}


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


def scan_barcode(image):
    barcodes = decode(image)
    results = []
    for barcode in barcodes:
        barcode_data = barcode.data.decode("utf-8")
        barcode_type = barcode.type
        results.append({"data": barcode_data, "type": barcode_type})
    return results


def sanitize_filename(name):
    safe = "".join(c if c.isalnum() or c in "._-" else "_" for c in name)
    return safe[:100]


def upload_to_stage(conn, file_bytes, filename):
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError(f"File type {ext} not allowed.")
    if len(file_bytes) > MAX_FILE_SIZE_MB * 1024 * 1024:
        raise ValueError(f"File exceeds {MAX_FILE_SIZE_MB}MB limit.")

    safe_filename = sanitize_filename(filename)

    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
        tmp.write(file_bytes)
        tmp_path = tmp.name

    try:
        cursor = conn.cursor()
        cursor.execute(
            f"PUT file://{tmp_path} @BARCODE_UPLOADS.PUBLIC.IMAGE_STAGE/{safe_filename} AUTO_COMPRESS=FALSE OVERWRITE=FALSE"
        )
        cursor.close()
    finally:
        os.remove(tmp_path)


def log_upload(conn, barcode_value, filename, file_size, file_hash, notes=""):
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO BARCODE_UPLOADS.PUBLIC.UPLOAD_LOG "
        "(BARCODE_VALUE, FILENAME, FILE_SIZE, FILE_HASH, NOTES) "
        "VALUES (%s, %s, %s, %s, %s)",
        (barcode_value, sanitize_filename(filename), file_size, file_hash, notes),
    )
    cursor.close()


def process_upload(file_bytes, original_filename, barcodes, notes):
    ext = os.path.splitext(original_filename)[1] if original_filename else ".jpg"
    barcode_value = barcodes[0]["data"] if barcodes else "NO_BARCODE"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{sanitize_filename(barcode_value)}_{timestamp}{ext}"
    file_hash = hashlib.sha256(file_bytes).hexdigest()[:16]

    with st.spinner("Uploading..."):
        try:
            conn = get_snowflake_connection()
            upload_to_stage(conn, file_bytes, filename)
            log_upload(conn, barcode_value, filename, len(file_bytes), file_hash, notes)
            st.success(f"Uploaded **{filename}** successfully!")
        except ValueError as e:
            st.error(str(e))
        except Exception as e:
            st.error(f"Upload failed: {e}")


tab1, tab2 = st.tabs(["Camera", "File Upload"])

with tab1:
    camera_photo = st.camera_input("Take a photo of a barcode")
    if camera_photo is not None:
        image = Image.open(camera_photo)
        st.image(image, caption="Captured Photo", use_container_width=True)

        barcodes = scan_barcode(image)
        if barcodes:
            st.success(f"Found {len(barcodes)} barcode(s)!")
            for bc in barcodes:
                st.write(f"**Type:** {bc['type']} | **Value:** {bc['data']}")
        else:
            st.warning("No barcode detected. You can still upload the image.")

        notes = st.text_input("Add a note (optional)", key="camera_notes")

        if st.button("Upload Photo", key="camera_upload"):
            process_upload(camera_photo.getvalue(), "camera.jpg", barcodes, notes)

with tab2:
    uploaded_file = st.file_uploader(
        "Upload an image", type=["jpg", "jpeg", "png", "gif", "bmp"]
    )
    if uploaded_file is not None:
        image = Image.open(uploaded_file)
        st.image(image, caption="Uploaded Image", use_container_width=True)

        barcodes = scan_barcode(image)
        if barcodes:
            st.success(f"Found {len(barcodes)} barcode(s)!")
            for bc in barcodes:
                st.write(f"**Type:** {bc['type']} | **Value:** {bc['data']}")
        else:
            st.warning("No barcode detected. You can still upload the image.")

        notes = st.text_input("Add a note (optional)", key="file_notes")

        if st.button("Upload Image", key="file_upload"):
            process_upload(uploaded_file.getvalue(), uploaded_file.name, barcodes, notes)

st.divider()
st.caption("Upload only. Images are securely stored and cannot be deleted from this app.")
