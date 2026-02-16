from django.contrib import admin
from .models import StaffAttendance, StudentAttendance

admin.site.register(StudentAttendance)
admin.site.register(StaffAttendance)
