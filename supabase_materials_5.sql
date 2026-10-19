-- =====================================================================
-- supabase_materials_5.sql — شرح القواعد (Grammar) من مصادر خارجية، يُولَّد مرة لكل درس ويُخزَّن
-- شغّله بعد supabase_materials_4.sql. آمن عند إعادة التشغيل.
-- =====================================================================
create table if not exists grammar_explanations (
  id            bigint generated always as identity primary key,
  book_slug     text not null,
  lesson_title  text not null,
  title         text,                  -- قاعدة/قواعد الدرس كما حدّدها النظام
  content       text not null,         -- الشرح (Markdown: شرح عربي + أمثلة إنجليزية)
  sources       jsonb,                 -- [{title, uri}] المصادر الخارجية التي اعتُمد عليها
  source        text not null default 'ai' check (source in ('ai','manual')),
  updated_by    bigint,
  updated_at    timestamptz not null default now(),
  unique (book_slug, lesson_title)
);
