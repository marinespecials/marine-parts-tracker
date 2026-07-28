from django.urls import path
from . import views

urlpatterns = [
    # Main Portal Hub
    path('', views.hub_view, name='hub'),
    path('hub/', views.hub_view, name='app_hub'),
    
    # Universal Global Search
    path('search/', views.global_search, name='global_search'),
    
    # Live Operations Board
    path('live-board/', views.active_board, name='active_board'),
    
    # Orders & Status Pipeline
    path('orders/', views.orders_dashboard, name='orders_dashboard'),
    path('orders/create/', views.create_order, name='create_order'),
    path('orders/<int:order_id>/', views.order_detail, name='order_detail'),
    path('orders/<int:order_id>/pack/', views.mobile_packing_list, name='mobile_packing_list'),
    path('orders/<int:order_id>/add_item/', views.add_order_item, name='add_order_item'),
    path('orders/item/<int:item_id>/adjust/<str:action>/', views.adjust_order_item_qty, name='adjust_order_item_qty'),
    path('orders/item/<int:item_id>/link/', views.link_order_item_to_inventory, name='link_order_item_to_inventory'),
    path('orders/sync-history/', views.sync_all_historical_orders, name='sync_all_historical_orders'), # <-- NEW: 1-Click Sync
    path('orders/<int:order_id>/convert/', views.convert_order_to_invoice, name='convert_order_to_invoice'),
    path('orders/item/<int:item_id>/delete/', views.delete_order_item, name='delete_order_item'),
    path('orders/item/<int:item_id>/toggle/', views.toggle_item_packed, name='toggle_item_packed'),
    path('orders/<int:order_id>/status/<str:new_status>/', views.change_order_status, name='change_order_status'),
    path('orders/<int:order_id>/delete/', views.delete_order, name='delete_order'),

    # Warehouse & Stock
    path('warehouse/', views.inventory_list, name='inventory_list'),
    path('warehouse/<int:item_id>/adjust/<str:action>/', views.adjust_stock, name='adjust_stock'),
    path('warehouse/<int:item_id>/edit/', views.edit_inventory_item, name='edit_inventory_item'),
    path('warehouse/<int:item_id>/delete/', views.delete_inventory_item, name='delete_inventory_item'),
    
    # Client Catalog & Directory
    path('catalog/', views.client_pricelist, name='client_pricelist'),
    path('clients/', views.client_list, name='client_list'),
]