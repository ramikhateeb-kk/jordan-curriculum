-- supabase_reading_texts.sql — نصوص القراءة المعتمدة يدويًا (تتقدم على الاستخراج التلقائي). آمن عند إعادة التشغيل.
create table if not exists reading_texts (
  book_slug     text not null,
  lesson_title  text not null,
  text          text not null,
  updated_by    bigint,
  updated_at    timestamptz not null default now(),
  primary key (book_slug, lesson_title)
);
