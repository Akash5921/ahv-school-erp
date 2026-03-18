from django import forms
from django.core.exceptions import ValidationError

from .models import AcademicSession


class AcademicSessionForm(forms.ModelForm):
    class Meta:
        model = AcademicSession
        fields = ['name', 'start_date', 'end_date', 'is_active']
        widgets = {
            'start_date': forms.DateInput(attrs={'type': 'date'}),
            'end_date': forms.DateInput(attrs={'type': 'date'}),
        }

    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get('start_date')
        end_date = cleaned_data.get('end_date')
        if self.instance.pk and self.instance.is_locked:
            raise ValidationError('Locked academic sessions cannot be edited.')
        if start_date and end_date and start_date >= end_date:
            self.add_error('end_date', 'End date must be after start date.')
        return cleaned_data
