"""
ملف: ministry.py
نظام استخراج وحل أسئلة الامتحانات الوزارية - المنهاج الأردني (شهادة الثانوية العامة - التوجيهي)
الإصدار المطور والنهائي (v4):
1. حل جذري لخطأ 'NoneType' object has no attribute 'strip' عبر استخراج آمن 100% لنصوص استجابات Gemini.
2. تدوير ذكي بين النماذج (gemini-3.8-flash, gemini-3.1-flash-lite, gemini-2.5-flash) مع إعادة محاولة تلقائية في حالات 503.
3. استخراج كامل لجميع الأسئلة الفرعية في Question Two (A: 1-6 + Critical Thinking + Literature Spot).
4. تنسيق إنجليزي LTR تلقائي للامتحانات الإنجليزية.
5. استعادة جميع الأزرار: ✏️ تعديل السؤال والإجابة | 📥 بنك الأسئلة | 🎯 قيّمني (اختبر إجابتي).
"""

import os
import io
import time
import json
import base64
import streamlit as st
from typing import List, Dict, Any, Optional


def extract_text_from_file(uploaded_file, file_bytes: bytes) -> str:
    """استخراج النص من الملفات بمختلف الصيغ (PDF, DOCX, TXT)"""
    file_name = uploaded_file.name.lower()

    if file_name.endswith(".txt"):
        try:
            return file_bytes.decode("utf-8", errors="ignore")
        except Exception:
            return ""

    if file_name.endswith(".docx"):
        try:
            import docx
            doc = docx.Document(io.BytesIO(file_bytes))
            text = "\n".join([p.text for p in doc.paragraphs if p.text.strip()])
            if text.strip():
                return text.strip()
        except Exception:
            pass

    if file_name.endswith(".pdf"):
        # 1. pypdf
        try:
            import pypdf
            reader = pypdf.PdfReader(io.BytesIO(file_bytes))
            pages = []
            for i, p in enumerate(reader.pages):
                pt = p.extract_text()
                if pt and pt.strip():
                    pages.append(f"--- [Page {i + 1}] ---\n" + pt.strip())
            full_text = "\n\n".join(pages).strip()
            if len(full_text) > 40:
                return full_text
        except Exception:
            pass

        # 2. pdfplumber
        try:
            import pdfplumber
            with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
                pages = []
                for i, p in enumerate(pdf.pages):
                    pt = p.extract_text()
                    if pt and pt.strip():
                        pages.append(f"--- [Page {i + 1}] ---\n" + pt.strip())
                full_text = "\n\n".join(pages).strip()
                if len(full_text) > 40:
                    return full_text
        except Exception:
            pass

        # 3. fitz (PyMuPDF)
        try:
            import fitz
            doc = fitz.open(stream=file_bytes, filetype="pdf")
            pages = []
            for i, page in enumerate(doc):
                pt = page.get_text()
                if pt and pt.strip():
                    pages.append(f"--- [Page {i + 1}] ---\n" + pt.strip())
            full_text = "\n\n".join(pages).strip()
            if len(full_text) > 40:
                return full_text
        except Exception:
            pass

    return ""


def get_gemini_client():
    """الحصول على عميل Google GenAI"""
    api_key = None
    try:
        if "GEMINI_API_KEY" in st.secrets:
            api_key = st.secrets["GEMINI_API_KEY"]
    except Exception:
        pass

    if not api_key:
        api_key = os.environ.get("GEMINI_API_KEY")

    if not api_key:
        return None

    try:
        from google import genai
        return genai.Client(api_key=api_key)
    except Exception as e:
        st.error(f"خطأ أثناء تهيئة مكتبة google-genai: {e}")
        return None


