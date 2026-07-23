from django.urls import path
from . import views

urlpatterns = [
    # Main Hub
    path('', views.hub_view, name='hub'),
    path('hub/', views.hub_view, name='app_hub'),
    
    # Orders & Delivery
    path('orders/', views.orders_dashboard, name='orders_dashboard'),
    path('orders/<int:order_id>/convert/', views.convert_order_status, name='convert_order_status'),
    path('orders/delete/<int:order_id>/', views.delete_order, name='delete_order'),

    # Warehouse & Logistics
    path('warehouse/', views.inventory_list, name='inventory_list'),
    path('warehouse/<int:item_id>/adjust/<str:action>/', views.adjust_stock, name='adjust_stock'),
    path('warehouse/<int:item_id>/edit/', views.edit_inventory_item, name='edit_inventory_item'),
    path('warehouse/<int:item_id>/delete/', views.delete_inventory_item, name='delete_inventory_item'),
    
    # Client Ledgers
    path('clients/', views.client_list, name='client_list'),
]