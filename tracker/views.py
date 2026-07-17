import csv
from django.http import HttpResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.db.models import Q, Prefetch
from .models import Offer, Compartment, Item, Customer
from .forms import ItemForm

def dashboard(request):
    query = request.GET.get('q', '')
    search_results = None
    if query:
        search_results = Item.objects.filter(Q(name__icontains=query) | Q(offer__title__icontains=query))
    
    offers = Offer.objects.all()
    compartments = Compartment.objects.all()
    all_items = Item.objects.all()
    
    total_parts = all_items.count()
    delivered_parts = all_items.filter(is_delivered=True).count()
    global_progress = int((delivered_parts / total_parts) * 100) if total_parts > 0 else 0

    for offer in offers:
        count = offer.items.count()
        offer.progress = int((offer.items.filter(is_delivered=True).count() / count) * 100) if count > 0 else 0
            
    context = {
        'offers': offers, 'compartments': compartments, 'search_query': query, 
        'search_results': search_results, 'total_parts': total_parts, 'global_progress': global_progress
    }
    return render(request, 'tracker/dashboard.html', context)

def compartment_detail(request, comp_id):
    compartment = get_object_or_404(Compartment, id=comp_id)
    return render(request, 'tracker/compartment_detail.html', {'compartment': compartment, 'items': compartment.items.all()})

# --- OFFER/ITEM/CLIENT LOGIC ---
def add_offer(request):
    if request.method == 'POST':
        customer, _ = Customer.objects.get_or_create(name=request.POST.get('customer_name'))
        new_offer = Offer.objects.create(title=request.POST.get('title'), customer=customer)
        return redirect('offer_detail', offer_id=new_offer.id)
    return render(request, 'tracker/add_offer.html', {'customers': Customer.objects.all()})

def edit_offer(request, offer_id):
    offer = get_object_or_404(Offer, id=offer_id)
    if request.method == 'POST':
        customer, _ = Customer.objects.get_or_create(name=request.POST.get('customer_name'))
        offer.title = request.POST.get('title')
        offer.customer = customer
        offer.save()
        return redirect('dashboard')
    return render(request, 'tracker/edit_offer.html', {'offer': offer, 'customers': Customer.objects.all()})

def delete_offer(request, offer_id):
    if request.method == 'POST':
        get_object_or_404(Offer, id=offer_id).delete()
    return redirect('dashboard')

def offer_detail(request, offer_id):
    offer = get_object_or_404(Offer, id=offer_id)
    items = offer.items.all()
    available_in_storage = Item.objects.filter(offer__isnull=True)
    unique_part_names = Item.objects.values_list('name', flat=True).distinct()
    
    context = {
        'offer': offer, 
        'items': items, 
        'compartments': Compartment.objects.all(),
        'available_items': available_in_storage, 
        'unique_part_names': unique_part_names,
        'progress': int((items.filter(is_delivered=True).count() / items.count()) * 100) if items.count() > 0 else 0
    }
    return render(request, 'tracker/offer_detail.html', context)

def allocate_item(request, offer_id):
    if request.method == 'POST':
        item_id = request.POST.get('item_id')
        if item_id:
            item = get_object_or_404(Item, id=item_id)
            offer = get_object_or_404(Offer, id=offer_id)
            item.offer = offer
            item.save()
    return redirect('offer_detail', offer_id=offer_id)

def unallocate_item(request, item_id):
    item = get_object_or_404(Item, id=item_id)
    offer_id = item.offer.id if item.offer else None
    if request.method == 'POST':
        item.offer = None
        item.save()
    return redirect('offer_detail', offer_id=offer_id) if offer_id else redirect('item_list')

# --- MOBILE QR INTERCEPTOR UPDATED HERE ---
def item_list(request):
    scanned_id = request.GET.get('id')
    if scanned_id:
        # If the URL has ?id=... (like from a QR scan), show the mobile screen!
        item = get_object_or_404(Item, id=scanned_id)
        return render(request, 'tracker/mobile_item_detail.html', {'item': item})
        
    # Otherwise, load the normal grouped Master List
    compartments = Compartment.objects.prefetch_related(
        Prefetch('items', queryset=Item.objects.order_by('name', 'offer__title'))
    ).all()
    return render(request, 'tracker/item_list.html', {'compartments': compartments})

