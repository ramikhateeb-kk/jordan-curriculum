"""
btec_assistant.py
منظومة BTEC (واجهات + خط المعالجة):
  • الطالب (العاشر/الحادي عشر/الثاني عشر BTEC): يختار الواجب فقط فيُعرض دليله المخزَّن (نص + صور مولَّدة).
  • مشرف BTEC / المدير: يرفع ملفات الواجب → يُستخرج الواجب ويُولَّد دليل الطالب بصوره ويُخزَّن.
  • معلم BTEC: دليل شرح الواجب، متابعة تقدم الطلاب ومدى استيفاء المعايير، فحص أدلة الطالب بالذكاء الاصطناعي.
  • المدير: تعيين طاقم BTEC (مشرفون/معلمون) لكل تخصص وصف.
"""
import datetime as dt
import hashlib
import io
import re
import time

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

MAX_FILES, MAX_FILE_MB, MAX_TOTAL_MB = 10, 10, 18
MAX_AUDIO_MB = 25
AUDIO_MIME = {"mp3": "audio/mpeg", "wav": "audio/wav", "m4a": "audio/mp4", "ogg": "audio/ogg"}
LOCAL_FILES = BASE / "data" / "btec_files"
IMG_MIME = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "webp": "image/webp"}
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
CAD_MIME = {
    "dwg": "application/acad",
    "dxf": "application/dxf"
}
_AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
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


def read_uploads(files):
    """[UploadedFile] → (ملفات مجهَّزة, رسالة خطأ أو None)."""
    if not files:
        return [], "ارفع صورة أو ملفًا واحدًا على الأقل."
    if len(files) > MAX_FILES:
        return [], f"الحد الأقصى {MAX_FILES} ملفات في الطلب الواحد."
    out, total = [], 0
    for f in files:
        data = f.getvalue()
        total += len(data)
        if len(data) > MAX_FILE_MB * 1024 * 1024:
            return [], f"الملف «{f.name}» أكبر من {MAX_FILE_MB}MB."
        ext = f.name.rsplit(".", 1)[-1].lower() if "." in f.name else ""
        item = {"name": f.name, "data": data, "sha": hashlib.sha256(data).hexdigest(), "text": "", "pages": []}
        try:
            if ext in IMG_MIME:
                Image.open(io.BytesIO(data)).verify()
                item.update(kind="image", mime=IMG_MIME[ext], pages=[data])
            elif ext == "pdf":
                return [], f"ملفات PDF غير مقبولة («{f.name}»). حوّل الصفحات إلى صور أو استخدم ملف Word (docx)."
            elif ext == "docx":
                item.update(kind="docx", mime=DOCX_MIME, text=_docx_text(data))
            else:
                return [], f"نوع الملف «{f.name}» غير مدعوم. المسموح: صور (png/jpg/webp) أو Word (docx)."
        except Exception as e:  # noqa: BLE001
            return [], f"تعذّرت قراءة الملف «{f.name}»: {e}"
        out.append(item)
    if total > MAX_TOTAL_MB * 1024 * 1024:
        return [], f"مجموع حجم الملفات أكبر من {MAX_TOTAL_MB}MB."
    return out, None


# ================================================================ تخزين الملفات
def _put(path, data, mime, download_name, public_image=True):
    if catalog.backend_name() == "supabase":
        try:
            link = file_store.upload_file(path, data, mime, download_name)
            return link.split("?", 1)[0] if public_image else link
        except Exception as e:  # noqa: BLE001
            st.warning(f"⚠️ تعذّر رفع أحد الملفات إلى التخزين: {e}")
            return ""
    p = LOCAL_FILES / path.replace("btec/", "", 1)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)
    return str(p)


def store_sources(items, folder):
    images, docs, n = [], [], 0
    for it in items:
        for page in it["pages"]:
            n += 1
            try:
                data, mime = imgs.prepare(Image.open(io.BytesIO(page)))
            except Exception:  # noqa: BLE001
                continue
            images.append(_put(f"btec/{folder}/src{n:02d}.{'png' if mime == 'image/png' else 'jpg'}", data, mime, f"page{n}"))
        if it["kind"] != "image":
            ext = "docx"
            docs.append({"name": it["name"], "url": _put(f"btec/{folder}/{it['sha'][:12]}.{ext}", it["data"],
                                                         it["mime"], it["name"], public_image=False)})
    return [u for u in images if u], docs


# ================================================================ خط معالجة رفع الواجب
def _norm(v):
    return re.sub(r"\s+", " ", str(v or "").translate(_AR_DIGITS).strip().lower())


def _codes(data):
    return sorted({re.sub(r"\s+", "", _norm(c.get("code"))).upper() for c in (data.get("criteria") or []) if c.get("code")})


def guide_key(data, grade, track_id, fallback_hash):
    unit, asg, codes = _norm(data.get("unit_number")), _norm(data.get("assignment_number")), _codes(data)
    if not unit and not codes:
        return f"g{grade}|t{track_id}|h{fallback_hash[:24]}"
    return f"g{grade}|t{track_id}|u{unit}|a{asg}|c{','.join(codes)}"


def _same(a, b):
    if not _norm(a.get("unit_number")) or _norm(a.get("unit_number")) != _norm(b.get("unit_number")):
        return False
    if _norm(a.get("assignment_number")) != _norm(b.get("assignment_number")):
        return False
    ca, cb = set(_codes(a)), set(_codes(b))
    return ca <= cb or cb <= ca


def default_title(d):
    unit = " ".join(x for x in (f"الوحدة {d.get('unit_number')}" if d.get("unit_number") else "", d.get("unit_title") or "") if x)
    asg = " ".join(x for x in (f"المهمة {d.get('assignment_number')}" if d.get("assignment_number") else "", d.get("assignment_title") or "") if x)
    return " — ".join(x for x in (unit, asg) if x) or "واجب BTEC"


