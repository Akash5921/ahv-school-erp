from django.contrib import admin
from .models import Staff


@admin.register(Staff)
class StaffAdmin(admin.ModelAdmin):
    list_display = ('staff_id', 'first_name', 'last_name', 'staff_type', 'school', 'is_active', 'user')
    list_filter = ('school', 'staff_type', 'is_active')
