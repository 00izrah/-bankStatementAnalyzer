from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import login
from django.contrib import messages
from django.db.models import Q
from django.views.decorators.http import require_POST
from .models import UploadedFile, Transaction, Category
from .forms import UploadStatementForm, CategoryForm, TransactionCategoryForm
from .services.upload_service import UploadService, UploadError
from .services.analytics_service import AnalyticsService
from .services.export_service import ExportService
from .services.logging_service import AuditLogger, log_exceptions, logger
from .validators import FileValidationError
from datetime import timedelta
from django.utils import timezone
import os


def home(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    return render(request, 'core/home.html')


def register(request):
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, 'Account created successfully!')
            return redirect('dashboard')
    else:
        form = UserCreationForm()
    return render(request, 'registration/register.html', {'form': form})


@login_required
@log_exceptions('dashboard')
def dashboard(request):
    date_filter = request.GET.get('date_range', 'all')
    page = request.GET.get('page', 1)
    search_query = request.GET.get('q', '').strip()
    category_filter = request.GET.get('category', '').strip()

    analytics = AnalyticsService(request.user)
    context = analytics.get_dashboard_data(
        date_filter=date_filter,
        page=page,
        search_query=search_query,
        category_filter=category_filter,
    )
    return render(request, 'core/dashboard.html', context)


@login_required
@log_exceptions('upload_statement')
def upload_statement(request):
    if request.method == 'POST':
        form = UploadStatementForm(request.POST, request.FILES)
        replace_existing = request.POST.get('replace_existing') == 'on'
        
        if form.is_valid():
            uploaded_file = request.FILES.get('file')
            
            try:
                # Use the upload service
                service = UploadService(request.user)
                result_file, stats = service.process_upload(
                    uploaded_file, 
                    replace_existing=replace_existing
                )
                
                # Build success message
                msg = f'✅ Statement uploaded successfully! {stats["transactions_created"]} transactions processed.'
                
                if stats['duplicates_skipped'] > 0:
                    msg += f' ({stats["duplicates_skipped"]} duplicates skipped)'
                
                if stats['balance_errors'] > 0:
                    msg += f' ⚠️ {stats["balance_errors"]} balance inconsistencies detected.'
                
                if stats['categorized_count'] > 0:
                    msg += f' 📊 {stats["categorized_count"]} transactions auto-categorized.'
                
                messages.success(request, msg)
                return redirect('dashboard')
                
            except FileValidationError as e:
                if isinstance(e.message, list):
                    for error in e.message:
                        messages.error(request, error)
                else:
                    messages.error(request, str(e.message))
                    
            except UploadError as e:
                messages.error(request, str(e))
                
            except Exception as e:
                logger.exception("Unexpected error during upload")
                messages.error(request, 'An unexpected error occurred while processing your file. Please try again.')
    else:
        form = UploadStatementForm()

    # Check if user has existing uploads
    existing_uploads = UploadedFile.objects.filter(user=request.user).count()
    
    return render(request, 'core/upload.html', {
        'form': form,
        'existing_uploads': existing_uploads,
    })


@login_required
@log_exceptions('manage_categories')
def manage_categories(request):
    if request.method == 'POST':
        form = CategoryForm(request.POST)
        if form.is_valid():
            category = form.save(commit=False)
            category.user = request.user
            category.save()
            messages.success(request, f'Category "{category.name}" created successfully!')
            return redirect('manage_categories')
    else:
        form = CategoryForm()

    categories = Category.objects.filter(
        Q(user=request.user) | Q(is_system=True)
    ).order_by('name')

    return render(request, 'core/manage_categories.html', {
        'form': form,
        'categories': categories,
    })


