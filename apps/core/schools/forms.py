from django import forms
from django.contrib.auth import get_user_model
from django.utils.text import slugify

from apps.core.schools.models import School, SchoolDomain


class SchoolOnboardingForm(forms.Form):
    school_name = forms.CharField(max_length=255)
    school_code = forms.CharField(
        max_length=40,
        required=False,
        help_text='Optional tenant code. Auto-generated when blank.',
    )
    school_subdomain = forms.CharField(
        max_length=63,
        required=False,
        help_text='Optional subdomain, e.g. north-campus',
    )
    school_domain = forms.CharField(
        max_length=253,
        required=False,
        help_text='Optional primary custom domain, e.g. erp.school.edu',
    )
    school_timezone = forms.CharField(max_length=64, required=False, initial='UTC')
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

        subdomain = cleaned_data.get('school_subdomain', '').strip()
        if subdomain:
            normalized_subdomain = slugify(subdomain)
            if normalized_subdomain != subdomain.lower():
                cleaned_data['school_subdomain'] = normalized_subdomain

            if School.objects.filter(subdomain=cleaned_data['school_subdomain']).exists():
                self.add_error('school_subdomain', 'This subdomain is already assigned.')

        return cleaned_data

    def clean_admin_username(self):
        username = self.cleaned_data['admin_username']
        user_model = get_user_model()
        if user_model.objects.filter(username=username).exists():
            raise forms.ValidationError('This username is already in use.')
        return username

    def clean_school_code(self):
        code = self.cleaned_data.get('school_code', '').strip()
        if not code:
            return ''
        normalized = slugify(code).replace('-', '_')
        if School.objects.filter(code=normalized).exists():
            raise forms.ValidationError('This school code is already in use.')
        return normalized

    def clean_school_domain(self):
        domain = self.cleaned_data.get('school_domain', '').strip().lower()
        if not domain:
            return ''
        if domain.startswith('www.'):
            domain = domain[4:]
        if SchoolDomain.objects.filter(domain=domain).exists():
            raise forms.ValidationError('This domain is already assigned.')
        return domain
