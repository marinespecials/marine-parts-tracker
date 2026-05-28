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

def offer_detail(request, offer_id):
    offer = get_object_or_404(Offer, id=offer_id)
    items = offer.items.all()
    context = {
        'offer': offer, 'items': items, 'compartments': Compartment.objects.all(),
        'progress': int((items.filter(is_delivered=True).count() / items.count()) * 100) if items.count() > 0 else 0
    }
    return render(request, 'tracker/offer_detail.html', context)

def item_list(request):
    return render(request, 'tracker/item_list.html', {'items': Item.objects.all().order_by('offer__title')})

# Original add_item for specific offers
def add_item(request, offer_id):
    if request.method == 'POST':
        Item.objects.create(name=request.POST.get('name'), quantity=request.POST.get('quantity'), 
                            compartment=get_object_or_404(Compartment, id=request.POST.get('compartment')), 
                            offer=get_object_or_404(Offer, id=offer_id))
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