from django.urls import path
from . import views
from .views import DashboardMetricsView

urlpatterns = [
    # User URLs
    path("users/", views.user_list, name="user-list"),
    path("users/<int:pk>/", views.user_detail, name="user-detail"),
    # Customer URLs
    # path("customers/", views.customer_list, name="customer-list"),
    path("customers/<int:pk>/", views.update_customer, name="update_customer"),
    # Transaction URLs
    path("transactions/", views.transaction_list, name="transaction-list"),
    path("transactions/<int:pk>/", views.transaction_detail, name="transaction-detail"),
    path(
        "transactions/<int:pk>/update-status/",
        views.update_transaction_status,
        name="update-transaction-status",
    ),
    path('api/dashboard/metrics/', DashboardMetricsView.as_view(), name='dashboard-metrics'),
    path('reports/sales/', views.sales_report, name='sales-report'),
    path('reports/sales/export/', views.export_sales_report, name='export-sales-report'),
    path('reports/customer-frequency/', views.customer_frequency_report, name='customer-frequency-report'),
    path('reports/customer-frequency/export/', views.export_customer_frequency_report, name='export-customer-frequency-report'),
     path(
        'customer/transactions/<int:transaction_id>/',
        views.customer_transaction_lookup,
        name='customer-transaction-lookup'
    ),
     path(
        'transactions/<int:transaction_id>/rate/',
        views.submit_rating,
        name='submit-rating'
    ),
]
