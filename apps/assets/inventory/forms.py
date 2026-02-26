from django import forms

from .models import InventoryCategory, InventoryItem, InventoryPurchase


class InventoryCategoryForm(forms.ModelForm):
    class Meta:
        model = InventoryCategory
        fields = ['name']


class InventoryItemForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        self.school = kwargs.pop('school', None)
        super().__init__(*args, **kwargs)

    class Meta:
        model = InventoryItem
        fields = ['name', 'category', 'location', 'quantity']

    def clean_category(self):
        category = self.cleaned_data.get('category')
        if self.school and category and category.school_id != self.school.id:
            raise forms.ValidationError('Selected category does not belong to your school.')
        return category


class InventoryPurchaseForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        self.school = kwargs.pop('school', None)
        super().__init__(*args, **kwargs)

    class Meta:
        model = InventoryPurchase
        fields = ['item', 'quantity_purchased', 'total_cost']

    def clean_item(self):
        item = self.cleaned_data.get('item')
        if self.school and item and item.school_id != self.school.id:
            raise forms.ValidationError('Selected item does not belong to your school.')
        return item