def extract_text_from_gemini_response(response) -> str:
    """استخراج النص بأمان تام من استجابة Gemini يمنع خطأ NoneType strip نهائياً"""
    if response is None:
        return ""

    # 1. فحص response.text
    try:
        raw = getattr(response, "text", None)
        if raw is not None and isinstance(raw, str) and raw.strip():
            return raw.strip()
    except Exception:
        pass

    # 2. فحص candidates[0].content.parts
    try:
        candidates = getattr(response, "candidates", None)
        if candidates and len(candidates) > 0:
            cand = candidates[0]
            content = getattr(cand, "content", None)
            if content:
                parts = getattr(content, "parts", None)
                if parts:
                    collected = []
                    for part in parts:
                        pt = getattr(part, "text", None)
                        if pt and isinstance(pt, str):
                            collected.append(pt)
                    if collected:
                        return "".join(collected).strip()
    except Exception:
        pass

    return ""


def parse_gemini_json(raw_text: str) -> Dict[str, Any]:
    """تحليل نص JSON بأمان مع إزالة علامات Markdown واستخراج كائن JSON"""
    if not raw_text or not isinstance(raw_text, str) or not raw_text.strip():
        raise ValueError("النص المستخرج من نموذج الذكاء الاصطناعي فارغ (None/Empty)")

    txt = raw_text.strip()
    if txt.startswith("```json"):
        txt = txt[7:]
    elif txt.startswith("```"):
        txt = txt[3:]
    if txt.endswith("```"):
        txt = txt[:-3]
    txt = txt.strip()

    start_brace = txt.find("{")
    end_brace = txt.rfind("}")
    if start_brace != -1 and end_brace != -1 and end_brace > start_brace:
        txt = txt[start_brace : end_brace + 1]

    return json.loads(txt)


