from django.contrib import admin
from .models import Customer, InventoryItem

@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ('name', 'email', 'phone', 'created_at')
    search_fields = ('name', 'email', 'phone')

@admin.register(InventoryItem)
class InventoryItemAdmin(admin.ModelAdmin):
    list_display = ('part_name', 'part_code', 'category', 'quantity', 'location', 'unit_cost')
    list_filter = ('category', 'location')
    search_fields = ('part_name', 'part_code', 'location')