def add_item(request, offer_id):
    if request.method == 'POST':
        name = request.POST.get('name').strip()
        quantity = int(request.POST.get('quantity', 1))
        comp_id = request.POST.get('compartment')
        
        existing_item = Item.objects.filter(name__iexact=name, compartment_id=comp_id, offer_id=offer_id).first()
        
        if existing_item:
            existing_item.quantity += quantity
            existing_item.save()
        else:
            Item.objects.create(
                name=name, quantity=quantity, 
                compartment=get_object_or_404(Compartment, id=comp_id), 
                offer=get_object_or_404(Offer, id=offer_id)
            )
    return redirect('offer_detail', offer_id=offer_id)

def add_master_item(request):
    if request.method == 'POST':
        form = ItemForm(request.POST)
        if form.is_valid():
            form.save() 
            return redirect('item_list') 
    else:
        form = ItemForm()
    return render(request, 'tracker/add_item.html', {'form': form})

def toggle_item(request, item_id):
    item = get_object_or_404(Item, id=item_id)
    item.is_delivered = not item.is_delivered
    item.save()
    # Now perfectly returns you to the mobile page if scanned from a phone
    previous_page = request.META.get('HTTP_REFERER', 'dashboard')
    return redirect(previous_page)

def delete_item(request, item_id):
    item = get_object_or_404(Item, id=item_id)
    if request.method == 'POST': 
        item.delete()
    previous_page = request.META.get('HTTP_REFERER', 'dashboard')
    return redirect(previous_page)

def add_compartment(request):
    if request.method == 'POST' and request.POST.get('name'): 
        Compartment.objects.create(name=request.POST.get('name'))
    return redirect('dashboard')

def edit_compartment(request, comp_id):
    comp = get_object_or_404(Compartment, id=comp_id)
    if request.method == 'POST':
        comp.name = request.POST.get('name')
        comp.save()
        return redirect('dashboard')
    return render(request, 'tracker/edit_compartment.html', {'compartment': comp})

def delete_compartment(request, comp_id):
    comp = get_object_or_404(Compartment, id=comp_id)
    if request.method == 'POST' and comp.items.count() == 0: comp.delete()
    return redirect('dashboard')

def client_list(request):
    if request.method == 'POST' and request.POST.get('name'): 
        Customer.objects.get_or_create(name=request.POST.get('name'))
    return render(request, 'tracker/client_list.html', {'customers': Customer.objects.all()})

def edit_client(request, client_id):
    c = get_object_or_404(Customer, id=client_id)
    if request.method == 'POST':
        c.name = request.POST.get('name')
        c.save()
        return redirect('client_list')
    return render(request, 'tracker/edit_client.html', {'client': c})

def delete_client(request, client_id):
    c = get_object_or_404(Customer, id=client_id)
    if request.method == 'POST' and c.offers.count() == 0: c.delete()
    return redirect('client_list')

def export_items_to_excel(request):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="marine_specials_inventory.csv"'
    writer = csv.writer(response)

    compartments = Compartment.objects.prefetch_related('items__offer__customer').all()

    for compartment in compartments:
        writer.writerow([f'=== LOCATION / CATEGORY: {compartment.name.upper()} ==='])
        writer.writerow(['Item Name', 'Quantity', 'Status', 'Assigned Order', 'Client'])

        items = compartment.items.all()
        if not items:
            writer.writerow(['(Empty)', '-', '-', '-', '-'])
        else:
            for item in items:
                offer_title = item.offer.title if item.offer else "Unassigned"
                customer_name = item.offer.customer.name if (item.offer and item.offer.customer) else "Unassigned"

                writer.writerow([
                    item.name, item.quantity,
                    "Delivered" if item.is_delivered else "Pending",
                    offer_title, customer_name
                ])
        writer.writerow([])
        writer.writerow([])
    return response

def update_item_quantity(request, item_id):
    item = get_object_or_404(Item, id=item_id)
    if request.method == 'POST':
        new_quantity = request.POST.get('quantity')
        if new_quantity and int(new_quantity) >= 0:
            item.quantity = int(new_quantity)
            item.save()
    previous_page = request.META.get('HTTP_REFERER', 'dashboard')
    return redirect(previous_page)

def duplicate_item(request, item_id):
    original_item = get_object_or_404(Item, id=item_id)
    if request.method == 'POST':
        Item.objects.create(
            name=f"{original_item.name} (Copy)", quantity=original_item.quantity,
            compartment=original_item.compartment, offer=original_item.offer, is_delivered=False 
        )
    previous_page = request.META.get('HTTP_REFERER', 'dashboard')
    return redirect(previous_page)