from django import forms

from .models import SalaryStructure


class SalaryStructureForm(forms.ModelForm):
    class Meta:
        model = SalaryStructure
        fields = ['staff', 'monthly_salary']
