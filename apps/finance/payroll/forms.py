from django import forms

from .models import SalaryStructure


class SalaryStructureForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        self.school = kwargs.pop('school', None)
        super().__init__(*args, **kwargs)

    class Meta:
        model = SalaryStructure
        fields = ['staff', 'monthly_salary']

    def clean_staff(self):
        staff = self.cleaned_data.get('staff')
        if self.school and staff and staff.school_id != self.school.id:
            raise forms.ValidationError('Selected staff does not belong to your school.')
        return staff
