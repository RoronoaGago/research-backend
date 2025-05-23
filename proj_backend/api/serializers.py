from rest_framework import serializers
from django.contrib.auth import authenticate
from .models import User, Transaction, Customer, Rating
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import authenticate


from rest_framework import serializers
from django.contrib.auth import get_user_model
User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            "id",
            "first_name",
            "last_name",
            "username",
            "password",
            "date_of_birth",
            "email",
            "phone_number",
        ]
        extra_kwargs = {
            "password": {
                "write_only": False,
                "min_length": 8,  # Enforce minimum length
                "style": {"input_type": "password"}  # Hide in browsable API
            },
            "email": {"required": True},  # Force email if needed
            # Preserve whitespace if desired
            "username": {"trim_whitespace": False}
        }

    def validate_email(self, value):
        value = value.lower().strip()  # Normalize email (lowercase + trim whitespace)
    
        # Skip uniqueness check if email hasn't changed (only during updates)
        if self.instance and self.instance.email.lower() == value:
            return value
    
        # Check for existing emails (case-insensitive)
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("A user with this email already exists.")
    
        return value

    def create(self, validated_data):
        """Handle extra fields from custom User model"""
        user = User.objects.create_user(
            **validated_data,
            # Auto-activate users (or set False for email verification)
            is_active=True
        )
        return user

    def update(self, instance, validated_data):
        password = validated_data.pop('password', None)
        user = super().update(instance, validated_data)

        if password:
            user.set_password(password)  # Hashes the new password
            user.save()

        return user


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)

        # Add custom claims
        token['first_name'] = user.first_name
        token['last_name'] = user.last_name
        token['username'] = user.username
        # Assuming these fields exist on your User model
        token['email'] = user.email
        return token


class CustomerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Customer
        fields = [
            "id",
            "first_name",
            "last_name",
            "address",
            "contact_number",
            "created_at",
        ]
        read_only_fields = ["created_at"]
        extra_kwargs = {
            "contact_number": {"validators": []}  # Disable unique validator
        }


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(write_only=True)

    def validate(self, data):
        username = data.get('username')
        password = data.get('password')

        if username and password:
            user = authenticate(username=username, password=password)
            if user:
                if not user.is_active:
                    raise serializers.ValidationError(
                        "User account is disabled.")
                data['user'] = user
            else:
                raise serializers.ValidationError(
                    "Unable to log in with provided credentials.")
        else:
            raise serializers.ValidationError(
                "Must include 'username' and 'password'.")
        return data


class TransactionSerializer(serializers.ModelSerializer):
    customer = CustomerSerializer()
    service_type_display = serializers.CharField(
        source="get_service_type_display", read_only=True
    )
    status_display = serializers.CharField(
        source="get_status_display", read_only=True)

    class Meta:
        model = Transaction
        fields = "__all__"
        read_only_fields = ["created_at", "updated_at", "completed_at"]

    def update(self, instance, validated_data):
        customer_data = validated_data.pop("customer", None)

        if customer_data:
            # More robust customer lookup/update
            customer_serializer = CustomerSerializer(
                instance=instance.customer,  # Existing customer instance
                data=customer_data,
                partial=True  # Allow partial updates
            )

            if customer_serializer.is_valid():
                customer = customer_serializer.save()
                instance.customer = customer
            else:
                # Handle validation errors - you might want to raise an exception
                raise serializers.ValidationError({
                    'customer': customer_serializer.errors
                })

        # Update other fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        instance.save()
        return instance
    customer = CustomerSerializer()
    service_type_display = serializers.CharField(
        source="get_service_type_display", read_only=True
    )
    status_display = serializers.CharField(
        source="get_status_display", read_only=True)

    class Meta:
        model = Transaction
        fields = "__all__"
        read_only_fields = ["created_at", "updated_at", "completed_at"]

    def update(self, instance, validated_data):
        # Handle nested updates for the customer field
        customer_data = validated_data.pop("customer", None)
        if customer_data:
            # Retrieve the customer instance using a unique field (e.g., contact_number)
            customer = Customer.objects.filter(
                contact_number=customer_data.get("contact_number")).first()
            if not customer:
                # Create a new customer if it doesn't exist
                customer = Customer.objects.create(**customer_data)
            instance.customer = customer  # Update the foreign key reference

        # Update other fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        instance.save()
        return instance


