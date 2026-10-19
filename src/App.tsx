/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import React, { useState } from 'react';
import { Header } from './components/Header';
import { ExplainTab } from './components/ExplainTab';
import { QuestionBankTab } from './components/QuestionBankTab';
import { CurriculumCatalogTab } from './components/CurriculumCatalogTab';
import { LessonPlanTab } from './components/LessonPlanTab';
import { ContentAnalysisTab } from './components/ContentAnalysisTab';
import { JORDAN_GRADES, GradeInfo, SubjectInfo } from './data/jordanCurriculum';

export default function App() {
  const [activeTab, setActiveTab] = useState<'explain' | 'qbank' | 'books' | 'plans' | 'analysis'>('explain');

  // Default to Tawjihi / Grade 12 English as it's the most common student reference point
  const defaultGrade = JORDAN_GRADES.find(g => g.id === 'grade-12') || JORDAN_GRADES[0];
  const [selectedGrade, setSelectedGrade] = useState<GradeInfo>(defaultGrade);
  const [selectedSubject, setSelectedSubject] = useState<SubjectInfo>(defaultGrade.subjects[0]);

  // Handler when user clicks an exercise in the catalog to explain it immediately
  const handleSelectUnitAndExercise = (_unitNumber: number, exerciseQuery: string) => {
    setActiveTab('explain');
    // Scroll smoothly to top
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  return (
    <div className="min-h-screen bg-slate-100/70 text-slate-900 flex flex-col font-['Cairo',sans-serif]">
      {/* Header with Navigation */}
      <Header
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        selectedGradeName={selectedGrade.name}
        selectedSubjectName={selectedSubject.name}
      />

      {/* Main Workspace Container */}
      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-6">
        {activeTab === 'explain' && (
          <ExplainTab
            grades={JORDAN_GRADES}
            selectedGrade={selectedGrade}
            setSelectedGrade={setSelectedGrade}
            selectedSubject={selectedSubject}
            setSelectedSubject={setSelectedSubject}
          />
        )}

        {activeTab === 'qbank' && (
          <QuestionBankTab
            grades={JORDAN_GRADES}
            selectedGrade={selectedGrade}
            selectedSubject={selectedSubject}
          />
        )}

        {activeTab === 'books' && (
          <CurriculumCatalogTab
            grades={JORDAN_GRADES}
            selectedGrade={selectedGrade}
            setSelectedGrade={setSelectedGrade}
            selectedSubject={selectedSubject}
            setSelectedSubject={setSelectedSubject}
            onSelectUnitAndExercise={handleSelectUnitAndExercise}
          />
        )}

        {activeTab === 'plans' && (
          <LessonPlanTab
            selectedGrade={selectedGrade}
            selectedSubject={selectedSubject}
          />
        )}

        {activeTab === 'analysis' && (
          <ContentAnalysisTab
            selectedGrade={selectedGrade}
            selectedSubject={selectedSubject}
          />
        )}
      </main>

      {/* Footer */}
      <footer className="bg-white border-t border-slate-200 py-6 mt-12 text-center text-xs text-slate-500 no-print">
        <div className="max-w-7xl mx-auto px-4 flex flex-col sm:flex-row items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <span className="font-bold text-slate-700">المساعد الذكي للمناهج الأردنية</span>
            <span>•</span>
            <span>متوافق مع كتب وزارة التربية والتعليم (كتاب الطالب وكتاب الأنشطة والتمارين)</span>
          </div>
          <p className="text-slate-400">
            تنسيق متطور للغة الإنجليزية LTR • إزالة فراغات كتب الأنشطة • حل بالذكاء الاصطناعي لجميع الأسئلة والصفحات
          </p>
        </div>
      </footer>
    </div>
  );
}
