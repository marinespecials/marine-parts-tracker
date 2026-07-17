from django.urls import path
from . import views

app_name = 'finance'

urlpatterns = [
    # This will be the main dashboard for the finance app
    path('', views.finance_dashboard, name='dashboard'),
]