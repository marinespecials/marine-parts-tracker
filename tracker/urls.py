from django.urls import path
from . import views

urlpatterns = [
    # Main Landing Hub
    path('', views.hub_view, name='hub'),
    path('hub/', views.hub_view, name='app_hub'),  # Alias compatibility
    
    # Restored Simple Orders & Delivery Manager
    path('orders/', views.orders_dashboard, name='orders_dashboard'),
    path('orders/delete/<int:order_id>/', views.delete_order, name='delete_order'),

    # Warehouse & Inventory
    path('warehouse/', views.inventory_list, name='inventory_list'),
    path('warehouse/<int:item_id>/edit/', views.edit_inventory_item, name='edit_inventory_item'),
    path('warehouse/<int:item_id>/delete/', views.delete_inventory_item, name='delete_inventory_item'),
    
    # Client Ledgers
    path('clients/', views.client_list, name='client_list'),
]