def create_assignment(user, items, grade, track_id, replace_id=None, subject_id=None, notes=None):
    """يعيد {"status": "created"|"exists"|"unreadable", ...}. يُحتسب طلب واحد من الحصة اليومية."""
    auth_ui.require_quota_or_stop(user)
    data = btec_ai.extract_data(items)
    if not data.get("readable", False):
        return {"status": "unreadable", "message": (data.get("reason") or "الملفات غير واضحة أو لا تحوي واجب BTEC.")
                + " يرجى رفع نسخة أوضح (صورة أقرب وبإضاءة جيدة، أو ملف Word الأصلي)."}

    combined = hashlib.sha256("|".join(sorted(it["sha"] for it in items)).encode()).hexdigest()
    key = guide_key(data, grade, track_id, combined)
    if replace_id is None:
        ex = store.select("btec_assignments", {"guide_key": key})
        if not ex:
            for cand in store.assignments_for(grade, track_id, columns="id,title,data"):
                if _same(data, cand.get("data") or {}):
                    ex = [cand]
                    break
        if ex:
            return {"status": "exists", "assignment": ex[0]}

    md = btec_ai.student_guide(items, data)
    if not md:
        return {"status": "unreadable", "message": "لم يُنتج المساعد ردًا. حاول مرة أخرى."}
    if md.lstrip().startswith("<<UNREADABLE>>"):
        return {"status": "unreadable", "message": md.replace("<<UNREADABLE>>", "").strip()}

    md, plan = btec_ai.split_illustrations(md)
    folder = combined[:16]
    gen, last_err = [], ""
    for ill in plan:
        res, err = btec_ai.make_image(ill["prompt"])
        if res:
            raw, mime = res
            url = _put(f"btec/{folder}/gen{ill['n']}.{'png' if 'png' in mime else 'jpg'}", raw, mime, f"illustration{ill['n']}")
        else:
            url, last_err = "", err or last_err
        # الصورة الفاشلة تبقى في القائمة بلا رابط (مع وصفها) ليمكن إعادة توليدها لاحقًا دون إعادة إنشاء الدليل
        gen.append({"n": ill["n"], "url": url, "caption": ill["caption"], "prompt": ill["prompt"]})
        time.sleep(3)   # تخفيف الضغط على حدّ المعدّل لنموذج الصور
    skipped = sum(1 for g in gen if not g["url"])
    src_images, docs = store_sources(items, folder)

    row = {"guide_key": key, "grade": grade, "track_id": track_id, "title": default_title(data), "data": data,
           "student_guide": md, "teacher_explain": None, "images": gen, "source_images": src_images,
           "documents": docs, "created_by": user["id"], "published": True, "subject_id": subject_id,
           "teacher_notes": notes or None}
    if replace_id is not None:
        old = store.assignment(replace_id)
        row["title"] = (old or {}).get("title") or row["title"]
        row["teacher_notes"] = notes or (old or {}).get("teacher_notes")   # لا نمحو الملاحظات القديمة إن تُركت الخانة فارغة
        store.update("btec_assignments", {"id": replace_id}, {k: v for k, v in row.items() if k != "guide_key"} |
                     {"guide_key": key})
        saved = store.assignment(replace_id)
    else:
        saved = store.upsert("btec_assignments", [row], "guide_key")[0]
    return {"status": "created", "assignment": saved, "images_skipped": skipped, "image_error": last_err}


def regenerate_images(a):
    """يعيد توليد الصور الناقصة فقط. يعيد (عدد ما نجح، آخر خطأ)."""
    items = list(a.get("images") or [])
    folder = hashlib.sha256((a.get("guide_key") or str(a["id"])).encode()).hexdigest()[:16]
    done, last = 0, ""
    for it in items:
        if it.get("url") or not it.get("prompt"):
            continue
        res, err = btec_ai.make_image(it["prompt"])
        if res:
            raw, mime = res
            url = _put(f"btec/{folder}/gen{it['n']}_{int(time.time())}.{'png' if 'png' in mime else 'jpg'}", raw, mime, f"illustration{it['n']}")
            if url:
                it["url"] = url
                done += 1
                continue
        last = err or last
        time.sleep(3)
    store.update("btec_assignments", {"id": a["id"]}, {"images": items})
    return done, last


# ================================================================ وسائط الشرح: فيديو يوتيوب وملفات صوتية
_YT_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")


def parse_youtube(url):
    """معرّف فيديو يوتيوب من رابط watch / youtu.be / embed / shorts / live؛ None إن لم يكن رابطًا صالحًا."""
    url = (url or "").strip()
    m = re.match(r"^(?:https?://)?(?:www\.|m\.)?(?:youtube\.com|youtube-nocookie\.com)/(?:watch\?(?:.*&)?v=|embed/|shorts/|live/)([A-Za-z0-9_-]{11})", url) \
        or re.match(r"^(?:https?://)?youtu\.be/([A-Za-z0-9_-]{11})", url)
    return m.group(1) if m and _YT_ID.match(m.group(1)) else None


def _render_media_item(m, staff=False):
    title = m.get("title") or ("فيديو" if m.get("kind") == "youtube" else "ملف صوتي")
    st.markdown(f"**{'🎬' if m.get('kind') == 'youtube' else '🎧'} {title}**" +
                ("  ·  🔒 للمعلمين فقط" if staff and not m.get("student_visible", True) else ""))
    if m.get("kind") == "youtube":
        st.video(f"https://www.youtube.com/watch?v={m['id']}")
    elif m.get("url"):
        st.audio(m["url"])


def _show_media(a, staff=False):
    """عرض وسائط الشرح: الطالب يرى ما عُلِّم «يظهر للطلاب» فقط، والطاقم يرى الكل."""
    items = [m for m in (a.get("media") or []) if staff or m.get("student_visible", True)]
    if not items:
        return
    st.markdown("#### 🎬 شرح الواجب: فيديو وصوت")
    for m in items:
        _render_media_item(m, staff=staff)


