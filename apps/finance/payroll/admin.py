from django.contrib import admin
from .models import SalaryStructure, SalaryPayment

admin.site.register(SalaryStructure)
admin.site.register(SalaryPayment)
