from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('add-offer/', views.add_offer, name='add_offer'),
    path('offer/<int:offer_id>/', views.offer_detail, name='offer_detail'),
    path('edit-offer/<int:offer_id>/', views.edit_offer, name='edit_offer'),
    path('delete-offer/<int:offer_id>/', views.delete_offer, name='delete_offer'),
    
    path('compartment/<int:comp_id>/', views.compartment_detail, name='compartment_detail'),
    
    path('items/', views.item_list, name='item_list'),
    path('offer/<int:offer_id>/add/', views.add_item, name='add_item'),
    path('toggle-item/<int:item_id>/', views.toggle_item, name='toggle_item'),
    path('delete-item/<int:item_id>/', views.delete_item, name='delete_item'),
    
    path('add-compartment/', views.add_compartment, name='add_compartment'),
    path('edit-compartment/<int:comp_id>/', views.edit_compartment, name='edit_compartment'),
    path('delete-compartment/<int:comp_id>/', views.delete_compartment, name='delete_compartment'),

    path('clients/', views.client_list, name='client_list'),
    path('edit-client/<int:client_id>/', views.edit_client, name='edit_client'),
    path('delete-client/<int:client_id>/', views.delete_client, name='delete_client'),
]
from django.urls import path
from . import views

urlpatterns = [
    # ... your other urls ...
    path('item/add/', views.add_item, name='add_item'),
]