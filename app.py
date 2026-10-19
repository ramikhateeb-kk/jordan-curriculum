import io
import json
import re
import streamlit as st
from PIL import Image
from gtts import gTTS
from google.genai import types

import accounts as acc
import auth_ui
import catalog
import companion
import explain_ctx
import ingest
import profile_ctx
from config import GEMINI_MODEL
from exam import render_exam_builder
from lesson_plan import render_lesson_plan_builder
from semester_plan import render_semester_plan_builder
from content_analysis import render_content_analysis_builder
from attendance import render_attendance_builder
from marks_book import render_marks_book_builder
from ministry import render_ministry
from qbank_manager import render_qbank_builder
from quiz import render_quiz
from rag import answer, get_client, load_index, select_context
from slides import render_slides_builder
from teach_help import render_teach_help_builder

st.set_page_config(page_title="مساعد المنهاج الأردني", page_icon="📚", layout="centered")

st.markdown("""
<style>
html, body, .stApp, [data-testid="stMarkdownContainer"] { direction: rtl; text-align: right; }
[data-testid="stSelectbox"] div, textarea, input { direction: rtl; text-align: right; }

.hero {
    background: linear-gradient(120deg, #1e3a5f 0%, #2e6f5e 100%);
    padding: 28px 24px; border-radius: 18px; margin-bottom: 20px; text-align: center;
    box-shadow: 0 6px 18px rgba(0,0,0,.12);
}
.hero h1 { color: #fff; margin: 0 0 6px 0; font-size: 1.7rem; }
.hero p { color: #dfe9e6; margin: 0; font-size: .95rem; }

/* شريط الإدخال الموحّد (إرفاق + نص + ميكروفون) */
[data-testid="stChatInput"] { direction: ltr; }
[data-testid="stChatInput"] > div {
    border-radius: 28px; border: 1px solid #e2e2e2; background: #fff;
    box-shadow: 0 2px 10px rgba(0,0,0,.08);
}
[data-testid="stChatInput"] textarea { direction: rtl; text-align: right; }

div[data-testid="stButton"] > button {
    width: 100%; padding: 12px 10px; border-radius: 14px; border: 1px solid #e2e2e2;
    background: #ffffff; font-size: 1.05rem; font-weight: 600; color: #1e3a5f;
    box-shadow: 0 2px 8px rgba(0,0,0,.06); transition: all .15s ease;
}
div[data-testid="stButton"] > button:hover {
    border-color: #2e6f5e; box-shadow: 0 4px 14px rgba(46,111,94,.25); transform: translateY(-2px);
    color: #2e6f5e;
}
div[data-testid="stButton"] > button[kind="primary"] {
    background: linear-gradient(120deg, #2e6f5e, #1e3a5f); color: #fff; border: none;
}
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="hero">
  <h1>📚 مساعد المنهاج الأردني</h1>
  <p>اختر صفّك ومادتك، واحصل على شرح أو تقييم من الكتاب مباشرة</p>
</div>
""", unsafe_allow_html=True)


def clean_markdown_for_speech(text):
    """تنظيف النص من رموز التنسيق لضمان القراءة الصوتية الواضحة"""
    text = re.sub(r'\*+|\#+|`+|_+', '', text)
    text = re.sub(r'\[.*?\]\(.*?\)', '', text)
    text = re.sub(r'\n+', ' ', text)
    return text.strip()


def text_to_speech(text, lang='ar'):
    """تحويل النص إلى صوت مسموع بصوت المعلم (نبرة ذكر أعمق وأبطأ)"""
    try:
        clean_text = clean_markdown_for_speech(text)
        if not clean_text:
            return None
        clean_text = clean_text[:1000]
        
        tts = gTTS(text=clean_text, lang=lang, slow=False)
        fp = io.BytesIO()
        tts.write_to_fp(fp)
        fp.seek(0)
        return fp
    except Exception as e:
        st.error(f"خطأ في توليد الصوت: {e}")
        return None


@st.cache_data(ttl=60, show_spinner=False)
def books_cached():
    return catalog.list_books()


@st.cache_data(ttl=60, show_spinner=False)
def tracks_cached():
    return catalog.list_tracks()


try:
    books = books_cached()
    tracks = tracks_cached()
