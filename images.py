"""
images.py
صور ورسومات الأسئلة. تُصغَّر وتُضغط ثم تُخزَّن في جدول question_images (Supabase) أو في مجلد محلي مؤقت،
ويحمل السؤال معرّفها فقط (data["image_id"]) فلا تثقل قوائم الأسئلة. تُحمَّل الصورة عند عرضها فقط.
"""
import base64
import io
import json

import requests
import streamlit as st
from PIL import Image

import catalog
from config import BASE

LOCAL_DIR = BASE / "data" / "qimages"
TIMEOUT = 20
MAX_SIDE = 1000          # أطول ضلع بالبكسل بعد التصغير
PNG_LIMIT = 220_000      # أكبر من ذلك يُحفظ JPEG لتقليل الحجم


def prepare(img):
    """PIL.Image → (bytes, mime) مصغّرة ومضغوطة."""
    img = img.convert("RGB")
    img.thumbnail((MAX_SIDE, MAX_SIDE))
    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=True)
    if buf.tell() <= PNG_LIMIT:
        return buf.getvalue(), "image/png"
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=82, optimize=True)
    return buf.getvalue(), "image/jpeg"


def crop_box(img, box, pad=0.01):
    """box = [ymin, xmin, ymax, xmax] مقيسة 0..1000 (صيغة Gemini). يعيد المقطوع أو None إن كان الصندوق غير معقول."""
    try:
        y0, x0, y1, x1 = (float(v) for v in box)
    except (TypeError, ValueError):
        return None
    if not (0 <= y0 < y1 <= 1000 and 0 <= x0 < x1 <= 1000):
        return None
    if (y1 - y0) * (x1 - x0) < 0.01 * 1000 * 1000:      # أقل من 1% من الصفحة: ليس شكلًا
        return None
    w, h = img.size
    px, py = pad * w, pad * h
    return img.crop((max(0, int(x0 / 1000 * w - px)), max(0, int(y0 / 1000 * h - py)),
                     min(w, int(x1 / 1000 * w + px)), min(h, int(y1 / 1000 * h + py))))


def save(data, mime="image/png"):
    """يخزّن الصورة ويعيد معرّفها."""
    if catalog.backend_name() == "supabase":
        url, h = catalog._sb()
        r = requests.post(f"{url}/rest/v1/question_images", headers={**h, "Prefer": "return=representation"},
                          timeout=TIMEOUT, data=json.dumps([{"mime": mime, "b64": base64.b64encode(data).decode()}]))
        catalog._check(r)
        return r.json()[0]["id"]
    LOCAL_DIR.mkdir(parents=True, exist_ok=True)
    nxt = max([int(p.stem) for p in LOCAL_DIR.glob("*.bin")] or [0]) + 1
    (LOCAL_DIR / f"{nxt}.bin").write_bytes(data)
    return nxt


@st.cache_data(ttl=3600, show_spinner=False)
def load(image_id):
    """bytes الصورة أو None."""
    if not image_id:
        return None
    try:
        if catalog.backend_name() == "supabase":
            url, h = catalog._sb()
            r = requests.get(f"{url}/rest/v1/question_images", headers=h, timeout=TIMEOUT,
                             params={"select": "b64", "id": f"eq.{image_id}"})
            catalog._check(r)
            rows = r.json()
            return base64.b64decode(rows[0]["b64"]) if rows else None
        p = LOCAL_DIR / f"{image_id}.bin"
        return p.read_bytes() if p.exists() else None
    except Exception:  # noqa: BLE001
        return None
