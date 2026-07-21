from django.urls import path
from . import views

app_name = 'finance'

urlpatterns = [
    path('', views.finance_dashboard, name='dashboard'),
    path('upload-ocr/', views.upload_ocr, name='upload_ocr'),
    
    # NEW REVIEW ROUTE
    path('invoice/<int:invoice_id>/review/', views.ocr_review, name='ocr_review'),
    
    path('update-db/', views.update_cloud_db, name='update_db'),
]