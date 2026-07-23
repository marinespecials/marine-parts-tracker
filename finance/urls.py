from django.urls import path
from . import views

app_name = 'finance'

urlpatterns = [
    path('', views.finance_dashboard, name='dashboard'),
    path('create/', views.create_invoice, name='create_invoice'),
    path('bulk-import/', views.bulk_import_links, name='bulk_import'),
    path('invoice/<int:invoice_id>/edit/', views.edit_invoice, name='edit_invoice'),
    path('invoice/<int:invoice_id>/delete/', views.delete_invoice, name='delete_invoice'),
    path('client/<int:client_id>/', views.client_ledger, name='client_ledger'),
    path('export-csv/', views.export_finances_csv, name='export_finances'),
    
    # Spare Parts & Price Tracking
    path('prices/', views.price_history_dashboard, name='price_history'),
    path('prices/delete/<int:record_id>/', views.delete_price_record, name='delete_price_record'),

    # Master Pricelist & Client Exporter
    path('pricelist/', views.pricelist_dashboard, name='pricelist_dashboard'),
    path('pricelist/export/', views.export_pricelist_csv, name='export_pricelist_csv'),
    path('pricelist/delete/<int:item_id>/', views.delete_pricelist_item, name='delete_pricelist_item'),
]