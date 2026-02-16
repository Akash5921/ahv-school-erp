
from django.urls import path
from .views import collect_fee

urlpatterns = [
    path('collect/', collect_fee, name='collect_fee'),
]
