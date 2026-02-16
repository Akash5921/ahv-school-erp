from django.urls import path
from .views import pay_salary

urlpatterns = [
    path('salary/pay/', pay_salary, name='pay_salary'),
]
