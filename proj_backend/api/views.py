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
)
from django.db.models.functions import TruncDate  # Add this import at the top of your file
@api_view(['GET', 'POST'])
def user_list(request):
    """
    List all users or create a new user
    """
    if request.method == 'GET':
        users = User.objects.all().order_by('-created_at')
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
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    elif request.method == 'DELETE':
        user.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

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
        transactions = Transaction.objects.select_related('customer').order_by('-created_at')
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
        serializer = TransactionSerializer(transaction, data=request.data, partial=True)
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
        first_day_of_month = today.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        
        # Get all metrics in a single query where possible
        monthly_transactions = Transaction.objects.filter(
            created_at__gte=first_day_of_month
        )
        
        total_sales = monthly_transactions.aggregate(
            total=Sum('grand_total')
        )['total'] or 0
        
        total_transactions = monthly_transactions.count()
        
        ongoing_services = Transaction.objects.filter(
            status__in=['pending', 'in_progress']
        ).count()
        
        data = {
            'total_sales': float(total_sales),  # Convert Decimal to float for JSON serialization
            'total_transactions': total_transactions,
            'ongoing_services': ongoing_services,
            'month': first_day_of_month.strftime('%B %Y')
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
        end_date = (start_date + timedelta(days=32)).replace(day=1) - timedelta(days=1)
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
        end_date = (start_date + timedelta(days=32)).replace(day=1) - timedelta(days=1)
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
    total_sales = float(queryset.aggregate(total=Sum('grand_total'))['total']) or 0
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
                max_len = max(df[col].astype(str).str.len().max(), len(col)) + 2
                worksheet.set_column(i, i, max_len)
            
            # Format currency columns
            currency_cols = ['Subtotal', 'Additional Fee', 'Grand Total']
            for col in currency_cols:
                if col in df.columns:
                    col_idx = df.columns.get_loc(col)
                    worksheet.set_column(col_idx, col_idx, None, currency_format)
        
        # Create combined summary sheet with charts
        summary_data = {
            'Report Period': f"{start_date} to {end_date}",
            'Total Sales (₱)': total_sales,
            'Total Transactions': total_transactions,
            'Average Sale (₱)': average_sale,
        }
        
        # Write summary data
        summary_df = pd.DataFrame([summary_data])
        summary_df.to_excel(writer, sheet_name='Summary', startrow=0, index=False)
        worksheet = writer.sheets['Summary']
        
        # Format summary sheet
        for i, col in enumerate(summary_df.columns):
            max_len = max(summary_df[col].astype(str).str.len().max(), len(col)) + 2
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
            daily_df['date'] = pd.to_datetime(daily_df['date']).dt.strftime('%b. %d')
            # Convert daily_total to numeric - handles various cases
        if pd.api.types.is_numeric_dtype(daily_df['daily_total']):
            # Already numeric, just ensure it's float
            daily_df['daily_total'] = daily_df['daily_total'].astype(float)
        else:
            # Not numeric - convert to string first, then clean and convert to float
            daily_df['daily_total'] = (
                daily_df['daily_total'].astype(str)
                .str.replace('[^\\d.]', '', regex=True)  # Remove non-numeric chars
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
            daily_df.to_excel(writer, sheet_name='Summary', startrow=5, index=False)
            # Get the last row number
            last_row = len(daily_df) + 6  # +5 because we started at row 5
            
            # Create bar chart for sales
            sales_chart = workbook.add_chart({'type': 'column'})  # Changed to bar chart
            
            sales_chart.add_series({
                'name': 'Daily Sales',
                'categories': f"=Summary!$A$7:$A${last_row}",  # Start from row 6
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
            worksheet.insert_chart('F2', sales_chart, {'x_scale': 1.5, 'y_scale': 1})
            worksheet.insert_chart('F20', transactions_chart, {'x_scale': 1.5, 'y_scale': 1})

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