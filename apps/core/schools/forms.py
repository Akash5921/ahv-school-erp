from django import forms
from django.contrib.auth import get_user_model


class SchoolOnboardingForm(forms.Form):
    school_name = forms.CharField(max_length=255)
    school_address = forms.CharField(widget=forms.Textarea, required=False)
    school_phone = forms.CharField(max_length=20, required=False)
    school_email = forms.EmailField(required=False)

    admin_username = forms.CharField(max_length=150)
    admin_email = forms.EmailField(required=False)
    admin_password = forms.CharField(widget=forms.PasswordInput)

    session_name = forms.CharField(max_length=20, help_text='Example: 2026-27')
    session_start_date = forms.DateField(widget=forms.DateInput(attrs={'type': 'date'}))
    session_end_date = forms.DateField(widget=forms.DateInput(attrs={'type': 'date'}))

    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get('session_start_date')
        end_date = cleaned_data.get('session_end_date')

        if start_date and end_date and start_date >= end_date:
            self.add_error('session_end_date', 'End date must be after start date.')

        return cleaned_data

    def clean_admin_username(self):
        username = self.cleaned_data['admin_username']
        user_model = get_user_model()
        if user_model.objects.filter(username=username).exists():
            raise forms.ValidationError('This username is already in use.')
        return username
