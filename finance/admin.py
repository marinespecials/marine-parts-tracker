from django.contrib import admin
from .models import ClientFinancialProfile, Invoice, PriceRecord

@admin.register(ClientFinancialProfile)
class ClientFinancialProfileAdmin(admin.ModelAdmin):
    list_display = ('customer', 'internal_rating', 'payment_terms_days', 'lifetime_revenue')
    search_fields = ('customer__name',)
    list_filter = ('internal_rating',)

@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ('invoice_number', 'customer', 'offer', 'issue_date', 'total_amount', 'status')
    search_fields = ('invoice_number', 'customer__name', 'offer__title')
    list_filter = ('status', 'issue_date')

@admin.register(PriceRecord)
class PriceRecordAdmin(admin.ModelAdmin):
    list_display = ('part_name', 'transaction_type', 'unit_price', 'currency', 'supplier_or_client_name', 'date_recorded')
    search_fields = ('part_name', 'supplier_or_client_name', 'invoice__invoice_number')
    list_filter = ('transaction_type', 'date_recorded')