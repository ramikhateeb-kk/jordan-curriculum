"""
explain_ctx.py
مواد «اشرح لي» الإضافية لدرس/وحدة محددة: تمارين الكتاب المرافق (الأنشطة)، والأسئلة الوزارية المعتمدة على الدرس، وشرح القواعد الخارجي.
"""
import companion
import grammar_ext
import ministry
import subject_profiles as sp

WORKBOOK_MAX = 9000
MAX_LESSONS = 6
MAX_GRAMMAR = 2


def build(slug, idx, flat_lessons, scope_titles, user, lang):
    """يعيد (extras للنموذج، grammar_blocks للإدراج بعد الإجابة).
    extras: {"workbook": نص، "ministry": نص، "grammar": [{"id","lesson"}]} — بلا نص الشرح الخارجي نفسه (يُدرَج حرفيًا بعد الإجابة).
    الأسئلة الوزارية تُستعمل أمثلةً فقط إن كان بنكها مفتوحًا للمعلمين/الطلاب (أو كان المستخدم مديرًا/مشرفًا)."""
    lessons = [l for l in flat_lessons if l["title"] in set(scope_titles)][:MAX_LESSONS]
    extras, blocks = {"workbook": "", "ministry": "", "grammar": []}, []
    if not lessons:
        return extras, blocks
    parts = []
    for l in lessons:
        t = companion.exercises_text(l, max_chars=3000)
        if t:
            parts.append(f"[{l['title']}]\n{t}")
    extras["workbook"] = "\n\n".join(parts)[:WORKBOOK_MAX]
    try:
        if ministry.is_visible(slug) or user["role"] in ("admin", "supervisor"):
            extras["ministry"] = ministry.examples_for_lessons(slug, [l["title"] for l in lessons], 6, lang)
    except Exception:  # noqa: BLE001
        pass
    if lang == "en":
        for l in lessons:
            if len(blocks) >= MAX_GRAMMAR or sp.lesson_kind(l["title"]) not in grammar_ext.GRAMMAR_KINDS:
                continue
            row = grammar_ext.get_explanation(slug, l, idx)         # مخزَّن، أو يُولَّد مرة واحدة بالبحث ثم يُخزَّن
            if row:
                gid = len(blocks) + 1
                blocks.append({"id": gid, "lesson": l["title"], "md": grammar_ext.render_md(row)})
                extras["grammar"].append({"id": gid, "lesson": l["title"]})
    return extras, blocks
