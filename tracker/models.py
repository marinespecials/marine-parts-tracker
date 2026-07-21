from django.db import models

class Customer(models.Model):
    name = models.CharField(max_length=200)

    def __str__(self):
        return self.name

class Offer(models.Model):
    title = models.CharField(max_length=200)
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='offers')

    def __str__(self):
        return self.title

class Compartment(models.Model):
    name = models.CharField(max_length=100)

    def __str__(self):
        return self.name

class Item(models.Model):
    name = models.CharField(max_length=200)
    quantity = models.IntegerField(default=1)
    is_delivered = models.BooleanField(default=False)
    compartment = models.ForeignKey(Compartment, on_delete=models.CASCADE, related_name='items')
    offer = models.ForeignKey(Offer, on_delete=models.SET_NULL, related_name='items', null=True, blank=True)

# ==========================================
    # 📦 FACILITY RELOCATION MODULE
    # ==========================================
    TRANSFER_STATUSES = [
        ('ACTIVE', 'Active Stock'),
        ('UNUTILIZED', 'Unutilized / Purge'),
        ('PACKED', 'Ready for Transfer'),
        ('MOVED', 'Transferred to New Facility')
    ]
    transfer_status = models.CharField(
        max_length=20, 
        choices=TRANSFER_STATUSES, 
        default='ACTIVE'
    )
    current_piraeus_bin = models.CharField(
        max_length=50, 
        blank=True, 
        help_text="Current bin location (e.g., Rack A2)"
    )
    destination_facility_bin = models.CharField(
        max_length=50, 
        blank=True, 
        help_text="Target location for the reorganization"
    )
    def __str__(self):
        return f"{self.name} x{self.quantity}"