from __future__ import annotations

from datetime import date, timedelta
from io import BytesIO

from PIL import Image, ImageDraw
from django.core.exceptions import ValidationError
from django.db import transaction

from apps.core.hr.models import Staff, Substitution, TeacherSubjectAssignment

from .models import DAY_CHOICES, TimetableEntry


WEEKDAY_ORDER = [day for day, _ in DAY_CHOICES]
DAY_LABELS = dict(DAY_CHOICES)


def weekday_key(target_date: date) -> str:
    return WEEKDAY_ORDER[target_date.weekday()]


def week_range(anchor_date: date):
    monday = anchor_date - timedelta(days=anchor_date.weekday())
    saturday = monday + timedelta(days=5)
    return monday, saturday


def _images_to_pdf_bytes(images):
    if not images:
        return b''
    rgb_images = [img.convert('RGB') for img in images]
    output = BytesIO()
    rgb_images[0].save(output, format='PDF', save_all=True, append_images=rgb_images[1:])
    return output.getvalue()


def get_available_teachers(*, school, session, school_class, subject, day_of_week, period, exclude_entry=None):
    assigned_teacher_ids = TeacherSubjectAssignment.objects.filter(
        school=school,
        session=session,
        school_class=school_class,
        subject=subject,
        is_active=True,
    ).values_list('teacher_id', flat=True)

    teachers = Staff.objects.filter(
        school=school,
        id__in=assigned_teacher_ids,
        is_active=True,
        user__role='teacher',
    )

    conflicts = TimetableEntry.objects.filter(
        school=school,
        session=session,
        day_of_week=day_of_week,
        period=period,
        is_active=True,
        teacher_id__in=teachers.values_list('id', flat=True),
    )
    if exclude_entry is not None:
        conflicts = conflicts.exclude(pk=exclude_entry.pk)

    conflict_teacher_ids = conflicts.values_list('teacher_id', flat=True)
    return teachers.exclude(id__in=conflict_teacher_ids).order_by('employee_id')


def resolve_effective_teacher(entry: TimetableEntry, target_date: date):
    substitution = Substitution.objects.filter(
        school=entry.school,
        session=entry.session,
        date=target_date,
        period=entry.period,
        school_class=entry.school_class,
        section=entry.section,
        subject=entry.subject,
        original_teacher=entry.teacher,
        is_active=True,
    ).select_related('substitute_teacher', 'substitute_teacher__user').first()

    if substitution:
        return substitution.substitute_teacher, substitution
    return entry.teacher, None


def teacher_can_handle_slot(*, entry: TimetableEntry, teacher: Staff, target_date: date) -> bool:
    effective_teacher, _ = resolve_effective_teacher(entry, target_date)
    return effective_teacher.id == teacher.id


def build_class_timetable_grid(*, school, session, school_class, section, periods, view_date):
    entries = TimetableEntry.objects.filter(
        school=school,
        session=session,
        school_class=school_class,
        section=section,
        is_active=True,
    ).select_related('period', 'subject', 'teacher', 'teacher__user')

    entry_map = {
        (entry.day_of_week, entry.period_id): entry
        for entry in entries
    }

    view_day_key = weekday_key(view_date)
    substitutions = Substitution.objects.filter(
        school=school,
        session=session,
        date=view_date,
        school_class=school_class,
        section=section,
        is_active=True,
    ).select_related('period', 'substitute_teacher', 'substitute_teacher__user', 'subject')
    substitution_map = {sub.period_id: sub for sub in substitutions}

    rows = []
    for day_key in WEEKDAY_ORDER:
        row = {'day_key': day_key, 'day_label': DAY_LABELS[day_key], 'cells': []}
        for period in periods:
            entry = entry_map.get((day_key, period.id))
            substitution = None
            effective_teacher = None
            if day_key == view_day_key and entry:
                substitution = substitution_map.get(period.id)
                if substitution and substitution.subject_id == entry.subject_id and substitution.original_teacher_id == entry.teacher_id:
                    effective_teacher = substitution.substitute_teacher
            row['cells'].append(
                {
                    'period': period,
                    'entry': entry,
                    'substitution': substitution,
                    'effective_teacher': effective_teacher,
                }
            )
        rows.append(row)

    return rows


@transaction.atomic
def save_timetable_entry(*, school, session, school_class, section, day_of_week, period, subject, teacher, is_active=True, entry=None):
    timetable_entry = entry or TimetableEntry(
        school=school,
        session=session,
        school_class=school_class,
        section=section,
        day_of_week=day_of_week,
        period=period,
    )

    timetable_entry.school = school
    timetable_entry.session = session
    timetable_entry.school_class = school_class
    timetable_entry.section = section
    timetable_entry.day_of_week = day_of_week
    timetable_entry.period = period
    timetable_entry.subject = subject
    timetable_entry.teacher = teacher
    timetable_entry.is_active = is_active
    timetable_entry.full_clean()
    timetable_entry.save()
    return timetable_entry


