"""
ميزة (قيمني): أسئلة سؤالًا تلو الآخر من درس أو أكثر (حتى من وحدات مختلفة)، مع تقييم فوري.
لتقليل طلبات Gemini: تُخزَّن الأسئلة المولَّدة في قاعدة بيانات (qbank)، وقبل توليد أي سؤال جديد
يُفحص إن كان مخزَّنًا سلفًا لهذا الدرس ونوع السؤال، وتُختار الأسئلة عشوائيًا فلا يتكرر ترتيبها نفسه لكل طالب.
تقييم الإجابات الكتابية يستخدم الإجابة النموذجية والتوضيح المحفوظين فقط، دون إعادة إرسال نص الدرس، لتقليل التوكنز.
"""
import json
import random
import re

import streamlit as st
from google.genai import types

import qbank
from config import GEMINI_MODEL
from rag import get_client, select_context

QTYPES = {
    "اختيار من متعدد": "mcq",
    "صح أو خطأ": "tf",
    "أكمل الفراغ": "fill",
    "سؤال قصير": "short",
    "مختلط": "mixed",
}

SYSTEM = (
    "أنت معلم للمنهاج الأردني يضع أسئلة تقويمية دقيقة. التزم بالآتي بصرامة:\n"
    "1) استخدم فقط نص الكتاب المرفق، ولا تستخدم أي معلومة من خارجه، ولا تخترع تفاصيل ليست فيه.\n"
    "2) يجب أن تكون إجابة السؤال موجودة صراحة في النص المرفق، لا مُستنتجة أو مُخمَّنة.\n"
    "3) اكتب بالعربية الفصحى الواضحة، وضع رقم الصفحة التي أخذت منها السؤال بدقة.\n"
    "4) في الاختيار من متعدد اجعل الخيارات الثلاثة الخاطئة معقولة، لكن غير موجودة في النص كإجابة صحيحة.\n"
    "أعد JSON فقط بلا أي نص آخر."
)
GRADE_SYSTEM = (
    "أنت مصحّح دقيق. قارن إجابة الطالب بالإجابة النموذجية المعطاة فقط (لا مصدر آخر عندك). "
    "اقبل اختلاف الصياغة والمرادفات ما دام المعنى صحيحًا. أعد JSON فقط بلا أي نص آخر."
)

CONTEXT_BUDGET = 30000  # حد أقصى لطول نص الدرس المُرسَل عند توليد سؤال جديد (لا يُستخدم عند التصحيح)

SPECS = {
    "mcq": ('سؤال اختيار من متعدد بأربعة خيارات وإجابة صحيحة واحدة فقط',
            '{"type":"mcq","question":"...","options":["...","...","...","..."],'
            '"correct_index":0,"explanation":"...","page":12}'),
    "tf": ('عبارة يحكم عليها الطالب بالصواب أو الخطأ',
           '{"type":"tf","question":"عبارة ...","correct":true,"explanation":"...","page":12}'),
    "fill": ('سؤال أكمل الفراغ: جملة من الكتاب فيها فراغ واحد مكتوب ______ وإجابته كلمة أو عبارة قصيرة',
             '{"type":"fill","question":"... ______ ...","model_answer":"...","explanation":"...","page":12}'),
    "short": ('سؤال قصير يُجاب عنه بجملة أو جملتين',
              '{"type":"short","question":"...","model_answer":"...","explanation":"...","page":12}'),
}


def _json(client, system, prompt, temperature=0.4):
    for _ in range(2):
        try:
            r = client.models.generate_content(
                model=GEMINI_MODEL, contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system, temperature=temperature,
                    response_mime_type="application/json"))
            txt = re.sub(r"^```(?:json)?|```$", "", r.text.strip()).strip()
            return json.loads(txt)
        except Exception as e:  # noqa: BLE001
            print("خطأ في توليد/قراءة JSON:", e)
    return None


def _valid(q, qtype, ctx_pages):
    if not isinstance(q, dict) or not str(q.get("question", "")).strip():
        return False
    valid_pages = {p["page"] for p in ctx_pages}
    if q.get("page") is not None and int(q.get("page", -1)) not in valid_pages:
        return False  # رقم صفحة غير موجود فعلًا في النص المُرسَل: نرفض السؤال
    if qtype == "mcq":
        o = q.get("options")
        return isinstance(o, list) and len(o) == 4 and len(set(map(str, o))) == 4 \
            and isinstance(q.get("correct_index"), int) and 0 <= q["correct_index"] < 4
    if qtype == "tf":
        return isinstance(q.get("correct"), bool)
    return bool(str(q.get("model_answer", "")).strip())


