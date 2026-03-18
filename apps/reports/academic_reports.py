from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from django.db.models import Avg, Count, Max, Min

from apps.core.exams.models import ExamResultSummary, ExamSubject, StudentMark

from .filters import scoped_student_records


def _report(title, columns, rows, summary):
    return {
        'title': title,
        'columns': columns,
        'rows': rows,
        'summary': summary,
    }


def class_strength_report(filters):
    rows_qs = scoped_student_records(filters).values(
        'school_class__name',
        'section__name',
    ).annotate(total=Count('student_id', distinct=True)).order_by(
        'school_class__display_order',
        'section__name',
    )
    rows = [[row['school_class__name'], row['section__name'], row['total']] for row in rows_qs]
    total_students = sum(row[2] for row in rows)
    return _report(
        'Class Strength Report',
        ['Class', 'Section', 'Students'],
        rows,
        [('Total Students', total_students), ('Class Sections', len(rows))],
    )


def subject_performance_report(filters):
    marks = StudentMark.objects.filter(
        school=filters.school,
    ).select_related('subject', 'exam', 'student')
    if filters.session:
        marks = marks.filter(session=filters.session)
    if filters.exam:
        marks = marks.filter(exam=filters.exam)
    if filters.school_class:
        marks = marks.filter(exam__school_class=filters.school_class)
    if filters.section:
        marks = marks.filter(exam__section=filters.section)

    pass_marks_map = {
        (row.exam_id, row.subject_id): row.pass_marks
        for row in ExamSubject.objects.filter(
            exam_id__in=marks.values_list('exam_id', flat=True).distinct(),
            is_active=True,
        ).only('exam_id', 'subject_id', 'pass_marks')
    }

    grouped = defaultdict(list)
    for mark in marks:
        grouped[mark.subject.name].append(mark)

    rows = []
    for subject_name in sorted(grouped):
        entries = grouped[subject_name]
        values = [entry.marks_obtained for entry in entries]
        pass_count = 0
        for entry in entries:
            threshold = pass_marks_map.get((entry.exam_id, entry.subject_id), Decimal('0.00'))
            if entry.marks_obtained >= threshold:
                pass_count += 1
        pass_rate = round((pass_count / len(entries)) * 100, 2) if entries else 0
        rows.append([
            subject_name,
            round(sum(values) / len(values), 2),
            max(values),
            min(values),
            pass_count,
            f'{pass_rate}%',
        ])

    return _report(
        'Subject-wise Performance Report',
        ['Subject', 'Average', 'Highest', 'Lowest', 'Pass Count', 'Pass Rate'],
        rows,
        [('Subjects', len(rows)), ('Mark Entries', sum(len(items) for items in grouped.values()))],
    )


def student_result_report(filters):
    summaries = ExamResultSummary.objects.filter(
        school=filters.school,
    ).select_related('student', 'exam', 'exam__exam_type', 'exam__school_class', 'exam__section')
    if filters.session:
        summaries = summaries.filter(session=filters.session)
    if filters.exam:
        summaries = summaries.filter(exam=filters.exam)
    if filters.school_class:
        summaries = summaries.filter(exam__school_class=filters.school_class)
    if filters.section:
        summaries = summaries.filter(exam__section=filters.section)
    if filters.student:
        summaries = summaries.filter(student=filters.student)

    rows = [[
        row.student.admission_number,
        row.student.full_name,
        row.exam.exam_type.name,
        row.exam.school_class.name,
        row.exam.section.name if row.exam.section_id else 'All',
        row.total_marks,
        row.percentage,
        row.grade or '-',
        row.rank or '-',
        row.get_result_status_display(),
    ] for row in summaries.order_by('-exam__start_date', 'student__admission_number')]
    return _report(
        'Student Result Report',
        ['Admission No', 'Student', 'Exam', 'Class', 'Section', 'Total', 'Percentage', 'Grade', 'Rank', 'Status'],
        rows,
        [('Result Rows', len(rows))],
    )


def top_performers_report(filters):
    summaries = ExamResultSummary.objects.filter(
        school=filters.school,
    ).select_related('student', 'exam', 'exam__exam_type')
    if filters.session:
        summaries = summaries.filter(session=filters.session)
    if filters.exam:
        summaries = summaries.filter(exam=filters.exam)
    if filters.school_class:
        summaries = summaries.filter(exam__school_class=filters.school_class)
    if filters.section:
        summaries = summaries.filter(exam__section=filters.section)

    rows = [[
        row.rank or '-',
        row.student.admission_number,
        row.student.full_name,
        row.exam.exam_type.name,
        row.percentage,
        row.grade or '-',
        row.total_marks,
    ] for row in summaries.order_by('rank', '-percentage', 'student__admission_number')[:20]]
    return _report(
        'Top Performers Report',
        ['Rank', 'Admission No', 'Student', 'Exam', 'Percentage', 'Grade', 'Total Marks'],
        rows,
        [('Top Rows', len(rows))],
    )


def failures_report(filters):
    summaries = ExamResultSummary.objects.filter(
        school=filters.school,
        result_status=ExamResultSummary.STATUS_FAIL,
    ).select_related('student', 'exam', 'exam__exam_type')
    if filters.session:
        summaries = summaries.filter(session=filters.session)
    if filters.exam:
        summaries = summaries.filter(exam=filters.exam)
    if filters.school_class:
        summaries = summaries.filter(exam__school_class=filters.school_class)
    if filters.section:
        summaries = summaries.filter(exam__section=filters.section)

    rows = [[
        row.student.admission_number,
        row.student.full_name,
        row.exam.exam_type.name,
        row.percentage,
        row.grade or '-',
        row.total_marks,
    ] for row in summaries.order_by('-exam__start_date', 'student__admission_number')]
    return _report(
        'Failures List',
        ['Admission No', 'Student', 'Exam', 'Percentage', 'Grade', 'Total Marks'],
        rows,
        [('Failures', len(rows))],
    )


def grade_distribution_report(filters):
    summaries = ExamResultSummary.objects.filter(
        school=filters.school,
    )
    if filters.session:
        summaries = summaries.filter(session=filters.session)
    if filters.exam:
        summaries = summaries.filter(exam=filters.exam)
    if filters.school_class:
        summaries = summaries.filter(exam__school_class=filters.school_class)
    if filters.section:
        summaries = summaries.filter(exam__section=filters.section)

    distribution = summaries.values('grade').annotate(total=Count('id')).order_by('grade')
    rows = [[row['grade'] or 'Ungraded', row['total']] for row in distribution]
    return _report(
        'Grade Distribution Report',
        ['Grade', 'Students'],
        rows,
        [('Grades', len(rows)), ('Students', sum(row[1] for row in rows))],
    )
