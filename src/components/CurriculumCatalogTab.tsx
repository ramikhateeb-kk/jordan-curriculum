import React, { useState } from 'react';
import { BookOpen, Layers, CheckCircle, ChevronDown, ChevronUp, ExternalLink } from 'lucide-react';
import { GradeInfo, SubjectInfo } from '../data/jordanCurriculum';

interface CurriculumCatalogTabProps {
  grades: GradeInfo[];
  selectedGrade: GradeInfo;
  setSelectedGrade: (g: GradeInfo) => void;
  selectedSubject: SubjectInfo;
  setSelectedSubject: (s: SubjectInfo) => void;
  onSelectUnitAndExercise: (unitNumber: number, exerciseQuery: string) => void;
}

export const CurriculumCatalogTab: React.FC<CurriculumCatalogTabProps> = ({
  grades,
  selectedGrade,
  setSelectedGrade,
  selectedSubject,
  setSelectedSubject,
  onSelectUnitAndExercise,
}) => {
  const [expandedUnit, setExpandedUnit] = useState<number | null>(1);

  return (
    <div className="space-y-6">
      {/* Top Banner */}
      <div className="bg-white rounded-2xl p-5 border border-slate-200 shadow-sm flex flex-wrap items-center justify-between gap-4">
        <div>
          <h2 className="text-lg font-bold text-slate-800 flex items-center gap-2">
            <BookOpen className="w-5 h-5 text-emerald-600" />
            <span>فهرس ومحتوى المناهج المدرسية الأردنية</span>
          </h2>
          <p className="text-xs text-slate-500 mt-0.5">
            تصفح الكتب المدرسية المقررة (كتاب الطالب وكتاب الأنشطة) ونتاجات التعلم لكل وحدة دراسية
          </p>
        </div>

        {/* Grade tabs selector */}
        <div className="flex items-center gap-1.5 overflow-x-auto max-w-full pb-1 scrollbar-none">
          {grades.map((g) => (
            <button
              key={g.id}
              onClick={() => {
                setSelectedGrade(g);
                setSelectedSubject(g.subjects[0]);
              }}
              className={`text-xs px-3 py-1.5 rounded-xl font-medium shrink-0 transition-all ${
                selectedGrade.id === g.id
                  ? 'bg-emerald-700 text-white font-bold shadow-xs'
                  : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
              }`}
            >
              {g.name}
            </button>
          ))}
        </div>
      </div>

      {/* Subjects Row */}
      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-2.5">
        {selectedGrade.subjects.map((s) => (
          <button
            key={s.id}
            onClick={() => setSelectedSubject(s)}
            className={`p-3 rounded-2xl border text-right transition-all flex flex-col justify-between h-24 ${
              selectedSubject.id === s.id
                ? 'bg-emerald-600 text-white border-emerald-600 shadow-md scale-102'
                : 'bg-white hover:bg-slate-50 text-slate-700 border-slate-200 shadow-2xs'
            }`}
          >
            <div className="flex items-center justify-between w-full">
              <span className="text-lg">{s.isEnglish ? '🇬🇧' : '🇯🇴'}</span>
              <span className={`text-[10px] px-1.5 py-0.5 rounded ${selectedSubject.id === s.id ? 'bg-emerald-700 text-white' : 'bg-slate-100 text-slate-500'}`}>
                {s.units.length} وحدات
              </span>
            </div>
            <span className="text-xs font-bold line-clamp-2 mt-2 leading-snug">
              {s.name}
            </span>
          </button>
        ))}
      </div>

      {/* Units & Detailed Content */}
      <div className="space-y-4">
        <div className="flex items-center justify-between text-sm font-bold text-slate-700 px-1">
          <span>الوحدات الدراسية لمادة {selectedSubject.name} ({selectedGrade.name})</span>
          <span className="text-xs text-slate-500 font-normal">اضغط على أي وحدة لعرض المفاهيم والتمارين</span>
        </div>

        <div className="space-y-3">
          {selectedSubject.units.map((unit) => {
            const isExpanded = expandedUnit === unit.number;

            return (
              <div
                key={unit.number}
                className="bg-white rounded-2xl border border-slate-200 overflow-hidden shadow-2xs transition-all"
              >
                <button
                  onClick={() => setExpandedUnit(isExpanded ? null : unit.number)}
                  className="w-full text-right p-4.5 flex items-center justify-between hover:bg-slate-50 transition-colors"
                >
                  <div className="flex items-center gap-3">
                    <span className="w-8 h-8 rounded-xl bg-emerald-100 text-emerald-800 font-black flex items-center justify-center text-xs shrink-0">
                      {unit.number}
                    </span>
                    <div>
                      <h4 className="text-sm font-bold text-slate-800">{unit.title}</h4>
                      {unit.titleEn && (
                        <p className="text-xs text-slate-500 font-english mt-0.5" dir="ltr">
                          {unit.titleEn}
                        </p>
                      )}
                    </div>
                  </div>

                  <div className="flex items-center gap-2">
                    <span className="text-xs bg-slate-100 text-slate-600 px-2 py-0.5 rounded-md">
                      {unit.topics.length} موضوعات رئيسية
                    </span>
                    {isExpanded ? (
                      <ChevronUp className="w-4 h-4 text-slate-400" />
                    ) : (
                      <ChevronDown className="w-4 h-4 text-slate-400" />
                    )}
                  </div>
                </button>

                {isExpanded && (
                  <div className="p-4.5 pt-0 border-t border-slate-100 bg-slate-50/50 space-y-4">
                    {/* Topics / Learning Outcomes */}
                    <div>
                      <span className="text-xs font-bold text-slate-700 block mb-2">
                        📌 موضوعات الوحدة ونتاجات التعلم:
                      </span>
                      <div className="flex flex-wrap gap-2">
                        {unit.topics.map((t, tidx) => (
                          <span
                            key={tidx}
                            className="text-xs bg-white text-slate-700 px-3 py-1 rounded-xl border border-slate-200 font-medium"
                          >
                            • {t}
                          </span>
                        ))}
                      </div>
                    </div>

                    {/* Sample Exercises from Activity Book & Student Book */}
                    {unit.sampleExercises && unit.sampleExercises.length > 0 && (
                      <div>
                        <span className="text-xs font-bold text-slate-700 block mb-2">
                          📝 تمارين وأنشطة نموذجية في الكتاب المقرر:
                        </span>
                        <div className="space-y-2">
                          {unit.sampleExercises.map((ex, exIdx) => (
                            <div
                              key={exIdx}
                              className="bg-white p-3 rounded-xl border border-slate-200 flex items-center justify-between gap-3 text-xs"
                            >
                              <div>
                                <span className="font-bold text-emerald-800 ml-2">
                                  {ex.bookType === 'activity_book' ? 'كتاب الأنشطة' : 'كتاب الطالب'} - صفحة {ex.page} (تمرين {ex.exerciseNum}):
                                </span>
                                <span className="text-slate-700 font-medium">{ex.question}</span>
                              </div>
                              <button
                                onClick={() =>
                                  onSelectUnitAndExercise(
                                    unit.number,
                                    `حل تمرين ${ex.exerciseNum} صفحة ${ex.page} في ${ex.bookType === 'activity_book' ? 'كتاب الأنشطة' : 'كتاب الطالب'}`
                                  )
                                }
                                className="px-3 py-1 bg-emerald-600 hover:bg-emerald-700 text-white font-bold rounded-lg shrink-0 transition-colors"
                              >
                                شرح وحل هذا التمرين
                              </button>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
};