def _media_manager(a):
    """إضافة/حذف وسائط الشرح (طاقم BTEC)."""
    aid = a["id"]
    media = [dict(m) for m in (a.get("media") or [])]
    st.markdown("#### 🎬 فيديو وصوت لشرح الواجب")
    if not media:
        st.caption("لا توجد وسائط بعد. أضف رابط يوتيوب أو ملفًا صوتيًا.")
    for k, m in enumerate(media):
        with st.container(border=True):
            _render_media_item(m)
            c1, c2 = st.columns([3, 1])
            vis = c1.checkbox("يظهر للطلاب", value=m.get("student_visible", True), key=f"btec_mvis_{aid}_{m['id_key']}")
            if vis != m.get("student_visible", True):
                m["student_visible"] = vis
                store.update("btec_assignments", {"id": aid}, {"media": media})
                st.rerun()
            if c2.button("🗑️ حذف", key=f"btec_mdel_{aid}_{m['id_key']}"):
                store.update("btec_assignments", {"id": aid}, {"media": [x for x in media if x["id_key"] != m["id_key"]]})
                st.rerun()

    t_yt, t_au = st.tabs(["➕ فيديو يوتيوب", "➕ ملف صوتي"])
    with t_yt:
        url = st.text_input("رابط الفيديو", key=f"btec_yt_url_{aid}", placeholder="https://www.youtube.com/watch?v=...")
        title = st.text_input("العنوان (اختياري)", key=f"btec_yt_title_{aid}")
        vis = st.checkbox("يظهر للطلاب", value=True, key=f"btec_yt_vis_{aid}")
        if st.button("➕ إضافة الفيديو", key=f"btec_yt_add_{aid}"):
            vid = parse_youtube(url)
            if not vid:
                st.error("الرابط غير صالح. استخدم رابط فيديو يوتيوب (watch أو youtu.be أو embed أو shorts).")
            else:
                media.append({"id_key": f"{int(time.time() * 1000)}", "kind": "youtube", "id": vid, "title": title.strip(),
                              "student_visible": vis})
                store.update("btec_assignments", {"id": aid}, {"media": media})
                st.rerun()
    with t_au:
        up = st.file_uploader("الملف الصوتي (mp3 / m4a / wav / ogg)", type=list(AUDIO_MIME), key=f"btec_au_up_{aid}")
        title = st.text_input("العنوان (اختياري)", key=f"btec_au_title_{aid}")
        vis = st.checkbox("يظهر للطلاب", value=True, key=f"btec_au_vis_{aid}")
        if st.button("➕ إضافة الملف الصوتي", key=f"btec_au_add_{aid}", disabled=up is None):
            data = up.getvalue()
            ext = up.name.rsplit(".", 1)[-1].lower()
            if len(data) > MAX_AUDIO_MB * 1024 * 1024:
                st.error(f"الملف أكبر من {MAX_AUDIO_MB}MB.")
            elif ext not in AUDIO_MIME:
                st.error("صيغة غير مدعومة.")
            else:
                folder = hashlib.sha256((a.get("guide_key") or str(aid)).encode()).hexdigest()[:16]
                key = f"{int(time.time() * 1000)}"
                url = _put(f"btec/{folder}/audio_{key}.{ext}", data, AUDIO_MIME[ext], up.name)
                if not url:
                    st.error("تعذّر رفع الملف إلى التخزين.")
                else:
                    media.append({"id_key": key, "kind": "audio", "url": url, "title": title.strip() or up.name,
                                  "student_visible": vis})
                    store.update("btec_assignments", {"id": aid}, {"media": media})
                    st.rerun()


# ================================================================ عرض الدليل
def show_guide(a, staff=False):
    d = a.get("data") or {}
    meta = [("المؤهل", d.get("qualification")), ("الوحدة", " — ".join(x for x in (d.get("unit_number"), d.get("unit_title")) if x)),
            ("المهمة", " — ".join(x for x in (d.get("assignment_number"), d.get("assignment_title")) if x)),
            ("تاريخ التسليم", d.get("deadline"))]
    meta = [(k, v) for k, v in meta if v]
    if meta:
        st.markdown("  \n".join(f"**{k}:** {v}" for k, v in meta))
    if staff:
        if a.get("source_images"):
            with st.expander(f"🖼️ صفحات الواجب الأصلية ({len(a['source_images'])})"):
                for u in a["source_images"]:
                    st.image(u, use_container_width=True)
        for doc in a.get("documents") or []:
            if str(doc.get("url", "")).startswith("http"):
                st.markdown(f"📎 [{doc['name']}]({doc['url']})")
    notes = (a.get("teacher_notes") or "").strip()
    if notes:
        st.warning("**📌 ملاحظات مهمة**\n\n" + notes.replace("\n", "  \n"))
    _show_media(a, staff=staff)
    st.divider()
    by_n = {i["n"]: i for i in (a.get("images") or [])}
    for chunk in re.split(r"(\[\[IMG:\d+\]\])", a.get("student_guide") or ""):
        m = re.fullmatch(r"\[\[IMG:(\d+)\]\]", chunk)
        if m:
            img = by_n.get(int(m.group(1)))
            if img and img.get("url"):
                st.image(img["url"], caption=img.get("caption"), use_container_width=True)
        elif chunk.strip():
            rich_text.show(chunk, "rtl")


def _criteria(a):
    return [c for c in ((a.get("data") or {}).get("criteria") or []) if c.get("code")]


# ================================================================ المباحث (تُضاف من المدير بلا أي كتاب)
def _subject_picker(track_id, key, published_only=False, grade=None, allow_all=False):
    """يعيد "all" | "none" | رقم المبحث. إن لم تُعرَّف مباحث للتخصص يعيد "all" دون عرض شيء."""
    subs = store.subjects_for(track_id)
    has_none = bool(store.assignments_for(grade, track_id, published_only, columns="id", subject="none")) if grade else False
    if not subs:
        return "all"
    opts = ([("all", "كل المباحث")] if allow_all else []) + [(s["id"], s["name"]) for s in subs] + ([("none", "واجبات بلا مبحث")] if has_none else [])
    pick = st.selectbox("المبحث", [o[0] for o in opts], key=key, format_func=lambda v: dict(opts)[v])
    return pick


def render_subjects_admin(tracks):
    st.subheader("📘 مباحث BTEC")
    st.caption("أضف أسماء المباحث لكل صف وتخصص مباشرة، ولا حاجة لرفع أي كتاب. تُربط الواجبات بالمبحث عند رفعها، ويختار الطالب مبحثه ثم واجبه.")
    bt = btec_tracks(tracks)
    if not bt:
        st.warning("لا توجد تخصصات BTEC. شغّل supabase_btec.sql أولًا.")
        return
    tid = st.selectbox("الصف / التخصص", [t["id"] for t in bt], key="btec_subj_track",
                       format_func=lambda t: scope_label(tracks, next(x["grade"] for x in bt if x["id"] == t), t))
    track = next(t for t in bt if t["id"] == tid)

    cur = store.subjects_for(tid, active_only=False)
    for sj in cur:
        c1, c2, c3 = st.columns([5, 2, 1])
        new_name = c1.text_input("اسم المبحث", value=sj["name"], key=f"btec_sj_n_{sj['id']}", label_visibility="collapsed")
        active = c2.checkbox("فعّال", value=sj["active"], key=f"btec_sj_a_{sj['id']}")
        if c3.button("💾", key=f"btec_sj_s_{sj['id']}", help="حفظ التعديل"):
            store.update("btec_subjects", {"id": sj["id"]}, {"name": new_name.strip() or sj["name"], "active": active})
            st.rerun()
        with st.expander(f"🗑️ حذف «{sj['name']}»", expanded=False):
            n = len(store.select("btec_assignments", {"subject_id": sj["id"]}, columns="id"))
            st.caption(f"سيُحذف المبحث فقط؛ الواجبات المرتبطة به ({n}) تبقى وتظهر ضمن «واجبات بلا مبحث».")
            if st.checkbox("أؤكد الحذف", key=f"btec_sj_c_{sj['id']}") and st.button("حذف", key=f"btec_sj_d_{sj['id']}"):
                store.delete("btec_subjects", {"id": sj["id"]})
                st.rerun()
    if not cur:
        st.info("لا توجد مباحث لهذا الصف/التخصص بعد.")

    st.markdown("**إضافة مباحث** (اسم في كل سطر)")
    names = st.text_area("أسماء المباحث", key=f"btec_sj_new_{tid}", height=110, label_visibility="collapsed")
    others = [t for t in bt if t["name"] == track["name"] and t["id"] != tid]
    also = st.checkbox("أضفها أيضًا لنفس التخصص في باقي الصفوف (" + "، ".join(GRADES[t["grade"] - 1] for t in others) + ")",
                       key=f"btec_sj_also_{tid}") if others else False
    if st.button("➕ إضافة", type="primary", key=f"btec_sj_add_{tid}"):
        lines = [x.strip() for x in names.splitlines() if x.strip()]
        if not lines:
            st.error("اكتب اسم مبحث واحد على الأقل.")
        else:
            for t in [track] + (others if also else []):
                exist = {s["name"] for s in store.subjects_for(t["id"], active_only=False)}
                base = len(exist)
                rows = [{"grade": t["grade"], "track_id": t["id"], "name": n, "sort_order": base + i, "active": True}
                        for i, n in enumerate(dict.fromkeys(lines)) if n not in exist]
                store.upsert("btec_subjects", rows, "track_id,name")
            st.success("تمت الإضافة.")
            st.rerun()