except Exception as e:  # noqa: BLE001
    st.error(f"تعذّر قراءة جدول الكتب: {e}")
    st.stop()

user = auth_ui.require_login()
role = user["role"]   # "student" | "teacher" | "supervisor" | "admin"

if role == "admin":
    with st.sidebar.expander("🤖 حالة نماذج الذكاء الاصطناعي"):
        import rag as _rag
        for _m, _st in _rag.model_status():
            st.write(f"{_m}: {_st}")
        st.caption(f"آخر نموذج أجاب: {_rag.LAST_USED[0] or '—'} — يُضاف نموذج بديل بمتغير GEMINI_FALLBACK_MODELS.")
    admin_view = st.sidebar.radio("عرض المدير", ["📚 استخدام المنصة", "👑 إدارة الحسابات"])
    if admin_view == "👑 إدارة الحسابات":
        auth_ui.render_admin_accounts_panel(user)
        st.stop()

scope = acc.teacher_scope(user["id"]) if role in ("teacher", "supervisor") else []
grade_options = acc.grade_options(user, books, scope)
if not grade_options:
    msg = ("لم تُحدَّد لصفك مواد بعد." if role == "student" else
          "لم تُعتمد لك أي مباحث/صفوف بعد. يرجى التواصل مع الإدارة.")
    st.info(msg)
    st.stop()

# ---- الصف → الفصل → التخصص (للصفوف 10-12) → المادة
c1, c2 = st.columns(2)
if role == "student":
    grade = user["grade"]
    c1.markdown(f"**الصف الدراسي:** الصف {grade}")
else:
    grade = c1.selectbox("الصف الدراسي", grade_options, format_func=lambda g: f"الصف {g}")
sem = c2.selectbox("الفصل الدراسي", [1, 2], format_func=lambda s: "الأول" if s == 1 else "الثاني")

track_id, track = None, ""
grade_tracks = acc.tracks_for_user(user, tracks, grade, scope=scope)
if grade_tracks:
    if role == "student":
        track_id, track = grade_tracks[0]["id"], grade_tracks[0]["name"]
        st.markdown(f"**التخصص:** {track}")
    else:
        track = st.selectbox("التخصص", [t["name"] for t in grade_tracks], key=f"track_{grade}")
        track_id = next(t["id"] for t in grade_tracks if t["name"] == track)
elif role == "student" and catalog.tracks_of_grade(tracks, grade):
    st.info("لم يُحدَّد تخصصك بعد. يرجى التواصل مع الإدارة لإكمال بيانات حسابك.")
    st.stop()
elif role != "student" and catalog.tracks_of_grade(tracks, grade):
    st.info("لا توجد تخصصات معتمدة لك في هذا الصف. يرجى التواصل مع الإدارة.")
    st.stop()

pool = acc.books_in_context(user, books, grade, track_id, scope)
subjects = [b for b in pool if b["semester"] == sem and not catalog.is_companion(b)]
if not subjects:
    st.info("لم تُضف مواد هذا الصف/التخصص/الفصل بعد، أو لا تملك صلاحية عليها.")
    st.stop()

# المواد المشتركة بين تخصصات الصف تُوسَم بعلامة كي يعرف المستخدم أنها ليست خاصة بتخصصه
subject_labels = {b["subject"]: b["subject"] + (" (مشترك)" if track_id and catalog.is_common(b) else "")
                  for b in subjects}
subject = st.selectbox("المادة", list(subject_labels), format_func=lambda s: subject_labels[s])
book = next(b for b in subjects if b["subject"] == subject)
slug = book["slug"]
lang = book["lang"]   # "ar" | "en" — كتب الإنجليزية تُنتَج لها خطط وتحليل بالإنجليزية واتجاه LTR
ctx = profile_ctx.build(user, grade, track, subject, sem)
grade_label = f"الصف {grade}" + (f" {track}" if track else "")

try:
    with st.spinner("جارٍ تجهيز الكتاب..."):
        if ingest.ensure_index(book):
            load_index.cache_clear()
except RuntimeError as e:
    st.error(str(e))
    st.stop()

idx = load_index(grade, sem, slug)
if idx is None:
    st.error("تعذّرت معالجة الكتاب.")
    st.stop()

