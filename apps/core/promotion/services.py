from __future__ import annotations

from collections import defaultdict

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.core.academic_sessions.models import AcademicSession
from apps.core.academic_sessions.services import activate_session, ensure_session_editable
from apps.core.academics.models import AcademicConfig, ClassSubject, Period, SchoolClass, Section
from apps.core.attendance.models import StudentAttendance, StudentPeriodAttendance
from apps.core.attendance.services import lock_attendance_records
from apps.core.exams.models import Exam, ExamResultSummary, StudentMark
from apps.core.fees.models import ClassFeeStructure
from apps.core.fees.services import student_outstanding_summary, sync_student_fees_for_student
from apps.core.hr.models import Payroll, StaffAttendance
from apps.core.students.models import Student, StudentSessionRecord
from apps.core.students.services import change_student_status, sync_student_academic_links

from .models import PromotionRecord
from .validators import (
    build_year_end_validation,
    promotion_requires_clear_fees,
    student_fee_due,
    student_result_finalized,
    student_result_summary,
    validate_session_ready_for_promotion,
)


def _ensure_school_scope(*, school, session):
    if not session:
        raise ValidationError('Academic session is required.')
    if session.school_id != school.id:
        raise ValidationError('Selected session does not belong to your school.')
    return session


def _suggest_target_class(*, student, target_classes):
    if not target_classes:
        return None
    if not student.current_class_id:
        return target_classes[0]

    higher = [row for row in target_classes if row.display_order > student.current_class.display_order]
    if higher:
        return higher[0]

    same_order = [row for row in target_classes if row.display_order == student.current_class.display_order]
    if same_order:
        return same_order[0]

    same_name = [row for row in target_classes if row.name == student.current_class.name]
    if same_name:
        return same_name[0]

    return target_classes[0]


def _suggest_target_section(*, student, target_class, sections_by_class):
    if not target_class:
        return None
    target_sections = sections_by_class.get(target_class.id, [])
    if not target_sections:
        return None
    if student.current_section_id:
        for row in target_sections:
            if row.name == student.current_section.name:
                return row
    return target_sections[0]


def clone_session_configuration(*, source_session, target_session, copy_fee_structure=False):
    school = source_session.school
    if target_session.school_id != school.id:
        raise ValidationError('Source and target sessions must belong to the same school.')

    class_map = {}
    created_counts = {
        'classes': 0,
        'sections': 0,
        'class_subjects': 0,
        'periods': 0,
        'academic_configs': 0,
        'fee_structures': 0,
    }

    source_classes = list(
        SchoolClass.objects.filter(
            school=school,
            session=source_session,
        ).order_by('display_order', 'name', 'id')
    )
    for source_class in source_classes:
        target_class, created = SchoolClass.objects.update_or_create(
            school=school,
            session=target_session,
            name=source_class.name,
            defaults={
                'code': source_class.code,
                'display_order': source_class.display_order,
                'is_active': source_class.is_active,
            },
        )
        class_map[source_class.id] = target_class
        created_counts['classes'] += int(created)

    source_sections = Section.objects.filter(
        school_class__session=source_session,
        school_class__school=school,
    ).select_related('school_class').order_by('school_class__display_order', 'name', 'id')
    for source_section in source_sections:
        target_class = class_map.get(source_section.school_class_id)
        if not target_class:
            continue
        _, created = Section.objects.update_or_create(
            school_class=target_class,
            name=source_section.name,
            defaults={
                'capacity': source_section.capacity,
                'class_teacher': None,
                'is_active': source_section.is_active,
            },
        )
        created_counts['sections'] += int(created)

    source_class_subjects = ClassSubject.objects.filter(
        school_class__session=source_session,
        school_class__school=school,
    ).select_related('school_class', 'subject').order_by('school_class__display_order', 'subject__name', 'id')
    for source_mapping in source_class_subjects:
        target_class = class_map.get(source_mapping.school_class_id)
        if not target_class:
            continue
        _, created = ClassSubject.objects.update_or_create(
            school_class=target_class,
            subject=source_mapping.subject,
            defaults={
                'is_compulsory': source_mapping.is_compulsory,
                'max_marks': source_mapping.max_marks,
                'pass_marks': source_mapping.pass_marks,
            },
        )
        created_counts['class_subjects'] += int(created)

    source_periods = Period.objects.filter(
        school=school,
        session=source_session,
    ).order_by('period_number', 'id')
    for source_period in source_periods:
        _, created = Period.objects.update_or_create(
            school=school,
            session=target_session,
            period_number=source_period.period_number,
            defaults={
                'start_time': source_period.start_time,
                'end_time': source_period.end_time,
                'is_active': source_period.is_active,
            },
        )
        created_counts['periods'] += int(created)

    source_config = AcademicConfig.objects.filter(
        school=school,
        session=source_session,
    ).first()
    if source_config:
        _, created = AcademicConfig.objects.update_or_create(
            school=school,
            session=target_session,
            defaults={
                'total_periods_per_day': source_config.total_periods_per_day,
                'working_days': source_config.working_days,
                'grading_enabled': source_config.grading_enabled,
                'attendance_type': source_config.attendance_type,
                'marks_decimal_allowed': source_config.marks_decimal_allowed,
            },
        )
        created_counts['academic_configs'] = int(created)

    if copy_fee_structure:
        fee_structures = ClassFeeStructure.objects.filter(
            school=school,
            session=source_session,
            is_active=True,
        ).select_related('school_class', 'fee_type').order_by('school_class__display_order', 'fee_type__name', 'id')
        for row in fee_structures:
            target_class = class_map.get(row.school_class_id)
            if not target_class:
                continue
            _, created = ClassFeeStructure.objects.update_or_create(
                school=school,
                session=target_session,
                school_class=target_class,
                fee_type=row.fee_type,
                defaults={
                    'amount': row.amount,
                    'is_active': row.is_active,
                },
            )
            created_counts['fee_structures'] += int(created)

    return created_counts


