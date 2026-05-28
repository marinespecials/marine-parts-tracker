from django.db import models
import qrcode
from io import BytesIO
from django.core.files.base import ContentFile

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
    offer = models.ForeignKey(Offer, on_delete=models.CASCADE, related_name='items')
    
    # The field causing the 500 error because the database doesn't know it exists yet
    qr_code = models.ImageField(upload_to='qr_codes/', blank=True, null=True)

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        
        # Save first to ensure the Item gets a primary key (ID)
        super().save(*args, **kwargs)
        
        # Only generate a QR code if it's a brand new item and doesn't have one
        if is_new and not self.qr_code:
            domain = "https://marine-specials-tracker.onrender.com" 
            url = f"{domain}/items/" 
            
            qr = qrcode.QRCode(version=1, box_size=10, border=5)
            qr.add_data(url)
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")
            
            buffer = BytesIO()
            img.save(buffer, format="PNG")
            file_name = f'qr_item_{self.id}.png'
            self.qr_code.save(file_name, ContentFile(buffer.getvalue()), save=False)
            
            # Remove force_insert to prevent database crash on the second save
            kwargs.pop('force_insert', None)
            super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} x{self.quantity}"