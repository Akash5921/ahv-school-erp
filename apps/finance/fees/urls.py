
from django.urls import path
from .views import collect_fee

urlpatterns = [
    path('fees/collect/', collect_fee, name='collect_fee'),
]