@transaction.atomic
def initialize_new_session(
    *,
    school,
    name,
    start_date,
    end_date,
    created_by=None,
    source_session=None,
    copy_academic_structure=True,
    copy_fee_structure=False,
    make_current=False,
):
    if source_session:
        _ensure_school_scope(school=school, session=source_session)

    new_session = AcademicSession(
        school=school,
        name=name,
        start_date=start_date,
        end_date=end_date,
        is_active=False,
    )
    new_session.full_clean()
    new_session.save()

    copied = {}
    if source_session and copy_academic_structure:
        copied = clone_session_configuration(
            source_session=source_session,
            target_session=new_session,
            copy_fee_structure=copy_fee_structure,
        )

    if make_current:
        activate_session(school=school, session=new_session)

    return {
        'session': new_session,
        'copied': copied,
        'created_by_id': getattr(created_by, 'id', None),
    }


def build_promotion_dashboard(*, school, from_session, to_session, school_class=None, section=None):
    _ensure_school_scope(school=school, session=from_session)
    _ensure_school_scope(school=school, session=to_session)

    students = Student.objects.filter(
        school=school,
        session=from_session,
        is_archived=False,
    ).select_related('current_class', 'current_section').order_by(
        'current_class__display_order',
        'current_section__name',
        'admission_number',
    )
    if school_class:
        students = students.filter(current_class=school_class)
    if section:
        students = students.filter(current_section=section)

    target_classes = list(
        SchoolClass.objects.filter(
            school=school,
            session=to_session,
            is_active=True,
        ).order_by('display_order', 'name', 'id')
    )
    sections_by_class = defaultdict(list)
    for target_section in Section.objects.filter(
        school_class__school=school,
        school_class__session=to_session,
        school_class__is_active=True,
        is_active=True,
    ).select_related('school_class').order_by('school_class__display_order', 'name', 'id'):
        sections_by_class[target_section.school_class_id].append(target_section)

    existing_promotions = {
        row.student_id: row
        for row in PromotionRecord.objects.filter(
            school=school,
            from_session=from_session,
            to_session=to_session,
        ).select_related('to_class', 'to_section')
    }

    rows = []
    for student in students:
        summary = student_result_summary(student=student, session=from_session)
        due_total = student_outstanding_summary(
            student=student,
            session=from_session,
            as_of_date=from_session.end_date,
        )['total_due']
        suggested_class = _suggest_target_class(student=student, target_classes=target_classes)
        suggested_section = _suggest_target_section(
            student=student,
            target_class=suggested_class,
            sections_by_class=sections_by_class,
        )
        promotion_record = existing_promotions.get(student.id)
        rows.append({
            'student': student,
            'result_summary': summary,
            'result_finalized': summary is not None,
            'fee_due': due_total,
            'fee_clear': due_total <= 0,
            'suggested_class': promotion_record.to_class if promotion_record and promotion_record.to_class_id else suggested_class,
            'suggested_section': promotion_record.to_section if promotion_record and promotion_record.to_section_id else suggested_section,
            'existing_record': promotion_record,
            'existing_status': promotion_record.status if promotion_record else '',
        })

    return {
        'rows': rows,
        'target_classes': target_classes,
        'target_sections': [row for values in sections_by_class.values() for row in values],
        'readiness': build_year_end_validation(school=school, session=from_session),
    }


