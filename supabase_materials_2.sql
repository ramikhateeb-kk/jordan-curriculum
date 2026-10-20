-- =====================================================================
-- supabase_materials_2.sql — صور الأسئلة + ترحيل الأسئلة الوزارية إلى بنك «قيّمني» والاختبارات
-- شغّله بعد supabase_materials.sql. آمن عند إعادة التشغيل.
-- =====================================================================

-- صور ورسومات الأسئلة (مصغّرة ومضغوطة؛ يحمل السؤال معرّفها فقط في data.image_id).
create table if not exists question_images (
  id          bigint generated always as identity primary key,
  mime        text   not null default 'image/png',
  b64         text   not null,
  created_at  timestamptz not null default now()
);

-- ترحيل السؤال الوزاري المعتمد إلى جدول questions (بنك قيّمني والاختبارات) يدويًا بزر من المشرف.
alter table ministry_questions add column if not exists qbank_id       bigint;
alter table ministry_questions add column if not exists transferred_at timestamptz;
