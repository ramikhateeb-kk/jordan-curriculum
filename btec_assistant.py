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
        for i, page in enumerate(pdf):
            if i >= MAX_PDF_PAGES:
                break
            pages.append(page.get_pixmap(matrix=fitz.Matrix(1.4, 1.4)).tobytes("png"))
    return pages


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
                item.update(kind="pdf", mime="application/pdf", pages=_pdf_pages_png(data))
            elif ext == "docx":
                item.update(kind="docx", mime=DOCX_MIME, text=_docx_text(data))
            else:
                return [], f"نوع الملف «{f.name}» غير مدعوم. المسموح: صور، PDF، Word (docx)."
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
            ext = "pdf" if it["kind"] == "pdf" else "docx"
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
                + " يرجى رفع نسخة أوضح (صورة أقرب وبإضاءة جيدة، أو ملف PDF/Word الأصلي)."}

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
    show_guide(a)

    crit = _criteria(a)
    prog = {p["criterion"]: p for p in store.select("btec_progress", {"assignment_id": pick, "student_id": user["id"]})}
    if crit and prog:
        with st.expander("📈 تقدّمي في معايير هذا الواجب"):
            st.dataframe(pd.DataFrame([{"المعيار": c["code"], "الحالة": prog.get(c["code"], {}).get("status", "لم يبدأ")}
                                       for c in crit]), hide_index=True, use_container_width=True)
            note = (prog.get("_note") or {}).get("note")
            if note:
                st.info(f"ملاحظة المعلم: {note}")


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
def _students(grade, track_id):
    out = [u for u in acc.list_users(role="student") if u["status"] == "active" and u.get("grade") == grade
           and u.get("track_id") == track_id]
    names = {}
    for u in out:   # تمييز الأسماء المكررة
        names[u["id"]] = u["name"] if sum(1 for x in out if x["name"] == u["name"]) == 1 else f"{u['name']} (#{u['id']})"
    return names


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

    names = (["📤 رفع واجب"] if is_sup else []) + ["📚 الواجبات", "🧑‍🏫 دليل شرح الواجب", "📈 متابعة التقدم", "🔎 فحص الأدلة"]
    tabs = dict(zip(names, st.tabs(names)))

    if is_sup:
        with tabs["📤 رفع واجب"]:
            _tab_upload(user, grade, sel, subj)
    with tabs["📚 الواجبات"]:
        _tab_assignments(grade, sel, is_sup, subj)
    with tabs["🧑‍🏫 دليل شرح الواجب"]:
        _tab_teacher_explain(user, grade, sel, subj)
    with tabs["📈 متابعة التقدم"]:
        _tab_progress(user, grade, sel, subj)
    with tabs["🔎 فحص الأدلة"]:
        _tab_evidence(user, grade, sel, subj)


