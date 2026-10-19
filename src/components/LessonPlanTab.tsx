import React, { useState } from 'react';
import { FileText, Sparkles, Printer, Copy, Check, RefreshCw } from 'lucide-react';
import { GradeInfo, SubjectInfo } from '../data/jordanCurriculum';

interface LessonPlanTabProps {
  selectedGrade: GradeInfo;
  selectedSubject: SubjectInfo;
}

export const LessonPlanTab: React.FC<LessonPlanTabProps> = ({
  selectedGrade,
  selectedSubject,
}) => {
  const [lessonTitle, setLessonTitle] = useState<string>('');
  const [unitTitle, setUnitTitle] = useState<string>(selectedSubject.units[0]?.title || '');
  const [duration, setDuration] = useState<string>('حصة واحدة (45 دقيقة)');
  const [loading, setLoading] = useState<boolean>(false);
  const [planResult, setPlanResult] = useState<string>('');
  const [copied, setCopied] = useState<boolean>(false);

  const handleGeneratePlan = async () => {
    if (!lessonTitle.trim()) return;
    setLoading(true);
    setPlanResult('');
    try {
      const res = await fetch('/api/curriculum/lesson-plan', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          gradeId: selectedGrade.id,
          subjectId: selectedSubject.id,
          lessonTitle,
          unitTitle,
          duration,
        }),
      });
      const data = await res.json();
      if (data.success) {
        setPlanResult(data.plan);
      }
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const handleCopy = () => {
    navigator.clipboard.writeText(planResult);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="space-y-6">
      <div className="bg-white rounded-2xl shadow-sm border border-slate-200 p-5 no-print">
        <div className="flex items-center justify-between pb-4 border-b border-slate-100">
          <div>
            <h2 className="text-lg font-bold text-slate-800 flex items-center gap-2">
              <FileText className="w-5 h-5 text-emerald-600" />
              <span>إعداد خطط الدروس والخطط الفصلية</span>
            </h2>
            <p className="text-xs text-slate-500 mt-0.5">
              توليد خطة درس يومية معتمدة وفق نموذج وزارة التربية والتعليم الأردنية
            </p>
          </div>
          <span className="text-xs font-semibold px-3 py-1 bg-emerald-50 text-emerald-800 rounded-lg border border-emerald-200">
            {selectedSubject.name} • {selectedGrade.name}
          </span>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3.5 mt-4">
          <div>
            <label className="block text-xs font-semibold text-slate-600 mb-1.5">عنوان الدرس:</label>
            <input
              type="text"
              value={lessonTitle}
              onChange={(e) => setLessonTitle(e.target.value)}
              placeholder="مثال: Reported Speech أو حل المعادلات التربيعية"
              className="w-full text-sm bg-slate-50 border border-slate-200 rounded-xl px-3 py-2 text-slate-800 focus:outline-none focus:ring-2 focus:ring-emerald-500/30"
            />
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-600 mb-1.5">الوحدة التابع لها:</label>
            <input
              type="text"
              value={unitTitle}
              onChange={(e) => setUnitTitle(e.target.value)}
              placeholder="مثال: الوحدة الأولى: تكنولوجيا المعلومات"
              className="w-full text-sm bg-slate-50 border border-slate-200 rounded-xl px-3 py-2 text-slate-800 focus:outline-none focus:ring-2 focus:ring-emerald-500/30"
            />
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-600 mb-1.5">المدة الزمنية:</label>
            <select
              value={duration}
              onChange={(e) => setDuration(e.target.value)}
              className="w-full text-sm bg-slate-50 border border-slate-200 rounded-xl px-3 py-2 text-slate-800 focus:outline-none focus:ring-2 focus:ring-emerald-500/30"
            >
              <option value="حصة واحدة (45 دقيقة)">حصة واحدة (45 دقيقة)</option>
              <option value="حصتان متتاليتان (90 دقيقة)">حصتان متتاليتان (90 دقيقة)</option>
              <option value="خطة أسبوعية">خطة أسبوعية</option>
            </select>
          </div>
        </div>

        <div className="mt-4 flex justify-end">
          <button
            onClick={handleGeneratePlan}
            disabled={loading || !lessonTitle.trim()}
            className="flex items-center gap-2 px-5 py-2.5 bg-emerald-600 hover:bg-emerald-700 text-white text-sm font-bold rounded-xl shadow-md transition-all active:scale-95 disabled:opacity-60"
          >
            {loading ? (
              <>
                <RefreshCw className="w-4 h-4 animate-spin" />
                <span>جاري إعداد الخطة...</span>
              </>
            ) : (
              <>
                <Sparkles className="w-4 h-4 text-amber-300" />
                <span>توليد الخطة المعتمدة</span>
              </>
            )}
          </button>
        </div>
      </div>

      {planResult && (
        <div className="bg-white rounded-2xl shadow-sm border border-slate-200 overflow-hidden print-area">
          <div className="bg-slate-800 text-white px-5 py-3 flex items-center justify-between no-print">
            <span className="text-sm font-bold">نموذج خطة الدرس اليومية - وزارة التربية والتعليم</span>
            <div className="flex items-center gap-2 text-xs">
              <button
                onClick={handleCopy}
                className="flex items-center gap-1 px-3 py-1.5 bg-slate-700 hover:bg-slate-600 rounded-lg text-slate-200 transition-all"
              >
                {copied ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
                <span>{copied ? 'تم النسخ' : 'نسخ الخطة'}</span>
              </button>
              <button
                onClick={() => window.print()}
                className="flex items-center gap-1 px-3 py-1.5 bg-slate-700 hover:bg-slate-600 rounded-lg text-slate-200 transition-all"
              >
                <Printer className="w-3.5 h-3.5" />
                <span>طباعة الخطة</span>
              </button>
            </div>
          </div>

          <div className="p-6 md:p-8 space-y-4 text-slate-800 leading-relaxed text-sm md:text-base whitespace-pre-line text-right">
            {planResult}
          </div>
        </div>
      )}
    </div>
  );
};
