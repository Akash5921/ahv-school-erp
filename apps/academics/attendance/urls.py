from django.urls import path
from .views import mark_attendance, monthly_report

urlpatterns = [
    path('attendance/mark/', mark_attendance, name='mark_attendance'),
    path('attendance/monthly/', monthly_report, name='monthly_report'),

]
