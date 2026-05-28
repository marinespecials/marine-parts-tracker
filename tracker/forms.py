from django import forms
from .models import Item

class ItemForm(forms.ModelForm):
    class Meta:
        model = Item
        # We include all fields EXCEPT the qr_code, because the system makes that automatically!
        fields = ['name', 'quantity', 'is_delivered', 'compartment', 'offer']
        
        # Optional: Add Bootstrap classes to make the form look nice
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control'}),
            'is_delivered': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'compartment': forms.Select(attrs={'class': 'form-control'}),
            'offer': forms.Select(attrs={'class': 'form-control'}),
        }