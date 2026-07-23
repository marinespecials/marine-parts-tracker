from django.contrib import admin
from .models import Invoice, ClientFinancialProfile, PriceRecord, MasterPricelistItem

@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ('invoice_number', 'customer', 'total_amount', 'issue_date', 'status')
    list_filter = ('status', 'issue_date')
    search_fields = ('invoice_number', 'customer__name')

@admin.register(ClientFinancialProfile)
class ClientFinancialProfileAdmin(admin.ModelAdmin):
    list_display = ('customer', 'payment_terms_days') if hasattr(ClientFinancialProfile, 'payment_terms_days') else ('customer',)
    search_fields = ('customer__name',)

@admin.register(PriceRecord)
class PriceRecordAdmin(admin.ModelAdmin):
    list_display = ('part_name', 'part_code', 'supplier_or_client_name', 'unit_price', 'currency', 'date_recorded')
    search_fields = ('part_name', 'part_code', 'supplier_or_client_name')

@admin.register(MasterPricelistItem)
class MasterPricelistItemAdmin(admin.ModelAdmin):
    list_display = ('part_name', 'part_code', 'category', 'brand', 'cost_price', 'markup_percent', 'availability')
    list_filter = ('category', 'availability')
    search_fields = ('part_name', 'part_code', 'brand')