def _generate(client, idx, slug, lesson, qtype, asked_texts):
    """يولّد سؤالًا جديدًا من نص الدرس، ويحفظه في قاعدة البيانات ليُعاد استخدامه لاحقًا.
    يعيد (السؤال، معرّفه الجديد في قاعدة البيانات أو None إن تعذّر الحفظ)."""
    desc, schema = SPECS[qtype]
    ctx_pages = select_context(idx, lesson["title"], (lesson["start"], lesson["end"]), max_chars=CONTEXT_BUDGET)
    if not ctx_pages:
        return None, None
    ctx = "\n\n".join(f"=== صفحة {p['page']} ===\n{p['text']}" for p in ctx_pages)
    asked = "\n".join(f"- {a}" for a in asked_texts) or "لا يوجد"
    prompt = (
        f"الدرس: {lesson['title']}\n\nنص من الكتاب (المصدر الوحيد المسموح به):\n{ctx}\n\n"
        f"أنشئ {desc}، اعتمادًا على هذا النص فقط.\n"
        f"لا تكرر هذه الأسئلة الموجودة سلفًا لهذا الدرس:\n{asked}\n\n"
        f"أعد JSON بهذا الشكل بالضبط:\n{schema}")
    for _ in range(2):
        q = _json(client, SYSTEM, prompt)
        if _valid(q, qtype, ctx_pages):
            q["type"] = qtype
            if qtype == "mcq":
                correct = str(q["options"][q["correct_index"]])
                opts = [str(o) for o in q["options"]]
                random.shuffle(opts)
                q["options"], q["correct_index"] = opts, opts.index(correct)
            new_id = None
            try:
                new_id = qbank.add_question(slug, lesson["start"], lesson["end"], qtype, q)
            except Exception as e:  # noqa: BLE001
                print("تعذّر حفظ السؤال في قاعدة البيانات:", e)  # لا نوقف التقييم بسبب هذا
            return q, new_id
    return None, None


def next_question(client, idx, slug, lessons, quiz):
    """يفحص أولًا قاعدة الأسئلة عبر كل الدروس المطلوبة معًا، ويختار سؤالًا غير مُستخدَم عشوائيًا إن وُجد.
    لا يُولَّد سؤال جديد بالذكاء الاصطناعي إلا إذا لم يبقَ أي سؤال غير مُستخدَم في البنك لهذه الدروس ونوع السؤال."""
    qtype = quiz["qtype"] if quiz["qtype"] != "mixed" else random.choice(["mcq", "tf", "fill", "short"])
    pool = []
    for lesson in lessons:
        bank = qbank.list_questions(slug, lesson["start"], lesson["end"], qtype)
        pool += [(lesson, qid, data) for qid, data in bank
                if qid not in quiz["asked_ids"] and data.get("question") not in quiz["asked_texts"]]
    if pool:
        lesson, qid, data = random.choice(pool)
        q = dict(data)
        q["_lesson"] = lesson["title"]
        quiz["asked_ids"].add(qid)
        return q
    for lesson in random.sample(lessons, len(lessons)):  # البنك فارغ لهذا النوع: نولّد سؤالًا جديدًا
        q, new_id = _generate(client, idx, slug, lesson, qtype, quiz["asked_texts"])
        if q:
            q["_lesson"] = lesson["title"]
            if new_id is not None:  # نستثنيه فورًا حتى لا يُعرَض مجددًا بوصفه "من البنك" في السؤال التالي
                quiz["asked_ids"].add(new_id)
            return q
    return None


def correct_text(q):
    if q["type"] == "mcq":
        return q["options"][q["correct_index"]]
    if q["type"] == "tf":
        return "صح" if q["correct"] else "خطأ"
    return q["model_answer"]


def grade(client, q, ans):
    """يعيد (الدرجة من 0 إلى 1، ملاحظة). الاختيار من متعدد وصح/خطأ محليًا بلا Gemini.
    الأسئلة الكتابية تُصحَّح بمقارنة إجابة الطالب بالإجابة النموذجية المحفوظة فقط (بلا إعادة إرسال نص الدرس)."""
    if q["type"] == "mcq":
        return (1.0 if ans == q["options"][q["correct_index"]] else 0.0), ""
    if q["type"] == "tf":
        return (1.0 if (ans == "صح") == q["correct"] else 0.0), ""
    prompt = (
        f"السؤال: {q['question']}\nالإجابة النموذجية: {q['model_answer']}\n"
        f"توضيح إضافي: {q.get('explanation', '')}\nإجابة الطالب: {ans}\n\n"
        "الدرجة: 1 إن كانت صحيحة (يُقبل اختلاف الصياغة والمرادفات مع بقاء المعنى صحيحًا)، "
        "0.5 إن كانت صحيحة جزئيًا أو ناقصة، 0 إن كانت خاطئة. "
        'أعد JSON: {"score": 1, "feedback": "ملاحظة قصيرة ومشجعة"}')
    r = _json(client, GRADE_SYSTEM, prompt, temperature=0) or {}
    try:
        score = float(r.get("score", 0))
    except (TypeError, ValueError):
        score = 0.0
    return max(0.0, min(1.0, score)), str(r.get("feedback", ""))


