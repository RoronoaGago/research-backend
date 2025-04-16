from django.db import models
from django.utils import timezone
from django.core.validators import MinValueValidator, MaxValueValidator

class User(models.Model):
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    username = models.CharField(max_length=100, unique=True)
    password = models.CharField(
        max_length=128
    )  # In production, use Django's built-in User model or extend AbstractUser
    date_of_birth = models.DateField(null=True, blank=True)
    email = models.EmailField(unique=True)
    phone_number = models.CharField(max_length=20, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):

        return f"{self.first_name} {self.last_name} ({self.username})"


class Customer(models.Model):
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    address = models.TextField()
    contact_number = models.CharField(max_length=20, unique=True)  # Enforce uniqueness
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    def transaction_count(self):
        return self.transactions.count()

    def __str__(self):
        return f"{self.first_name} {self.last_name}"
    
    class Meta:
        ordering = ['-created_at']


class Transaction(models.Model):
    SERVICE_CHOICES = [
        ("standard", "Standard (6-8 hours)"),
        ("express", "Express (2 hours)"),
    ]

    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("in_progress", "In Progress"),
        ("ready_for_pickup", "Ready for Pickup"),
        ("completed", "Completed"),
        ("cancelled", "Cancelled"),
    ]
    # Customer Information
    customer = models.ForeignKey(
        Customer, on_delete=models.PROTECT, related_name="transactions"
    )
    # Laundry Details
    service_type = models.CharField(max_length=20, choices=SERVICE_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")

    # Item Weights
    regular_clothes_weight = models.DecimalField(
        max_digits=6, decimal_places=2, default=0
    )
    jeans_weight = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    linens_weight = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    comforter_weight = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    # Calculated Fields (stored but not calculated in backend)
    subtotal = models.DecimalField(max_digits=10, decimal_places=2)
    additional_fee = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    grand_total = models.DecimalField(max_digits=10, decimal_places=2)

    # Timestamps
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    # # Additional fields
    # notes = models.TextField(blank=True)

    def __str__(self):
        return f"Transaction #{self.id} - {self.first_name} {self.last_name}"

    class Meta:
        ordering = ["-created_at"]
        
class Rating(models.Model):
    transaction = models.OneToOneField(
        Transaction,  # or your actual Transaction model import
        on_delete=models.CASCADE,
        related_name='rating'
    )
    rating = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)]  # 1-5 star rating
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Rating {self.rating} for Transaction #{self.transaction.id}"
