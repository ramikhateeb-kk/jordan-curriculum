"""
semester_plan.py
ميزة الخطة الفصلية الرسمية وفق نموذج وزارة التربية والتعليم الأردنية (FORM # QF71-1-47rev.a).
تضمن ترتيب الأعمدة من اليمين إلى اليسار (النتاجات على اليمين والتأمل على اليسار) واحتواء كل وحدة بصفحة واحدة.
"""
import io
import json
import re

import streamlit as st
from docx import Document
from docx.enum.section import WD_ORIENT, WD_SECTION
from docx.enum.table import WD_TABLE_DIRECTION
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt
from google.genai import types

import accounts as acc
import auth_ui
import english_docs as en
import plan_cache
import profile_ctx
from config import GEMINI_MODEL
from rag import get_client, select_context
from word_rtl import center as _center, doc_table as _doc_table
from word_rtl import no_borders as _no_borders
from word_rtl import rtl_p as _rtl_p, rtl_section as _rtl_section
from word_rtl import rtl_table as _rtl_table, run as _run

SYSTEM_SEMESTER = (
    "أنت مشرف تربوي خبير يساعد معلمي المنهاج الأردني على إعداد الخطة الفصلية. "
    "اعتمد على نص الوحدة المرفق فقط. اكتب بصيغة نقاط مختصرة ودقيقة "
    "بحيث تتسع الوحدة بصفحة واحدة فقط. أعد JSON فقط."
)

SCHEMA_SEMESTER = '''{
  "outcomes": ["تحديد المفاهيم الرئيسية للوحدة", "تحليل التطبيقات العملية والمظاهر"],
  "resources": ["الكتاب المدرسي", "أجهزة الحاسوب / المعمل", "جهاز العرض Data show"],
  "strategies": ["التدريس المباشر", "العمل الجماعي (التعلم التعاوني)", "التفكير الناقد"],
  "eval_strategies": ["الملاحظة المباشرة", "التقويم المعتمد على الأداء"],
  "eval_tools": ["سلم التقدير الرقمي", "قوائم الرصد"],
  "activities": ["أوراق عمل", "عروض تقديمية interactive"]
}'''


def _set_cell_v_center(cell):
    tcPr = cell._tc.get_or_add_tcPr()
    vAlign = OxmlElement('w:vAlign')
    vAlign.set(qn('w:val'), 'center')
    tcPr.append(vAlign)


def _generate_unit_plan(idx, unit, lang="ar"):
    """خطة وحدة (أو درس واحد في الحساب التجريبي) — unit: {title,start,end}."""
    client = get_client()
    ctx_pages = select_context(idx, unit["title"], (unit["start"], unit["end"]), max_chars=30000)
    if lang == "en":
        fallback_en = en.semester_fallback(unit["title"])
        if not ctx_pages:
            return fallback_en
        ctx = "\n\n".join(f"=== Page {p['page']} ===\n{p['text']}" for p in ctx_pages)
        prompt = (f"Unit: {unit['title']}\n\nUnit text:\n{ctx}\n\n"
                  f"Return a very concise semester plan for the unit following this schema:\n{en.SCHEMA_SEMESTER}")
        try:
            r = client.models.generate_content(
                model=GEMINI_MODEL, contents=prompt,
                config=types.GenerateContentConfig(system_instruction=en.SYSTEM_SEMESTER, temperature=0.3,
                                                    response_mime_type="application/json"))
            return json.loads(re.sub(r"^```(?:json)?|```$", "", r.text.strip(), flags=re.MULTILINE).strip())
        except Exception as e:  # noqa: BLE001
            print(f"Fallback semester plan used for {unit['title']}: {e}")
            return fallback_en
    
    fallback_data = {
        "outcomes": [
            f"يتوقع في نهاية الوحدة أن يكتسب الطالب المهارات الأساسية لـ {unit['title']}.",
            "تطبيق النتاجات التعليمية والأنشطة العمليّة المرفقة بالكتاب."
        ],
        "resources": ["الكتاب المدرسي", "أجهزة الحاسوب", "جهاز العرض Data show"],
        "strategies": ["التدريس المباشر", "العمل الجماعي", "التفكير الناقد"],
        "eval_strategies": ["الملاحظة المباشرة", "التقويم المعتمد على الأداء"],
        "eval_tools": ["سلم التقدير الرقمي", "أوراق العمل"],
        "activities": ["أوراق عمل تشاركية", "عروض تقديمية"]
    }

    if not ctx_pages:
        return fallback_data

    ctx = "\n\n".join(f"=== صفحة {p['page']} ===\n{p['text']}" for p in ctx_pages)
    prompt = f"الوحدة: {unit['title']}\n\nنص الوحدة:\n{ctx}\n\nأعد الخطة الفصلية للوحدة بأسلوب مختصر جداً وفق السكيما التالية:\n{SCHEMA_SEMESTER}"
    
    try:
        r = client.models.generate_content(
            model=GEMINI_MODEL, contents=prompt,
            config=types.GenerateContentConfig(system_instruction=SYSTEM_SEMESTER, temperature=0.3, response_mime_type="application/json"))
        clean_text = re.sub(r"^```(?:json)?|```$", "", r.text.strip(), flags=re.MULTILINE).strip()
        return json.loads(clean_text)
    except Exception as e:
        print(f"تنبيه: تم استخدام البيانات المجهزة تلقائياً للوحدة {unit['title']} بسبب خطأ API: {e}")
        return fallback_data


