from django.contrib import admin

from .models import Driver, Route, RouteStop, StudentTransport, Vehicle


@admin.register(Driver)
class DriverAdmin(admin.ModelAdmin):
    list_display = ('name', 'license_number', 'school', 'phone', 'is_active')
    list_filter = ('school', 'is_active')
    search_fields = ('name', 'license_number', 'phone')


@admin.register(Vehicle)
class VehicleAdmin(admin.ModelAdmin):
    list_display = ('vehicle_number', 'vehicle_type', 'capacity', 'assigned_driver', 'school', 'is_active')
    list_filter = ('school', 'vehicle_type', 'is_active')
    search_fields = ('vehicle_number', 'registration_number')


@admin.register(Route)
class RouteAdmin(admin.ModelAdmin):
    list_display = ('route_name', 'start_point', 'end_point', 'vehicle', 'default_fee', 'school', 'is_active')
    list_filter = ('school', 'is_active')
    search_fields = ('route_name', 'start_point', 'end_point')


@admin.register(RouteStop)
class RouteStopAdmin(admin.ModelAdmin):
    list_display = ('route', 'stop_name', 'stop_order')
    list_filter = ('route__school',)
    search_fields = ('route__route_name', 'stop_name')


@admin.register(StudentTransport)
class StudentTransportAdmin(admin.ModelAdmin):
    list_display = ('student', 'session', 'route', 'stop_name', 'transport_fee', 'is_active')
    list_filter = ('school', 'session', 'is_active')
    search_fields = ('student__admission_number', 'student__first_name', 'route__route_name')
