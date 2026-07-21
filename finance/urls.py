from django.urls import path
from . import views

app_name = 'finance'

urlpatterns = [
    path('', views.finance_dashboard, name='dashboard'),
    path('upload-ocr/', views.upload_ocr, name='upload_ocr'),
    path('invoice/<int:invoice_id>/review/', views.ocr_review, name='ocr_review'),
    path('client/<int:client_id>/', views.client_ledger, name='client_ledger'),
    
    # NEW DELETE ROUTE
    path('invoice/<int:invoice_id>/delete/', views.delete_invoice, name='delete_invoice'),
    
    path('update-db/', views.update_cloud_db, name='update_db'),
    # NEW EXPORT ROUTE
    path('export-finances/', views.export_finances_csv, name='export_finances'),
    # NEW SAP ENTERPRISE PAGE
    path('sap-enterprise/', views.sap_overview, name='sap_overview'),
]   