def _validate_target_assignment(*, to_session, to_class, to_section, status):
    if status == PromotionRecord.STATUS_DROPPED:
        return
    if not to_class:
        raise ValidationError('Target class is required for promoted or retained students.')
    if not to_section:
        raise ValidationError('Target section is required for promoted or retained students.')
    if to_class.session_id != to_session.id:
        raise ValidationError('Target class must belong to target session.')
    if to_section.school_class_id != to_class.id:
        raise ValidationError('Target section must belong to target class.')


@transaction.atomic
def promote_student(
    *,
    student,
    to_session,
    promoted_by,
    status=PromotionRecord.STATUS_PROMOTED,
    to_class=None,
    to_section=None,
    remarks='',
    require_clear_fees=None,
    allow_override=False,
):
    if status not in {
        PromotionRecord.STATUS_PROMOTED,
        PromotionRecord.STATUS_RETAINED,
        PromotionRecord.STATUS_DROPPED,
    }:
        raise ValidationError('Invalid promotion status.')

    from_session = student.session
    if from_session.school_id != student.school_id or to_session.school_id != student.school_id:
        raise ValidationError('Promotion sessions must belong to student school.')
    if from_session.id == to_session.id:
        raise ValidationError('Target session must be different from current session.')
    if not student.current_class_id or not student.current_section_id:
        raise ValidationError('Student must have a current class-section assignment before promotion.')
    if not allow_override:
        ensure_session_editable(
            session=from_session,
            message='Locked sessions cannot be used for promotion.',
        )
        ensure_session_editable(
            session=to_session,
            message='Locked target sessions cannot receive promotions.',
        )
        validate_session_ready_for_promotion(
            school=student.school,
            session=from_session,
            require_clear_fees=require_clear_fees,
        )

    if PromotionRecord.objects.filter(
        student=student,
        from_session=from_session,
        to_session=to_session,
    ).exists():
        raise ValidationError('This student already has a promotion record for the selected session transition.')

    require_clear_fees = promotion_requires_clear_fees() if require_clear_fees is None else require_clear_fees
    if not allow_override and not student_result_finalized(student=student, session=from_session):
        raise ValidationError('Results must be finalized before promoting this student.')
    if require_clear_fees and not allow_override and student_fee_due(student=student, session=from_session) > 0:
        raise ValidationError('Student has pending dues and cannot be promoted.')

    _validate_target_assignment(
        to_session=to_session,
        to_class=to_class,
        to_section=to_section,
        status=status,
    )

    from_class = student.current_class
    from_section = student.current_section
    historical_status = Student.STATUS_ACTIVE

    if status == PromotionRecord.STATUS_PROMOTED:
        historical_status = Student.STATUS_PASSED
        student.session = to_session
        student.current_class = to_class
        student.current_section = to_section
        student.status = Student.STATUS_ACTIVE
        student.is_active = True
        student.save(update_fields=['session', 'current_class', 'current_section', 'status', 'is_active'])
        sync_student_academic_links(student)
        sync_student_fees_for_student(student=student, previous_session=from_session)
    elif status == PromotionRecord.STATUS_RETAINED:
        historical_status = Student.STATUS_ACTIVE
        student.session = to_session
        student.current_class = to_class
        student.current_section = to_section
        student.status = Student.STATUS_ACTIVE
        student.is_active = True
        student.save(update_fields=['session', 'current_class', 'current_section', 'status', 'is_active'])
        sync_student_academic_links(student)
        sync_student_fees_for_student(student=student, previous_session=from_session)
    else:
        historical_status = Student.STATUS_DROPPED
        change_student_status(
            student=student,
            new_status=Student.STATUS_DROPPED,
            changed_by=promoted_by,
            reason=remarks,
        )

    StudentSessionRecord.objects.filter(
        student=student,
        session=from_session,
    ).update(status=historical_status, is_current=False)

    record = PromotionRecord(
        school=student.school,
        student=student,
        from_class=from_class,
        from_section=from_section,
        to_class=to_class,
        to_section=to_section,
        from_session=from_session,
        to_session=to_session,
        promoted_by=promoted_by,
        status=status,
        remarks=(remarks or '')[:255],
    )
    record.full_clean()
    record.save()
    return record


