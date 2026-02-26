from django import forms

from .models import Bus, Route, StudentTransport


class BusForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        self.school = kwargs.pop('school', None)
        super().__init__(*args, **kwargs)

    class Meta:
        model = Bus
        fields = ['bus_number', 'capacity', 'driver']

    def clean_driver(self):
        driver = self.cleaned_data.get('driver')
        if self.school and driver and driver.school_id != self.school.id:
            raise forms.ValidationError('Selected driver does not belong to your school.')
        return driver


class RouteForm(forms.ModelForm):
    class Meta:
        model = Route
        fields = ['name', 'start_point', 'end_point']


class StudentTransportForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        self.school = kwargs.pop('school', None)
        super().__init__(*args, **kwargs)

    class Meta:
        model = StudentTransport
        fields = ['student', 'bus', 'route']

    def clean(self):
        cleaned_data = super().clean()
        student = cleaned_data.get('student')
        bus = cleaned_data.get('bus')
        route = cleaned_data.get('route')

        if student and bus and student.school_id != bus.school_id:
            self.add_error('bus', 'Selected bus does not belong to the student school.')
        if student and route and student.school_id != route.school_id:
            self.add_error('route', 'Selected route does not belong to the student school.')
        if self.school:
            if student and student.school_id != self.school.id:
                self.add_error('student', 'Selected student does not belong to your school.')
            if bus and bus.school_id != self.school.id:
                self.add_error('bus', 'Selected bus does not belong to your school.')
            if route and route.school_id != self.school.id:
                self.add_error('route', 'Selected route does not belong to your school.')

        return cleaned_data
