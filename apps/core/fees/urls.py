from django.urls import path

from .views import (
    carry_forward_manage,
    class_fee_structure_deactivate,
    class_fee_structure_list,
    class_fee_structure_update,
    concession_deactivate,
    concession_list,
    concession_update,
    dues_report,
    fee_receipt_detail,
    fee_receipt_pdf,
    fee_type_deactivate,
    fee_type_list,
    fee_type_update,
    installment_deactivate,
    installment_list,
    installment_update,
    ledger_list,
    payment_manage,
    refund_list,
    student_fee_list,
    student_fee_sync_single,
)

urlpatterns = [
    path('types/', fee_type_list, name='fee_type_list_core'),
    path('types/<int:pk>/edit/', fee_type_update, name='fee_type_update_core'),
    path('types/<int:pk>/deactivate/', fee_type_deactivate, name='fee_type_deactivate_core'),

    path('class-structures/', class_fee_structure_list, name='class_fee_structure_list_core'),
    path('class-structures/<int:pk>/edit/', class_fee_structure_update, name='class_fee_structure_update_core'),
    path('class-structures/<int:pk>/deactivate/', class_fee_structure_deactivate, name='class_fee_structure_deactivate_core'),

    path('installments/', installment_list, name='installment_list_core'),
    path('installments/<int:pk>/edit/', installment_update, name='installment_update_core'),
    path('installments/<int:pk>/deactivate/', installment_deactivate, name='installment_deactivate_core'),

    path('student-fees/', student_fee_list, name='student_fee_list_core'),
    path('student-fees/<int:student_id>/sync/', student_fee_sync_single, name='student_fee_sync_single_core'),

    path('concessions/', concession_list, name='concession_list_core'),
    path('concessions/<int:pk>/edit/', concession_update, name='concession_update_core'),
    path('concessions/<int:pk>/deactivate/', concession_deactivate, name='concession_deactivate_core'),

    path('payments/', payment_manage, name='payment_manage_core'),
    path('receipts/<int:receipt_id>/', fee_receipt_detail, name='fee_receipt_detail_core'),
    path('receipts/<int:receipt_id>/pdf/', fee_receipt_pdf, name='fee_receipt_pdf_core'),

    path('refunds/', refund_list, name='refund_list_core'),

    path('dues/', dues_report, name='dues_report_core'),
    path('carry-forward/', carry_forward_manage, name='carry_forward_manage_core'),
    path('ledger/', ledger_list, name='ledger_list_core'),
]