class TransactionCreateSerializer(serializers.ModelSerializer):
    customer = CustomerSerializer()

    class Meta:
        model = Transaction
        fields = "__all__"

    def create(self, validated_data):
        customer_data = validated_data.pop("customer")
        contact_number = customer_data["contact_number"].strip().replace(
            " ", "")

        # Get or create customer (bypassing serializer validation)
        customer, created = Customer.objects.get_or_create(
            contact_number=contact_number, defaults=customer_data
        )

        # Create transaction
        transaction = Transaction.objects.create(
            customer=customer, **validated_data)

        return transaction

    customer = CustomerSerializer()

    class Meta:
        model = Transaction
        fields = "__all__"

    def validate(self, data):
        # Skip automatic unique validation for customer contact_number
        return data

    def create(self, validated_data):
        customer_data = validated_data.pop("customer")
        contact_number = customer_data["contact_number"].strip().replace(
            " ", "")

        # Manually handle customer lookup/creation
        try:
            customer = Customer.objects.get(contact_number=contact_number)
        except Customer.DoesNotExist:
            customer = Customer.objects.create(**customer_data)

        return Transaction.objects.create(customer=customer, **validated_data)

    customer = CustomerSerializer()

    class Meta:
        model = Transaction
        fields = [
            "customer",
            "service_type",
            "regular_clothes_weight",
            "jeans_weight",
            "linens_weight",
            "comforter_weight",
            "subtotal",
            "additional_fee",
            "grand_total",
        ]

    def create(self, validated_data):
        customer_data = validated_data.pop("customer")

        # Clean the phone number (remove spaces, dashes, etc.)
        contact_number = (
            customer_data["contact_number"].strip().replace(
                " ", "").replace("-", "")
        )

        # Try to get the existing customer or create a new one
        customer, created = Customer.objects.get_or_create(
            contact_number=contact_number,
            defaults={
                "first_name": customer_data["first_name"],
                "last_name": customer_data["last_name"],
                "address": customer_data["address"],
                "contact_number": contact_number,  # Use cleaned version
            },
        )

        # Create the transaction
        transaction = Transaction.objects.create(
            customer=customer, **validated_data)

        return transaction


class DashboardMetricsSerializer(serializers.Serializer):
    total_sales = serializers.DecimalField(max_digits=10, decimal_places=2)
    total_transactions = serializers.IntegerField()
    start_date = serializers.DateField()
    end_date = serializers.DateField()
    ongoing_services = serializers.IntegerField()
    recent_transactions = serializers.SerializerMethodField()
    transactions = serializers.ListField(
        child=serializers.DictField(), required=False)

    def get_recent_transactions(self, obj):
        from .serializers import TransactionSerializer
        recent = Transaction.objects.all().order_by('-created_at')[:5]
        return TransactionSerializer(recent, many=True).data


class MonthlySalesSerializer(serializers.Serializer):
    month = serializers.CharField()
    total = serializers.DecimalField(max_digits=10, decimal_places=2)


class SalesReportSerializer(serializers.Serializer):
    period = serializers.CharField()
    start_date = serializers.DateField()
    end_date = serializers.DateField()
    total_sales = serializers.DecimalField(max_digits=10, decimal_places=2)
    total_transactions = serializers.IntegerField()
    average_sale = serializers.DecimalField(max_digits=10, decimal_places=2)
    service_type_breakdown = serializers.DictField()
    status_breakdown = serializers.DictField()
    transactions = serializers.ListField(
        child=serializers.DictField(), required=False)


class ReportRequestSerializer(serializers.Serializer):
    start_date = serializers.DateField(required=False)
    end_date = serializers.DateField(required=False)
    period = serializers.ChoiceField(
        choices=['daily', 'weekly', 'monthly', 'custom'],
        default='monthly'
    )
    service_type = serializers.ChoiceField(
        choices=[choice[0] for choice in Transaction.SERVICE_CHOICES],
        required=False
    )
    status = serializers.ChoiceField(
        choices=[choice[0] for choice in Transaction.STATUS_CHOICES],
        required=False
    )
    customer_id = serializers.IntegerField(required=False)
    include_details = serializers.BooleanField(default=False)


class CustomerFrequencySerializer(serializers.Serializer):
    period = serializers.CharField()
    start_date = serializers.DateField()
    end_date = serializers.DateField()
    total_customers = serializers.IntegerField()
    total_transactions = serializers.IntegerField()
    total_spent = serializers.DecimalField(max_digits=10, decimal_places=2)
    average_spent = serializers.DecimalField(max_digits=10, decimal_places=2)
    # Breakdown fields similar to SalesReport
    customer_breakdown = serializers.ListField(
        child=serializers.DictField(),
        help_text="List of customers with their individual metrics"
    )
    spending_breakdown = serializers.DictField(
        help_text="Breakdown by spending ranges (high, medium, low)"
    )
    frequency_breakdown = serializers.DictField(
        help_text="Breakdown by transaction frequency"
    )
    transactions = serializers.ListField(
        child=serializers.DictField(),
        required=False
    )


class PublicTransactionSerializer(serializers.ModelSerializer):
    service_type = serializers.CharField(source='get_service_type_display')
    status = serializers.CharField(source='get_status_display')
    customer = CustomerSerializer()

    class Meta:
        model = Transaction
        fields = [
            'id',
            'customer',
            'service_type',
            'status',
            'regular_clothes_weight',
            'jeans_weight',
            'linens_weight',
            'comforter_weight',
            'subtotal',
            'additional_fee',
            'grand_total',
            'created_at',
            'updated_at',
            'completed_at'
        ]
        read_only_fields = fields  # All fields are read-only for customers


class RatingSerializer(serializers.ModelSerializer):
    class Meta:
        model = Rating
        fields = ['rating']
        extra_kwargs = {
            'rating': {
                'min_value': 1,
                'max_value': 5,
                'error_messages': {
                    'min_value': 'Rating must be at least 1',
                    'max_value': 'Rating cannot be more than 5'
                }
            }
        }

    def validate(self, data):
        # Ensure one rating per transaction
        if self.instance is None and Rating.objects.filter(transaction=self.context['transaction']).exists():
            raise serializers.ValidationError(
                "This transaction already has a rating.")
        return data
