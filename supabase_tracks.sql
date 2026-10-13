-- =====================================================================
-- supabase_tracks.sql  —  التخصصات (للصفوف 10 و11 و12) + العام الهجري + لغة الكتاب + الحساب التجريبي
-- شغّله مرة واحدة في Supabase → SQL Editor. كل الأوامر آمنة عند إعادة التشغيل.
-- =====================================================================

-- 1) التخصصات: يضيفها مدير النظام لكل صف (هندسي، زراعي، علمي، أدبي، ...).
--    «الشعبة» (أ، ب...) تبقى حرًّا يكتبه المعلم في نماذجه، وليست جزءًا من هذا الجدول.
create table if not exists tracks (
  id          bigint generated always as identity primary key,
  grade       integer not null check (grade between 10 and 12),
  name        text    not null,
  sort_order  integer not null default 0,
  active      boolean not null default true,
  created_at  timestamptz default now(),
  unique (grade, name)
);

-- 2) ربط الكتاب بالتخصصات.
--    كتاب بلا أي صف في هذا الجدول  = كتاب مشترك لكل تخصصات صفّه (مثل المهارات الرقمية).
--    كتاب له صف أو أكثر           = خاص بهذه التخصصات فقط.
--    restrict: لا يمكن حذف تخصص مرتبط بكتب (وإلا تحوّلت كتبه فجأة إلى «مشتركة»)؛ يُوقَف بدلًا من الحذف.
create table if not exists book_tracks (
  book_id   bigint not null references books(id)  on delete cascade,
  track_id  bigint not null references tracks(id) on delete restrict,
  primary key (book_id, track_id)
);

-- 3) تخصص الطالب، وتخصصات المعلم المعتمدة (NULL = كل تخصصات الصف)، والحساب التجريبي.
alter table users            add column if not exists track_id bigint references tracks(id) on delete restrict;
alter table users            add column if not exists is_trial boolean not null default false;
alter table teacher_subjects add column if not exists track_id bigint references tracks(id) on delete restrict;

-- المفتاح الفريد القديم (user_id, subject, grade) لا يسمح بنفس المبحث/الصف لأكثر من تخصص.
alter table teacher_subjects drop constraint if exists teacher_subjects_user_id_subject_grade_key;
drop index  if exists teacher_subjects_user_id_subject_grade_key;
create unique index if not exists teacher_subjects_uniq
  on teacher_subjects (user_id, subject, grade, coalesce(track_id, 0));

-- 4) لغة الكتاب: 'ar' (الافتراضي) أو 'en'. كتب 'en' تُنتَج لها خطة الدرس والخطة الفصلية وتحليل المحتوى
--    بالإنجليزية واتجاه الصفحة من اليسار إلى اليمين.
alter table books add column if not exists lang text not null default 'ar' check (lang in ('ar','en'));
update books set lang = 'en' where lang = 'ar' and (subject ilike '%english%' or subject like '%إنجليز%' or subject like '%انجليز%');

-- 5) العام الدراسي الهجري: اتركه NULL ليحسبه النظام من تواريخ الفصلين، أو اكتبه يدويًا (مثل 1448/1449).
alter table academic_calendar add column if not exists hijri_label text;

-- 6) الحساب التجريبي للمعلم.
--    max_count للمزايا المحسوبة (lesson_plan, semester_plan) = عدد الدروس المسموحة.
--    للمزايا الأخرى: 0 = مقفلة، وأي رقم أكبر من 0 = مفتوحة.
create table if not exists trial_limits (
  feature    text primary key,
  max_count  integer not null default 0
);
insert into trial_limits (feature, max_count) values
  ('lesson_plan', 1), ('semester_plan', 1), ('content_analysis', 0), ('exam', 0),
  ('slides', 0), ('teach_help', 0), ('attendance', 0), ('marks_book', 0)
on conflict (feature) do nothing;

create table if not exists trial_usage (
  user_id  bigint  not null references users(id) on delete cascade,
  feature  text    not null,
  count    integer not null default 0,
  primary key (user_id, feature)
);

insert into role_limits (role, daily_limit) values ('trial', 5) on conflict (role) do nothing;
