from django.urls import path
from . import views

app_name = 'finance'

urlpatterns = [
    path('', views.finance_dashboard, name='dashboard'),
    path('create/', views.create_invoice, name='create_invoice'),
    path('bulk-import/', views.bulk_import_links, name='bulk_import'),
    path('invoice/<int:invoice_id>/edit/', views.edit_invoice, name='edit_invoice'),
    path('client/<int:client_id>/', views.client_ledger, name='client_ledger'),
    path('invoice/<int:invoice_id>/delete/', views.delete_invoice, name='delete_invoice'),
    path('export-finances/', views.export_finances_csv, name='export_finances'),
    path('update-db/', views.update_cloud_db, name='update_db'),
]