from .serializers import CustomTokenObtainPairSerializer
from datetime import datetime, timedelta
from rest_framework.decorators import api_view
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.utils import timezone
from django.shortcuts import get_object_or_404
from django.db.models import Sum, Count
from datetime import timedelta
import pandas as pd
from django.http import FileResponse
from io import BytesIO
from .models import User, Customer, Transaction
from .serializers import (
    UserSerializer,
    TransactionSerializer,
    TransactionCreateSerializer,
    CustomerSerializer,
    DashboardMetricsSerializer,
    SalesReportSerializer,
    ReportRequestSerializer,
    CustomerFrequencySerializer,
    PublicTransactionSerializer,
    RatingSerializer,
    LoginSerializer
)
# Add this import at the top of your file
from django.db.models.functions import TruncDate
from django.db.models import Max  # Add this with your other imports
from django.contrib.auth import authenticate, login
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.views import TokenObtainPairView
import logging
logger = logging.getLogger(__name__)


class ProtectedView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        content = {'message': 'Hello, World! This is a protected view!'}
        return Response(content)


class CustomTokenObtainPairView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer


@api_view(['GET', 'POST'])
def user_list(request):
    """
    List all users or create a new user
    """
    if request.method == 'GET':
        users = User.objects.all().order_by('-date_joined')
        serializer = UserSerializer(users, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    elif request.method == 'POST':
        serializer = UserSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)



@api_view(['GET', 'PUT', 'DELETE'])
def user_detail(request, pk):
    """
    Retrieve, update or delete a user instance
    """
    user = get_object_or_404(User, pk=pk)

    if request.method == 'GET':
        serializer = UserSerializer(user)
        return Response(serializer.data, status=status.HTTP_200_OK)

    elif request.method == 'PUT':
        serializer = UserSerializer(user, data=request.data, partial=True)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
            
        # Check if sensitive fields were modified
        sensitive_fields = ['email', 'password', 'username']
        needs_new_token = any(field in request.data for field in sensitive_fields)
        
        serializer.save()
        
        response_data = serializer.data
        
        # Generate new token if needed
        if needs_new_token:
            refresh = RefreshToken.for_user(user)
            # Add custom claims
            refresh['first_name'] = user.first_name
            refresh['last_name'] = user.last_name
            refresh['username'] = user.username
            refresh['email'] = user.email
            
            response_data['token'] = {
                'access': str(refresh.access_token),
                'refresh': str(refresh),
            }
        
        return Response(response_data, status=status.HTTP_200_OK)
    
@api_view(['PUT'])
def update_customer(request, pk):
    """
    Update a customer instance
    """
    customer = get_object_or_404(Customer, pk=pk)
    serializer = CustomerSerializer(customer, data=request.data, partial=True)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data, status=status.HTTP_200_OK)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET', 'POST'])