meta = idx[2]
if meta.get("scanned_ratio", 0) > 0.3:
    st.warning(
        f"⚠️ نحو {round(meta['scanned_ratio']*100)}% من صفحات هذا الكتاب صور بلا نص قابل للقراءة "
        "(كتاب ممسوح ضوئيًا)، لذلك قد تكون الإجابات ناقصة في تلك الأجزاء.")

units = catalog.compute_units(book["units"], book["page_offset"], meta.get("pages", 0))
flat_lessons = [
    {"label": f"{u['title'].split(':')[0]}: {l['title']}", "title": l["title"], "start": l["start"],
     "end": l["end"], "unit_title": u["title"]}
    for u in units for l in u["lessons"]
]
companion.attach(books, book, flat_lessons, lang)   # lang لكل درس + ربط تمارين الكتاب المرافق (إن وُجد)
if not units:
    st.info("لم تُدخل وحدات ودروس هذا الكتاب بعد من صفحة الإدارة.")

if "action" not in st.session_state or st.session_state.get("action_book") != slug:
    st.session_state.action = None
    st.session_state.action_book = slug

st.markdown("#### ماذا تريد أن تفعل؟")
if role == "student":
    b1, b2, b3 = st.columns(3)
    if b1.button("📖\n\nاشرح لي"):
        st.session_state.action = "explain"
    if b2.button("📝\n\nقيّمني"):
        st.session_state.action = "quiz"
    if b3.button("📜\n\nأسئلة وزارية"):
        st.session_state.action = "ministry"
else:
    r1_col1, r1_col2, r1_col3 = st.columns(3)
    if r1_col1.button("🧾\n\nإنشاء اختبار"):
        st.session_state.action = "exam"
    if r1_col2.button("🗒️\n\nخطة درس"):
        st.session_state.action = "plan"
    if r1_col3.button("📅\n\nالخطة الفصلية"):
        st.session_state.action = "semester_plan"

    r2_col1, r2_col2, r2_col3 = st.columns(3)
    if r2_col1.button("📊\n\nتحليل المحتوى"):
        st.session_state.action = "content_analysis"
    if r2_col2.button("🧑‍🏫\n\nمساعد الشرح"):
        st.session_state.action = "teach_help"
    if r2_col3.button("💻\n\nعرض تقديمي"):
        st.session_state.action = "slides"

    r3_col1, r3_col2, r3_col3 = st.columns(3)
    if r3_col1.button("📋\n\nدفتر الحضور والغياب"):
        st.session_state.action = "attendance"
    if r3_col3.button("📒\n\nدفتر العلامات"):
        st.session_state.action = "marks_book"
    if role in ("supervisor", "admin"):   # المعلم العادي لا يملك صلاحية بنك الأسئلة
        if r3_col2.button("🏦\n\nبنك الأسئلة"):
            st.session_state.action = "qbank"

    r4_col1, _r4b, _r4c = st.columns(3)
    if r4_col1.button("📜\n\nأسئلة وزارية"):
        st.session_state.action = "ministry"

action = st.session_state.action
if not action:
    st.stop()

st.divider()

# ---- الحساب التجريبي: الخدمات المقفلة
TRIAL_FEATURE_OF = {"exam": "exam", "plan": "lesson_plan", "semester_plan": "semester_plan",
                    "content_analysis": "content_analysis", "teach_help": "teach_help", "slides": "slides",
                    "attendance": "attendance", "marks_book": "marks_book"}
if acc.is_trial(user) and action in TRIAL_FEATURE_OF and acc.trial_remaining(user, TRIAL_FEATURE_OF[action]) == 0:
    st.warning("🔒 هذه الخدمة غير متاحة في الحساب التجريبي (أو استنفدت حصتك منها). "
               "للحصول على كامل الميزات يرجى التواصل مع الإدارة لترقية حسابك.")
    st.stop()


@st.cache_data(ttl=7 * 24 * 3600, max_entries=500, show_spinner=False)
def cached_answer(book_key, topic, pages, request, _idx, extras_json="", book_lang="ar"):
    ctx_pages = select_context(_idx, f"{topic} {request}".strip(), pages)
    extras = json.loads(extras_json) if extras_json else None
    return answer(get_client(), request, ctx_pages, extras, book_lang), ctx_pages