# ================================================================ الطالب
def render_student(user, tracks):
    grade, track_id = user["grade"], user.get("track_id")
    st.markdown("### 🎓 مساعد BTEC")
    st.markdown(f"**الصف:** {scope_label(tracks, grade, track_id)}")
    subj = _subject_picker(track_id, key="btec_stu_subj", published_only=True, grade=grade)
    rows = store.assignments_for(grade, track_id, published_only=True, columns="id,title", subject=subj)
    if not rows:
        st.info("لا توجد واجبات منشورة لهذا المبحث بعد. سيظهر هنا كل واجب بمجرد أن يرفعه المشرف.")
        return
    pick = st.selectbox("اختر الواجب", [r["id"] for r in rows], format_func=lambda i: next(r["title"] for r in rows if r["id"] == i))
    a = store.assignment(pick)
    t_guide, t_eval = st.tabs(["📘 دليل الواجب", "✅ تقييم الواجب"])
    with t_guide:
        show_guide(a)
    with t_eval:
        _student_eval(user, a)


STUDENT_VERDICT = {"met": "✅ منجز", "partial": "🟡 جزئي", "not_met": "❌ غير منجز", "not_assessable": "⚪ غير واضح"}


def _student_eval(user, a):
    """الطالب يرفع واجبه فيُقارَن بمعايير هذا الواجب ويُعطى تقريرًا بما أُنجز وما ينقص. لا يُحفظ شيء."""
    crit = _criteria(a)
    if not crit:
        st.info("لم تُستخرج معايير لهذا الواجب، لذا لا يمكن تقييمه هنا.")
        return
    st.caption("ارفع واجبك (صور/Word) وسيقارنه المساعد بمعايير هذا الواجب ويخبرك بما أنجزته وما ينقصك قبل التسليم. "
               "لا تُحفظ ملفاتك ولا التقرير في النظام؛ نزّل التقرير إن أردت الاحتفاظ به. التقييم استرشادي وليس درجة رسمية، "
               "والتقييم النهائي لمعلمك. يُحتسب طلب واحد من حصتك اليومية.")
    aid = a["id"]
    ups = st.file_uploader("ملفات واجبك", type=["png", "jpg", "jpeg", "webp", "docx"],
                           accept_multiple_files=True, key=f"btec_se_up_{aid}")
    rkey = f"btec_se_report_{aid}"
    if st.button("✅ قيّم واجبي", type="primary", key=f"btec_se_run_{aid}"):
        items, err = read_uploads(ups)
        if err:
            st.error(err)
        else:
            auth_ui.require_quota_or_stop(user)
            with st.spinner("جارٍ مقارنة واجبك بالمعايير..."):
                try:
                    res = btec_ai.evaluate_for_student(a["data"], items, a.get("teacher_notes"))
                except Exception as e:  # noqa: BLE001
                    res = None
                    st.error(f"حدث خطأ: {e}")
            if res and res.get("criteria"):
                st.session_state[rkey] = {"assignment_label": a["title"], "student_label": user.get("name", ""), "result": res,
                                          "date": dt.datetime.now().strftime("%Y-%m-%d %H:%M")}
            elif res is not None:
                st.error("تعذّر فهم نتيجة التقييم. حاول مرة أخرى.")
    rep = st.session_state.get(rkey)
    if not rep:
        return
    res = rep["result"]
    st.divider()
    codes = {c["code"] for c in crit}
    rows = [c for c in res["criteria"] if c.get("code") in codes]
    met = sum(1 for c in rows if c.get("verdict") == "met")
    st.markdown("#### 📄 تقرير تقييم واجبك")
    st.metric("المعايير المنجزة", f"{met} من {len(crit)}")
    if res.get("summary"):
        st.info(res["summary"])
    _show_ai_usage(res, student=True)
    st.dataframe(pd.DataFrame([{"المعيار": c.get("code"), "الحالة": STUDENT_VERDICT.get(c.get("verdict"), "—"),
                                "شو لقيت بشغلك": c.get("evidence_found", ""), "شو ناقص": c.get("missing", ""),
                                "نصيحة": c.get("feedback", "")} for c in rows]), hide_index=True, use_container_width=True)
    if res.get("next_steps"):
        st.markdown("**الخطوات اللي بعدها:**")
        for i, s_ in enumerate(res["next_steps"], 1):
            st.markdown(f"{i}. {s_}")
    try:
        st.download_button("⬇️ تنزيل التقرير (Word)", _report_docx(rep), file_name="btec_assignment_review.docx",
                           mime=DOCX_MIME, key=f"btec_se_dl_{aid}")
    except Exception as e:  # noqa: BLE001
        st.caption(f"تعذّر إنشاء ملف Word: {e}")


