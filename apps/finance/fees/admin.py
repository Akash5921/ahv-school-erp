from django.contrib import admin
from .models import FeeInstallment, FeePayment, FeeStructure, StudentFee

admin.site.register(FeeStructure)
admin.site.register(FeeInstallment)
admin.site.register(StudentFee)
admin.site.register(FeePayment)