def _draw_grid_pdf(title, periods, rows):
    width = 1800
    header_h = 90
    row_h = 110
    col_w_day = 180
    col_w = max(180, (width - col_w_day - 40) // max(1, len(periods)))
    height = 220 + header_h + row_h * (len(rows) + 1)

    image = Image.new('RGB', (width, height), 'white')
    draw = ImageDraw.Draw(image)

    draw.text((30, 20), title, fill='black')

    start_x = 20
    start_y = 110

    draw.rectangle((start_x, start_y, start_x + col_w_day, start_y + row_h), outline='black')
    draw.text((start_x + 10, start_y + 35), 'Day', fill='black')

    for idx, period in enumerate(periods):
        x1 = start_x + col_w_day + idx * col_w
        x2 = x1 + col_w
        draw.rectangle((x1, start_y, x2, start_y + row_h), outline='black')
        draw.text((x1 + 8, start_y + 15), f"P{period.period_number}", fill='black')
        draw.text((x1 + 8, start_y + 50), f"{period.start_time}-{period.end_time}", fill='black')

    for ridx, row in enumerate(rows):
        y1 = start_y + row_h * (ridx + 1)
        y2 = y1 + row_h
        draw.rectangle((start_x, y1, start_x + col_w_day, y2), outline='black')
        draw.text((start_x + 10, y1 + 40), row['day_label'], fill='black')

        for cidx, cell in enumerate(row['cells']):
            x1 = start_x + col_w_day + cidx * col_w
            x2 = x1 + col_w
            draw.rectangle((x1, y1, x2, y2), outline='black')

            entry = cell.get('entry')
            if not entry:
                draw.text((x1 + 8, y1 + 40), '-', fill='black')
                continue

            subject_line = entry.subject.code
            teacher_line = entry.teacher.employee_id
            draw.text((x1 + 8, y1 + 12), subject_line, fill='black')
            draw.text((x1 + 8, y1 + 44), teacher_line, fill='black')

            substitution = cell.get('substitution')
            if substitution:
                draw.text((x1 + 8, y1 + 74), f"Sub: {substitution.substitute_teacher.employee_id}", fill=(200, 0, 0))

    return _images_to_pdf_bytes([image])


def generate_class_timetable_pdf(*, school, session, school_class, section, periods, view_date):
    rows = build_class_timetable_grid(
        school=school,
        session=session,
        school_class=school_class,
        section=section,
        periods=periods,
        view_date=view_date,
    )
    title = f"Class Timetable - {school.name} | {session.name} | {school_class.name}-{section.name}"
    return _draw_grid_pdf(title, periods, rows)


def build_teacher_timetable_grid(*, school, session, teacher, periods):
    entries = TimetableEntry.objects.filter(
        school=school,
        session=session,
        teacher=teacher,
        is_active=True,
    ).select_related('period', 'subject', 'school_class', 'section')

    entry_map = {
        (entry.day_of_week, entry.period_id): entry
        for entry in entries
    }

    rows = []
    for day_key in WEEKDAY_ORDER:
        row = {'day_key': day_key, 'day_label': DAY_LABELS[day_key], 'cells': []}
        for period in periods:
            row['cells'].append({'period': period, 'entry': entry_map.get((day_key, period.id))})
        rows.append(row)

    return rows


def generate_teacher_timetable_pdf(*, school, session, teacher, periods):
    rows = build_teacher_timetable_grid(
        school=school,
        session=session,
        teacher=teacher,
        periods=periods,
    )
    title = f"Teacher Timetable - {school.name} | {session.name} | {teacher.full_name}"
    return _draw_grid_pdf(title, periods, rows)


def teacher_substitutions_for_week(*, school, session, teacher, anchor_date):
    week_start, week_end = week_range(anchor_date)

    substitutions_as_substitute = Substitution.objects.filter(
        school=school,
        session=session,
        substitute_teacher=teacher,
        date__range=(week_start, week_end),
        is_active=True,
    ).select_related('period', 'school_class', 'section', 'subject', 'original_teacher', 'original_teacher__user')

    substitutions_as_original = Substitution.objects.filter(
        school=school,
        session=session,
        original_teacher=teacher,
        date__range=(week_start, week_end),
        is_active=True,
    ).select_related('period', 'school_class', 'section', 'subject', 'substitute_teacher', 'substitute_teacher__user')

    return substitutions_as_substitute.order_by('date', 'period__period_number'), substitutions_as_original.order_by(
        'date', 'period__period_number'
    )


def assert_teacher_profile(user):
    staff = Staff.objects.filter(user=user, school=user.school, is_active=True).first()
    if not staff:
        raise ValidationError('No active staff profile linked to this user.')
    if user.role != 'teacher':
        raise ValidationError('Only teacher users can use this view.')
    return staff
