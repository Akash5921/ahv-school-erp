from django.contrib import admin
from .models import FeeStructure, StudentFee, FeePayment

admin.site.register(FeeStructure)
admin.site.register(StudentFee)
admin.site.register(FeePayment)