# ---------------------------------------------------------------- اشرح لي
# ---- اتجاه النص في «اشرح لي» و«قيّمني»: الإنجليزية من اليسار لليمين والعربية من اليمين لليسار
# الواجهة عمومًا RTL؛ هنا نجعل اتجاه الأساس حسب لغة الكتاب (إنجليزي ← LTR)، وكل فقرة/خيار/سطر يتبع لغته تلقائيًا
# (unicode-bidi: plaintext) فتبقى الشروح العربية لكتاب إنجليزي مضبوطة أيضًا. يُطبَّق على كل ما يلي العلامة في الصفحة.
if action in ("explain", "quiz"):
    _base, _side = ("ltr", "left") if lang == "en" else ("rtl", "right")
    _S = ':is([data-testid="stElementContainer"], .element-container):has(#bidi-marker) ~ ' \
         ':is([data-testid="stElementContainer"], .element-container)'
    st.markdown(
        f"""<div id="bidi-marker"></div><style>
{_S}, {_S} * {{ direction: {_base} !important; }}
{_S} :is(p, li, h1, h2, h3, h4, h5, h6, td, th, blockquote, label) {{ unicode-bidi: plaintext !important; text-align: start !important; }}
{_S} :is(textarea, input) {{ direction: {_base} !important; text-align: {_side} !important; unicode-bidi: plaintext !important; }}
.stApp:has(#bidi-marker) [data-testid="stChatInput"] textarea {{ direction: {_base} !important; unicode-bidi: plaintext !important; text-align: start !important; }}
</style>""", unsafe_allow_html=True)

