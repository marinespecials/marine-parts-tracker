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
    
    # NEW: Field to store the QR code image
    qr_code = models.ImageField(upload_to='qr_codes/', blank=True, null=True)

    def save(self, *args, **kwargs):
        # Only generate a QR code if it doesn't already have one
        if not self.qr_code:
            # Save first to ensure the Item gets a primary key (ID) from the database
            super().save(*args, **kwargs)
            
            # Create the URL for this specific item
            # Ensure the path matches the URL pattern you set in urls.py
            domain = "https://marine-specials-tracker.onrender.com" 
            url = f"{domain}/item/update/{self.id}/"
            
            # Generate the QR code image
            qr = qrcode.QRCode(version=1, box_size=10, border=5)
            qr.add_data(url)
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")
            
            # Save the image to the Django model
            buffer = BytesIO()
            img.save(buffer, format="PNG")
            file_name = f'qr_item_{self.id}.png'
            self.qr_code.save(file_name, ContentFile(buffer.getvalue()), save=False)

        # Final save to commit the new QR code image to the database
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} x{self.quantity}"