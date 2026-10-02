from django.urls import path
from . import views

app_name = 'finance'

urlpatterns = [
    # Dashboard
    path('', views.finance_dashboard, name='dashboard'),
    
    # Invoice Management
    path('invoices/create/', views.create_invoice, name='create_invoice'),
    path('invoices/<int:invoice_id>/', views.invoice_detail, name='invoice_detail'),
    path('invoices/<int:invoice_id>/edit/', views.edit_invoice, name='edit_invoice'),
    path('invoices/<int:invoice_id>/delete/', views.delete_invoice, name='delete_invoice'),
    path('invoices/<int:invoice_id>/add_item/', views.add_invoice_item, name='add_invoice_item'),
    path('invoices/item/<int:item_id>/delete/', views.delete_invoice_item, name='delete_invoice_item'),
    path('invoices/<int:invoice_id>/update/', views.update_invoice_details, name='update_invoice_details'),

    # Client Ledger
    path('clients/<int:client_id>/', views.client_ledger, name='client_ledger'),

    # Drive & Pricing
    path('import/', views.bulk_import, name='bulk_import'),
    path('pricelist/', views.pricelist_dashboard, name='pricelist_dashboard'),
    path('history/', views.price_history, name='price_history'),
    path('history/<int:record_id>/delete/', views.delete_price_record, name='delete_price_record'),
    path('export/', views.export_finances, name='export_finances'),
]