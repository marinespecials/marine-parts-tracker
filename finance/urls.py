from django.urls import path
from . import views

app_name = 'finance'

urlpatterns = [
    path('', views.finance_dashboard, name='dashboard'),
    path('upload-ocr/', views.upload_ocr, name='upload_ocr'),
    path('invoice/<int:invoice_id>/review/', views.ocr_review, name='ocr_review'),
    
    # NEW: SAP-STYLE CLIENT PAGE
    path('client/<int:client_id>/', views.client_ledger, name='client_ledger'),
    
    path('update-db/', views.update_cloud_db, name='update_db'),
]