# ================================================================ طاقم BTEC (واجهة المدير)
def render_staff_admin(tracks):
    st.subheader("🎓 إدارة طاقم BTEC")
    bt = btec_tracks(tracks)
    if not bt:
        st.warning("لا توجد تخصصات BTEC. شغّل supabase_btec.sql أو أضفها من «🎓 التخصصات» (يجب أن يحوي الاسم كلمة BTEC).")
        return
    users = [u for u in acc.list_users(status="active") if u["role"] in ("teacher", "supervisor")]
    if not users:
        st.info("لا توجد حسابات معلمين/مشرفين فعّالة. اعتمد الحسابات أولًا من «طلبات قيد المراجعة».")
        return
    uname = {u["id"]: u["name"] for u in users}
    tlabel = {t["id"]: scope_label(tracks, t["grade"], t["id"]) for t in bt}

    st.markdown("**تعيين / تعديل صلاحيات مستخدم**")
    uid = st.selectbox("المستخدم", list(uname), format_func=lambda i: f"{uname[i]} — {acc.ROLE_AR.get(next(u['role'] for u in users if u['id'] == i))}")
    cur = store.select("btec_staff", {"user_id": uid})
    role = st.radio("دوره في BTEC", ["supervisor", "teacher"], horizontal=True,
                    index=0 if any(r["role"] == "supervisor" for r in cur) else 1,
                    format_func=lambda r: "مشرف BTEC (يرفع الواجبات ويديرها)" if r == "supervisor" else "معلم BTEC")
    chosen = st.multiselect("الصفوف/التخصصات", list(tlabel), default=[r["track_id"] for r in cur if r["track_id"] in tlabel],
                            format_func=lambda i: tlabel[i])
    if st.button("💾 حفظ", type="primary", key="btec_staff_save"):
        store.delete("btec_staff", {"user_id": uid})
        store.upsert("btec_staff", [{"user_id": uid, "track_id": t, "role": role} for t in chosen], "user_id,track_id")
        st.success("تم الحفظ.")
        st.rerun()

    st.divider()
    allrows = store.select("btec_staff")
    if allrows:
        st.markdown("**الطاقم الحالي**")
        st.dataframe(pd.DataFrame([{"المستخدم": uname.get(r["user_id"], r["user_id"]),
                                    "الدور": "مشرف" if r["role"] == "supervisor" else "معلم",
                                    "الصف/التخصص": tlabel.get(r["track_id"], r["track_id"])} for r in allrows]),
                     hide_index=True, use_container_width=True)


# ================================================================ واجهة المشرف / المعلم / المدير
def _pick_assignment(grade, track_id, key, published_only=False, subj="all"):
    rows = store.assignments_for(grade, track_id, published_only=published_only, columns="id,title,published", subject=subj)
    if not rows:
        st.info("لا توجد واجبات لهذا الصف/التخصص بعد.")
        return None
    aid = st.selectbox("الواجب", [r["id"] for r in rows], key=key,
                       format_func=lambda i: next(r["title"] + ("" if r["published"] else " (مخفي)") for r in rows if r["id"] == i))
    return store.assignment(aid)


def render_staff(user, tracks):
    """للمدير، ولمن له صلاحية BTEC (مشرف/معلم)."""
    is_admin = user["role"] == "admin"
    bt = {t["id"]: t for t in btec_tracks(tracks)}
    rows = store.staff_rows(user["id"]) if not is_admin else [{"track_id": t, "role": "supervisor"} for t in bt]
    rows = [r for r in rows if r["track_id"] in bt]
    if not rows:
        st.info("لم تُسند إليك أي صفوف/تخصصات BTEC بعد. يرجى التواصل مع الإدارة.")
        return
    role_of = {r["track_id"]: r["role"] for r in rows}
    sel = st.selectbox("الصف / التخصص", [r["track_id"] for r in rows], key="btec_scope",
                       format_func=lambda t: scope_label(tracks, bt[t]["grade"], t) + ("  •  مشرف" if role_of[t] == "supervisor" and not is_admin else ""))
    grade, is_sup = bt[sel]["grade"], role_of[sel] == "supervisor"

    subj = _subject_picker(sel, key=f"btec_staff_subj_{sel}", grade=grade, allow_all=True)

    names = (["📤 رفع واجب"] if is_sup else []) + ["📚 الواجبات", "🧑‍🏫 دليل شرح الواجب", "🔎 فحص الأدلة"]
    tabs = dict(zip(names, st.tabs(names)))

    if is_sup:
        with tabs["📤 رفع واجب"]:
            _tab_upload(user, grade, sel, subj)
    with tabs["📚 الواجبات"]:
        _tab_assignments(grade, sel, is_sup, subj)
    with tabs["🧑‍🏫 دليل شرح الواجب"]:
        _tab_teacher_explain(user, grade, sel, subj)
    with tabs["🔎 فحص الأدلة"]:
        _tab_evidence(user, grade, sel, subj)


def _tab_upload(user, grade, track_id, subj="all"):
    st.caption("ارفع صور الواجب أو ملفه (صور/Word). سيُستخرج الواجب ومعاييره ويُولَّد دليل الطالب بنصه وصوره، ثم يُخزَّن ليختاره الطلاب. "
               "يُحتسب طلب واحد من حصتك اليومية.")
    subs = store.subjects_for(track_id)
    subject_id = None
    if subs:
        ids = [s["id"] for s in subs]
        subject_id = st.selectbox("المبحث", ids, key=f"btec_up_subj_{track_id}",
                                  index=ids.index(subj) if subj in ids else 0,
                                  format_func=lambda i: next(s["name"] for s in subs if s["id"] == i))
    else:
        st.info("لم تُعرَّف مباحث لهذا الصف/التخصص؛ سيُحفظ الواجب بلا مبحث. يضيف المدير المباحث من «📘 مباحث BTEC».")
    ups = st.file_uploader("ملفات الواجب", type=["png", "jpg", "jpeg", "webp", "docx"],
                           accept_multiple_files=True, key="btec_up")
    notes = st.text_area("📌 ملاحظات مهمة (اختياري)", key=f"btec_up_notes_{track_id}", height=110,
                         placeholder="مثال: التسليم عبر المنصة فقط، يلزم إرفاق صور من العمل الميداني، موعد العرض يوم الأحد...",
                         help="تظهر للطالب في إطار «ملاحظات مهمة» مع دليل تنفيذ الواجب.")
    replace_id = st.session_state.pop("btec_replace", None)
    if st.button("🚀 حلّل الواجب وأنشئ الدليل", type="primary", key="btec_up_run") or replace_id:
        items, err = read_uploads(ups)
        if err:
            st.error(err)
            return
        with st.spinner("جارٍ تحليل الواجب وإعداد الدليل والصور... قد يستغرق ذلك عدة دقائق."):
            try:
                res = create_assignment(user, items, grade, track_id, replace_id=replace_id, subject_id=subject_id,
                                    notes=notes.strip())
            except Exception as e:  # noqa: BLE001
                st.error(f"حدث خطأ أثناء المعالجة: {e}")
                return
        if res["status"] == "unreadable":
            st.warning(f"⚠️ {res['message']}")
        elif res["status"] == "exists":
            ex = res["assignment"]
            st.warning(f"هذا الواجب مرفوع مسبقًا باسم «{ex['title']}». لن يُعاد توليده. "
                       "إن أردت استبدال دليله بنسخة جديدة اضغط الزر أدناه.")
            if st.button("♻️ استبدال الدليل الحالي", key="btec_do_replace"):
                st.session_state["btec_replace"] = ex["id"]
                st.rerun()
        else:
            st.success("✅ تم إنشاء الدليل وحفظه، وهو متاح الآن للطلاب.")
            if res.get("images_skipped"):
                st.warning(f"تعذّر توليد {res['images_skipped']} من الصور التوضيحية. السبب: {res.get('image_error') or 'غير معروف'}\n\n"
                           "يمكنك إعادة المحاولة من «📚 الواجبات» ← «⚙️ إدارة هذا الواجب» ← «🖼️ إعادة توليد الصور الناقصة».")
            show_guide(res["assignment"], staff=True)


