
from django.urls import path
from .views import (
    collect_fee,
    dues_report,
    fee_installment_manage,
    fee_receipt,
    fee_structure_list,
    student_fee_manage,
)

urlpatterns = [
    path('structures/', fee_structure_list, name='fee_structure_list'),
    path('structures/<int:fee_structure_id>/installments/', fee_installment_manage, name='fee_installment_manage'),
    path('students/', student_fee_manage, name='student_fee_manage'),
    path('collect/', collect_fee, name='collect_fee'),
    path('dues/', dues_report, name='dues_report'),
    path('receipt/<int:payment_id>/', fee_receipt, name='fee_receipt'),
]
