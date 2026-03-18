from django import forms
from django.core.exceptions import ValidationError

from apps.core.academic_sessions.models import AcademicSession
from apps.core.students.models import Student

from .models import Driver, Route, RouteStop, StudentTransport, Vehicle


def _school_sessions(school):
    return AcademicSession.objects.filter(school=school).order_by('-start_date')


class DriverForm(forms.ModelForm):
    class Meta:
        model = Driver
        fields = ['name', 'license_number', 'phone', 'address', 'joining_date', 'is_active']
        widgets = {
            'joining_date': forms.DateInput(attrs={'type': 'date'}),
        }


class VehicleForm(forms.ModelForm):
    class Meta:
        model = Vehicle
        fields = [
            'vehicle_number',
            'vehicle_type',
            'capacity',
            'registration_number',
            'insurance_expiry',
            'fitness_expiry',
            'assigned_driver',
            'is_active',
        ]
        widgets = {
            'insurance_expiry': forms.DateInput(attrs={'type': 'date'}),
            'fitness_expiry': forms.DateInput(attrs={'type': 'date'}),
        }

    def __init__(self, *args, **kwargs):
        self.school = kwargs.pop('school', None)
        super().__init__(*args, **kwargs)
        self.fields['assigned_driver'].queryset = Driver.objects.none()
        if self.school:
            self.fields['assigned_driver'].queryset = Driver.objects.filter(
                school=self.school,
                is_active=True,
            ).order_by('name')

    def clean_assigned_driver(self):
        driver = self.cleaned_data.get('assigned_driver')
        if self.school and driver and driver.school_id != self.school.id:
            raise ValidationError('Driver does not belong to selected school.')
        return driver


class RouteForm(forms.ModelForm):
    class Meta:
        model = Route
        fields = ['route_name', 'start_point', 'end_point', 'vehicle', 'default_fee', 'is_active']

    def __init__(self, *args, **kwargs):
        self.school = kwargs.pop('school', None)
        super().__init__(*args, **kwargs)
        self.fields['vehicle'].queryset = Vehicle.objects.none()
        if self.school:
            self.fields['vehicle'].queryset = Vehicle.objects.filter(
                school=self.school,
                is_active=True,
            ).order_by('vehicle_number')

    def clean_vehicle(self):
        vehicle = self.cleaned_data.get('vehicle')
        if self.school and vehicle and vehicle.school_id != self.school.id:
            raise ValidationError('Vehicle does not belong to selected school.')
        return vehicle


class RouteStopForm(forms.ModelForm):
    class Meta:
        model = RouteStop
        fields = ['route', 'stop_name', 'stop_order']

    def __init__(self, *args, **kwargs):
        self.school = kwargs.pop('school', None)
        super().__init__(*args, **kwargs)
        self.fields['route'].queryset = Route.objects.none()
        if self.school:
            self.fields['route'].queryset = Route.objects.filter(
                school=self.school,
                is_active=True,
            ).order_by('route_name')

    def clean_route(self):
        route = self.cleaned_data.get('route')
        if self.school and route and route.school_id != self.school.id:
            raise ValidationError('Route does not belong to selected school.')
        return route


class StudentTransportForm(forms.ModelForm):
    class Meta:
        model = StudentTransport
        fields = [
            'session',
            'student',
            'route',
            'stop_name',
            'pickup_time',
            'drop_time',
            'transport_fee',
            'is_active',
        ]
        widgets = {
            'pickup_time': forms.TimeInput(attrs={'type': 'time'}),
            'drop_time': forms.TimeInput(attrs={'type': 'time'}),
        }

    def __init__(self, *args, **kwargs):
        self.school = kwargs.pop('school', None)
        self.default_session = kwargs.pop('default_session', None)
        super().__init__(*args, **kwargs)

        self.fields['session'].queryset = AcademicSession.objects.none()
        self.fields['student'].queryset = Student.objects.none()
        self.fields['route'].queryset = Route.objects.none()

        selected_session_id = None
        if self.is_bound:
            selected_session_id = self.data.get('session')
        elif self.instance and self.instance.pk:
            selected_session_id = self.instance.session_id
        elif self.default_session:
            selected_session_id = self.default_session.id
            self.initial.setdefault('session', self.default_session.id)

        if not self.school:
            return

        self.fields['session'].queryset = _school_sessions(self.school)
        students = Student.objects.filter(
            school=self.school,
            is_active=True,
            is_archived=False,
            status=Student.STATUS_ACTIVE,
        ).order_by('admission_number')
        if selected_session_id:
            students = students.filter(session_id=selected_session_id)
        self.fields['student'].queryset = students

        self.fields['route'].queryset = Route.objects.filter(
            school=self.school,
            is_active=True,
            vehicle__is_active=True,
        ).select_related('vehicle').order_by('route_name')

    def clean(self):
        cleaned = super().clean()
        session = cleaned.get('session')
        student = cleaned.get('student')
        route = cleaned.get('route')

        if self.school and session and session.school_id != self.school.id:
            raise ValidationError('Session does not belong to selected school.')
        if student and session and student.session_id != session.id:
            raise ValidationError('Student does not belong to selected session.')
        if self.school and route and route.school_id != self.school.id:
            raise ValidationError('Route does not belong to selected school.')
        return cleaned
