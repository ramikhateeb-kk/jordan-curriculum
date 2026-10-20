-- =====================================================================
-- supabase_materials.sql — المرافقات: كتاب مرافق (أنشطة) + بنك الأسئلة الوزارية السابقة + نمط الأسئلة
-- شغّله مرة واحدة في Supabase → SQL Editor (بعد supabase_tracks.sql). آمن عند إعادة التشغيل.
-- =====================================================================

-- 1) كتاب مرافق: parent_slug = معرّف الكتاب الرئيسي الذي يرافقه هذا الكتاب (NULL = كتاب رئيسي).
--    الكتاب المرافق يُخفى من قوائم المواد، ويُستخدم مصدرَ تمارين للكتاب الرئيسي.
alter table books add column if not exists parent_slug text;

-- 2) امتحانات وزارية سابقة (ملف/دورة) لكتاب.
create table if not exists ministry_exams (
  id          bigint generated always as identity primary key,
  book_slug   text    not null,
  year        integer,
  session     text,                 -- الدورة: الشتوية، الصيفية، الفصل الأول...
  title       text,
  created_by  bigint,
  created_at  timestamptz not null default now()
);
create index if not exists ministry_exams_book on ministry_exams (book_slug);

-- 3) أسئلة هذه الامتحانات بعد استخراجها. لا تظهر لأحد قبل الاعتماد (status = approved).
create table if not exists ministry_questions (
  id            bigint generated always as identity primary key,
  exam_id       bigint not null references ministry_exams(id) on delete cascade,
  book_slug     text   not null,
  number        integer,
  qtype         text   not null,    -- mcq | tf | fill | short | essay | matching | other
  data          jsonb  not null,    -- نص السؤال والخيارات والإجابة والعلامة والقسم والتعليمات
  lesson_title  text,               -- الدرس المرتبط (اختياري)
  status        text   not null default 'draft' check (status in ('draft','approved','rejected')),
  reviewed_by   bigint,
  reviewed_at   timestamptz,
  created_at    timestamptz not null default now()
);
create index if not exists ministry_questions_book_status on ministry_questions (book_slug, status);

-- 4) نمط الأسئلة الوزارية لكل كتاب (ملخّص يُستنتج من الأسئلة المعتمدة).
create table if not exists ministry_style (
  book_slug   text primary key,
  data        jsonb not null,
  based_on    integer not null default 0,
  updated_at  timestamptz not null default now()
);

-- 5) إظهار بنك الأسئلة الوزارية للمعلم والطالب أو إخفاؤه (يتحكم به المدير). الافتراضي: مخفي.
create table if not exists ministry_settings (
  book_slug  text primary key,
  visible    boolean not null default false
);
