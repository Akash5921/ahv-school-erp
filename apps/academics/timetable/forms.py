from django import forms

from apps.academics.staff.models import Staff
from apps.core.academic_sessions.models import AcademicSession
from apps.core.academics.models import SchoolClass, Section, Subject

from .models import TimetableEntry


class TimetableEntryForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        self.school = kwargs.pop('school', None)
        super().__init__(*args, **kwargs)

        if self.school:
            self.fields['academic_session'].queryset = AcademicSession.objects.filter(
                school=self.school
            ).order_by('-start_date')
            self.fields['school_class'].queryset = SchoolClass.objects.filter(
                school=self.school
            ).order_by('order', 'name')
            self.fields['section'].queryset = Section.objects.filter(
                school_class__school=self.school
            ).order_by('school_class__order', 'name')
            self.fields['subject'].queryset = Subject.objects.filter(
                school=self.school
            ).select_related('school_class').order_by('school_class__order', 'name')
            self.fields['teacher'].queryset = Staff.objects.filter(
                school=self.school,
                staff_type='teacher',
                is_active=True
            ).order_by('first_name', 'last_name')

    class Meta:
        model = TimetableEntry
        fields = [
            'academic_session',
            'school_class',
            'section',
            'subject',
            'teacher',
            'day_of_week',
            'period_number',
            'start_time',
            'end_time',
            'room',
            'is_active',
        ]
        widgets = {
            'start_time': forms.TimeInput(attrs={'type': 'time'}),
            'end_time': forms.TimeInput(attrs={'type': 'time'}),
        }

    def clean(self):
        cleaned_data = super().clean()
        academic_session = cleaned_data.get('academic_session')
        school_class = cleaned_data.get('school_class')
        section = cleaned_data.get('section')
        subject = cleaned_data.get('subject')
        teacher = cleaned_data.get('teacher')
        day_of_week = cleaned_data.get('day_of_week')
        start_time = cleaned_data.get('start_time')
        end_time = cleaned_data.get('end_time')
        is_active = cleaned_data.get('is_active')

        if start_time and end_time and start_time >= end_time:
            self.add_error('end_time', 'End time must be later than start time.')

        if section and school_class and section.school_class_id != school_class.id:
            self.add_error('section', 'Selected section does not belong to the selected class.')

        if subject and school_class and subject.school_class_id != school_class.id:
            self.add_error('subject', 'Selected subject does not belong to the selected class.')

        if teacher and teacher.staff_type != 'teacher':
            self.add_error('teacher', 'Selected staff member is not a teacher.')

        if self.school:
            if academic_session and academic_session.school_id != self.school.id:
                self.add_error('academic_session', 'Selected session does not belong to your school.')
            if school_class and school_class.school_id != self.school.id:
                self.add_error('school_class', 'Selected class does not belong to your school.')
            if section and section.school_class.school_id != self.school.id:
                self.add_error('section', 'Selected section does not belong to your school.')
            if subject and subject.school_id != self.school.id:
                self.add_error('subject', 'Selected subject does not belong to your school.')
            if teacher and teacher.school_id != self.school.id:
                self.add_error('teacher', 'Selected teacher does not belong to your school.')

        # Only active entries participate in runtime scheduling conflict checks.
        if is_active and academic_session and day_of_week and start_time and end_time:
            conflict_queryset = TimetableEntry.objects.filter(
                academic_session=academic_session,
                day_of_week=day_of_week,
                is_active=True,
            ).exclude(pk=self.instance.pk if self.instance else None)

            if school_class and section:
                class_conflict = conflict_queryset.filter(
                    school_class=school_class,
                    section=section,
                    start_time__lt=end_time,
                    end_time__gt=start_time,
                ).exists()
                if class_conflict:
                    self.add_error(
                        'start_time',
                        'Time slot overlaps with another timetable entry for this class and section.'
                    )

            if teacher:
                teacher_conflict = conflict_queryset.filter(
                    teacher=teacher,
                    start_time__lt=end_time,
                    end_time__gt=start_time,
                ).exists()
                if teacher_conflict:
                    self.add_error(
                        'teacher',
                        'Selected teacher has another timetable entry in this time slot.'
                    )

        return cleaned_data
