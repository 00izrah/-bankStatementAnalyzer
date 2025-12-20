from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import login, authenticate
from django.contrib import messages
from django.db.models import Sum, Q, Avg, Count, Max, Min
from django.db.models.functions import TruncMonth, TruncWeek, ExtractHour
from django.core.serializers.json import DjangoJSONEncoder
from django.utils import timezone
from datetime import timedelta
from .models import UploadedFile, Transaction, Category
from .forms import UploadStatementForm, CategoryForm, TransactionCategoryForm
from .parsers import BANK_PARSERS
import json
import os

def home(request):
    return render(request, 'core/home.html')

def register(request):
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password1')
            user = authenticate(username=username, password=password)
            login(request, user)
            messages.success(request, f'Account created successfully! Welcome, {username}!')
            return redirect('dashboard')
    else:
        form = UserCreationForm()
    
    return render(request, 'registration/register.html', {'form': form})

@login_required
def dashboard(request):
    user_files = UploadedFile.objects.filter(user=request.user).order_by('-uploaded_at')
    transactions = Transaction.objects.filter(uploaded_file__user=request.user)
    
    # Get date range for filtering
    date_filter = request.GET.get('date_range', 'all')
    if date_filter == 'month':
        start_date = timezone.now() - timedelta(days=30)
        transactions = transactions.filter(date__gte=start_date)
    elif date_filter == '3months':
        start_date = timezone.now() - timedelta(days=90)
        transactions = transactions.filter(date__gte=start_date)
    elif date_filter == '6months':
        start_date = timezone.now() - timedelta(days=180)
        transactions = transactions.filter(date__gte=start_date)
    elif date_filter == 'year':
        start_date = timezone.now() - timedelta(days=365)
        transactions = transactions.filter(date__gte=start_date)

    # Basic statistics
    total_spent = transactions.filter(amount__lt=0).aggregate(total=Sum('amount'))['total'] or 0
    total_income = transactions.filter(amount__gt=0).aggregate(total=Sum('amount'))['total'] or 0
    avg_transaction = transactions.aggregate(avg=Avg('amount'))['avg'] or 0
    transaction_count = transactions.count()
    largest_expense = transactions.filter(amount__lt=0).aggregate(max=Min('amount'))['max'] or 0
    largest_income = transactions.filter(amount__gt=0).aggregate(max=Max('amount'))['max'] or 0

    # Get spending by category with percentages
    category_totals = list(transactions.filter(amount__lt=0).values('category__name')
        .annotate(
            total=Sum('amount'),
            count=Count('id'),
            avg=Avg('amount')
        )
        .order_by('total'))
    
    total_spending = abs(sum(cat['total'] for cat in category_totals))
    for cat in category_totals:
        cat['percentage'] = (abs(cat['total']) / total_spending * 100) if total_spending else 0
        cat['total'] = abs(cat['total'])  # Convert to positive for display

    # Get monthly spending trend
    monthly_totals = list(transactions.annotate(
        month=TruncMonth('date')
    ).values('month').annotate(
        expenses=Sum('amount', filter=Q(amount__lt=0)),
        income=Sum('amount', filter=Q(amount__gt=0)),
        transaction_count=Count('id')
    ).order_by('month'))

    # Get weekly spending pattern
    weekly_totals = list(transactions.filter(amount__lt=0).annotate(
        week=TruncWeek('date')
    ).values('week').annotate(
        total=Sum('amount')
    ).order_by('week'))

    # Recent high-value transactions
    high_value_transactions = transactions.order_by('amount')[:5]  # Top 5 expenses
    
    context = {
        'files': user_files,
        'transactions': transactions.order_by('-date')[:50],  # Show last 50 transactions
        'category_totals': json.dumps(category_totals, cls=DjangoJSONEncoder),
        'monthly_totals': json.dumps(monthly_totals, cls=DjangoJSONEncoder),
        'weekly_totals': json.dumps(weekly_totals, cls=DjangoJSONEncoder),
        'stats': {
            'total_spent': abs(total_spent),
            'total_income': total_income,
            'avg_transaction': abs(avg_transaction),
            'transaction_count': transaction_count,
            'largest_expense': abs(largest_expense),
            'largest_income': largest_income,
        },
        'high_value_transactions': high_value_transactions,
        'date_filter': date_filter,
    }
    return render(request, 'core/dashboard.html', context)

