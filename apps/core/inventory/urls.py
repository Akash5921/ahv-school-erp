from django.urls import path

from .views import (
    inventory_asset_deactivate,
    inventory_asset_list,
    inventory_asset_update,
    inventory_book_deactivate,
    inventory_book_issue_list,
    inventory_book_list,
    inventory_book_update,
    inventory_purchase_list,
    inventory_report_assets,
    inventory_report_library,
    inventory_report_low_stock,
    inventory_report_overdue,
    inventory_report_purchases,
    inventory_report_vendor,
    inventory_stock_deactivate,
    inventory_stock_list,
    inventory_stock_update,
    inventory_vendor_deactivate,
    inventory_vendor_list,
    inventory_vendor_update,
)

urlpatterns = [
    path('assets/', inventory_asset_list, name='inventory_asset_list_core'),
    path('assets/<int:pk>/edit/', inventory_asset_update, name='inventory_asset_update_core'),
    path('assets/<int:pk>/deactivate/', inventory_asset_deactivate, name='inventory_asset_deactivate_core'),

    path('stock/', inventory_stock_list, name='inventory_stock_list_core'),
    path('stock/<int:pk>/edit/', inventory_stock_update, name='inventory_stock_update_core'),
    path('stock/<int:pk>/deactivate/', inventory_stock_deactivate, name='inventory_stock_deactivate_core'),

    path('vendors/', inventory_vendor_list, name='inventory_vendor_list_core'),
    path('vendors/<int:pk>/edit/', inventory_vendor_update, name='inventory_vendor_update_core'),
    path('vendors/<int:pk>/deactivate/', inventory_vendor_deactivate, name='inventory_vendor_deactivate_core'),

    path('purchases/', inventory_purchase_list, name='inventory_purchase_list_core'),

    path('library/books/', inventory_book_list, name='inventory_book_list_core'),
    path('library/books/<int:pk>/edit/', inventory_book_update, name='inventory_book_update_core'),
    path('library/books/<int:pk>/deactivate/', inventory_book_deactivate, name='inventory_book_deactivate_core'),
    path('library/issues/', inventory_book_issue_list, name='inventory_book_issue_list_core'),

    path('reports/assets/', inventory_report_assets, name='inventory_report_assets_core'),
    path('reports/low-stock/', inventory_report_low_stock, name='inventory_report_low_stock_core'),
    path('reports/purchases/', inventory_report_purchases, name='inventory_report_purchases_core'),
    path('reports/vendors/', inventory_report_vendor, name='inventory_report_vendor_core'),
    path('reports/library/', inventory_report_library, name='inventory_report_library_core'),
    path('reports/overdue/', inventory_report_overdue, name='inventory_report_overdue_core'),
]