if action == "explain":
    ALL_BOOK, WHOLE_UNIT = "كل الكتاب", "الوحدة كاملة"
    pages, topic, unit_name = None, "", ALL_BOOK
    scope_titles = []          # دروس النطاق المختار (لجلب تمارين الأنشطة والأسئلة الوزارية وشرح القواعد)
    if units:
        unit_titles = [ALL_BOOK] + [u["title"] for u in units]
        unit_name = st.selectbox("الوحدة", unit_titles)
        if unit_name != ALL_BOOK:
            unit = units[unit_titles.index(unit_name) - 1]
            lesson_titles = [WHOLE_UNIT] + [l["title"] for l in unit["lessons"]]
            lesson = st.selectbox("الدرس", lesson_titles)
            if lesson == WHOLE_UNIT:
                pages, topic = (unit["start"], unit["end"]), unit_name
                scope_titles = [x["title"] for x in unit["lessons"]]
            else:
                l = unit["lessons"][lesson_titles.index(lesson) - 1]
                pages, topic = (l["start"], l["end"]), lesson
                scope_titles = [lesson]
            
            max_allowed_pages = 20
            page_count = pages[1] - pages[0] + 1
            if page_count > max_allowed_pages:
                st.info(f"💡 تم تحديد الاستعلام بأول {max_allowed_pages} صفحة من هذا الدرس لضمان دقة الشرح.")
                pages = (pages[0], pages[0] + max_allowed_pages - 1)
            
            st.caption(f"صفحات الملف المحددة للشرح: {pages[0]} – {pages[1]}")

    # إعدادات الشرح (فوق شريط الإدخال)
    col_lang, col_tts = st.columns(2)
    with col_lang:
        lang_choice = st.radio("لغة الشرح وقراءة الصوت:", ["العربية", "English"], horizontal=True)
        lang_code = 'ar' if lang_choice == "العربية" else 'en'
    with col_tts:
        enable_tts = st.checkbox("🔊 تفعيل قراءة الإجابة بصوت المعلم", value=True)

    # سجل المحادثة (للعرض فقط؛ لا يُرسل إلى Gemini حتى تبقى الأسئلة قابلة للتخزين المؤقت)
    history = st.session_state.setdefault("explain_chat", [])
    if history and st.button("🗑️ مسح المحادثة", key="explain_clear_chat"):
        history.clear()
        st.rerun()

    for msg in history:
        with st.chat_message(msg["role"]):
            if msg.get("image") is not None:
                st.image(msg["image"], width=260)
            st.markdown(msg["content"])
            if msg.get("ctx_pages"):
                with st.expander("صفحات الكتاب المستخدمة في الإجابة"):
                    for p in msg["ctx_pages"]:
                        st.caption(f"صفحة {p['page']}")
                        st.write(p["text"])
            if msg.get("audio"):
                st.audio(msg["audio"], format="audio/mp3")

    # ---- شريط الإدخال الموحّد: + (صورة/ملف نصي) | نص | 🎤 (تسجيل صوتي)
    prompt = st.chat_input(
        "اكتب سؤالك هنا…",
        accept_file=True,
        file_type=["png", "jpg", "jpeg", "txt"],
        accept_audio=True,
        key="explain_chat_input",
    )

    if prompt:
        typed_text = (getattr(prompt, "text", "") or "").strip()
        files = list(getattr(prompt, "files", None) or [])
        audio_file = getattr(prompt, "audio", None)

        uploaded_image, file_text_prompt, input_error = None, "", None

        # المرفقات
        for f in files:
            if f.size > 5 * 1024 * 1024:
                input_error = "❌ حجم الملف كبير جداً. الحد الأقصى المسموح به هو 5MB."
                break
            if f.type == "text/plain":
                try:
                    file_text_prompt = f.read().decode("utf-8")[:2000]
                except Exception as e:  # noqa: BLE001
                    input_error = f"تعذر قراءة النص: {e}"
            else:
                try:
                    uploaded_image = Image.open(f)
                except Exception as e:  # noqa: BLE001
                    input_error = f"تعذر فتح الصورة: {e}"

        # التسجيل الصوتي → نص (نفس طريقة التفريغ السابقة)
        voice_text = ""
        if audio_file is not None and not input_error:
            with st.spinner("جارٍ تحويل كلامك الصوتي إلى نص..."):
                try:
                    audio_part = types.Part.from_bytes(data=audio_file.getvalue(), mime_type="audio/wav")
                    auth_ui.require_quota_or_stop(user)
                    client = get_client()   # يجب الاحتفاظ بالمتغير وإلا يُغلق الاتصال أثناء الطلب
                    res = client.models.generate_content(
                        model=GEMINI_MODEL,
                        contents=[
                            "أنت محول صوت إلى نص. قم بتفريغ المقطع الصوتي حرفياً باللغة العربية بدون إضافة أي مقدمات:",
                            audio_part
                        ]
                    )
                    if res.text:
                        voice_text = re.sub(r'^(النص|التفريغ|الكلام المنطوق):?\s*', '', res.text.strip(),
                                            flags=re.IGNORECASE).strip(' "\'')
                except Exception as e:  # noqa: BLE001
                    input_error = f"حدث خطأ أثناء قراءة الصوت: {e}"

        final_prompt = "\n".join(t for t in (typed_text, voice_text, file_text_prompt) if t).strip()

        if input_error:
            st.error(input_error)
        elif not final_prompt and not uploaded_image:
            st.warning("يرجى كتابة سؤال، التسجيل بصوتك، أو رفع صورة/ملف تحتوي على السؤال أولاً.")
        else:
            history.append({"role": "user", "content": final_prompt or "📷 (صورة بدون نص)",
                            "image": uploaded_image})
            with st.chat_message("user"):
                if uploaded_image is not None:
                    st.image(uploaded_image, width=260)
                st.markdown(final_prompt or "📷 (صورة بدون نص)")

            with st.chat_message("assistant"):
                with st.spinner("جارٍ إعداد الإجابة للشرح من المنهاج..."):
                    try:
                        if uploaded_image:
                            auth_ui.require_quota_or_stop(user)
                            sys_instruction = "أنت معلم خبير أردني. اشرح وحل الأسئلة الموضحة في الصورة بأسلوب تعليمي واصل ومبسط بلسان معلم ذكر."
                            if lang_code == 'en':
                                sys_instruction = "You are an expert male tutor. Solve and explain the questions in the attached image clearly."
                            prompt_text = final_prompt if final_prompt else "قم بحل وشرح الأسئلة الموضحة في الصورة."
                            client = get_client()
                            response = client.models.generate_content(
                                model=GEMINI_MODEL,
                                contents=[uploaded_image, prompt_text],
                                config=types.GenerateContentConfig(system_instruction=sys_instruction, temperature=0.3)
                            )
                            text, ctx_pages = response.text, []
                        else:
                            auth_ui.require_quota_or_stop(user)   # ملاحظة: يُحتسب لكل سؤال حر؛ راجع تعليق التكامل
                            extras, gblocks = explain_ctx.build(slug, idx, flat_lessons, scope_titles, user, lang)
                            text, ctx_pages = cached_answer((grade, sem, slug, book["pdf_url"]), topic, pages, final_prompt, idx,
                                                            json.dumps(extras, ensure_ascii=False, sort_keys=True), lang)
                            for g in gblocks:                      # شرح القاعدة الخارجي يُدرَج حرفيًا مكان العلامة
                                text = text.replace(f"<<GRAMMAR:{g['id']}>>", g["md"])
                            text = re.sub(r"<<GRAMMAR:\d+>>", "", text)

                        st.markdown(text)
                        if ctx_pages:
                            with st.expander("صفحات الكتاب المستخدمة في الإجابة"):
                                for p in ctx_pages:
                                    st.caption(f"صفحة {p['page']}")
                                    st.write(p["text"])

                        audio_bytes = None
                        if enable_tts and text:
                            audio_fp = text_to_speech(text, lang=lang_code)
                            if audio_fp:
                                audio_bytes = audio_fp.getvalue()
                                st.audio(audio_bytes, format="audio/mp3")

                        history.append({"role": "assistant", "content": text,
                                        "ctx_pages": ctx_pages, "audio": audio_bytes})
                        del history[:-10]   # نحتفظ بآخر 10 رسائل فقط لتوفير الذاكرة
                    except Exception as e:  # noqa: BLE001
                        st.error(f"حدث خطأ أثناء معالجة الطلب: {e}")

