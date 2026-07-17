from django.urls import path
from . import views

urlpatterns = [
    # The new Main Hub is now the homepage (loads when you go to your website's base URL)
    path('', views.app_hub, name='app_hub'),
    
    # TEMPORARY SECRET ROUTE - Delete this after you create your admin account!
    path('setup-admin/', views.setup_admin, name='setup_admin'),
    
    # The Tracker Dashboard moved here (loads at yourwebsite.com/tracker/)
    path('tracker/', views.dashboard, name='dashboard'),
    
    # --- All your existing tracker routes ---
    path('compartment/<int:comp_id>/', views.compartment_detail, name='compartment_detail'),
    path('offer/add/', views.add_offer, name='add_offer'),
    path('offer/<int:offer_id>/edit/', views.edit_offer, name='edit_offer'),
    path('offer/<int:offer_id>/delete/', views.delete_offer, name='delete_offer'),
    path('offer/<int:offer_id>/', views.offer_detail, name='offer_detail'),
    path('items/', views.item_list, name='item_list'),
    
    # Original add item for specific offers
    path('offer/<int:offer_id>/item/add/', views.add_item, name='add_item'),
    
    # The Add Master Item URL
    path('item/add/', views.add_master_item, name='add_master_item'),
    
    path('item/<int:item_id>/toggle/', views.toggle_item, name='toggle_item'),
    path('item/<int:item_id>/delete/', views.delete_item, name='delete_item'),
    path('compartment/add/', views.add_compartment, name='add_compartment'),
    path('compartment/<int:comp_id>/edit/', views.edit_compartment, name='edit_compartment'),
    path('compartment/<int:comp_id>/delete/', views.delete_compartment, name='delete_compartment'),
    path('clients/', views.client_list, name='client_list'),
    path('client/<int:client_id>/edit/', views.edit_client, name='edit_client'),
    path('client/<int:client_id>/delete/', views.delete_client, name='delete_client'),
    path('offer/<int:offer_id>/allocate/', views.allocate_item, name='allocate_item'),
    path('item/<int:item_id>/unallocate/', views.unallocate_item, name='unallocate_item'),
    
    # The Excel Export route
    path('export-inventory/', views.export_items_to_excel, name='export_inventory'),
    
    # The Live Quantity Update route
    path('item/<int:item_id>/update-quantity/', views.update_item_quantity, name='update_item_quantity'),
]