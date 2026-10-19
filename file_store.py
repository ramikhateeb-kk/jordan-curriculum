"""
file_store.py - تخزين واسترجاع الملفات والمستندات التعليمية محلياً وسحابياً
"""

import os
import shutil

BASE_DIR = os.path.dirname(__file__)
UPLOADS_DIR = os.path.join(BASE_DIR, "data", "uploads")
EXPORTS_DIR = os.path.join(BASE_DIR, "data", "exports")

os.makedirs(UPLOADS_DIR, exist_ok=True)
os.makedirs(EXPORTS_DIR, exist_ok=True)

def save_uploaded_file(uploaded_file, category: str = "general") -> str:
    target_dir = os.path.join(UPLOADS_DIR, category)
    os.makedirs(target_dir, exist_ok=True)
    file_path = os.path.join(target_dir, uploaded_file.name)
    with open(file_path, "wb") as f:
        f.write(uploaded_file.getbuffer() if hasattr(uploaded_file, "getbuffer") else uploaded_file.read())
    return file_path

def get_exported_file_path(filename: str) -> str:
    return os.path.join(EXPORTS_DIR, filename)