def render_quiz(idx, slug, lessons):
    """lessons: قائمة [{"title","start","end"}] اختارها الطالب، ويمكن أن تكون من وحدات مختلفة."""
    S = st.session_state
    if not lessons:
        st.info("اختر درسًا واحدًا على الأقل لتبدأ.")
        return

    sig = tuple(sorted((l["start"], l["end"]) for l in lessons))
    if S.get("quiz_sig") != sig:
        S.pop("quiz", None)
        S["quiz_sig"] = sig
    quiz = S.get("quiz")

    if quiz is None:
        st.subheader("اختبر نفسك")
        st.caption("الدروس المختارة: " + "، ".join(l["title"] for l in lessons))
        qt = st.selectbox("نوع الأسئلة", list(QTYPES))
        n = st.number_input("عدد الأسئلة", min_value=1, value=5, step=1)
        if st.button("ابدأ التقييم", type="primary"):
            S["quiz"] = {"qtype": QTYPES[qt], "n": int(n), "i": 0, "score": 0.0,
                         "asked_ids": set(), "asked_texts": [], "cur": None, "res": None, "hist": []}
            st.rerun()
        return

    if quiz["i"] >= quiz["n"]:
        pct = round(100 * quiz["score"] / quiz["n"]) if quiz["n"] else 0
        st.subheader("النتيجة النهائية")
        st.metric("الدرجة", f"{quiz['score']:g} / {quiz['n']}", f"{pct}%")
        if pct >= 85:
            st.success("ممتاز! مستواك رائع في هذه الدروس.")
        elif pct >= 60:
            st.info("جيد. راجع الأسئلة التي أخطأت فيها أدناه.")
        else:
            st.warning("تحتاج إلى مراجعة هذه الدروس، جرّب طلب شرحها ثم أعد التقييم.")
        with st.expander("مراجعة الأسئلة"):
            for k, h in enumerate(quiz["hist"], 1):
                icon = "✅" if h["score"] == 1 else ("🟡" if h["score"] > 0 else "❌")
                st.markdown(f"**{k}. {icon} {h['q']}**")
                st.write(f"إجابتك: {h['ans']}")
                st.write(f"الإجابة الصحيحة: {h['correct']}")
        if st.button("تقييم جديد"):
            S.pop("quiz", None)
            st.rerun()
        return

    client = get_client()
    if quiz["cur"] is None:
        with st.spinner("جارٍ إعداد السؤال..."):
            quiz["cur"] = next_question(client, idx, slug, lessons, quiz)
        if quiz["cur"] is None:
            st.error("تعذّر إعداد سؤال موثّق من نص الدرس. حاول مرة أخرى.")
            if st.button("إعادة المحاولة"):
                st.rerun()
            return
        quiz["asked_texts"].append(quiz["cur"]["question"])
    q = quiz["cur"]

    st.progress(quiz["i"] / quiz["n"])
    st.markdown(f"**السؤال {quiz['i'] + 1} من {quiz['n']}** — {q.get('_lesson', '')}")
    st.markdown(q["question"])

    if quiz["res"] is None:
        key = f"ans_{quiz['i']}"
        if q["type"] == "mcq":
            ans = st.radio("اختر الإجابة", q["options"], index=None, key=key)
        elif q["type"] == "tf":
            ans = st.radio("الحكم", ["صح", "خطأ"], index=None, key=key, horizontal=True)
        elif q["type"] == "fill":
            ans = st.text_input("اكتب الكلمة أو العبارة المناسبة", key=key)
        else:
            ans = st.text_area("اكتب إجابتك", key=key)
        c1, c2 = st.columns([3, 1])
        if c1.button("أجب", disabled=not (ans and str(ans).strip())):
            with st.spinner("جارٍ تقييم إجابتك..."):
                score, fb = grade(client, q, str(ans).strip())
            quiz["score"] += score
            quiz["res"] = {"score": score, "fb": fb, "ans": str(ans).strip()}
            quiz["hist"].append({"q": q["question"], "ans": str(ans).strip(),
                                 "correct": correct_text(q), "score": score})
            st.rerun()
        if c2.button("⏹️ إنهاء التقييم الآن"):
            quiz["n"] = quiz["i"]
            st.rerun()
        return

    res = quiz["res"]
    if res["score"] == 1:
        st.success("إجابة صحيحة! 🎉")
    elif res["score"] > 0:
        st.warning("إجابة صحيحة جزئيًا")
    else:
        st.error("إجابة غير صحيحة")
    st.write(f"الإجابة الصحيحة: {correct_text(q)}")
    if q.get("explanation"):
        page = f" (صفحة {q['page']})" if q.get("page") else ""
        st.info(f"{q['explanation']}{page}")
    if res["fb"]:
        st.caption(res["fb"])
    last = quiz["i"] + 1 >= quiz["n"]
    b1, b2 = st.columns([3, 1])
    if b1.button("عرض النتيجة" if last else "السؤال التالي ◀"):
        quiz["i"] += 1
        quiz["cur"] = None
        quiz["res"] = None
        st.rerun()
    if not last and b2.button("⏹️ إنهاء الآن"):
        quiz["n"] = quiz["i"] + 1
        quiz["i"] += 1
        quiz["cur"] = None
        quiz["res"] = None
        st.rerun()
