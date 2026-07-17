import csv
from django.http import HttpResponse
from django.shortcuts import render, get_object_or_404, redirect
from .models import Offer, Compartment, Item, Customer
from django.db.models import Q
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

# 1. UPDATED: Send unique part names to the frontend for Auto-Suggest
def offer_detail(request, offer_id):
    offer = get_object_or_404(Offer, id=offer_id)
    items = offer.items.all()
    available_in_storage = Item.objects.filter(offer__isnull=True)
    
    # NEW: Grab a list of all unique part names ever typed into the system
    unique_part_names = Item.objects.values_list('name', flat=True).distinct()
    
    context = {
        'offer': offer, 
        'items': items, 
        'compartments': Compartment.objects.all(),
        'available_items': available_in_storage, 
        'unique_part_names': unique_part_names, # Sending them to the HTML
        'progress': int((items.filter(is_delivered=True).count() / items.count()) * 100) if items.count() > 0 else 0
    }
    return render(request, 'tracker/offer_detail.html', context)

# 2. ADD THIS NEW FUNCTION (Assigns an item to an order)
def allocate_item(request, offer_id):
    if request.method == 'POST':
        item_id = request.POST.get('item_id')
        if item_id:
            item = get_object_or_404(Item, id=item_id)
            offer = get_object_or_404(Offer, id=offer_id)
            item.offer = offer
            item.save()
    return redirect('offer_detail', offer_id=offer_id)

# 3. ADD THIS NEW FUNCTION (Removes an item from an order back to storage)
def unallocate_item(request, item_id):
    item = get_object_or_404(Item, id=item_id)
    offer_id = item.offer.id
    if request.method == 'POST':
        item.offer = None # Removes the link, putting it back in storage
        item.save()
    return redirect('offer_detail', offer_id=offer_id)

def item_list(request):
    return render(request, 'tracker/item_list.html', {'items': Item.objects.all().order_by('offer__title')})

# 2. UPDATED: Prevent duplicate rows and merge quantities instead
def add_item(request, offer_id):
    if request.method == 'POST':
        name = request.POST.get('name').strip() # .strip() removes accidental spaces
        quantity = int(request.POST.get('quantity', 1))
        comp_id = request.POST.get('compartment')
        
        # Check if this exact part already exists in this specific order and location
        existing_item = Item.objects.filter(
            name__iexact=name, # __iexact means it ignores capital letters when matching
            compartment_id=comp_id, 
            offer_id=offer_id
        ).first()
        
        if existing_item:
            # WMS FEATURE: If it exists, don't make a new row. Just add the quantities!
            existing_item.quantity += quantity
            existing_item.save()
        else:
            # If it truly doesn't exist yet, create a normal new row
            Item.objects.create(
                name=name, 
                quantity=quantity, 
                compartment=get_object_or_404(Compartment, id=comp_id), 
                offer=get_object_or_404(Offer, id=offer_id)
            )
    return redirect('offer_detail', offer_id=offer_id)

# NEW: Add item to the master list via the frontend form
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
    return redirect('offer_detail', offer_id=item.offer.id)

def delete_item(request, item_id):
    item = get_object_or_404(Item, id=item_id)
    offer_id = item.offer.id
    if request.method == 'POST': item.delete()
    return redirect('offer_detail', offer_id=offer_id)

def add_compartment(request):
    if request.method == 'POST' and request.POST.get('name'): Compartment.objects.create(name=request.POST.get('name'))
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
    if request.method == 'POST' and request.POST.get('name'): Customer.objects.get_or_create(name=request.POST.get('name'))
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

# --- UPDATED EXPORT FUNCTION ---
def export_items_to_excel(request):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="marine_specials_inventory.csv"'
    writer = csv.writer(response)

    # Grab all compartments (categories) to group the list
    compartments = Compartment.objects.prefetch_related('items__offer__customer').all()

    for compartment in compartments:
        # 1. Create a bold visual header for each category
        writer.writerow([f'=== LOCATION / CATEGORY: {compartment.name.upper()} ==='])
        
        # 2. Write the column titles for this specific section
        writer.writerow(['Item Name', 'Quantity', 'Status', 'Assigned Order', 'Client'])

        # 3. Get all the items that belong ONLY to this compartment
        items = compartment.items.all()

        if not items:
            # If the compartment is empty, note it so you know
            writer.writerow(['(Empty)', '-', '-', '-', '-'])
        else:
            # Loop through the items and write them under the category header
            for item in items:
                offer_title = item.offer.title if item.offer else "Unassigned"
                customer_name = item.offer.customer.name if (item.offer and item.offer.customer) else "Unassigned"

                writer.writerow([
                    item.name,
                    item.quantity,
                    "Delivered" if item.is_delivered else "Pending",
                    offer_title,
                    customer_name
                ])
        
        # 4. Add a couple of blank rows to create visual spacing before the next category
        writer.writerow([])
        writer.writerow([])

    return response

# --- NEW QUANTITY UPDATE FUNCTION ---
def update_item_quantity(request, item_id):
    item = get_object_or_404(Item, id=item_id)
    if request.method == 'POST':
        new_quantity = request.POST.get('quantity')
        # Make sure they actually typed a number and it isn't negative
        if new_quantity and int(new_quantity) >= 0:
            item.quantity = int(new_quantity)
            item.save()
            
    # This trick safely redirects you back to the exact page you were just looking at
    previous_page = request.META.get('HTTP_REFERER', 'dashboard')
    return redirect(previous_page)