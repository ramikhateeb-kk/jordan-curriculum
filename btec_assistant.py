"""
btec_assistant.py
منظومة BTEC (واجهات + خط المعالجة):
  • الطالب (العاشر/الحادي عشر/الثاني عشر BTEC): يختار الواجب فقط فيُعرض دليله المخزَّن (نص + صور مولَّدة).
  • مشرف BTEC / المدير: يرفع ملفات الواجب → يُستخرج الواجب ويُولَّد دليل الطالب بصوره ويُخزَّن.
  • معلم BTEC: دليل شرح الواجب، متابعة تقدم الطلاب ومدى استيفاء المعايير، فحص أدلة الطالب بالذكاء الاصطناعي.
  • المدير: تعيين طاقم BTEC (مشرفون/معلمون) لكل تخصص وصف.
"""
import hashlib
import io
import re

import pandas as pd
import streamlit as st
from PIL import Image

import accounts as acc
import auth_ui
import btec_ai
import btec_store as store
import catalog
import file_store
import images as imgs
import rich_text
from config import BASE, GRADES

MAX_FILES, MAX_FILE_MB, MAX_TOTAL_MB, MAX_PDF_PAGES = 10, 10, 18, 20
LOCAL_FILES = BASE / "data" / "btec_files"
IMG_MIME = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "webp": "image/webp"}
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
_AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
STATUSES = ["لم يبدأ", "قيد التنفيذ", "سُلِّم", "محقَّق", "غير محقَّق", "يحتاج إعادة"]
VERDICT = {"met": ("✅ محقَّق", "محقَّق"), "partial": ("🟡 جزئي", "قيد التنفيذ"),
           "not_met": ("❌ غير محقَّق", "غير محقَّق"), "not_assessable": ("⚪ غير قابل للحكم", None)}


# ================================================================ التعرّف على المستخدمين
def is_btec_track(name):
    n = (name or "").lower()
    return "btec" in n or "بيتك" in n


def btec_tracks(tracks):
    return [t for t in tracks if is_btec_track(t["name"]) and t.get("active", True)]


def is_btec_student(user, tracks):
    """طالب في الصف 10/11/12 تخصصه يحوي كلمة BTEC."""
    if user.get("role") != "student" or user.get("grade") not in (10, 11, 12):
        return False
    t = next((t for t in tracks if t["id"] == user.get("track_id")), None)
    return bool(t and is_btec_track(t["name"]))


def has_general_scope(user, tracks):
    """هل لهذا المعلم/المشرف صلاحيات على المنهاج العام (غير BTEC) إلى جانب BTEC؟"""
    btec_ids = {t["id"] for t in btec_tracks(tracks)}
    if any(r.get("track_id") not in btec_ids for r in acc.teacher_scope(user["id"])):
        return True
    return user["role"] == "supervisor" and bool(acc.supervisor_subjects(user["id"]))


def scope_label(tracks, grade, track_id):
    return f"{GRADES[grade - 1]} — {catalog.track_name(tracks, track_id)}"


# ================================================================ قراءة الملفات المرفوعة
def _docx_text(data):
    from docx import Document
    from docx.table import Table
    from docx.text.paragraph import Paragraph
    doc = Document(io.BytesIO(data))
    out = []
    for child in doc.element.body.iterchildren():
        if child.tag.endswith("}p"):
            t = Paragraph(child, doc).text.strip()
            if t:
                out.append(t)
        elif child.tag.endswith("}tbl"):
            for row in Table(child, doc).rows:
                cells = []
                for c in row.cells:
                    ct = c.text.strip().replace("\n", " ")
                    if not cells or cells[-1] != ct:
                        cells.append(ct)
                out.append(" | ".join(cells))
    return "\n".join(out)


def _pdf_pages_png(data):
    try:
        import fitz
    except ImportError:
        return []
    pages = []
    with fitz.open(stream=data, filetype="pdf") as pdf:
