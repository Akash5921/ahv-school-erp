from django.urls import path

from .views import report_detail, report_index

urlpatterns = [
    path('', report_index, name='report_index'),
    path('<slug:slug>/', report_detail, name='report_detail'),
]
