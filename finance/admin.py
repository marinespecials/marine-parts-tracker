from django.contrib import admin
from .models import Invoice, ClientFinancialProfile, PriceRecord

@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ('invoice_number', 'customer', 'issue_date', 'total_amount', 'status')
    search_fields = ('invoice_number', 'customer__name')

@admin.register(ClientFinancialProfile)
class ClientFinancialProfileAdmin(admin.ModelAdmin):
    list_display = ('customer', 'lifetime_revenue', 'internal_rating', 'payment_terms_days')

@admin.register(PriceRecord)
class PriceRecordAdmin(admin.ModelAdmin):
    list_display = ('date_recorded', 'supplier_or_client_name', 'part_name', 'unit_price', 'currency')