def get_or_generate_semester_plan(idx, slug, units, user=None, lang="ar"):
    cached = plan_cache.get_semester_plan(slug)
    if cached:
        return cached, True
    if user is not None:
        auth_ui.require_quota_or_stop(user)   # خصم واحد لكل عملية توليد (لا لكل وحدة)

    units_plans = []
    for unit in units:
        plan_data = _generate_unit_plan(idx, unit, lang)
        if plan_data:
            units_plans.append({
                "title": unit["title"],
                "periods": unit.get("periods", "14"),
                "pages": f"{unit.get('start', '')} - {unit.get('end', '')}",
                "start_date": unit.get("start_date", "........"),
                "end_date": unit.get("end_date", "........"),
                "plan": plan_data
            })

    if units_plans:
        try:
            plan_cache.save_semester_plan(slug, units_plans)
        except Exception as e:
            print("تعذر حفظ الخطة الفصلية في الكاش:", e)

    return units_plans, False


def _add_semester_page(doc, is_first, meta, unit_data):
    section = doc.sections[0] if is_first else doc.add_section(WD_SECTION.NEW_PAGE)
    section.orientation = WD_ORIENT.LANDSCAPE
    section.page_width = Cm(29.7)
    section.page_height = Cm(21.0)

    section.top_margin = section.bottom_margin = Cm(0.6)
    section.left_margin = section.right_margin = Cm(1.0)
    _rtl_section(section)

    footer = section.footer
    footer_p = footer.paragraphs[0]
    footer_p.paragraph_format.space_before = Pt(0)
    footer_p.paragraph_format.space_after = Pt(0)
    _run(_rtl_p(footer_p, WD_ALIGN_PARAGRAPH.RIGHT), "FORM # QF71-1-47rev.a", 8, False)

    _center(doc, "الخطة الفصلية", 13, True)

    # 1. الترويسة العلويّة
    top_table = _doc_table(doc, 3, 3, [Cm(9.0), Cm(9.5), Cm(9.0)])
    top_table.table_direction = WD_TABLE_DIRECTION.RTL
    _rtl_table(top_table)

    r0 = top_table.rows[0].cells
    _run(_rtl_p(r0[0].paragraphs[0], WD_ALIGN_PARAGRAPH.RIGHT), f"المبحث: {meta['subject']}", 10, True)
    _run(_rtl_p(r0[1].paragraphs[0], WD_ALIGN_PARAGRAPH.CENTER), f"الفصل الدراسي {meta['semester']}", 10, True)
    _run(_rtl_p(r0[2].paragraphs[0], WD_ALIGN_PARAGRAPH.LEFT), f"الصف : {meta['grade']}", 10, True)

    r1 = top_table.rows[1].cells
    _run(_rtl_p(r1[0].paragraphs[0], WD_ALIGN_PARAGRAPH.RIGHT), f"عنوان الوحدة: {unit_data['title']}", 10, True)
    _run(_rtl_p(r1[1].paragraphs[0], WD_ALIGN_PARAGRAPH.CENTER), f"الصفحات: {unit_data.get('pages', '')}", 10)
    _run(_rtl_p(r1[2].paragraphs[0], WD_ALIGN_PARAGRAPH.LEFT), f"عدد الحصص: {unit_data.get('periods', '')}", 10)

    r2 = top_table.rows[2].cells
    _run(_rtl_p(r2[1].paragraphs[0], WD_ALIGN_PARAGRAPH.CENTER), f"الفترة الزمنية: من: {unit_data.get('start_date', '')} إلى {unit_data.get('end_date', '')}", 10)

    # 2. إنشاء الجدول الرئيسي 3 صفوف و 7 أعمدة (عكس المصفوفة لتظهر RTL سليمة)
    # 6: النتاجات العامة (يمين) | 5: مصادر التعلم | 4: استراتيجيات التدريس | 3: تقويم (استراتيجيات) | 2: تقويم (أدوات) | 1: أنشطة | 0: التأمل الذاتي (يسار)
    main_table = _doc_table(doc, 3, 7, [Cm(4.5), Cm(3.0), Cm(3.0), Cm(3.2), Cm(3.5), Cm(3.3), Cm(7.2)], borders=True)
    main_table.table_direction = WD_TABLE_DIRECTION.RTL
    _rtl_table(main_table)

    # --- خطوات الدمج الآمنة تجنباً لـ InvalidSpanError ---
    # أولاً: دمج خلية التقويم الأفقية في الصف الأول (العمودين 2 و 3)
    eval_cell = main_table.rows[0].cells[2].merge(main_table.rows[0].cells[3])
    _run(_rtl_p(eval_cell.paragraphs[0], WD_ALIGN_PARAGRAPH.CENTER), "التقويم", 9.5, True)

    # ثانياً: دمج باقي الأعمدة رأسياً (0، 1، 4، 5، 6) بشكل فردي ودقيق
    for col_idx in [0, 1, 4, 5, 6]:
        c_top = main_table.rows[0].cells[col_idx]
        c_bottom = main_table.rows[1].cells[col_idx]
        c_top.merge(c_bottom)

    # كتابة عناوين رؤوس الأعمدة
    _run(_rtl_p(main_table.rows[0].cells[6].paragraphs[0], WD_ALIGN_PARAGRAPH.CENTER), "النتاجات العامة", 9.5, True)
    _run(_rtl_p(main_table.rows[0].cells[5].paragraphs[0], WD_ALIGN_PARAGRAPH.CENTER), "المواد والتجهيزات\n(مصادر التعلم)", 9.5, True)
    _run(_rtl_p(main_table.rows[0].cells[4].paragraphs[0], WD_ALIGN_PARAGRAPH.CENTER), "استراتيجيات التدريس", 9.5, True)

    # عناوين الصف الفرعي للتقويم
    _run(_rtl_p(main_table.rows[1].cells[3].paragraphs[0], WD_ALIGN_PARAGRAPH.CENTER), "الاستراتيجيات", 9, True)
    _run(_rtl_p(main_table.rows[1].cells[2].paragraphs[0], WD_ALIGN_PARAGRAPH.CENTER), "الأدوات", 9, True)

    _run(_rtl_p(main_table.rows[0].cells[1].paragraphs[0], WD_ALIGN_PARAGRAPH.CENTER), "أنشطة مرافقة", 9.5, True)
    _run(_rtl_p(main_table.rows[0].cells[0].paragraphs[0], WD_ALIGN_PARAGRAPH.CENTER), "التأمل الذاتي حول الوحدة", 9.5, True)

    for cell in main_table.rows[0].cells + main_table.rows[1].cells:
        _set_cell_v_center(cell)

    plan = unit_data["plan"]

    # 1. النتاجات العامة (العمود 6 - أقصى اليمين)
    c_out = main_table.rows[2].cells[6]
    p_h = c_out.paragraphs[0]
    p_h.paragraph_format.space_before = Pt(0)
    p_h.paragraph_format.space_after = Pt(2)
    _run(_rtl_p(p_h, WD_ALIGN_PARAGRAPH.RIGHT), "يتوقع في نهاية الوحدة أن يكون الطالب قادرا على :", 9, True)
    for item in plan.get("outcomes", []):
        p = c_out.add_paragraph()
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after = Pt(1)
        _run(_rtl_p(p, WD_ALIGN_PARAGRAPH.RIGHT), f"- {item}", 8.5)

    # 2. مصادر التعلم (العمود 5)
    c_res = main_table.rows[2].cells[5]
    for i, item in enumerate(plan.get("resources", [])):
        p = c_res.paragraphs[0] if i == 0 else c_res.add_paragraph()
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after = Pt(1)
        _run(_rtl_p(p, WD_ALIGN_PARAGRAPH.RIGHT), f"- {item}", 8.5)

    # 3. استراتيجيات التدريس (العمود 4)
    c_strat = main_table.rows[2].cells[4]
    for i, item in enumerate(plan.get("strategies", [])):
        p = c_strat.paragraphs[0] if i == 0 else c_strat.add_paragraph()
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after = Pt(1)
        _run(_rtl_p(p, WD_ALIGN_PARAGRAPH.RIGHT), f"- {item}", 8.5)

    # 4. استراتيجيات التقويم (العمود 3 - تحت الاستراتيجيات)
    c_ev_s = main_table.rows[2].cells[3]
    for i, item in enumerate(plan.get("eval_strategies", [])):
        p = c_ev_s.paragraphs[0] if i == 0 else c_ev_s.add_paragraph()
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after = Pt(1)
        _run(_rtl_p(p, WD_ALIGN_PARAGRAPH.RIGHT), f"- {item}", 8.5)

    # 5. أدوات التقويم (العمود 2 - تحت الأدوات)
    c_ev_t = main_table.rows[2].cells[2]
    for i, item in enumerate(plan.get("eval_tools", [])):
        p = c_ev_t.paragraphs[0] if i == 0 else c_ev_t.add_paragraph()
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after = Pt(1)
        _run(_rtl_p(p, WD_ALIGN_PARAGRAPH.RIGHT), f"- {item}", 8.5)

    # 6. الأنشطة المرافقة (العمود 1)
    c_act = main_table.rows[2].cells[1]
    for i, item in enumerate(plan.get("activities", [])):
        p = c_act.paragraphs[0] if i == 0 else c_act.add_paragraph()
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after = Pt(1)
        _run(_rtl_p(p, WD_ALIGN_PARAGRAPH.RIGHT), f"- {item}", 8.5)

    # 7. التأمل الذاتي (العمود 0 - أقصى اليسار)
    c_ref = main_table.rows[2].cells[0]
    p_rf = c_ref.paragraphs[0]
    p_rf.paragraph_format.space_before = Pt(0)
    p_rf.paragraph_format.space_after = Pt(1)
    _run(_rtl_p(p_rf, WD_ALIGN_PARAGRAPH.RIGHT),
         "أشعر بالرضا عن: ........................................................\n\n"
         "التحديات التي واجهتني:.......................................................\n\n"
         "مقترحات التحسين .......................................................", 8.5)

    # معلومات عامة عن الطلبة
    p_info = doc.add_paragraph()
    p_info.paragraph_format.space_before = Pt(6)
    p_info.paragraph_format.space_after = Pt(4)
    _run(_rtl_p(p_info, WD_ALIGN_PARAGRAPH.RIGHT), "معلومات عامة عن الطلبة : ............................................................", 9.5, True)

    # أسفل الجدول والتواقيع (إعداد المعلم على اليمين تماماً وبمحاذاة منسقة)
    sig = _doc_table(doc, 2, 4, [Cm(8.0), Cm(7.0), Cm(6.0), Cm(6.0)])
    sig.table_direction = WD_TABLE_DIRECTION.RTL
    _rtl_table(sig)
    _no_borders(sig)

    r0_s = sig.rows[0].cells
    _run(_rtl_p(r0_s[0].paragraphs[0], WD_ALIGN_PARAGRAPH.RIGHT), f"إعداد المعلم/ة : {meta['teacher']}", 9.5, True)
    _run(_rtl_p(r0_s[1].paragraphs[0], WD_ALIGN_PARAGRAPH.RIGHT), f"مدير/ة المدرسة : {meta['principal']}", 9.5, True)
    _run(_rtl_p(r0_s[2].paragraphs[0], WD_ALIGN_PARAGRAPH.RIGHT), "التوقيع : ....................", 9)
    _run(_rtl_p(r0_s[3].paragraphs[0], WD_ALIGN_PARAGRAPH.RIGHT), "التاريخ :...............", 9)

    r1_s = sig.rows[1].cells
    _run(_rtl_p(r1_s[0].paragraphs[0], WD_ALIGN_PARAGRAPH.RIGHT), "المشرف التربوي : ....................", 9.5, True)
    _run(_rtl_p(r1_s[2].paragraphs[0], WD_ALIGN_PARAGRAPH.RIGHT), "التوقيع : ....................", 9)
    _run(_rtl_p(r1_s[3].paragraphs[0], WD_ALIGN_PARAGRAPH.RIGHT), "التاريخ :...............", 9)


