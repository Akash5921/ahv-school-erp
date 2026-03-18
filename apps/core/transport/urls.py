from django.urls import path

from .views import (
    transport_driver_deactivate,
    transport_driver_list,
    transport_driver_update,
    transport_report_driver,
    transport_report_fee_pending,
    transport_report_insurance,
    transport_report_route,
    transport_report_vehicle,
    transport_route_deactivate,
    transport_route_list,
    transport_route_update,
    transport_stop_delete,
    transport_student_allocation_list,
    transport_vehicle_deactivate,
    transport_vehicle_list,
    transport_vehicle_update,
)

urlpatterns = [
    path('drivers/', transport_driver_list, name='transport_driver_list_core'),
    path('drivers/<int:pk>/edit/', transport_driver_update, name='transport_driver_update_core'),
    path('drivers/<int:pk>/deactivate/', transport_driver_deactivate, name='transport_driver_deactivate_core'),

    path('vehicles/', transport_vehicle_list, name='transport_vehicle_list_core'),
    path('vehicles/<int:pk>/edit/', transport_vehicle_update, name='transport_vehicle_update_core'),
    path('vehicles/<int:pk>/deactivate/', transport_vehicle_deactivate, name='transport_vehicle_deactivate_core'),

    path('routes/', transport_route_list, name='transport_route_list_core'),
    path('routes/<int:pk>/edit/', transport_route_update, name='transport_route_update_core'),
    path('routes/<int:pk>/deactivate/', transport_route_deactivate, name='transport_route_deactivate_core'),
    path('stops/<int:pk>/delete/', transport_stop_delete, name='transport_stop_delete_core'),

    path('allocations/', transport_student_allocation_list, name='transport_student_allocation_list_core'),

    path('reports/routes/', transport_report_route, name='transport_report_route_core'),
    path('reports/vehicles/', transport_report_vehicle, name='transport_report_vehicle_core'),
    path('reports/drivers/', transport_report_driver, name='transport_report_driver_core'),
    path('reports/insurance/', transport_report_insurance, name='transport_report_insurance_core'),
    path('reports/fee-pending/', transport_report_fee_pending, name='transport_report_fee_pending_core'),
]
