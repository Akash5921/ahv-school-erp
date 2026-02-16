from django.contrib import admin
from .models import InventoryCategory, InventoryItem, InventoryPurchase

admin.site.register(InventoryCategory)
admin.site.register(InventoryItem)
admin.site.register(InventoryPurchase)