def _headings(md):
    """[(رقم السطر, نص العنوان)] لعناوين Markdown في الدليل."""
    return [(n, ln.lstrip("# ").strip()) for n, ln in enumerate(md.split("\n")) if re.match(r"^#{1,3}\s", ln)]


def _insert_marker(md, n, where):
    """يضيف [[IMG:n]] في نهاية الدليل (where=None) أو بداية الدليل ("top") أو بعد سطر عنوان محدد (رقم السطر)."""
    mk = f"\n[[IMG:{n}]]\n"
    lines = md.split("\n")
    if where is None:
        return md.rstrip() + "\n" + mk
    if where == "top":
        return mk.lstrip() + "\n" + md
    lines.insert(int(where) + 1, mk)
    return "\n".join(lines)


def _edit_guide(a):
    """تحرير نص دليل الطالب المحفوظ وإدارة صوره (مشرف BTEC/المدير)."""
    aid = a["id"]
    tkey = f"btec_ed_txt_{aid}"
    pend = st.session_state.pop(f"btec_ed_pending_{aid}", None)
    if pend is not None:                 # نتيجة عملية على الصور: نحدّث النص الظاهر قبل إنشاء الحقل
        st.session_state[tkey] = pend
    elif tkey not in st.session_state:
        st.session_state[tkey] = a["student_guide"]
    st.caption("عدّل النص كما تريد (Markdown). العلامة `[[IMG:رقم]]` هي مكان الصورة في الدليل؛ احتفظ بها إن أردت بقاء الصورة، وانقلها لتغيير مكانها.")
    md = st.text_area("نص دليل الطالب", height=480, key=tkey)
    images = [dict(i) for i in (a.get("images") or [])]

    st.markdown("**🖼️ صور الدليل**")
    for im in images:
        c1, c2, c3 = st.columns([2, 4, 1])
        if im.get("url"):
            c1.image(im["url"], use_container_width=True)
        else:
            c1.caption("⚠️ ناقصة")
        im["caption"] = c2.text_input(f"التعليق — صورة {im['n']}  (`[[IMG:{im['n']}]]`)", value=im.get("caption") or "",
                                      key=f"btec_cap_{aid}_{im['n']}")
        if c3.button("🗑️", key=f"btec_imdel_{aid}_{im['n']}", help="حذف الصورة من الدليل"):
            rest = [i for i in images if i["n"] != im["n"]]
            new_md = re.sub(rf"\n?\[\[IMG:{im['n']}\]\]\n?", "\n", md)
            store.update("btec_assignments", {"id": aid}, {"student_guide": new_md, "images": rest,
                                                           "updated_at": dt.datetime.utcnow().isoformat()})
            st.session_state[f"btec_ed_pending_{aid}"] = new_md
            st.rerun()

    with st.expander("➕ إضافة صورة إلى الدليل"):
        up = st.file_uploader("الصورة", type=["png", "jpg", "jpeg", "webp"], key=f"btec_imup_{aid}")
        cap = st.text_input("تعليق الصورة (اختياري)", key=f"btec_imcap_{aid}")
        heads = _headings(md)
        opts = [None, "top"] + [h[0] for h in heads]
        lab = {None: "في نهاية الدليل", "top": "في بداية الدليل", **{h[0]: f"بعد العنوان: {h[1]}" for h in heads}}
        where = st.selectbox("مكان الصورة", opts, format_func=lambda v: lab[v], key=f"btec_imwhere_{aid}")
        if st.button("➕ إضافة", key=f"btec_imadd_{aid}", disabled=up is None):
            try:
                data, mime = imgs.prepare(Image.open(io.BytesIO(up.getvalue())))
            except Exception as e:  # noqa: BLE001
                st.error(f"تعذّرت قراءة الصورة: {e}")
                return
            n = max([i["n"] for i in images] or [0]) + 1
            folder = hashlib.sha256((a.get("guide_key") or str(aid)).encode()).hexdigest()[:16]
            url = _put(f"btec/{folder}/add{n}_{int(time.time())}.{'png' if mime == 'image/png' else 'jpg'}", data, mime, f"image{n}")
            if not url:
                st.error("تعذّر رفع الصورة إلى التخزين.")
                return
            images.append({"n": n, "url": url, "caption": cap.strip(), "prompt": ""})
            new_md = _insert_marker(md, n, where)
            store.update("btec_assignments", {"id": aid}, {"student_guide": new_md, "images": images,
                                                           "updated_at": dt.datetime.utcnow().isoformat()})
            st.session_state[f"btec_ed_pending_{aid}"] = new_md
            st.rerun()
        st.caption("تُحفظ تعديلات النص الحالية مع إضافة الصورة أو حذفها.")

    c1, c2 = st.columns(2)
    if c1.button("💾 حفظ التعديلات", type="primary", key=f"btec_edsave_{aid}"):
        store.update("btec_assignments", {"id": aid}, {"student_guide": md, "images": images,
                                                       "updated_at": dt.datetime.utcnow().isoformat()})
        st.success("تم حفظ الدليل. سيراه الطلاب بهذا الشكل.")
        st.rerun()
    if c2.checkbox("معاينة", key=f"btec_edprev_{aid}"):
        show_guide({**a, "student_guide": md, "images": images})


