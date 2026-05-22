from django import forms
from .models import OrderItem

class ItemForm(forms.ModelForm):
    class Meta:
        model = OrderItem
        fields = ['name', 'quantity', 'compartment']
        widgets = {
            'name': forms.TextInput(attrs={'placeholder': 'Item Name', 'class': 'form-input'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-input'}),
            'compartment': forms.Select(attrs={'class': 'form-input'}),
        }