def transaction_list(request):
    """
    List all transactions or create a new transaction
    """
    if request.method == 'GET':
        transactions = Transaction.objects.select_related(
            'customer').order_by('-created_at')
        serializer = TransactionSerializer(transactions, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    elif request.method == 'POST':
        serializer = TransactionCreateSerializer(data=request.data)
        if serializer.is_valid():
            transaction = serializer.save()
            full_serializer = TransactionSerializer(transaction)
            return Response(full_serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET', 'PUT', 'DELETE'])
def transaction_detail(request, pk):
    """
    Retrieve, update or delete a transaction instance
    """
    transaction = get_object_or_404(Transaction, pk=pk)

    if request.method == 'GET':
        serializer = TransactionSerializer(transaction)
        return Response(serializer.data, status=status.HTTP_200_OK)

    elif request.method == 'PUT':
        serializer = TransactionSerializer(
            transaction, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    elif request.method == 'DELETE':
        transaction.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(['POST'])
def update_transaction_status(request, pk):
    """
    Update transaction status
    """
    transaction = get_object_or_404(Transaction, pk=pk)
    new_status = request.data.get('status')

    if not new_status or new_status not in dict(Transaction.STATUS_CHOICES).keys():
        return Response(
            {'error': 'Invalid status'},
            status=status.HTTP_400_BAD_REQUEST
        )

    transaction.status = new_status
    if new_status == 'completed':
        transaction.completed_at = timezone.now()
    transaction.save()

    serializer = TransactionSerializer(transaction)
    return Response(serializer.data, status=status.HTTP_200_OK)


class DashboardMetricsView(APIView):
    """
    API endpoint that returns dashboard metrics
    """

    def get(self, request):
        # Calculate metrics for this month
        today = timezone.now()
        first_day_of_month = today.replace(
            day=1, hour=0, minute=0, second=0, microsecond=0)
        start_date = today.replace(day=1)
        end_date = (start_date + timedelta(days=32)
                    ).replace(day=1) - timedelta(days=1)

        # Get all metrics in a single query where possible
        # Base queryset with date filtering
        monthly_transactions = Transaction.objects.filter(
            created_at__date__gte=start_date,
            created_at__date__lte=end_date
        )

        total_sales = monthly_transactions.aggregate(
            total=Sum('grand_total')
        )['total'] or 0

        total_transactions = monthly_transactions.count()

        ongoing_services = Transaction.objects.filter(
            status__in=['pending', 'in_progress']
        ).count()

        data = {
            # Convert Decimal to float for JSON serialization
            'total_sales': float(total_sales),
            'total_transactions': total_transactions,
            'start_date': start_date.date(),  # Convert to date
            'end_date': end_date.date(),      # Convert to date
            'ongoing_services': ongoing_services,
            'month': first_day_of_month.strftime('%B %Y'),
            'transactions': TransactionSerializer(
                monthly_transactions.order_by('-created_at'),
                many=True
            ).data
        }

        serializer = DashboardMetricsSerializer(data)
        return Response(serializer.data, status=status.HTTP_200_OK)


@api_view(['GET'])
def sales_report(request):
    """
    Generate sales report with filtering options
    """
    # Validate request parameters
    serializer = ReportRequestSerializer(data=request.query_params)
    serializer.is_valid(raise_exception=True)
    params = serializer.validated_data

    # Determine date range
    today = timezone.now().date()
    if params['period'] == 'daily':
        start_date = today
        end_date = today
    elif params['period'] == 'weekly':
        start_date = today - timedelta(days=today.weekday())
        end_date = start_date + timedelta(days=6)
    elif params['period'] == 'monthly':
        start_date = today.replace(day=1)
        end_date = (start_date + timedelta(days=32)
                    ).replace(day=1) - timedelta(days=1)
    else:  # custom
        start_date = params.get('start_date', today - timedelta(days=30))
        end_date = params.get('end_date', today)

    # Base queryset with date filtering
    queryset = Transaction.objects.filter(
        created_at__date__gte=start_date,
        created_at__date__lte=end_date
    )

    # Apply additional filters
    if params.get('service_type'):
        queryset = queryset.filter(service_type=params['service_type'])
    if params.get('status'):
        queryset = queryset.filter(status=params['status'])
    if params.get('customer_id'):
        queryset = queryset.filter(customer_id=params['customer_id'])

    # Calculate metrics
    total_sales = queryset.aggregate(total=Sum('grand_total'))['total'] or 0
    total_transactions = queryset.count()
    average_sale = total_sales / total_transactions if total_transactions else 0

    # Service type breakdown
    service_breakdown = queryset.values('service_type').annotate(
        total=Sum('grand_total'),
        count=Count('id')
    ).order_by('-total')

    # Status breakdown
    status_breakdown = queryset.values('status').annotate(
        count=Count('id')
    ).order_by('-count')

    # Prepare response data
    report_data = {
        'period': params['period'],
        'start_date': start_date,
        'end_date': end_date,
        'total_sales': total_sales,
        'total_transactions': total_transactions,
        'average_sale': average_sale,
        'service_type_breakdown': {
            item['service_type']: {
                'total': item['total'],
                'count': item['count']
            } for item in service_breakdown
        },
        'status_breakdown': {
            item['status']: item['count'] for item in status_breakdown
        }
    }

    # Include transaction details if requested
    if params['include_details']:
        report_data['transactions'] = TransactionSerializer(
            queryset.order_by('-created_at'),
            many=True
        ).data

    # Serialize and return response
    return Response(SalesReportSerializer(report_data).data)


@api_view(['GET'])
def export_sales_report(request):
    """
    Export sales report to Excel with filtering options
    """
    # Validate request parameters
    serializer = ReportRequestSerializer(data=request.query_params)
    serializer.is_valid(raise_exception=True)
    params = serializer.validated_data

    # Determine date range
    today = timezone.now().date()
    if params['period'] == 'daily':
        start_date = today
        end_date = today
    elif params['period'] == 'weekly':
        start_date = today - timedelta(days=today.weekday())
        end_date = start_date + timedelta(days=6)
    elif params['period'] == 'monthly':
        start_date = today.replace(day=1)
        end_date = (start_date + timedelta(days=32)
                    ).replace(day=1) - timedelta(days=1)
    else:  # custom
        start_date = params.get('start_date', today - timedelta(days=30))
        end_date = params.get('end_date', today)

    # Base queryset with date filtering
    queryset = Transaction.objects.filter(
        created_at__date__gte=start_date,
        created_at__date__lte=end_date
    ).select_related('customer')

    # Apply additional filters
    if params.get('service_type'):
        queryset = queryset.filter(service_type=params['service_type'])
    if params.get('status'):
        queryset = queryset.filter(status=params['status'])
    if params.get('customer_id'):
        queryset = queryset.filter(customer_id=params['customer_id'])

    # Prepare data for Excel export
    transactions = queryset.order_by('-created_at')

    # Create a Pandas DataFrame from the transactions
    data = []
    for t in transactions:
        data.append({
            'Transaction ID': t.id,
            'Date': t.created_at.date(),
            'Customer Name': f"{t.customer.first_name} {t.customer.last_name}",
            'Customer Contact': t.customer.contact_number,
            'Service Type': t.get_service_type_display(),
            'Status': t.get_status_display(),
            'Regular Clothes (kg)': float(t.regular_clothes_weight),
            'Jeans (kg)': float(t.jeans_weight),
            'Beddings (kg)': float(t.linens_weight),
            'Comforter (kg)': float(t.comforter_weight),
            'Subtotal (₱)': float(t.subtotal),
            'Additional Fee (₱)': float(t.additional_fee),
            'Grand Total (₱)': float(t.grand_total),
        })

    # Create summary data
    total_sales = float(queryset.aggregate(
        total=Sum('grand_total'))['total']) or 0
    total_transactions = queryset.count()
    average_sale = total_sales / total_transactions if total_transactions else 0

    # Get daily sales and transaction data for the charts
    daily_data = queryset.annotate(
        date=TruncDate('created_at')
    ).values('date').annotate(
        daily_total=Sum('grand_total'),
        transaction_count=Count('id')
    ).order_by('date')

    # Create Excel file in memory
    output = BytesIO()

    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        workbook = writer.book

        # Format for currency and styling
        currency_format = workbook.add_format({'num_format': '#,##0.00'})
        bold_format = workbook.add_format({'bold': True})
        header_format = workbook.add_format({
            'bold': True,
            'bg_color': '#f8f9fa',
            'border': 1
        })

        # Write transactions sheet
        if data:
            df = pd.DataFrame(data)
            df.to_excel(writer, sheet_name='Transactions', index=False)

            # Auto-adjust columns' width and format
            worksheet = writer.sheets['Transactions']
            for i, col in enumerate(df.columns):
                max_len = max(df[col].astype(
                    str).str.len().max(), len(col)) + 2
                worksheet.set_column(i, i, max_len)

            # Format currency columns
            currency_cols = ['Subtotal', 'Additional Fee', 'Grand Total']
            for col in currency_cols:
                if col in df.columns:
                    col_idx = df.columns.get_loc(col)
                    worksheet.set_column(
                        col_idx, col_idx, None, currency_format)

        # Create combined summary sheet with charts
        summary_data = {
            'Report Period': f"{start_date} to {end_date}",
            'Total Sales (₱)': total_sales,
            'Total Transactions': total_transactions,
            'Average Sale (₱)': average_sale,
        }

        # Write summary data
        summary_df = pd.DataFrame([summary_data])
        summary_df.to_excel(writer, sheet_name='Summary',
                            startrow=0, index=False)
        worksheet = writer.sheets['Summary']

        # Format summary sheet
        for i, col in enumerate(summary_df.columns):
            max_len = max(summary_df[col].astype(
                str).str.len().max(), len(col)) + 2
            worksheet.set_column(i, i, max_len)

        # Format currency columns in summary
        worksheet.set_column(1, 1, None, currency_format)  # Total Sales
        worksheet.set_column(3, 3, None, currency_format)  # Average Sale

        # Add charts if we have daily data
        if daily_data:
            # Create DataFrame for daily data
            daily_df = pd.DataFrame(list(daily_data))
            # Convert to datetime and format as "Apr. 12" style
            #  daily_df['date'] = pd.to_datetime(daily_df['date']).dt.strftime('%Y-%m-%d')
            daily_df['date'] = pd.to_datetime(
                daily_df['date']).dt.strftime('%b. %d')
            # Convert daily_total to numeric - handles various cases
        if pd.api.types.is_numeric_dtype(daily_df['daily_total']):
            # Already numeric, just ensure it's float
            daily_df['daily_total'] = daily_df['daily_total'].astype(float)
        else:
            # Not numeric - convert to string first, then clean and convert to float
            daily_df['daily_total'] = (
                daily_df['daily_total'].astype(str)
                # Remove non-numeric chars
                .str.replace('[^\\d.]', '', regex=True)
                .replace('', '0')  # Handle empty strings
                .astype(float)
            )
            # Rename columns to desired display names
            daily_df = daily_df.rename(columns={
                'date': 'Date',
                'daily_total': 'Daily Total (₱)',
                'transaction_count': 'Transaction Count'
            })

            daily_df.sort_values('Date', inplace=True)

            # Write daily data below summary (starting at row 5)
            daily_df.to_excel(writer, sheet_name='Summary',
                              startrow=5, index=False)
            # Get the last row number
            last_row = len(daily_df) + 6  # +5 because we started at row 5

            # Create bar chart for sales
            sales_chart = workbook.add_chart(
                {'type': 'column'})  # Changed to bar chart

            sales_chart.add_series({
                'name': 'Daily Sales',
                # Start from row 6
                'categories': f"=Summary!$A$7:$A${last_row}",
                'values': f"=Summary!$B$7:$B${last_row}",
                'fill': {'color': '#465FFF'},
                'border': {'color': '#465FFF'},
            })

            # Configure X-axis - SIMPLIFIED
            sales_chart.set_x_axis({
                'text_axis': True,  # Treat as text categories
                'labels': {'rotate': -45}
            })
            sales_chart.set_y_axis({
                'name': 'Total Sales (₱)',  # Add currency symbol
                'num_format': '#,##0.00',
            })
            sales_chart.set_title({'name': 'Daily Sales'})
            sales_chart.set_legend({'none': True})  # Cleaner look

            # Create line chart for transactions
            transactions_chart = workbook.add_chart({'type': 'line'})

            transactions_chart.add_series({
                'name': 'Daily Transactions',
                'categories': f"=Summary!$A$7:$A${last_row}",
                'values': f"=Summary!$C$7:$C${last_row}",
                'line': {'color': '#465FFF', 'width': 3},
                'marker': {
                    'type': 'circle',
                    'fill': {'color': '#FFFFFF'},  # White fill
                    'line': {'color': '#3B82F6', 'width': 2},  # Blue border
                    'size': 7,
                },
            })

            transactions_chart.set_x_axis({
                # 'name': 'Date',
                'date_axis': True,
                'num_format': 'mmm dd',
                'text_axis': False,
                'labels': {
                    'show': True,
                    'rotate': -45,  # Match the rotation of sales chart
                }
            })
            transactions_chart.set_y_axis({
                'name': 'Transaction Count',
                'min': 0,  # Ensure chart starts at 0
                'num_format': '0',  # Force integer format
            })
            transactions_chart.set_legend({'none': True})  # Cleaner look
            transactions_chart.set_title({'name': 'Daily Transaction'})

            # Insert charts into summary sheet
            worksheet.insert_chart('F2', sales_chart, {
                                   'x_scale': 1.5, 'y_scale': 1})
            worksheet.insert_chart('F20', transactions_chart, {
                                   'x_scale': 1.5, 'y_scale': 1})

    # Prepare response
    output.seek(0)

    # Format filename based on period type
    if params['period'] == 'daily':
        # For daily reports: "Sales Report (Apr 15 2025)"
        filename = f"Sales Report ({pd.to_datetime(start_date).strftime('%b %d %Y')}).xlsx"
    else:
        # For weekly/monthly/custom: "Sales Report (Apr 1 - Apr 15 2025)"
        start_fmt = pd.to_datetime(start_date).strftime('%b %d %Y')
        end_fmt = pd.to_datetime(end_date).strftime('%b %d %Y')

        if start_fmt == end_fmt:
            # If start and end are same date (shouldn't happen except daily)
            filename = f"Sales Report ({start_fmt}).xlsx"
        else:
            # Show date range
            filename = f"Sales Report ({start_fmt} - {end_fmt}).xlsx"

    response = FileResponse(
        output,
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Access-Control-Expose-Headers'] = 'Content-Disposition'
    response['Content-Disposition'] = f'attachment; filename="{filename}"'

    return response


@api_view(['GET'])
def customer_frequency_report(request):
    """
    Generate customer frequency report with filtering options
    Returns customer name, contact number, total transactions, total spent, and average spent
    """
    # Validate request parameters
    serializer = ReportRequestSerializer(data=request.query_params)
    serializer.is_valid(raise_exception=True)
    params = serializer.validated_data

    # Determine date range
    today = timezone.now().date()
    if params['period'] == 'daily':
        start_date = today
        end_date = today
    elif params['period'] == 'weekly':
        start_date = today - timedelta(days=today.weekday())
        end_date = start_date + timedelta(days=6)
    elif params['period'] == 'monthly':
        start_date = today.replace(day=1)
        end_date = (start_date + timedelta(days=32)
                    ).replace(day=1) - timedelta(days=1)
    else:  # custom
        # Default to 1 year for customer analysis
        start_date = params.get('start_date', today - timedelta(days=365))
        end_date = params.get('end_date', today)

    # Base queryset - customers with transactions in the date range
    customers = Customer.objects.filter(
        transactions__created_at__date__gte=start_date,
        transactions__created_at__date__lte=end_date
    ).distinct().annotate(
        total_transactions=Count('transactions'),
        total_spent=Sum('transactions__grand_total'),
        last_transaction_date=Max('transactions__created_at')
    ).filter(total_transactions__gt=0)  # Only include customers with transactions

    # Apply additional filters if provided
    if params.get('service_type'):
        customers = customers.filter(
            transactions__service_type=params['service_type'])
    if params.get('status'):
        customers = customers.filter(transactions__status=params['status'])
    if params.get('customer_id'):
        customers = customers.filter(id=params['customer_id'])

    # Calculate aggregate metrics
    total_customers = customers.count()
    overall_total_spent = customers.aggregate(
        total=Sum('total_spent'))['total'] or 0
    overall_total_transactions = customers.aggregate(
        total=Sum('total_transactions'))['total'] or 0
    overall_avg_spent = overall_total_spent / \
        overall_total_transactions if overall_total_transactions else 0

    # Prepare customer breakdown
    customer_breakdown = []
    for customer in customers:
        avg_spent = customer.total_spent / \
            customer.total_transactions if customer.total_transactions else 0
        customer_breakdown.append({
            'id': customer.id,
            'first_name': customer.first_name,
            'last_name': customer.last_name,
            'contact_number': customer.contact_number,
            'total_transactions': customer.total_transactions,
            'total_spent': customer.total_spent,
            'average_spent': avg_spent,
            'last_transaction_date': customer.last_transaction_date
        })

    # Prepare spending breakdown (example)
    spending_breakdown = {
        'high': customers.filter(total_spent__gte=1000).count(),
        'medium': customers.filter(total_spent__gte=500, total_spent__lt=1000).count(),
        'low': customers.filter(total_spent__lt=500).count()
    }

    # Prepare frequency breakdown (example)
    frequency_breakdown = {
        'frequent': customers.filter(total_transactions__gte=5).count(),
        'occasional': customers.filter(total_transactions__gte=2, total_transactions__lt=5).count(),
        'one_time': customers.filter(total_transactions=1).count()
    }

    # Prepare the response data (now structured like SalesReport)
    report_data = {
        'period': params['period'],
        'start_date': start_date,
        'end_date': end_date,
        'total_customers': total_customers,
        'total_transactions': overall_total_transactions,
        'total_spent': overall_total_spent,
        'average_spent': overall_avg_spent,
        'customer_breakdown': customer_breakdown,
        'spending_breakdown': spending_breakdown,
        'frequency_breakdown': frequency_breakdown
    }

    # Include transaction details if requested
    if params.get('include_details'):
        transactions = Transaction.objects.filter(
            created_at__date__gte=start_date,
            created_at__date__lte=end_date
        )
        if params.get('customer_id'):
            transactions = transactions.filter(
                customer_id=params['customer_id'])
        report_data['transactions'] = TransactionSerializer(
            transactions.order_by('-created_at'),
            many=True
        ).data

    return Response(CustomerFrequencySerializer(report_data).data)


@api_view(['GET'])
def export_customer_frequency_report(request):
    """
    Export customer frequency report to Excel with filtering options
    Returns Excel file with customer frequency data
    """
    # Validate request parameters (same as original report)
    serializer = ReportRequestSerializer(data=request.query_params)
    serializer.is_valid(raise_exception=True)
    params = serializer.validated_data

    # Determine date range (same as original report)
    today = timezone.now().date()
    if params['period'] == 'daily':
        start_date = today
        end_date = today
    elif params['period'] == 'weekly':
        start_date = today - timedelta(days=today.weekday())
        end_date = start_date + timedelta(days=6)
    elif params['period'] == 'monthly':
        start_date = today.replace(day=1)
        end_date = (start_date + timedelta(days=32)
                    ).replace(day=1) - timedelta(days=1)
    else:  # custom
        start_date = params.get('start_date', today - timedelta(days=365))
        end_date = params.get('end_date', today)

    # Get customer data (same as original report)
    customers = Customer.objects.filter(
        transactions__created_at__date__gte=start_date,
        transactions__created_at__date__lte=end_date
    ).distinct().annotate(
        total_transactions=Count('transactions'),
        total_spent=Sum('transactions__grand_total'),
        last_transaction_date=Max('transactions__created_at')
    ).filter(total_transactions__gt=0)

    # Prepare data for Excel
    data = []
    for idx, customer in enumerate(customers, start=1):
        avg_spent = customer.total_spent / \
            customer.total_transactions if customer.total_transactions else 0

        data.append({
            'Ranking': idx,
            'Customer Name': f"{customer.first_name} {customer.last_name}",
            'Phone Number': customer.contact_number,
            'Total Transactions': customer.total_transactions,
            # Rounded to 2 decimal places
            'Total Spent': round(float(customer.total_spent), 2),
            # Rounded to 2 decimal places
            'Average Spent': round(float(avg_spent), 2),
            'Last Transaction Date': customer.last_transaction_date.strftime('%Y-%m-%d') if customer.last_transaction_date else ''
        })

    # Sort by total transactions (descending)
    data.sort(key=lambda x: x['Total Transactions'], reverse=True)

    # Update ranking after sorting
    for idx, item in enumerate(data, start=1):
        item['Ranking'] = idx

    # Create DataFrame
    df = pd.DataFrame(data)

    # Reorder columns
    df = df[[
        'Ranking',
        'Customer Name',
        'Phone Number',
        'Total Transactions',
        'Total Spent',
        'Average Spent',
        'Last Transaction Date'
    ]]

    # Create Excel file in memory
    output = BytesIO()
    writer = pd.ExcelWriter(output, engine='xlsxwriter')
    df.to_excel(writer, sheet_name='Customer Frequency', index=False)

    # Get workbook and worksheet objects for formatting
    workbook = writer.book
    # Add number formatting (after header formatting)
    # 2 decimal places with thousands separator
    number_format = workbook.add_format({'num_format': '#,##0.00'})
    worksheet = writer.sheets['Customer Frequency']
    # Apply formatting to currency columns
    worksheet.set_column('E:E', None, number_format)  # Total Spent (column E)
    # Average Spent (column F)
    worksheet.set_column('F:F', None, number_format)

    # Add formatting
    header_format = workbook.add_format({
        'bold': True,
        'text_wrap': True,
        'valign': 'top',
        'fg_color': '#4472C4',
        'font_color': 'white',
        'border': 1
    })

    # Write the column headers with the defined format
    for col_num, value in enumerate(df.columns.values):
        worksheet.write(0, col_num, value, header_format)

    # Auto-adjust columns' width
    for column in df:
        column_width = max(df[column].astype(
            str).map(len).max(), len(column)) + 2
        col_idx = df.columns.get_loc(column)
        worksheet.set_column(col_idx, col_idx, column_width)

    # Add a pie chart showing transaction distribution
    if len(df) > 0:
        chart_sheet_name = 'Transaction Distribution'

        # Create a summary dataframe for the chart
        chart_df = df[['Customer Name', 'Total Transactions']].copy()
        chart_df = chart_df.sort_values('Total Transactions', ascending=False)

        # If many customers, group smaller ones into "Others"
        if len(chart_df) > 10:
            top_10 = chart_df.head(10)
            others = pd.DataFrame({
                'Customer Name': ['Others'],
                'Total Transactions': [chart_df['Total Transactions'][10:].sum()]
            })
            chart_df = pd.concat([top_10, others])

        # Write chart data to a new sheet
        chart_df.to_excel(writer, sheet_name=chart_sheet_name, index=False)

        # Create pie chart
        chart = workbook.add_chart({'type': 'pie'})

        # Configure the chart
        chart.add_series({
            'name': 'Transaction Distribution',
            'categories': f"='{chart_sheet_name}'!$A$2:$A${len(chart_df)+1}",
            'values': f"='{chart_sheet_name}'!$B$2:$B${len(chart_df)+1}",
            'data_labels': {'percentage': True, 'category': True}
        })

        chart.set_title({'name': 'Customer Transaction Distribution'})
        chart.set_style(10)

        # Insert the chart into the worksheet
        worksheet.insert_chart('H2', chart)

    writer.close()
    output.seek(0)

   # Format filename based on period type
    if params['period'] == 'daily':
        # For daily reports: "Customer Frequency Report (Apr 15 2025)"
        filename = f"Customer Frequency Report ({pd.to_datetime(start_date).strftime('%b %d %Y')}).xlsx"
    else:
        # For weekly/monthly/custom: "Sales Report (Apr 1 - Apr 15 2025)"
        start_fmt = pd.to_datetime(start_date).strftime('%b %d %Y')
        end_fmt = pd.to_datetime(end_date).strftime('%b %d %Y')

        if start_fmt == end_fmt:
            # If start and end are same date (shouldn't happen except daily)
            filename = f"Customer Frequency Report ({start_fmt}).xlsx"
        else:
            # Show date range
            filename = f"Customer Frequency Report ({start_fmt} - {end_fmt}).xlsx"

    response = FileResponse(
        output,
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Access-Control-Expose-Headers'] = 'Content-Disposition'
    response['Content-Disposition'] = f'attachment; filename="{filename}"'

    return response


@api_view(['GET'])  # Explicitly specifying GET method
def customer_transaction_lookup(request, transaction_id):
    """
    API endpoint for customers to lookup their transaction details by ID

    Returns:
    - 200 OK: Transaction found (returns transaction data)
    - 400 Bad Request: Invalid transaction ID (empty, non-integer, or <= 0)
    - 404 Not Found: Transaction not found
    """
    # Check for empty/None transaction_id
    if not transaction_id:
        return Response(
            {"error": "Transaction ID is required and cannot be empty"},
            status=status.HTTP_400_BAD_REQUEST
        )

    try:
        # Validate the transaction_id is a positive integer
        transaction_id = int(transaction_id)
        if transaction_id <= 0:
            raise ValueError
    except ValueError:
        return Response(
            {"error": "Transaction ID must be a positive integer"},
            status=status.HTTP_400_BAD_REQUEST
        )

    # Get the transaction or return 404
    transaction = get_object_or_404(Transaction, id=transaction_id)

    # Serialize the transaction data
    serializer = PublicTransactionSerializer(transaction)
    return Response(serializer.data, status=status.HTTP_200_OK)


@api_view(['POST'])
def submit_rating(request, transaction_id):
    transaction = get_object_or_404(Transaction, id=transaction_id)
    serializer = RatingSerializer(
        data=request.data,
        context={'transaction': transaction}  # Pass transaction for validation
    )

    if serializer.is_valid():
        serializer.save(transaction=transaction)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
