from django.urls import path
from . import views

urlpatterns = [
    # Main Portal
    path('', views.hub_view, name='hub'),
    path('hub/', views.hub_view, name='app_hub'),
    
    # Live Operations Board
    path('live-board/', views.active_board, name='active_board'),
    
    # Orders & Status Pipeline
    path('orders/', views.orders_dashboard, name='orders_dashboard'),
    path('orders/<int:order_id>/', views.order_detail, name='order_detail'),
    path('orders/<int:order_id>/add_item/', views.add_order_item, name='add_order_item'),
    path('orders/item/<int:item_id>/delete/', views.delete_order_item, name='delete_order_item'),
    path('orders/item/<int:item_id>/toggle/', views.toggle_item_packed, name='toggle_item_packed'),
    path('orders/<int:order_id>/status/<str:new_status>/', views.change_order_status, name='change_order_status'),
    path('orders/<int:order_id>/delete/', views.delete_order, name='delete_order'),

    # Warehouse & Master Items List
    path('warehouse/', views.inventory_list, name='inventory_list'),
    path('warehouse/<int:item_id>/adjust/<str:action>/', views.adjust_stock, name='adjust_stock'),
    path('warehouse/<int:item_id>/edit/', views.edit_inventory_item, name='edit_inventory_item'),
    path('warehouse/<int:item_id>/delete/', views.delete_inventory_item, name='delete_inventory_item'),
    
    # Client Ledgers
    path('clients/', views.client_list, name='client_list'),
]