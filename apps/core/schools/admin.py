from django.contrib import admin

from .models import School, SchoolDomain


@admin.register(School)
class SchoolAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'subdomain', 'is_active', 'current_session')
    list_filter = ('is_active',)
    search_fields = ('name', 'code', 'subdomain', 'email')


@admin.register(SchoolDomain)
class SchoolDomainAdmin(admin.ModelAdmin):
    list_display = ('domain', 'school', 'is_primary', 'is_active')
    list_filter = ('is_primary', 'is_active')
    search_fields = ('domain', 'school__name', 'school__code')
