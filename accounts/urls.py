from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from accounts.views import FraudGuardTokenObtainPairView, CurrentUserView

urlpatterns = [
    path("token/", FraudGuardTokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("me/", CurrentUserView.as_view(), name="current_user"),
]