def build_semester_docx(meta, units_plans, lang="ar"):
    if lang == "en":
        return en.build_semester_docx(meta, units_plans)
    doc = Document()
    for i, u_data in enumerate(units_plans):
        _add_semester_page(doc, i == 0, meta, u_data)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _lesson_scope_plans(idx, lessons, lang, user):
    """الحساب التجريبي: خطة فصلية لدرس (أو دروس) محددة فقط، وليست للمنهاج كاملًا. لا تُحفظ في الكاش
    المشترك أبدًا حتى لا تُسترجع لاحقًا على أنها الخطة الكاملة للمبحث."""
    if user is not None:
        auth_ui.require_quota_or_stop(user)
    out = []
    for l in lessons:
        plan = _generate_unit_plan(idx, {"title": l["title"], "start": l["start"], "end": l["end"]}, lang)
        out.append({"title": l["title"], "periods": "1", "pages": f"{l['start']} - {l['end']}",
                    "start_date": "........", "end_date": "........", "plan": plan})
    return out


def render_semester_plan_builder(idx, slug, subject, units, flat_lessons=None, user=None, ctx=None, lang="ar"):
    st.subheader("📅 الخطة الفصلية" if lang != "en" else "📅 الخطة الفصلية (Semester Plan — English, LTR)")
    ctx = ctx or {}
    if lang == "en":
        st.caption("🇬🇧 هذا كتاب لغة إنجليزية: ستُنتَج الخطة بالإنجليزية واتجاه الصفحة من اليسار إلى اليمين.")

    remaining = acc.trial_remaining(user, "semester_plan") if user is not None else None
    chosen_lessons = []
    if remaining is not None:
        st.info(f"🧪 حساب تجريبي: تُنتَج لك الخطة الفصلية لعدد {remaining} درس/دروس فقط (وليس للمنهاج كاملًا).")
        labels = [l["label"] for l in (flat_lessons or [])]
        picked = st.multiselect("اختر الدرس", labels, default=labels[:1], max_selections=remaining,
                                key="sem_trial_lessons")
        chosen_lessons = [l for l in (flat_lessons or []) if l["label"] in picked]
    else:
        if plan_cache.get_semester_plan(slug) is not None:
            st.info("💡 توجد خطة فصلية جاهزة ومحفوظة لهذا المبحث وسيتم استرجاع جميع وحداتها فوراً.")

    # ما يعرفه النظام لا يُسأل عنه: الصف والتخصص والفصل والعام الدراسي واسم المعلم
    grade_txt = (f"Grade {ctx['grade']}" + (f" ({ctx['track']})" if ctx.get("track") else "")) \
        if lang == "en" else ctx.get("class_label", "")
    grade = profile_ctx.known_input("الصف الدراسي", grade_txt, "sem_grade")
    semester = ctx.get("sem_name_en") if lang == "en" else ctx.get("sem_name")
    year = profile_ctx.known_input("العام الدراسي", ctx.get("greg_year"), "sem_year", placeholder="2026/2027")
    teacher = profile_ctx.known_input("اسم المعلم/ـة", ctx.get("teacher"), "sem_teacher")
    profile_ctx.known_summary([("المبحث", subject), ("الصف", grade_txt), ("الفصل", ctx.get("sem_name")),
                               ("العام الدراسي", ctx.get("greg_year")), ("المعلم", ctx.get("teacher"))])
    principal = st.text_input("اسم مدير/ة المدرسة", key="sem_principal")   # غير معروف للنظام

    if st.button("🚀 إنشاء / استرجاع الخطة الفصلية", type="primary", key="btn_sem",
                 disabled=(remaining is not None and not chosen_lessons)):
        with st.spinner("جارٍ معالجة وتوليد الخطة..."):
            if remaining is not None:
                units_plans, from_cache = _lesson_scope_plans(idx, chosen_lessons, lang, user), False
            else:
                units_plans, from_cache = get_or_generate_semester_plan(idx, slug, units, user=user, lang=lang)

        if units_plans:
            meta = {"subject": subject, "grade": grade, "semester": semester, "year": year,
                    "teacher": teacher, "principal": principal}
            docx_bytes = build_semester_docx(meta, units_plans, lang)
            if remaining is not None:
                acc.trial_consume(user, "semester_plan", len(chosen_lessons))
                st.success(f"تم إعداد الخطة الفصلية للدرس المحدد ({len(units_plans)}).")
            else:
                st.success(f"تم إعداد الخطة الفصلية بنجاح لجميع وحدات الكتاب ({len(units_plans)} وحدة)!")
            st.download_button(
                "⬇️ تنزيل الخطة الفصلية (Word)",
                data=docx_bytes,
                file_name=f"الخطة_الفصلية_{subject}.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            )
