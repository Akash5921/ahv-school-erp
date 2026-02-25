from django import forms

from .models import Bus, Route, StudentTransport


class BusForm(forms.ModelForm):
    class Meta:
        model = Bus
        fields = ['bus_number', 'capacity', 'driver']


class RouteForm(forms.ModelForm):
    class Meta:
        model = Route
        fields = ['name', 'start_point', 'end_point']


class StudentTransportForm(forms.ModelForm):
    class Meta:
        model = StudentTransport
        fields = ['student', 'bus', 'route']
