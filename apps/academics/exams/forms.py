from django import forms

from apps.academics.staff.models import Staff
from apps.core.academic_sessions.models import AcademicSession
from apps.core.academics.models import SchoolClass, Section, Subject

from .models import Exam, ExamSchedule


class ExamForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        self.school = kwargs.pop('school', None)
        super().__init__(*args, **kwargs)

        if self.school:
            self.fields['academic_session'].queryset = AcademicSession.objects.filter(
                school=self.school
            ).order_by('-start_date')

    class Meta:
        model = Exam
        fields = ['academic_session', 'name', 'start_date', 'end_date', 'is_published']
        widgets = {
            'start_date': forms.DateInput(attrs={'type': 'date'}),
            'end_date': forms.DateInput(attrs={'type': 'date'}),
        }

    def clean(self):
        cleaned_data = super().clean()
        academic_session = cleaned_data.get('academic_session')
        start_date = cleaned_data.get('start_date')
        end_date = cleaned_data.get('end_date')

        if start_date and end_date and end_date < start_date:
            self.add_error('end_date', 'End date must be on or after start date.')

        if self.school and academic_session and academic_session.school_id != self.school.id:
            self.add_error('academic_session', 'Selected session does not belong to your school.')

        return cleaned_data


class ExamScheduleForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        self.school = kwargs.pop('school', None)
        self.exam = kwargs.pop('exam', None)
        super().__init__(*args, **kwargs)

        if self.school:
            self.fields['school_class'].queryset = SchoolClass.objects.filter(
                school=self.school
            ).order_by('order', 'name')
            self.fields['section'].queryset = Section.objects.filter(
                school_class__school=self.school
            ).order_by('school_class__order', 'name')
            self.fields['subject'].queryset = Subject.objects.filter(
                school=self.school
            ).select_related('school_class').order_by('school_class__order', 'name')
            self.fields['invigilator'].queryset = Staff.objects.filter(
                school=self.school,
                is_active=True
            ).order_by('first_name', 'last_name')

    class Meta:
        model = ExamSchedule
        fields = [
            'school_class',
            'section',
            'subject',
            'date',
            'start_time',
            'end_time',
            'max_marks',
            'pass_marks',
            'room',
            'invigilator',
            'is_active',
        ]
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date'}),
            'start_time': forms.TimeInput(attrs={'type': 'time'}),
            'end_time': forms.TimeInput(attrs={'type': 'time'}),
        }

    def clean(self):
        cleaned_data = super().clean()
        school_class = cleaned_data.get('school_class')
        section = cleaned_data.get('section')
        subject = cleaned_data.get('subject')
        date = cleaned_data.get('date')
        start_time = cleaned_data.get('start_time')
        end_time = cleaned_data.get('end_time')
        max_marks = cleaned_data.get('max_marks')
        pass_marks = cleaned_data.get('pass_marks')
        invigilator = cleaned_data.get('invigilator')
        is_active = cleaned_data.get('is_active')

        if start_time and end_time and start_time >= end_time:
            self.add_error('end_time', 'End time must be later than start time.')

        if max_marks is not None and max_marks <= 0:
            self.add_error('max_marks', 'Maximum marks must be greater than zero.')

        if pass_marks is not None and pass_marks < 0:
            self.add_error('pass_marks', 'Passing marks cannot be negative.')

        if max_marks is not None and pass_marks is not None and pass_marks > max_marks:
            self.add_error('pass_marks', 'Passing marks cannot exceed maximum marks.')

        if section and school_class and section.school_class_id != school_class.id:
            self.add_error('section', 'Selected section does not belong to the selected class.')

        if subject and school_class and subject.school_class_id != school_class.id:
            self.add_error('subject', 'Selected subject does not belong to the selected class.')

        if self.exam and self.exam.academic_session:
            if date and (date < self.exam.start_date or date > self.exam.end_date):
                self.add_error('date', 'Exam date must be within the selected exam date range.')

        if self.school:
            if school_class and school_class.school_id != self.school.id:
                self.add_error('school_class', 'Selected class does not belong to your school.')
            if section and section.school_class.school_id != self.school.id:
                self.add_error('section', 'Selected section does not belong to your school.')
            if subject and subject.school_id != self.school.id:
                self.add_error('subject', 'Selected subject does not belong to your school.')
            if invigilator and invigilator.school_id != self.school.id:
                self.add_error('invigilator', 'Selected invigilator does not belong to your school.')

        if is_active and date and start_time and end_time and self.school:
            conflict_queryset = ExamSchedule.objects.filter(
                school=self.school,
                date=date,
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
                        'Time slot overlaps with another exam schedule for this class and section.'
                    )

            if invigilator:
                invigilator_conflict = conflict_queryset.filter(
                    invigilator=invigilator,
                    start_time__lt=end_time,
                    end_time__gt=start_time,
                ).exists()
                if invigilator_conflict:
                    self.add_error(
                        'invigilator',
                        'Selected invigilator has another exam assignment in this time slot.'
                    )

        return cleaned_data
