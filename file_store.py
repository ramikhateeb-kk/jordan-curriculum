"""
file_store.py
رفع ملفات (Word / PowerPoint ...) إلى Supabase Storage وإرجاع رابط تحميل عام مباشر.
يستخدم نفس مفاتيح catalog (SUPABASE_URL / SUPABASE_KEY) عبر REST دون أي مكتبة إضافية.
"""
from urllib.parse import quote

import requests

import catalog

BUCKET = "teacher-files"   # Bucket عام في Supabase Storage
TIMEOUT = 30


def upload_file(path, data, mime, download_name):
    """يرفع bytes إلى BUCKET/path ويعيد رابطًا عامًا يُنزِّل الملف باسم download_name."""
    url, h = catalog._sb()
    headers = {"apikey": h["apikey"], "Authorization": h["Authorization"], "Content-Type": mime}
    r = requests.post(f"{url}/storage/v1/object/{BUCKET}/{path}",
                      headers=headers, data=data, timeout=TIMEOUT)
    # 409 = الملف نفسه مرفوع سابقًا (المسار يتضمن بصمة المحتوى) → نعتبره نجاحًا
    if not r.ok and r.status_code != 409 and "Duplicate" not in r.text:
        raise RuntimeError(f"فشل رفع الملف ({r.status_code}): {r.text[:200]}")
    return f"{url}/storage/v1/object/public/{BUCKET}/{path}?download={quote(download_name)}"
