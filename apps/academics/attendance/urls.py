from django.urls import path
from .views import (
    mark_attendance,
    mark_staff_attendance,
    monthly_report,
    monthly_staff_report,
)

urlpatterns = [
    path('mark/', mark_attendance, name='mark_attendance'),
    path('monthly/', monthly_report, name='monthly_report'),
    path('staff/mark/', mark_staff_attendance, name='mark_staff_attendance'),
    path('staff/monthly/', monthly_staff_report, name='monthly_staff_report'),

]
