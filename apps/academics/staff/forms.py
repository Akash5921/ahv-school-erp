from django import forms
from django.contrib.auth import get_user_model

from .models import Staff


class StaffForm(forms.ModelForm):
    class Meta:
        model = Staff
        fields = [
            'staff_id',
            'first_name',
            'last_name',
            'staff_type',
            'phone',
            'email',
            'joining_date',
            'is_active',
        ]
        widgets = {
            'joining_date': forms.DateInput(attrs={'type': 'date'}),
        }


class StaffUserMapForm(forms.Form):
    username = forms.CharField(max_length=150)
    email = forms.EmailField(required=False)
    password = forms.CharField(widget=forms.PasswordInput)
    role = forms.ChoiceField(
        choices=(
            ('teacher', 'Teacher'),
            ('accountant', 'Accountant'),
            ('staff', 'Staff'),
        )
    )

    def clean_username(self):
        username = self.cleaned_data['username']
        user_model = get_user_model()
        if user_model.objects.filter(username=username).exists():
            raise forms.ValidationError('Username already exists.')
        return username
