from django import forms

from .models import InventoryCategory, InventoryItem, InventoryPurchase


class InventoryCategoryForm(forms.ModelForm):
    class Meta:
        model = InventoryCategory
        fields = ['name']


class InventoryItemForm(forms.ModelForm):
    class Meta:
        model = InventoryItem
        fields = ['name', 'category', 'location', 'quantity']


class InventoryPurchaseForm(forms.ModelForm):
    class Meta:
        model = InventoryPurchase
        fields = ['item', 'quantity_purchased', 'total_cost']
