from django.urls import path
from .views import pay_salary, salary_structure_manage

urlpatterns = [
    path('salary/structures/', salary_structure_manage, name='salary_structure_manage'),
    path('salary/pay/', pay_salary, name='pay_salary'),
]
