from django.shortcuts import render
from .models import Invoice, ClientFinancialProfile, PriceRecord

def finance_dashboard(request):
    # Fetch all data to display on the dashboard
    invoices = Invoice.objects.all().order_by('-issue_date')
    profiles = ClientFinancialProfile.objects.all()
    # Get the 10 most recent price records
    recent_prices = PriceRecord.objects.all().order_by('-date_recorded')[:10]
    
    context = {
        'invoices': invoices,
        'profiles': profiles,
        'recent_prices': recent_prices,
    }
    return render(request, 'finance/finance_dashboard.html', context)