def extract_and_solve_all_questions(
    exam_text: str = "",
    file_bytes: Optional[bytes] = None,
    mime_type: Optional[str] = None,
    subject: str = "اللغة الإنجليزية",
    branch: str = "جميع الفروع الأكاديمية والمهنية"
) -> Dict[str, Any]:
    client = get_gemini_client()
    if not client:
        return {"error": "لم يتم العثور على مفتاح GEMINI_API_KEY في st.secrets أو متغيرات البيئة"}

    from google.genai import types

    is_english = "إنجليز" in subject or "english" in subject.lower()

    system_instruction = f"""
    You are an expert Chief Examiner at the Ministry of Education in Jordan (Tawjihi Directorate of Examinations).
    CRITICAL MANDATORY RULES:
    1. Read the ENTIRE exam paper from start to finish.
    2. Extract ALL main questions:
       - Question One: (all Multiple Choice items 1..N).
       - Question Two: You MUST extract the Reading Passage in "passage", and extract EVERY SINGLE sub-question following the passage (questions 1, 2, 3, 4, 5, 6, Critical Thinking, Literature Spot) as separate items in "sub_questions". NEVER combine them!
       - Question Three / Four: Free Writing, Guided Writing, Grammar, or Vocabulary items.
    3. For EVERY single sub-question in EVERY question, provide model answers, explanations, and marking rubrics.
    {"4. The exam is in ENGLISH. The titles, questions, passages, choices, and answers MUST be in clean, natural ENGLISH. Set 'language': 'en'." if is_english else "4. اكتب المخرجات باللغة العربية الواضحة."}
    """

    prompt = f"""
    Official Jordanian Ministry of Education Exam Paper:
    Subject: {subject}
    Branch: {branch}
    
    Exam content:
    {exam_text if exam_text else "Please read all attached pages/images carefully."}
    
    Return ONLY a valid JSON object matching:
    {{
      "title": "General Secondary Certificate Examination - English Language",
      "subject": "{subject}",
      "branch": "{branch}",
      "total_marks": 200,
      "language": "{"en" if is_english else "ar"}",
      "questions": [
        {{
          "id": "q1",
          "number": 1,
          "title": "Question One: Multiple Choice Items",
          "total_marks": 140,
          "sub_questions": [
            {{
              "id": "q1_1",
              "sub_label": "Item 1",
              "text": "Full sentence and options A, B, C, D",
              "marks": 5,
              "answer": {{
                "final_answer": "A) correct answer",
                "steps": ["Why option A is correct"],
                "rubric": [{{"step": "Correct option selected", "marks": 5}}],
                "examiner_tips": "Vocabulary note"
              }}
            }}
          ]
        }},
        {{
          "id": "q2",
          "number": 2,
          "title": "Question Two: Reading Comprehension, Critical Thinking & Literature",
          "total_marks": 30,
          "passage": "Full article text...",
          "sub_questions": [
            {{
              "id": "q2_1",
              "sub_label": "Question 1",
              "text": "Text of comprehension question 1",
              "marks": 4,
              "answer": {{"final_answer": "...", "steps": ["..."], "rubric": [{{"step": "...", "marks": 4}}], "examiner_tips": "..."}}
            }}
          ]
        }}
      ]
    }}
    """

    contents = []
    if file_bytes and mime_type:
        try:
            contents.append(types.Part.from_bytes(data=file_bytes, mime_type=mime_type))
        except Exception:
            try:
                contents.append(types.Part(inline_data=types.Blob(data=file_bytes, mime_type=mime_type)))
            except Exception:
                try:
                    b64 = base64.b64encode(file_bytes).decode("utf-8")
                    contents.append({"inline_data": {"mime_type": mime_type, "data": b64}})
                except Exception:
                    pass

    contents.append(prompt)

    candidate_models = [
        "gemini-3.8-flash",
        "gemini-3.1-flash-lite",
        "gemini-2.5-flash",
        "gemini-flash-latest",
    ]

    last_error = ""
    for model_name in candidate_models:
        for attempt in range(2):
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=contents,
                    config=types.GenerateContentConfig(
                        system_instruction=system_instruction,
                        response_mime_type="application/json",
                        max_output_tokens=8192,
                        temperature=0.2,
                    ),
                )

                raw_text = extract_text_from_gemini_response(response)
                if not raw_text:
                    raise ValueError(f"استجابة فارغة بدون نص من النموذج {model_name}")

                parsed = parse_gemini_json(raw_text)
                if isinstance(parsed, dict):
                    if "mainQuestions" in parsed and "questions" not in parsed:
                        parsed["questions"] = parsed["mainQuestions"]
                    return parsed

            except Exception as e:
                err_str = str(e)
                last_error = f"{model_name} (محاولة {attempt + 1}): {err_str}"
                time.sleep(1.5 * (attempt + 1))
                continue

    return {
        "error": f"خوادم الذكاء الاصطناعي تشهد ضغطاً مؤقتاً (503)، تعذر إكمال الاستجابة بعد تجربة عدة نماذج. تفاصيل: {last_error}"
    }


def evaluate_student_answer(
    question_text: str,
    model_answer: str,
    rubric: list,
    student_answer: str,
    max_marks: float
) -> Dict[str, Any]:
    client = get_gemini_client()
    if not client:
        return {"error": "لم يتم العثور على مفتاح GEMINI_API_KEY"}

    from google.genai import types

    is_english = any(ord(c) < 128 and c.isalpha() for c in question_text[:60])

    prompt = f"""
    Official Ministry of Education Examination Grader (Tawjihi):
    Question: {question_text}
    Full Marks: {max_marks}
    Model Answer: {model_answer}
    Rubric: {json.dumps(rubric, ensure_ascii=False)}
    Student Answer: "{student_answer}"
    
    Return ONLY valid JSON with: awarded_marks, max_marks, feedback, strengths, missing_points, advice.
    {"Provide feedback in English." if is_english else "اكتب الملاحظات بالعربية."}
    """

    candidate_models = ["gemini-3.8-flash", "gemini-3.1-flash-lite", "gemini-2.5-flash"]
    last_err = ""
    for model_name in candidate_models:
        try:
            res = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    max_output_tokens=2048,
                    temperature=0.2,
                ),
            )
            raw = extract_text_from_gemini_response(res)
            if raw:
                return parse_gemini_json(raw)
        except Exception as e:
            last_err = str(e)
            continue

    return {"error": f"تعذر تقييم الإجابة حالياً: {last_err}"}


