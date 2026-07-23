from django.contrib import admin
from .models import Customer, InventoryItem, OrderItem

@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ('name', 'created_at')
    search_fields = ('name',)

@admin.register(InventoryItem)
class InventoryItemAdmin(admin.ModelAdmin):
    list_display = ('part_name', 'part_code', 'category', 'quantity', 'location', 'unit_cost')
    list_filter = ('category', 'location')
    search_fields = ('part_name', 'part_code', 'location')

@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ('order', 'description', 'quantity', 'unit_price', 'is_packed')
    list_filter = ('is_packed',)
    search_fields = ('description', 'order__invoice_number')