@login_required
@log_exceptions('edit_transaction')
def edit_transaction(request, transaction_id):
    transaction_obj = get_object_or_404(
        Transaction, 
        id=transaction_id, 
        uploaded_file__user=request.user
    )
    
    if request.method == 'POST':
        old_category = transaction_obj.category
        form = TransactionCategoryForm(request.POST, instance=transaction_obj, user=request.user)
        if form.is_valid():
            form.save()
            
            # Log the change
            AuditLogger.log_transaction_edit(
                request.user,
                transaction_id,
                {
                    'old_category': old_category.name if old_category else None,
                    'new_category': transaction_obj.category.name if transaction_obj.category else None,
                }
            )
            
            messages.success(request, 'Transaction updated successfully!')
            return redirect('dashboard')
    else:
        form = TransactionCategoryForm(instance=transaction_obj, user=request.user)

    context = {
        'form': form,
        'transaction': transaction_obj,
    }
    return render(request, 'core/edit_transaction.html', context)


@login_required
@require_POST
@log_exceptions('delete_statement')
def delete_statement(request, file_id):
    """Delete an uploaded statement and all its transactions."""
    uploaded_file = get_object_or_404(UploadedFile, id=file_id, user=request.user)
    
    transaction_count = uploaded_file.transactions.count()
    
    # Log the deletion
    AuditLogger.log_delete(request.user, file_id, transaction_count)
    
    # Delete the physical file
    try:
        if uploaded_file.file and os.path.exists(uploaded_file.file.path):
            os.remove(uploaded_file.file.path)
    except Exception as e:
        logger.warning(f"Could not delete file: {e}")
    
    # Delete the database record (transactions will cascade delete)
    uploaded_file.delete()
    
    messages.success(request, f'Statement and {transaction_count} associated transactions deleted successfully!')
    return redirect('dashboard')


@login_required
@require_POST
@log_exceptions('clear_all_data')
def clear_all_data(request):
    """Clear all user data."""
    # Delete all files
    user_files = UploadedFile.objects.filter(user=request.user)
    total_transactions = Transaction.objects.filter(uploaded_file__user=request.user).count()
    
    for uploaded_file in user_files:
        try:
            if uploaded_file.file and os.path.exists(uploaded_file.file.path):
                os.remove(uploaded_file.file.path)
        except Exception as e:
            logger.warning(f"Could not delete file: {e}")
    
    user_files.delete()
    
    # Log the action
    AuditLogger.log_delete(request.user, 'all', total_transactions)
    
    messages.success(request, 'All your data has been cleared successfully!')
    return redirect('dashboard')


@login_required
def export_transactions_csv(request):
    """Export filtered transactions to CSV."""
    date_filter = request.GET.get('date_range', 'all')
    category_filter = request.GET.get('category', '').strip()
    search_query = request.GET.get('q', '').strip()

    queryset = Transaction.objects.filter(uploaded_file__user=request.user)

    days = AnalyticsService.DATE_FILTERS.get(date_filter)
    if days:
        start_date = timezone.now().date() - timedelta(days=days)
        queryset = queryset.filter(date__gte=start_date)

    if search_query:
        queryset = queryset.filter(
            Q(description__icontains=search_query) | Q(notes__icontains=search_query)
        )
    if category_filter:
        if category_filter == 'uncategorized':
            queryset = queryset.filter(category__isnull=True)
        elif category_filter.isdigit():
            queryset = queryset.filter(category_id=int(category_filter))

    return ExportService.export_csv(queryset)


@login_required
def export_transactions_json(request):
    """Export filtered transactions to JSON."""
    date_filter = request.GET.get('date_range', 'all')
    category_filter = request.GET.get('category', '').strip()
    search_query = request.GET.get('q', '').strip()

    queryset = Transaction.objects.filter(uploaded_file__user=request.user)

    days = AnalyticsService.DATE_FILTERS.get(date_filter)
    if days:
        start_date = timezone.now().date() - timedelta(days=days)
        queryset = queryset.filter(date__gte=start_date)

    if search_query:
        queryset = queryset.filter(
            Q(description__icontains=search_query) | Q(notes__icontains=search_query)
        )
    if category_filter:
        if category_filter == 'uncategorized':
            queryset = queryset.filter(category__isnull=True)
        elif category_filter.isdigit():
            queryset = queryset.filter(category_id=int(category_filter))

    return ExportService.export_json(queryset)