@transaction.atomic
def bulk_promote_students(
    *,
    school,
    from_session,
    to_session,
    actions,
    promoted_by,
    require_clear_fees=None,
    allow_override=False,
):
    _ensure_school_scope(school=school, session=from_session)
    _ensure_school_scope(school=school, session=to_session)
    if from_session.id == to_session.id:
        raise ValidationError('Select different from and to sessions for promotion.')
    if not allow_override:
        validate_session_ready_for_promotion(
            school=school,
            session=from_session,
            require_clear_fees=require_clear_fees,
        )

    students = {
        row.id: row
        for row in Student.objects.filter(
            school=school,
            session=from_session,
            id__in=[row['student_id'] for row in actions],
        ).select_related('current_class', 'current_section')
    }
    target_classes = {
        row.id: row
        for row in SchoolClass.objects.filter(
            school=school,
            session=to_session,
            is_active=True,
        )
    }
    target_sections = {
        row.id: row
        for row in Section.objects.filter(
            school_class__school=school,
            school_class__session=to_session,
            is_active=True,
        ).select_related('school_class')
    }

    processed = []
    errors = []
    for action in actions:
        student = students.get(action['student_id'])
        if not student:
            errors.append(f"Student #{action['student_id']} is not available in the selected session.")
            continue

        try:
            record = promote_student(
                student=student,
                to_session=to_session,
                promoted_by=promoted_by,
                status=action['status'],
                to_class=target_classes.get(action.get('to_class_id')),
                to_section=target_sections.get(action.get('to_section_id')),
                remarks=action.get('remarks', ''),
                require_clear_fees=require_clear_fees,
                allow_override=allow_override,
            )
        except ValidationError as exc:
            errors.append(f"{student.admission_number}: {'; '.join(exc.messages)}")
            continue

        processed.append(record)

    return processed, errors


@transaction.atomic
def close_session(*, session, closed_by, next_session=None, allow_override=False):
    if session.is_locked:
        return {
            'session': session,
            'attendance_locked': 0,
            'exam_locked': 0,
            'marks_locked': 0,
            'summaries_locked': 0,
            'payroll_locked': 0,
        }

    if not allow_override:
        validate_session_ready_for_promotion(school=session.school, session=session)

    if next_session:
        _ensure_school_scope(school=session.school, session=next_session)
        if next_session.id == session.id:
            raise ValidationError('Next session must be different from current session.')
        ensure_session_editable(
            session=next_session,
            message='Locked target sessions cannot be activated.',
        )

    attendance_info = lock_attendance_records(
        school=session.school,
        session=session,
    )
    now = timezone.now()
    exam_locked = Exam.objects.filter(
        school=session.school,
        session=session,
        is_locked=False,
    ).update(is_locked=True, updated_at=now)
    marks_locked = StudentMark.objects.filter(
        school=session.school,
        session=session,
        is_locked=False,
    ).update(is_locked=True)
    summaries_locked = ExamResultSummary.objects.filter(
        school=session.school,
        session=session,
        is_locked=False,
    ).update(is_locked=True)
    payroll_locked = Payroll.objects.filter(
        school=session.school,
        session=session,
        is_locked=False,
    ).update(is_locked=True, updated_at=now)

    session.attendance_locked = True
    session.is_locked = True
    session.locked_at = now
    session.locked_by = closed_by
    if not next_session and session.is_active:
        session.is_active = False
    session.save(update_fields=['attendance_locked', 'is_locked', 'locked_at', 'locked_by', 'is_active'])

    if next_session:
        activate_session(school=session.school, session=next_session)
    elif session.school.current_session_id == session.id:
        session.school.current_session = None
        session.school.save(update_fields=['current_session'])

    return {
        'session': session,
        'attendance_locked': (
            attendance_info['staff_locked']
            + attendance_info['student_daily_locked']
            + attendance_info['student_period_locked']
        ),
        'exam_locked': exam_locked,
        'marks_locked': marks_locked,
        'summaries_locked': summaries_locked,
        'payroll_locked': payroll_locked,
    }


@transaction.atomic
def unlock_session(*, session, unlocked_by, allow_override=False):
    if not allow_override:
        raise ValidationError('Only super admin override can unlock a closed session.')

    session.is_locked = False
    session.attendance_locked = False
    session.locked_at = None
    session.locked_by = None
    session.save(update_fields=['is_locked', 'attendance_locked', 'locked_at', 'locked_by'])

    Exam.objects.filter(school=session.school, session=session).update(is_locked=False, updated_at=timezone.now())
    StudentMark.objects.filter(school=session.school, session=session).update(is_locked=False)
    ExamResultSummary.objects.filter(school=session.school, session=session).update(is_locked=False)
    Payroll.objects.filter(school=session.school, session=session).update(is_locked=False, updated_at=timezone.now())
    StaffAttendance.objects.filter(school=session.school, session=session).update(is_locked=False)
    StudentAttendance.objects.filter(school=session.school, session=session).update(is_locked=False)
    StudentPeriodAttendance.objects.filter(school=session.school, session=session).update(is_locked=False)

    return {
        'session': session,
        'unlocked_by_id': getattr(unlocked_by, 'id', None),
    }
