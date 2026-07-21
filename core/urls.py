from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path('finance/', include('finance.urls')), # Routes traffic to your new Finance UI
    path('', include('tracker.urls')),         # Your existing tracker/hub routes
]

# This tells Django to allow browsers to view uploaded media (like QR codes and PDFs)
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)