def _tab_assignments(grade, track_id, is_sup, subj="all"):
    a = _pick_assignment(grade, track_id, "btec_view_pick", subj=subj)
    if not a:
        return
    if is_sup:
        with st.expander("⚙️ إدارة هذا الواجب"):
            title = st.text_input("عنوان الواجب (يظهر للطلاب)", value=a["title"], key=f"btec_t_{a['id']}")
            pub = st.checkbox("منشور للطلاب", value=a["published"], key=f"btec_p_{a['id']}")
            new_notes = st.text_area("📌 ملاحظات مهمة (تظهر للطالب مع الدليل)", value=a.get("teacher_notes") or "",
                                     key=f"btec_n_{a['id']}", height=110)
            subs = store.subjects_for(track_id)
            new_subj = a.get("subject_id")
            if subs:
                opts = [None] + [s["id"] for s in subs]
                new_subj = st.selectbox("المبحث", opts, index=opts.index(a.get("subject_id")) if a.get("subject_id") in opts else 0,
                                        key=f"btec_sj_{a['id']}",
                                        format_func=lambda i: "بلا مبحث" if i is None else next(s["name"] for s in subs if s["id"] == i))
            c1, c2 = st.columns(2)
            if c1.button("💾 حفظ التعديلات", key=f"btec_s_{a['id']}"):
                store.update("btec_assignments", {"id": a["id"]}, {"title": title.strip() or a["title"], "published": pub, "subject_id": new_subj,
                                                                  "teacher_notes": new_notes.strip() or None})
                st.rerun()
            missing = [i for i in (a.get("images") or []) if not i.get("url") and i.get("prompt")]
            if missing:
                st.caption(f"صور توضيحية ناقصة: {len(missing)}")
                if st.button("🖼️ إعادة توليد الصور الناقصة", key=f"btec_regen_{a['id']}"):
                    with st.spinner("جارٍ توليد الصور..."):
                        done, err = regenerate_images(a)
                    (st.success if done else st.error)(f"تم توليد {done} من {len(missing)}." + (f" آخر خطأ: {err}" if err else ""))
                    if done:
                        st.rerun()
            sure = c2.checkbox("أؤكد الحذف النهائي (مع متابعة التقدم والفحوص)", key=f"btec_d_{a['id']}")
            if c2.button("🗑️ حذف الواجب", disabled=not sure, key=f"btec_del_{a['id']}"):
                store.delete("btec_assignments", {"id": a["id"]})
                st.rerun()
    if is_sup:
        with st.expander("✏️ تعديل دليل الطالب وصوره"):
            _edit_guide(a)
    show_guide(a, staff=True)


def _tab_teacher_explain(user, grade, track_id, subj="all"):
    a = _pick_assignment(grade, track_id, "btec_exp_pick", subj=subj)
    if not a:
        return
    _media_manager(a)
    st.divider()
    if not a.get("teacher_explain"):
        st.info("لم يُولَّد دليل شرح لهذا الواجب بعد. يُولَّد مرة واحدة ثم يُخزَّن لكل المعلمين.")
        if st.button("✨ إنشاء دليل شرح الواجب", key=f"btec_gen_exp_{a['id']}"):
            auth_ui.require_quota_or_stop(user)
            with st.spinner("جارٍ إعداد دليل الشرح..."):
                try:
                    txt = btec_ai.teacher_explain(a["data"], a["student_guide"], a.get("teacher_notes"))
                except Exception as e:  # noqa: BLE001
                    st.error(f"حدث خطأ: {e}")
                    return
            if txt:
                store.update("btec_assignments", {"id": a["id"]}, {"teacher_explain": txt})
                st.rerun()
        return
    rich_text.show(a["teacher_explain"], "rtl")


BANDS = {"low": ("🟢", "منخفض"), "medium": ("🟡", "متوسط"), "high": ("🔴", "مرتفع"), "na": ("⚪", "غير قابل للتقدير")}
CONF = {"low": "منخفضة", "medium": "متوسطة", "high": "عالية"}
AI_NOTE_TEACHER = ("تقدير تقريبي من نموذج لغوي وليس أداة كشف مثبتة؛ قد يخطئ، خصوصًا مع الكتابة الرسمية أو التقنية أو لغير الناطقين بالعربية/الإنجليزية، "
                   "ولا يصلح وحده دليلًا على مخالفة. استخدمه لفتح حوار مع الطالب (مناقشته في عمله وخطوات إنجازه) وللتحقق من أثر العملية.")
AI_NOTE_STUDENT = ("هاد مؤشر تقريبي وممكن يغلط، ومش حكم عليك. المهم تكتب بأسلوبك وبمعلومات من مشروعك، "
                   "وتوثّق خطوات شغلك بصور وقياسات من تنفيذك إنت.")


def _ai_info(res):
    """(كائن ai_usage, النسبة المقرّبة أو None, الفئة low|medium|high|na) — الفئة تُشتق من النسبة لتفادي التناقض."""
    u = res.get("ai_usage") or {}
    try:
        pct = max(0, min(100, round(float(u.get("estimated_percent")))))
    except (TypeError, ValueError):
        pct = None
    if u.get("level") == "not_assessable" or pct is None:
        return u, None, "na"
    return u, pct, ("low" if pct < 25 else "medium" if pct <= 60 else "high")


def _show_ai_usage(res, student=False):
    if not res.get("ai_usage"):
        return
    u, pct, band = _ai_info(res)
    emoji, label = BANDS[band]
    st.markdown("##### 🤖 مؤشر استخدام الذكاء الاصطناعي")
    c1, c2, c3 = st.columns(3)
    c1.metric("النسبة التقديرية", f"{pct}%" if pct is not None else "—")
    c2.metric("المستوى", f"{emoji} {label}")
    c3.metric("الثقة بالتقدير", CONF.get(u.get("confidence"), "—"))
    if band == "na":
        st.caption("لا يمكن تقدير ذلك لهذا الملف (نص قليل أو الشغل صور/رسومات). " + (u.get("limitations") or ""))
    else:
        if u.get("indicators"):
            with st.expander("ما الذي بنى عليه التقدير؟"):
                st.markdown("**مؤشرات ترجّح الكتابة بالذكاء الاصطناعي:**")
                for x in u["indicators"]:
                    st.markdown(f"- {x}")
                if u.get("human_signals"):
                    st.markdown("**ما يرجّح أنه من عمل الطالب:**")
                    for x in u["human_signals"]:
                        st.markdown(f"- {x}")
                if u.get("limitations"):
                    st.caption(u["limitations"])
    st.caption("⚠️ " + (AI_NOTE_STUDENT if student else AI_NOTE_TEACHER))


def _rtl(par):
    from docx.oxml import OxmlElement
    pPr = par._p.get_or_add_pPr()
    pPr.append(OxmlElement("w:bidi"))
    for r in par.runs:
        r._r.get_or_add_rPr().append(OxmlElement("w:rtl"))


