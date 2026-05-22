from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('tracker.urls')), # This tells Django to look at your tracker app for the homepage
]