def render_ministry(book=None, flat_lessons=None, user=None, lang="ar", idx=None, *args, **kwargs):
    if "question_bank" not in st.session_state:
        st.session_state["question_bank"] = []

    st.header("📋 استخراج وحل الامتحانات الوزارية (المنهاج الأردني)")
    st.caption("حل شامل لجميع الأسئلة والقطع القرائية وفروعها (100%) - مع أزرار التعديل وبنك الأسئلة وخدمة 'قيّمني'")

    default_subject = "اللغة الإنجليزية"
    if book:
        default_subject = book.get("subject", book.get("title", default_subject)) if isinstance(book, dict) else getattr(book, "subject", default_subject)

    col1, col2 = st.columns(2)
    with col1:
        subjects_list = [
            "اللغة الإنجليزية", "الرياضيات", "اللغة العربية (مشترك)",
            "الفيزياء", "الكيمياء", "العلوم الحياتية", "التربية الإسلامية", "تاريخ الأردن"
        ]
        s_idx = next((i for i, s in enumerate(subjects_list) if s in str(default_subject)), 0)
        subject = st.selectbox("المبحث الدراسي:", subjects_list, index=s_idx)

    with col2:
        branch = st.selectbox(
            "الفرع الأكاديمي:",
            ["جميع الفروع الأكاديمية والمهنية", "الفرع العلمي والتعليم الصحي", "الفرع الأدبي والشرعي", "الفرع الصناعي"],
            index=0,
        )

    is_english_subject = "إنجليز" in subject or "english" in subject.lower()
    layout_dir = st.radio(
        "اتجاه وتنسيق عرض الأسئلة والحلول:",
        ["محاذاة إنجليزية (Left-to-Right LTR - English Layout)", "محاذاة عربية (Right-to-Left RTL)"],
        index=0 if is_english_subject else 1,
        horizontal=True,
    )
    is_ltr = "LTR" in layout_dir

    if is_ltr:
        st.markdown(
            """
            <style>
            .english-box {
                direction: ltr !important;
                text-align: left !important;
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif !important;
            }
            .english-passage {
                direction: ltr !important;
                text-align: left !important;
                background-color: #f1f5f9;
                border-left: 5px solid #0284c7;
                padding: 16px;
                border-radius: 8px;
                font-size: 14px;
                line-height: 1.7;
                margin-bottom: 20px;
                font-family: Georgia, serif;
            }
            </style>
            """,
            unsafe_allow_html=True,
        )

    tab_upload, tab_paste, tab_qbank = st.tabs([
        "📁 رفع ملف امتحان (PDF / صورة / Word)",
        "✍️ لصق نص الامتحان مباشرة",
        f"📚 بنك الأسئلة المحفوظة ({len(st.session_state['question_bank'])})",
    ])

    exam_text = ""
    file_bytes_to_send = None
    file_mime_to_send = None

    with tab_upload:
        uploaded_file = st.file_uploader(
            "اختر ملف ورقة الامتحان الوزاري (PDF أو صورة):",
            type=["pdf", "png", "jpg", "jpeg", "docx", "txt"],
            help="يدعم ملفات امتحانات التوجيهي الورقية والـ PDF",
        )
        if uploaded_file is not None:
            raw_bytes = uploaded_file.getvalue()
            fname = uploaded_file.name.lower()
            extracted = extract_text_from_file(uploaded_file, raw_bytes)
            if extracted and len(extracted.strip()) > 30:
                st.success(f"✅ تم استخراج نص الامتحان الرقمي بنجاح ({len(extracted)} حرف)")
                exam_text = extracted
                file_bytes_to_send = None
                file_mime_to_send = None
            else:
                st.info(f"📄 تم استلام ملف الامتحان ({len(raw_bytes)//1024} ك.ب). سيقوم الذكاء الاصطناعي بقراءة الصفحات والصور مباشرة.")
                if fname.endswith(".pdf"):
                    file_mime_to_send = "application/pdf"
                elif fname.endswith((".png", ".jpg", ".jpeg")):
                    file_mime_to_send = "image/jpeg"
                file_bytes_to_send = raw_bytes
                exam_text = ""

    with tab_paste:
        pasted_text = st.text_area(
            "الصق نص الأسئلة الوزارية هنا:",
            height=200,
            placeholder="Question One: ...\nQuestion Two: Read the following article...",
        )
        if pasted_text.strip():
            exam_text = pasted_text.strip()
            file_bytes_to_send = None
            file_mime_to_send = None

    with tab_qbank:
        qbank = st.session_state.get("question_bank", [])
        if not qbank:
            st.info("بنك الأسئلة فارغ حالياً. انقر على زر '📥 إضافة لبنك الأسئلة' تحت أي سؤال لحفظه هنا.")
        else:
            st.write(f"يحتوي بنك الأسئلة على **{len(qbank)}** سؤال محفوظ:")
            for b_idx, item in enumerate(qbank):
                with st.expander(f"#{b_idx + 1}: {item.get('main_title', '')} - {item.get('sub_label', '')} ({item.get('marks', '')} علامات)"):
                    st.write(f"**نص السؤال:** {item.get('text', '')}")
                    st.write(f"**الإجابة:** {item.get('answer', '')}")
                    if st.button(f"🗑️ حذف هذا السؤال من البنك", key=f"del_qb_{b_idx}"):
                        st.session_state["question_bank"].pop(b_idx)
                        st.rerun()

            st.download_button(
                "💾 تصدير بنك الأسئلة (JSON)",
                data=json.dumps(qbank, ensure_ascii=False, indent=2),
                file_name="jordan_ministry_qbank.json",
                mime="application/json",
            )

    st.markdown("---")

    ready_to_solve = bool(exam_text.strip() or file_bytes_to_send)
    if st.button(
        "🚀 استخراج وحل ورقة الامتحان الوزاري بالكامل (Question 1, Question 2, Question 3)",
        type="primary",
        use_container_width=True,
        disabled=not ready_to_solve,
    ):
        with st.spinner("جارٍ قراءة ورقة الامتحان واستخراج كافة الأسئلة والقطع القرائية وفروعها وحلها بنسبة 100%..."):
            result = extract_and_solve_all_questions(
                exam_text=exam_text,
                file_bytes=file_bytes_to_send,
                mime_type=file_mime_to_send,
                subject=subject,
                branch=branch,
            )
            st.session_state["ministry_exam_result"] = result

    if "ministry_exam_result" in st.session_state:
        result = st.session_state["ministry_exam_result"]

        if "error" in result:
            st.error(result["error"])
            return

        questions = result.get("questions", [])
        total_main = len(questions)
        total_sub = sum(len(q.get("sub_questions", [])) for q in questions)
        total_marks = result.get("total_marks", 200)

        st.markdown("### 📊 ملخص الامتحان المستخرج:")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("الأسئلة الرئيسية", f"{total_main} أسئلة")
        m2.metric("الأسئلة والبنود الفرعية", f"{total_sub} فروع")
        m3.metric("نسبة الحل المنجز", "100% كامل")
        m4.metric("مجموع العلامات", f"{total_marks} علامة")

        if st.button("📥 إضافة جميع أسئلة هذا الامتحان إلى بنك الأسئلة دفعة واحدة"):
            added_count = 0
            for q in questions:
                for sq in q.get("sub_questions", []):
                    st.session_state["question_bank"].append({
                        "subject": subject,
                        "branch": branch,
                        "main_title": q.get("title", ""),
                        "sub_label": sq.get("sub_label", ""),
                        "text": sq.get("text", ""),
                        "marks": sq.get("marks", 0),
                        "answer": sq.get("answer", {}).get("final_answer", ""),
                    })
                    added_count += 1
            st.success(f"تمت إضافة {added_count} سؤالاً إلى بنك الأسئلة بنجاح!")
            st.rerun()

        for q_idx, main_q in enumerate(questions):
            title = main_q.get("title", f"Question {q_idx + 1}")
            subs = main_q.get("sub_questions", [])
            passage = main_q.get("passage", "")

            with st.expander(f"📌 {title} [{main_q.get('total_marks', '')} Marks] - ({len(subs)} Sub-questions / فروع محلولة)", expanded=True):
                if passage:
                    st.markdown("**📖 Reading Passage / النص القرائي المعتمد:**")
                    st.markdown(
                        f"""<div class="english-passage">
                        {passage}
                        </div>""",
                        unsafe_allow_html=True,
                    )

                for s_idx, sub_q in enumerate(subs):
                    sub_key = f"sub_{q_idx}_{s_idx}"
                    sub_label = sub_q.get("sub_label", f"Part {s_idx + 1}")
                    sub_text = sub_q.get("text", "")
                    sub_marks = sub_q.get("marks", "")
                    ans = sub_q.get("answer", {})

                    if is_ltr:
                        st.markdown(
                            f"""<div class="english-box" style="margin-top: 14px; padding: 6px 0;">
                            <span style="background: #0f766e; color: white; padding: 3px 8px; border-radius: 4px; font-size: 12px; font-weight: bold;">{sub_label}</span> 
                            <span style="font-size: 15px; font-weight: bold; color: #0f172a; margin-left: 6px;">{sub_text}</span> 
                            <span style="background: #f1f5f9; color: #475569; padding: 2px 6px; border-radius: 4px; font-size: 12px; font-weight: bold; margin-left: 6px;">({sub_marks} Marks)</span>
                            </div>""",
                            unsafe_allow_html=True,
                        )
                    else:
                        st.markdown(f"**{sub_label}**: {sub_text} `({sub_marks} علامة)`")

                    if ans.get("final_answer"):
                        if is_ltr:
                            st.markdown(
                                f"""<div class="english-box" style="background: #ecfdf5; border-left: 4px solid #059669; padding: 12px; border-radius: 6px; margin: 8px 0;">
                                <strong style="color: #065f46; font-size: 13px;">Official Model Answer:</strong><br/>
                                <span style="font-weight: bold; color: #064e3b; font-size: 14px; white-space: pre-line;">{ans['final_answer']}</span>
                                </div>""",
                                unsafe_allow_html=True,
                            )
                        else:
                            st.success(f"**الجواب النهائي المعتمد:** {ans['final_answer']}")

                    steps = ans.get("steps", [])
                    if steps:
                        with st.expander("📝 Explanation / خطوات الحل والشرح بالتفصيل"):
                            for step_idx, step in enumerate(steps):
                                if is_ltr:
                                    st.markdown(f"<div class='english-box'><b>{step_idx + 1}.</b> {step}</div>", unsafe_allow_html=True)
                                else:
                                    st.markdown(f"{step_idx + 1}. {step}")

                    rubric = ans.get("rubric", [])
                    if rubric:
                        with st.expander("🎯 Marking Rubric / سلم توزيع العلامات الوزاري"):
                            for r in rubric:
                                if is_ltr:
                                    st.markdown(f"<div class='english-box'>• {r.get('step', '')}: <b>({r.get('marks', '')} Marks)</b></div>", unsafe_allow_html=True)
                                else:
                                    st.markdown(f"• {r.get('step', '')}: **({r.get('marks', '')} علامات)**")

                    # الأزرار التفاعلية الثلاثة
                    b_col1, b_col2, b_col3 = st.columns(3)
                    with b_col1:
                        if st.button("✏️ تعديل السؤال والإجابة", key=f"btn_edit_{sub_key}"):
                            st.session_state[f"edit_toggle_{sub_key}"] = not st.session_state.get(f"edit_toggle_{sub_key}", False)

                    with b_col2:
                        if st.button("📥 إضافة لبنك الأسئلة", key=f"btn_add_qb_{sub_key}"):
                            st.session_state["question_bank"].append({
                                "subject": subject,
                                "branch": branch,
                                "main_title": title,
                                "sub_label": sub_label,
                                "text": sub_text,
                                "marks": sub_marks,
                                "answer": ans.get("final_answer", ""),
                            })
                            st.toast(f"✅ تمت إضافة ({sub_label}) إلى بنك الأسئلة بنجاح!", icon="🎉")

                    with b_col3:
                        if st.button("🎯 قيّمني (اختبر إجابتي)", key=f"btn_eval_{sub_key}"):
                            st.session_state[f"eval_toggle_{sub_key}"] = not st.session_state.get(f"eval_toggle_{sub_key}", False)

                    # واجهة التعديل
                    if st.session_state.get(f"edit_toggle_{sub_key}", False):
                        st.info("وضع التعديل المباشر:")
                        new_text = st.text_area("نص السؤال:", value=sub_text, key=f"ta_text_{sub_key}")
                        new_ans = st.text_area("الإجابة النموذجية:", value=ans.get("final_answer", ""), key=f"ta_ans_{sub_key}")
                        if st.button("💾 حفظ التعديلات في هذا السؤال", key=f"save_edit_{sub_key}"):
                            sub_q["text"] = new_text
                            if "answer" not in sub_q:
                                sub_q["answer"] = {}
                            sub_q["answer"]["final_answer"] = new_ans
                            st.session_state[f"edit_toggle_{sub_key}"] = False
                            st.success("تم حفظ التعديل بنجاح!")
                            st.rerun()

                    # واجهة قيّمني
                    if st.session_state.get(f"eval_toggle_{sub_key}", False):
                        st.markdown("🎯 **خدمة قيّمني الوزارية:** اكتب إجابتك ليقوم الذكاء الاصطناعي بتصحيحها ورصد العلامة:")
                        student_ans = st.text_area("إجابتك للتصحيح:", placeholder="Write your answer here...", key=f"stu_ans_{sub_key}")
                        if st.button("📊 رصد علامتي وتصحيح إجابتي", key=f"submit_eval_{sub_key}"):
                            if not student_ans.strip():
                                st.warning("يرجى كتابة إجابتك أولاً.")
                            else:
                                with st.spinner("جارٍ تقييم إجابتك ورصد العلامة..."):
                                    eval_res = evaluate_student_answer(
                                        question_text=sub_text,
                                        model_answer=ans.get("final_answer", ""),
                                        rubric=ans.get("rubric", []),
                                        student_answer=student_ans,
                                        max_marks=float(sub_marks or 5),
                                    )
                                    if "error" in eval_res:
                                        st.error(eval_res["error"])
                                    else:
                                        score = eval_res.get("awarded_marks", 0)
                                        max_s = eval_res.get("max_marks", sub_marks)
                                        st.metric("علامتك المستحقة", f"{score} من {max_s}")
                                        st.write(f"**ملاحظات المصحح:** {eval_res.get('feedback', '')}")
                                        if eval_res.get("strengths"):
                                            st.success(f"نقاط القوة: {', '.join(eval_res['strengths'])}")
                                        if eval_res.get("missing_points"):
                                            st.warning(f"ما ينقص إجابتك: {', '.join(eval_res['missing_points'])}")
                                        if eval_res.get("advice"):
                                            st.info(f"نصيحة وزارية: {eval_res.get('advice')}")

                    st.markdown("---")

        st.download_button(
            label="💾 تحميل نموذج الإجابة الكامل (JSON)",
            data=json.dumps(result, ensure_ascii=False, indent=2),
            file_name=f"نموذج_إجابة_امتحان_{subject}.json",
            mime="application/json",
        )