def _report_docx(rep):
    """تقرير فحص الأدلة كملف Word (يمين-إلى-يسار)."""
    from docx import Document
    from docx.oxml import OxmlElement
    doc = Document()
    res = rep["result"]
    for text, lvl in ((f"تقرير فحص أدلة — {rep['assignment_label']}", 1),):
        h = doc.add_heading(text, level=lvl)
        _rtl(h)
    for line in (f"الطالب/التسليم: {rep['student_label'] or '—'}", f"التاريخ: {rep['date']}",
                 "تنبيه: هذا تقييم استشاري بالذكاء الاصطناعي؛ القرار النهائي لمعلم BTEC."):
        _rtl(doc.add_paragraph(line))
    if res.get("summary"):
        _rtl(doc.add_heading("الملخص", level=2))
        _rtl(doc.add_paragraph(res["summary"]))
    if res.get("ai_usage"):
        u, pct, band = _ai_info(res)
        _rtl(doc.add_heading("مؤشر استخدام الذكاء الاصطناعي", level=2))
        _rtl(doc.add_paragraph(f"النسبة التقديرية: {str(pct) + '%' if pct is not None else 'غير قابلة للتقدير'} — المستوى: {BANDS[band][1]} — "
                               f"الثقة: {CONF.get(u.get('confidence'), '—')}"))
        for x in u.get("indicators") or []:
            _rtl(doc.add_paragraph(str(x), style="List Bullet"))
        _rtl(doc.add_paragraph("تنبيه: " + AI_NOTE_TEACHER))
    tbl = doc.add_table(rows=1, cols=5)
    tbl.style = "Table Grid"
    tbl._tbl.tblPr.append(OxmlElement("w:bidiVisual"))
    for c, t in zip(tbl.rows[0].cells, ["المعيار", "النتيجة", "ما وُجد", "الناقص", "ملاحظة للطالب"]):
        c.text = t
    for c in res.get("criteria", []):
        cells = tbl.add_row().cells
        for cell, t in zip(cells, [c.get("code", ""), VERDICT.get(c.get("verdict"), ("—", None))[0],
                                   c.get("evidence_found", ""), c.get("missing", ""), c.get("feedback", "")]):
            cell.text = str(t)
    for row in tbl.rows:
        for cell in row.cells:
            for p in cell.paragraphs:
                _rtl(p)
    if res.get("next_steps"):
        _rtl(doc.add_heading("الخطوات التالية", level=2))
        for c in res["next_steps"]:
            _rtl(doc.add_paragraph(str(c), style="List Number"))
    if res.get("concerns"):
        _rtl(doc.add_heading("ملاحظات تستدعي انتباه المعلم", level=2))
        for c in res["concerns"]:
            _rtl(doc.add_paragraph(str(c), style="List Bullet"))
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _show_report(rep):
    res = rep["result"]
    st.markdown(f"#### 📄 تقرير فحص الأدلة — {rep['assignment_label']}")
    st.caption(f"الطالب/التسليم: {rep['student_label'] or '—'}  |  {rep['date']}  |  تقييم استشاري؛ القرار النهائي للمعلم.")
    crit = res.get("criteria") or []
    met = sum(1 for c in crit if c.get("verdict") == "met")
    if crit:
        st.metric("المعايير المحقَّقة", f"{met} من {len(crit)}")
    if res.get("summary"):
        st.info(res["summary"])
    _show_ai_usage(res)
    st.dataframe(pd.DataFrame([{"المعيار": c.get("code"), "النتيجة": VERDICT.get(c.get("verdict"), ("—", None))[0],
                                "ما وُجد": c.get("evidence_found", ""), "الناقص": c.get("missing", ""),
                                "ملاحظة للطالب": c.get("feedback", "")} for c in crit]),
                 hide_index=True, use_container_width=True)
    for c in res.get("concerns") or []:
        st.warning(f"⚠️ {c}")
    try:
        st.download_button("⬇️ تنزيل التقرير (Word)", _report_docx(rep), file_name="btec_evidence_report.docx",
                           mime=DOCX_MIME, key=f"btec_ev_dl_{abs(hash(rep['date'] + rep['student_label'] + rep['assignment_label']))}")
    except Exception as e:  # noqa: BLE001
        st.caption(f"تعذّر إنشاء ملف Word: {e}")


def _tab_evidence(user, grade, track_id, subj="all"):
    st.caption("ارفع ملف الواجب الذي سلّمه الطالب (صور/Word). سيتعرّف النظام على الواجب ويفحص الأدلة مقابل معاييره ويُعدّ تقريرًا. "
               "لا يلزم أن يكون الطالب مسجَّلًا، ولا يُحفظ شيء في النظام: نزّل التقرير إن أردت الاحتفاظ به. "
               "يُحتسب طلب واحد من حصتك اليومية.")
    ups = st.file_uploader("ملف الواجب المسلَّم", type=["png", "jpg", "jpeg", "webp", "docx"],
                           accept_multiple_files=True, key="btec_ev_up")
    label = st.text_input("اسم الطالب (اختياري — يظهر في التقرير)", key="btec_ev_label")
    manual = None
    if st.session_state.get("btec_ev_need_manual"):
        st.warning("لم أتمكن من تحديد الواجب ومعاييره من الملف المرفوع. اختر الواجب من القائمة ثم اضغط «افحص» مرة أخرى.")
        manual = _pick_assignment(grade, track_id, "btec_ev_pick", subj="all")

    if st.button("🔎 افحص الواجب", type="primary", key="btec_ev_run"):
        items, err = read_uploads(ups)
        if err:
            st.error(err)
        else:
            auth_ui.require_quota_or_stop(user)
            need_manual, res, alabel = False, None, ""
            with st.spinner("جارٍ تحديد الواجب وفحص الأدلة مقابل المعايير..."):
                try:
                    data = notes = None
                    if manual and _criteria(manual):
                        data, notes, alabel = manual["data"], manual.get("teacher_notes"), manual["title"]
                    else:
                        sub = btec_ai.extract_data(items)
                        if not sub.get("readable", False):
                            st.error((sub.get("reason") or "الملف غير واضح") + " — ارفع نسخة أوضح.")
                        else:
                            cand = next((c for c in store.assignments_for(grade, track_id)
                                         if _same(sub, c.get("data") or {}) and _criteria(c)), None)
                            if cand:
                                data, notes, alabel = cand["data"], cand.get("teacher_notes"), cand["title"]
                            elif sub.get("criteria"):
                                data, alabel = sub, default_title(sub)
                            else:
                                need_manual = True
                    if data:
                        res = btec_ai.review_evidence(data, items, label.strip(), notes)
                except Exception as e:  # noqa: BLE001
                    st.error(f"حدث خطأ: {e}")
            if need_manual:
                st.session_state["btec_ev_need_manual"] = True
                st.rerun()
            if res and res.get("criteria"):
                st.session_state.pop("btec_ev_need_manual", None)
                st.session_state["btec_ev_report"] = {"assignment_label": alabel, "student_label": label.strip(), "result": res,
                                                      "date": dt.datetime.now().strftime("%Y-%m-%d %H:%M")}
            elif res is not None:
                st.error("تعذّر فهم نتيجة الفحص. حاول مرة أخرى.")

    rep = st.session_state.get("btec_ev_report")
    if rep:
        st.divider()
        _show_report(rep)
