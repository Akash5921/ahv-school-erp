from django.contrib import admin

from .models import Asset, Book, BookIssue, Purchase, PurchaseItem, StockItem, Vendor


@admin.register(Asset)
class AssetAdmin(admin.ModelAdmin):
    list_display = ('asset_code', 'asset_name', 'category', 'condition', 'school', 'is_active')
    list_filter = ('school', 'category', 'condition', 'is_active')
    search_fields = ('asset_code', 'asset_name', 'location')


@admin.register(StockItem)
class StockItemAdmin(admin.ModelAdmin):
    list_display = ('item_code', 'item_name', 'category', 'quantity_available', 'minimum_threshold', 'school', 'is_active')
    list_filter = ('school', 'category', 'is_active')
    search_fields = ('item_code', 'item_name')


@admin.register(Vendor)
class VendorAdmin(admin.ModelAdmin):
    list_display = ('vendor_name', 'phone', 'email', 'gst_number', 'school', 'is_active')
    list_filter = ('school', 'is_active')
    search_fields = ('vendor_name', 'gst_number', 'phone')


class PurchaseItemInline(admin.TabularInline):
    model = PurchaseItem
    extra = 0


@admin.register(Purchase)
class PurchaseAdmin(admin.ModelAdmin):
    list_display = ('invoice_number', 'vendor', 'session', 'purchase_date', 'total_amount', 'school')
    list_filter = ('school', 'session', 'purchase_date')
    search_fields = ('invoice_number', 'vendor__vendor_name')
    inlines = [PurchaseItemInline]


@admin.register(Book)
class BookAdmin(admin.ModelAdmin):
    list_display = ('title', 'author', 'isbn', 'category', 'available_copies', 'total_copies', 'school', 'is_active')
    list_filter = ('school', 'category', 'is_active')
    search_fields = ('title', 'author', 'isbn')


@admin.register(BookIssue)
class BookIssueAdmin(admin.ModelAdmin):
    list_display = ('book', 'session', 'issued_student', 'issued_staff', 'issue_date', 'due_date', 'return_date', 'fine_amount')
    list_filter = ('school', 'session', 'issue_date', 'return_date', 'is_active')
    search_fields = ('book__title', 'issued_student__admission_number', 'issued_staff__employee_id')
