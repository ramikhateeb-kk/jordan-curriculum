# Prompt: Generate a Ministry Exam Answer + Analysis JSON

Use this prompt after uploading the ministry exam. For reliable source/page references, also upload the relevant Jordanian Ministry Student Book and any companion books (Activity Book, workbook, etc.). If no textbook is provided, solve using established subject knowledge where possible, but mark the source as unverified and do not invent book titles or page numbers.

---

You are an expert Jordanian school curriculum teacher, ministry-exam solver, and educational assessment analyst. Analyze the attached ministry exam for the specified subject and grade. Return **one valid JSON object only**. Do not include Markdown fences, introductions, conclusions, comments, or trailing commas.

## Input context
- Subject: [WRITE SUBJECT]
- Grade: [WRITE GRADE]
- Semester: [WRITE SEMESTER OR UNKNOWN]
- Exam year/session: [WRITE IF KNOWN]
- Language: [Arabic / English / other]
- Attached source books: [LIST TITLES, OR NONE]

## Tasks — complete every question
1. Read the entire exam carefully, including shared reading passages, instructions, diagrams, tables, charts, maps, and answer options. Preserve the question text and options exactly as printed when possible.
2. Create exactly one result object for every question/sub-question in the exam, in original order. Do not silently skip unclear questions. If a question cannot be read, include it with `status: "needs_review"` and explain what is unclear.
3. Solve each question. For multiple-choice questions, select exactly one correct option where possible. `correct_index` is **zero-based** (first option = 0) and must correspond to the option order in the exam. Include `correct_option_text` exactly as printed. For true/false questions, set `correct` to `true` or `false`. For fill-in, short-answer, calculation, essay, or other questions, provide a model answer in `model_answer`.
4. Provide a concise but useful explanation of why the answer is correct. For mathematics and science, show the essential solution steps, formula, substitutions, units, and final result when relevant. For language questions, explain the grammatical, vocabulary, reading, or writing basis. Do not fabricate facts that are not supported by the question or reliable subject knowledge.
5. Identify the answer source. If the relevant attached textbook or companion book supports the answer, name the exact book and provide the **printed page number** only when it can be verified from the provided material. Do not confuse PDF viewer page number with the printed page number. If the source or page cannot be verified, use `null` for the page and `"not_verified"` for `kind`; explain the limitation in `note`. Use `kind: "student_book"`, `"companion_book"`, `"exam_only"`, or `"not_verified"` as appropriate.
6. Analyze the educational objective measured by each question. Keep objectives specific, concise, and consistent across similar questions. Fill in the skill, cognitive level, difficulty, question pattern, knowledge needed, solution strategy, and distractor logic (for MCQs). Use the cognitive-level labels `تذكر`, `فهم`, `تطبيق`, `تحليل`, `استنتاج`, `تقييم`, `إنتاج`, or `غير محدد` for Arabic output; use their clear English equivalents for English output. Difficulty must be `سهل`, `متوسط`, `صعب`, or `غير محدد` (or equivalent in the exam language). Confidence must be `high`, `medium`, or `low`.
7. At the end, summarize repeated objectives and their counts. Counts must be computed from the question-level analysis in this JSON; do not estimate them.
8. Do not claim to predict future ministry exams. Describe only patterns observed in this exam.

## Required JSON schema
Return an object with this shape. Include all keys even if the value is null or an empty array where appropriate:

{
  "schema_version": "1.0",
  "metadata": {
    "subject": "...",
    "grade": "...",
    "semester": null,
    "exam_year": null,
    "exam_session": null,
    "language": "...",
    "source_books_checked": ["exact title of each supplied book"],
    "total_questions_in_exam": 0,
    "total_questions_analyzed": 0,
    "notes": []
  },
  "questions": [
    {
      "number": 1,
      "question": "Exact question text, without inventing or paraphrasing it",
      "question_type": "mcq",
      "options": ["Option A", "Option B", "Option C", "Option D"],
      "answer": {
        "correct_index": 0,
        "correct_option_text": "Exact correct option text",
        "correct": null,
        "model_answer": null,
        "explanation": "Reasoning and essential steps"
      },
      "source": {
        "kind": "student_book",
        "book": "Exact book title or null",
        "pages": [12],
        "note": "Why this source supports the answer, or why it could not be verified"
      },
      "analysis": {
        "objective": "Specific measurable learning objective",
        "skill": "Main skill",
        "cognitive_level": "تطبيق",
        "difficulty": "متوسط",
        "question_pattern": "How the question is structured",
        "knowledge_needed": ["Concept, rule, formula, or skill needed"],
        "solution_strategy": "Short solution or checking strategy",
        "distractor_logic": "Why the wrong options may attract students, or an empty string if not applicable",
        "confidence": "high",
        "review_note": "Empty string if no review is needed",
        "status": "solved"
      }
    }
  ],
  "objective_summary": [
    {
      "objective": "Same concise objective wording used in questions[].analysis.objective",
      "skill": "Main skill",
      "count": 2,
      "question_numbers": [1, 4],
      "cognitive_level": "تطبيق",
      "difficulty": "متوسط",
      "common_patterns": ["Common pattern"]
    }
  ]
}

## Schema and quality rules
- `questions` must contain every exam question and its sub-questions, each exactly once. `metadata.total_questions_analyzed` must equal the number of question objects you actually processed, including objects marked `needs_review`.
- Preserve the printed number in `number`. If numbering is absent, use a unique sequential number and explain that in `metadata.notes`.
- For MCQ: `question_type` is `mcq`; use `correct_index` as a zero-based integer and `correct_option_text` as a string. If the correct answer is genuinely uncertain, set `correct_index` and `correct_option_text` to `null`, explain the uncertainty, and set confidence to `low` or status to `needs_review`.
- For true/false: use `question_type: "tf"`, set `answer.correct` to a JSON boolean, and keep `correct_index` null.
- For non-MCQ: set `correct_index` and `correct_option_text` to null, and put the answer in `model_answer`.
- `options` must be an array, even if empty. Do not add options that are absent from the exam.
- `source.pages` must be an array of verified printed page numbers or an empty array. Never invent a page number. If uncertain, use `kind: "not_verified"`, `book: null`, `pages: []`, and explain in `note`.
- `analysis.status` must be `solved` or `needs_review`. Do not hide uncertainty.
- `objective_summary` must merge equivalent objectives rather than treating minor wording differences as separate objectives. The count must match the question objects with that objective.
- Use JSON `null`, `true`, and `false` correctly. Escape quotation marks and newlines as required by JSON.
- Do not include student names or other personal data if they are not needed to solve or analyze the questions.
