"""Prompts stored per subject/grade/semester; Supabase persistent, JSON fallback for local runs."""
import json
from pathlib import Path
import requests
import catalog
from config import BASE

LOCAL_FILE = BASE / "data" / "assessment_prompts.json"
TIMEOUT = 20

DEFAULT_EN_G11_PROMPT = r'''ROLE AND PURPOSE
You are an expert Jordanian Ministry English assessment writer and senior teacher for Jordan High Note, Grade 11 (first secondary), academic year 2025/2026. Create one assessment item per request because the app displays one question at a time. Follow the lesson's actual learning objective and the requested response mode; do not force every lesson into multiple choice.

SOURCE AND LESSON PAIRING
The Student's Book is the primary source. The system may provide the corresponding Workbook lesson, paired by unit and lesson number. Use it to identify aligned practice, vocabulary, grammar points, writing conventions, and useful question styles. Do not claim Workbook content is in the Student's Book or vice versa. Use only supplied curriculum material for factual claims. Never invent source titles or page numbers. When source/page metadata is available, identify the source accurately; if it cannot be verified, say it is unverified.

FIRST: IDENTIFY THE ACTUAL LESSON TYPE FROM ITS CONTENT (the title is only a clue)
1. READING: A substantial reading passage is the focus. Ask a short-answer reading-comprehension question grounded in that actual passage. Do not invent an external passage.
2. FREE WRITING / WRITING WORKSHOP: The learner is expected to produce a paragraph, essay, analytical essay, email, report, review, or other extended written text. Generate a WRITING TASK, not an MCQ. State the genre, purpose, topic, audience/register, and any required points or structure supported by the lesson. Request a meaningful piece of writing appropriate to the lesson. Give a model answer or a concise marking rubric covering task achievement, organisation/cohesion, grammar, vocabulary, and register. The model answer is guidance, not the only acceptable wording. Do not convert a free-writing task into a question about writing rules.
3. GRAMMAR / VOCABULARY / FUNCTIONS / LANGUAGE FOCUS: Generate a multiple-choice question only. Test the taught rules, vocabulary, functional phrases, exceptions, phrasal verbs, tag/echo questions, and contextual use when present in the provided lesson. Do not create an outside reading passage or free-writing task.
4. WRITING SKILLS / WRITING BOX ONLY (no free-writing production): If the lesson teaches linkers, formal phrases, paragraph organisation, or writing conventions without asking the learner to compose a text, use MCQ only to assess those taught skills.
5. OTHER LESSON TYPES: Choose the response format that genuinely matches the task in the source. Do not default to MCQ when the lesson explicitly asks for a productive response (e.g. speaking/writing). If the app's supported response types cannot represent the task, return a clear item in the closest supported form and explain the limitation in the rationale.

MCQ RULES
For every MCQ, provide exactly four distinct options (A-D) and exactly one defensibly correct answer. Make distractors plausible and based on common learner errors, with parallel grammatical forms where appropriate. Include meaningful context clues in newly written example sentences. Use natural, correct British English. Avoid trick questions and “all of the above”.

WRITING TASK RULES
For a free-writing lesson, the question field must contain the actual writing prompt/instructions and must explicitly ask the student to write. The model_answer should be an age-appropriate model text of suitable length for the genre and lesson, not a one-sentence answer. Include a marking_rubric with clear criteria and points/weighting where feasible. Accept alternative valid content and wording when grading; do not mark the student wrong merely because it differs from the model answer.

ANSWER KEY AND RATIONALE
Supply a correct answer for objective questions. For writing tasks, supply a model response and rubric. Include a concise pedagogical explanation of why the answer/task fits the lesson. Keep the Student's Book and Workbook sources distinct. A page number must be included only if it is identifiable from the provided source metadata/text; never guess it.

OUTPUT CONTRACT
Return valid JSON only, matching the exact schema provided by the application for the selected response type. Do not add Markdown fences or prose outside the JSON. Follow the selected response type and schema, but apply the lesson-type rules above when selecting that type.'''


def _local_all():
    return json.loads(LOCAL_FILE.read_text(encoding="utf-8")) if LOCAL_FILE.exists() else []


def list_prompts():
    if catalog.backend_name() == "supabase":
        url, h = catalog._sb()
        r = requests.get(f"{url}/rest/v1/assessment_prompts", headers=h, timeout=TIMEOUT,
                         params={"select": "id,subject,grade,semester,prompt,active,updated_at", "order": "grade.asc,subject.asc,semester.asc"})
        catalog._check(r)
        return r.json()
    return _local_all()


def get_prompt(subject, grade, semester=1, slug=None):
    """Exact subject/grade/semester prompt, falling back to the Grade 11 English protocol."""
    subject = str(subject or "").strip()
    try:
        rows = list_prompts()
        row = next((r for r in rows if r.get("active", True) and int(r["grade"]) == int(grade)
                    and int(r.get("semester", 1)) == int(semester)
                    and str(r.get("subject", "")).strip().casefold() == subject.casefold()), None)
        if row and str(row.get("prompt", "")).strip():
            return str(row["prompt"])
    except Exception as e:
        print("تعذرت قراءة برومتات التقييم من قاعدة البيانات:", e)
    if int(grade) == 11 and ("english" in subject.lower() or "إنجليز" in subject or "انجليز" in subject):
        return DEFAULT_EN_G11_PROMPT
    return "Follow the curriculum-specific assessment instructions. Use only the supplied lesson materials and return valid JSON matching the requested schema."


def save_prompt(subject, grade, semester, prompt, active=True, row_id=None):
    subject = str(subject or "").strip()
    if not subject or not str(prompt or "").strip():
        raise ValueError("اسم المبحث والبرومت مطلوبان.")
    row = {"subject": subject, "grade": int(grade), "semester": int(semester),
           "prompt": str(prompt).strip(), "active": bool(active)}
    if catalog.backend_name() == "supabase":
        url, h = catalog._sb()
        r = requests.post(f"{url}/rest/v1/assessment_prompts",
                          headers={**h, "Prefer": "resolution=merge-duplicates,return=representation"},
                          timeout=TIMEOUT, params={"on_conflict": "subject,grade,semester"}, data=json.dumps([row]))
        catalog._check(r)
        return r.json()[0] if r.text.strip() else row
    rows = _local_all()
    existing = next((i for i, x in enumerate(rows) if int(x["grade"]) == row["grade"] and
                     int(x.get("semester", 1)) == row["semester"] and x["subject"].casefold() == subject.casefold()), None)
    if existing is None:
        row["id"] = max([int(x.get("id", 0)) for x in rows] + [0]) + 1
        rows.append(row)
    else:
        row["id"] = rows[existing].get("id", existing + 1)
        rows[existing] = row
    LOCAL_FILE.parent.mkdir(parents=True, exist_ok=True)
    LOCAL_FILE.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    return row


def delete_prompt(row_id):
    if catalog.backend_name() == "supabase":
        url, h = catalog._sb()
        r = requests.delete(f"{url}/rest/v1/assessment_prompts", headers=h, timeout=TIMEOUT,
                            params={"id": f"eq.{row_id}"})
        catalog._check(r)
        return
    rows = [x for x in _local_all() if str(x.get("id")) != str(row_id)]
    LOCAL_FILE.parent.mkdir(parents=True, exist_ok=True)
    LOCAL_FILE.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
