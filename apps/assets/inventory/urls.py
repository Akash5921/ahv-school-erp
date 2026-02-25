from django.urls import path

from .views import category_list, item_list, purchase_item


urlpatterns = [
    path('categories/', category_list, name='inventory_category_list'),
    path('items/', item_list, name='inventory_item_list'),
    path('purchase/', purchase_item, name='inventory_purchase'),
]
