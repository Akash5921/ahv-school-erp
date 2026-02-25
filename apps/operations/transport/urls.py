from django.urls import path

from .views import (
    bus_delete,
    bus_list,
    route_delete,
    route_list,
    student_transport_manage,
    student_transport_remove,
)

urlpatterns = [
    path('buses/', bus_list, name='transport_bus_list'),
    path('buses/<int:pk>/delete/', bus_delete, name='transport_bus_delete'),
    path('routes/', route_list, name='transport_route_list'),
    path('routes/<int:pk>/delete/', route_delete, name='transport_route_delete'),
    path('students/', student_transport_manage, name='transport_student_manage'),
    path('students/<int:pk>/remove/', student_transport_remove, name='transport_student_remove'),
]
