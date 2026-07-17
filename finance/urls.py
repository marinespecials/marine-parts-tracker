from django.urls import path
from . import views

app_name = 'finance'

urlpatterns = [
    path('', views.finance_dashboard, name='dashboard'),
    path('upload-ocr/', views.upload_ocr, name='upload_ocr'), # <-- ADD THIS LINE
]