# ---------------------------------------------------------------- قيّمني
elif action == "quiz":
    if not flat_lessons:
        st.info("لم تُدخل دروس هذا الكتاب بعد.")
    else:
        selected = st.multiselect(
            "اختر درسًا أو أكثر (يمكن الجمع بين دروس من وحدات مختلفة)",
            [l["label"] for l in flat_lessons], default=[flat_lessons[0]["label"]])
        chosen = [l for l in flat_lessons if l["label"] in selected]
        render_quiz(idx, slug, chosen)

# ---------------------------------------------------------------- إنشاء اختبار (المعلم)
elif action == "exam":
    render_exam_builder(idx, slug, subject, sem, flat_lessons, ctx=ctx, user=user)

# ---------------------------------------------------------------- خطة الدرس (المعلم)
elif action == "plan":
    render_lesson_plan_builder(idx, slug, subject, flat_lessons, user=user, ctx=ctx, lang=lang)

# ---------------------------------------------------------------- الخطة الفصلية للمنهاج كاملًا (المعلم)
elif action == "semester_plan":
    if not units:
        st.info("لم تُدخل وحدات هذا الكتاب بعد.")
    else:
        render_semester_plan_builder(idx, slug, subject, units, flat_lessons=flat_lessons, user=user, ctx=ctx,
                                     lang=lang)

# ---------------------------------------------------------------- تحليل المحتوى للمنهاج كاملًا (المعلم)
elif action == "content_analysis":
    if not units:
        st.info("لم تُدخل وحدات هذا الكتاب بعد.")
    else:
        render_content_analysis_builder(idx, slug, subject, units, user=user, ctx=ctx, lang=lang)

# ---------------------------------------------------------------- العرض التقديمي (PPTX)
elif action == "slides":
    render_slides_builder(idx, slug, subject, flat_lessons, user=user)

# ---------------------------------------------------------------- مساعد الشرح (دليل المعلم)
elif action == "teach_help":
    render_teach_help_builder(idx, slug, subject, flat_lessons, grade_label=grade_label, user=user)

# ---------------------------------------------------------------- بنك الأسئلة (المعلم)
elif action == "attendance":
    render_attendance_builder(user, ctx=ctx)

elif action == "marks_book":
    render_marks_book_builder(user, ctx=ctx)

elif action == "qbank":
    if role not in ("supervisor", "admin"):
        st.error("لا تملك صلاحية الوصول إلى بنك الأسئلة.")
        st.stop()
    render_qbank_builder(idx, slug, subject, flat_lessons,
                        subject_scope=acc.qbank_subject_scope(user), user=user)

elif action == "ministry":
    render_ministry(book, flat_lessons, user, lang, idx)

# ---------------------------------------------------------------- الشروط الاحتياطية
else:
    st.info("يرجى اختيار إجراء من القائمة أعلاه.")