@login_required
def upload_statement(request):
    if request.method == 'POST':
        form = UploadStatementForm(request.POST, request.FILES)
        replace_existing = request.POST.get('replace_existing') == 'on'
        
        if form.is_valid():
            # If replace_existing, delete all old uploads and transactions
            if replace_existing:
                old_files = UploadedFile.objects.filter(user=request.user)
                for old_file in old_files:
                    if os.path.exists(old_file.file.path):
                        os.remove(old_file.file.path)
                old_files.delete()
                messages.info(request, 'Previous statements deleted.')
            
            uploaded_file = form.save(commit=False)
            uploaded_file.user = request.user
            uploaded_file.save()

            try:
                # Use universal parser for all banks
                parser_class = BANK_PARSERS.get('universal')
                
                # Parse the PDF file
                parser = parser_class(uploaded_file.file.path)
                transactions = parser.parse()
                
                # Get parsing statistics
                parsing_stats = parser.get_parsing_stats()

                # Get or create categories
                categories = {cat.name.lower(): cat for cat in Category.objects.filter(
                    Q(user=request.user) | Q(is_system=True)
                )}

                # Check for existing transactions to avoid duplicates
                existing_trans = Transaction.objects.filter(
                    uploaded_file__user=request.user
                ).values_list('date', 'description', 'amount')
                existing_set = set(existing_trans)

                # Save transactions to database
                transaction_count = 0
                duplicates_skipped = 0
                categorized_count = 0
                
                for transaction_data in transactions:
                    # Check if transaction already exists
                    trans_tuple = (
                        transaction_data['date'],
                        transaction_data['description'],
                        transaction_data['amount']
                    )
                    
                    if trans_tuple in existing_set:
                        duplicates_skipped += 1
                        continue
                    
                    # Find best matching category
                    category = None
                    desc = transaction_data['description'].lower()
                    
                    # First try using the parser's categorization
                    if not transaction_data.get('category'):
                        transaction_data['category'] = parser.categorize_transaction(transaction_data['description'])
                    
                    # Then match to database categories
                    for cat in categories.values():
                        if any(keyword in desc for keyword in cat.keyword_list):
                            category = cat
                            categorized_count += 1
                            break

                    Transaction.objects.create(
                        uploaded_file=uploaded_file,
                        date=transaction_data['date'],
                        description=transaction_data['description'],
                        amount=transaction_data['amount'],
                        category=category,
                        balance=transaction_data['balance']
                    )
                    transaction_count += 1

                uploaded_file.processed = True
                uploaded_file.transaction_count = transaction_count
                uploaded_file.save()
                
                # Build detailed success message
                msg = f'✅ Statement uploaded successfully! {transaction_count} transactions processed.'
                if duplicates_skipped > 0:
                    msg += f' ({duplicates_skipped} duplicates skipped)'
                if parsing_stats.get('balance_errors', 0) > 0:
                    msg += f' ⚠️ {parsing_stats["balance_errors"]} balance inconsistencies detected.'
                if categorized_count > 0:
                    msg += f' 📊 {categorized_count} transactions auto-categorized.'
                
                messages.success(request, msg)
            except Exception as e:
                messages.error(request, f'Error processing statement: {str(e)}')
                # Clean up the uploaded file if processing failed
                if os.path.exists(uploaded_file.file.path):
                    os.remove(uploaded_file.file.path)
                uploaded_file.delete()
            
            return redirect('dashboard')
    else:
        form = UploadStatementForm()
    
    # Get existing uploads count
    existing_uploads = UploadedFile.objects.filter(user=request.user).count()
    
    return render(request, 'core/upload.html', {
        'form': form,
        'existing_uploads': existing_uploads
    })

@login_required
def manage_categories(request):
    if request.method == 'POST':
        form = CategoryForm(request.POST)
        if form.is_valid():
            category = form.save(commit=False)
            category.user = request.user
            category.save()
            messages.success(request, 'Category created successfully!')
            return redirect('manage_categories')
    else:
        form = CategoryForm()

    # Get user's custom categories and system categories
    categories = Category.objects.filter(
        Q(user=request.user) | Q(is_system=True)
    ).order_by('name')

    context = {
        'form': form,
        'categories': categories,
    }
    return render(request, 'core/manage_categories.html', context)

@login_required
def edit_transaction(request, transaction_id):
    transaction = get_object_or_404(Transaction, id=transaction_id, uploaded_file__user=request.user)
    
    if request.method == 'POST':
        form = TransactionCategoryForm(request.POST, instance=transaction)
        if form.is_valid():
            form.save()
            messages.success(request, 'Transaction updated successfully!')
            return redirect('dashboard')
    else:
        form = TransactionCategoryForm(instance=transaction)

    context = {
        'form': form,
        'transaction': transaction,
    }
    return render(request, 'core/edit_transaction.html', context)

@login_required
def delete_statement(request, file_id):
    """Delete an uploaded statement and all its transactions."""
    uploaded_file = get_object_or_404(UploadedFile, id=file_id, user=request.user)
    
    # Delete the physical file
    if os.path.exists(uploaded_file.file.path):
        os.remove(uploaded_file.file.path)
    
    # Delete the database record (transactions will cascade delete)
    uploaded_file.delete()
    
    messages.success(request, 'Statement and associated transactions deleted successfully!')
    return redirect('dashboard')

@login_required
def clear_all_data(request):
    """Clear all statements and transactions for the current user."""
    if request.method == 'POST':
        # Delete all uploaded files and their physical files
        uploaded_files = UploadedFile.objects.filter(user=request.user)
        for uploaded_file in uploaded_files:
            if os.path.exists(uploaded_file.file.path):
                os.remove(uploaded_file.file.path)
        uploaded_files.delete()
        
        messages.success(request, 'All your data has been cleared!')
        return redirect('dashboard')
    
    return redirect('dashboard')