def _tab_upload(user, grade, track_id, subj="all"):
    st.caption("ارفع صور الواجب أو ملفه (PDF/Word). سيُستخرج الواجب ومعاييره ويُولَّد دليل الطالب بنصه وصوره، ثم يُخزَّن ليختاره الطلاب. "
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
    ups = st.file_uploader("ملفات الواجب", type=["png", "jpg", "jpeg", "webp", "pdf", "docx"],
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
    show_guide(a, staff=True)


def _tab_teacher_explain(user, grade, track_id, subj="all"):
    a = _pick_assignment(grade, track_id, "btec_exp_pick", subj=subj)
    if not a:
        return
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


def _tab_progress(user, grade, track_id, subj="all"):
    a = _pick_assignment(grade, track_id, "btec_prog_pick", subj=subj)
    if not a:
        return
    crit = _criteria(a)
    students = _students(grade, track_id)
    if not crit:
        st.info("لم تُستخرج معايير لهذا الواجب.")
        return
    if not students:
        st.info("لا يوجد طلاب فعّالون في هذا الصف/التخصص بعد.")
        return
    codes = [c["code"] for c in crit]
    saved = {(p["student_id"], p["criterion"]): p for p in store.select("btec_progress", {"assignment_id": a["id"]})}

    with st.expander("📋 المعايير"):
        st.dataframe(pd.DataFrame([{"الرمز": c["code"], "المستوى": c.get("level", ""), "النص": c.get("text", "")} for c in crit]),
                     hide_index=True, use_container_width=True)

    # ملخص الاستيفاء
    summ = []
    for sid, nm in students.items():
        done = sum(1 for c in codes if saved.get((sid, c), {}).get("status") == "محقَّق")
        summ.append({"الطالب": nm, "المحقَّق": f"{done}/{len(codes)}", "النسبة %": round(100 * done / len(codes))})
    st.markdown("**ملخص استيفاء المعايير**")
    st.dataframe(pd.DataFrame(summ), hide_index=True, use_container_width=True)

    st.markdown("**تحديث الحالات**")
    df = pd.DataFrame([{"الطالب": nm, **{c: saved.get((sid, c), {}).get("status", "لم يبدأ") for c in codes},
                        "ملاحظة": saved.get((sid, "_note"), {}).get("note") or ""} for sid, nm in students.items()])
    cfg = {c: st.column_config.SelectboxColumn(c, options=STATUSES, required=True) for c in codes}
    edited = st.data_editor(df, column_config=cfg, hide_index=True, disabled=["الطالب"], use_container_width=True,
                            key=f"btec_ed_{a['id']}")
    c1, c2 = st.columns(2)
    if c1.button("💾 حفظ المتابعة", type="primary", key=f"btec_save_prog_{a['id']}"):
        by_name = {v: k for k, v in students.items()}
        out = []
        for _, r in edited.iterrows():
            sid = by_name[r["الطالب"]]
            for c in codes:
                out.append({"assignment_id": a["id"], "student_id": sid, "criterion": c, "status": r[c], "updated_by": user["id"]})
            note = str(r["ملاحظة"] or "").strip()
            if note or (sid, "_note") in saved:
                out.append({"assignment_id": a["id"], "student_id": sid, "criterion": "_note", "status": "—",
                            "note": note, "updated_by": user["id"]})
        store.upsert("btec_progress", out, "assignment_id,student_id,criterion")
        st.success("تم حفظ المتابعة.")
        st.rerun()
    c2.download_button("⬇️ تنزيل CSV", edited.to_csv(index=False).encode("utf-8-sig"),
                       file_name=f"btec_progress_{a['id']}.csv", mime="text/csv", key=f"btec_csv_{a['id']}")


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
    st.caption("ارفع ملف الطالب الذي سلّمه (صور/PDF/Word) وسيفحصه النظام مقابل معايير الواجب ويُعدّ تقريرًا. "
               "لا يلزم أن يكون الطالب مسجَّلًا في النظام. لا تُحفظ ملفات الطالب، يُحفظ التقرير فقط. "
               "يُحتسب طلب واحد من حصتك اليومية.")
    mode = st.radio("ورقة الواجب", ["من الواجبات المخزَّنة في النظام", "أرفع ورقة الواجب الآن"], horizontal=True,
                    key="btec_ev_mode")
    a, sheet = None, None
    if mode.startswith("من"):
        a = _pick_assignment(grade, track_id, "btec_ev_pick", subj=subj)
        if a and not _criteria(a):
            st.warning("لم تُستخرج معايير لهذا الواجب، لذا لا يمكن فحص الأدلة مقابله. ارفع ورقة الواجب بدلًا من ذلك.")
    else:
        sheet = st.file_uploader("ورقة الواجب (صور/PDF/Word)", type=["png", "jpg", "jpeg", "webp", "pdf", "docx"],
                                 accept_multiple_files=True, key="btec_ev_sheet")
    label = st.text_input("اسم الطالب أو وصف التسليم (اختياري — يظهر في التقرير)", key="btec_ev_label")
    ups = st.file_uploader("ملف الطالب المسلَّم (الأدلة)", type=["png", "jpg", "jpeg", "webp", "pdf", "docx"],
                           accept_multiple_files=True, key="btec_ev_up")

    if st.button("🔎 افحص الأدلة", type="primary", key="btec_ev_run"):
        items, err = read_uploads(ups)
        sheet_items = None
        if not err and a is None:
            sheet_items, err = read_uploads(sheet)
            err = ("ورقة الواجب: " + err) if err else None
        if not err and a is not None and not _criteria(a):
            err = "لا يمكن الفحص: لا معايير مخزَّنة لهذا الواجب."
        if err:
            st.error(err)
        else:
            auth_ui.require_quota_or_stop(user)
            with st.spinner("جارٍ فحص الأدلة مقابل المعايير..."):
                try:
                    if a is not None:
                        data, notes, alabel = a["data"], a.get("teacher_notes"), a["title"]
                    else:
                        data = btec_ai.extract_data(sheet_items)
                        notes, alabel = None, default_title(data)
                    if not data.get("readable", True) or not data.get("criteria"):
                        st.error("تعذّرت قراءة معايير الواجب من الملف المرفوع. ارفع نسخة أوضح من ورقة الواجب.")
                        res = None
                    else:
                        res = btec_ai.review_evidence(data, items, label.strip(), notes)
                except Exception as e:  # noqa: BLE001
                    res = None
                    st.error(f"حدث خطأ: {e}")
            if res and res.get("criteria"):
                rep = {"assignment_label": alabel, "student_label": label.strip(), "result": res,
                       "date": dt.datetime.now().strftime("%Y-%m-%d %H:%M")}
                store.insert("btec_reviews", {"assignment_id": a["id"] if a else None, "student_label": rep["student_label"],
                                              "assignment_label": alabel, "result": res,
                                              "file_names": [i["name"] for i in items], "reviewed_by": user["id"],
                                              "created_at": dt.datetime.utcnow().isoformat()})
                st.session_state["btec_ev_report"] = rep
            elif res is not None:
                st.error("تعذّر فهم نتيجة الفحص. حاول مرة أخرى.")

    rep = st.session_state.get("btec_ev_report")
    if rep:
        st.divider()
        _show_report(rep)

    hist = store.select("btec_reviews", {"reviewed_by": user["id"]}, order="created_at.desc", limit=10)
    if hist:
        with st.expander("🕘 آخر تقاريري المحفوظة"):
            idx = st.selectbox("اختر تقريرًا", range(len(hist)), key="btec_ev_hist", format_func=lambda i: (
                f"{hist[i].get('assignment_label') or 'واجب'} — {hist[i].get('student_label') or 'بدون اسم'} — "
                f"{str(hist[i].get('created_at') or '')[:16].replace('T', ' ')}"))
            h = hist[idx]
            _show_report({"assignment_label": h.get("assignment_label") or "واجب", "student_label": h.get("student_label") or "",
                          "result": h["result"], "date": str(h.get("created_at") or "")[:16].replace("T", " ")})
