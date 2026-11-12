from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from accounts.models import User
from accounts.serializers import FraudGuardTokenObtainPairSerializer, UserSerializer


class FraudGuardTokenObtainPairView(TokenObtainPairView):
    serializer_class = FraudGuardTokenObtainPairSerializer


class CurrentUserView(generics.RetrieveAPIView):
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        return self.request.user
