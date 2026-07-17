from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('finance/', include('finance.urls')), # Routes traffic to your new Finance UI
    path('', include('tracker.urls')),         # Your existing tracker/hub routes
]