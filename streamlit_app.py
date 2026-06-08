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
        raise ValueError(f"File exceeds {MAX_FILE_SIZE_
