from django.contrib import admin
from django.contrib.auth import views as auth_views

from core.views import ThrottledLoginView
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('login/', ThrottledLoginView.as_view(), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('', include('tracker.urls')),  # Main Hub and Warehouse
    path('finance/', include('finance.urls')),  # Financial Intelligence
]
