from django.urls import path
from . import views

urlpatterns = [
    # Main Hub
    path('', views.hub_view, name='hub'),
    
    # Warehouse & Inventory Routes
    path('warehouse/', views.inventory_list, name='inventory_list'),
    path('warehouse/<int:item_id>/edit/', views.edit_inventory_item, name='edit_inventory_item'),
    path('warehouse/<int:item_id>/delete/', views.delete_inventory_item, name='delete_inventory_item'),
    
    # Client Ledgers Route
    path('clients/', views.client_list, name='client_list'),
]