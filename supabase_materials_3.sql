-- =====================================================================
-- supabase_materials_3.sql — نصوص القراءة المعتمدة (بتنسيقها الأصلي) وتمارين الدرس
-- شغّله بعد supabase_materials_2.sql. آمن عند إعادة التشغيل.
-- =====================================================================
create table if not exists reading_texts (
  id            bigint generated always as identity primary key,
  book_slug     text not null,
  lesson_title  text not null,
  title         text,                  -- عنوان النص إن طُبع
  text          text not null,         -- النص بأسطره وفقراته كما في الكتاب (فقرة = سطر فارغ بينها)
  exercises     text,                  -- تمارين الدرس المطبوعة في الصفحات نفسها (للاستئناس عند التوليد)
  source        text not null default 'ai' check (source in ('ai','manual')),
  updated_by    bigint,
  updated_at    timestamptz not null default now(),
  unique (book_slug, lesson_title)
);
