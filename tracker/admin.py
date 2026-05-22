from django.contrib import admin
# Fixed: Imported 'Item' instead of 'OrderItem'
from .models import Customer, Offer, Compartment, Item

admin.site.register(Customer)
admin.site.register(Offer)
admin.site.register(Compartment)
admin.site.register(Item)