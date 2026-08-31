"""
Analytics service for computing financial dashboard statistics and metrics.
"""
from decimal import Decimal
from datetime import timedelta
from typing import Dict, Any, Optional
from django.db.models import Sum, Q, Avg, Count
from django.db.models.functions import TruncMonth, TruncWeek
from django.utils import timezone
from ..models import Transaction, UploadedFile


class AnalyticsService:
    """Service to compute financial statistics, category breakdowns, and trends."""

    DATE_FILTERS = {
        'month': 30,
        '3months': 90,
        '6months': 180,
        'year': 365,
    }

    def __init__(self, user):
        self.user = user

    def get_dashboard_data(self, date_filter: str = 'all', page: int = 1, page_size: int = 50) -> Dict[str, Any]:
        """Compute all data needed to render the financial dashboard."""
        user_files = UploadedFile.objects.filter(user=self.user).order_by('-uploaded_at')
        base_queryset = Transaction.objects.filter(uploaded_file__user=self.user)

        # Apply date range filtering
        transactions = self._apply_date_filter(base_queryset, date_filter)

        # Compute key statistics
        stats = self._get_statistics(transactions)

        # Compute category breakdown
        categories = self._get_category_breakdown(transactions)

        # Compute monthly trend
        monthly_totals = self._get_monthly_trend(transactions)

        # Compute weekly pattern
        weekly_totals = self._get_weekly_pattern(transactions)

        # Recent high-value transactions (largest debits)
        high_value_transactions = transactions.filter(amount__lt=0).order_by('amount')[:5]

        # Recent transactions sorted by date
        recent_transactions = transactions.select_related('category', 'uploaded_file').order_by('-date')[:page_size]

        return {
            'files': user_files,
            'transactions': recent_transactions,
            'stats': stats,
            'categories': categories,
            'monthly_totals': monthly_totals,
            'weekly_totals': weekly_totals,
            'high_value_transactions': high_value_transactions,
            'date_filter': date_filter,
        }

    def _apply_date_filter(self, queryset, date_filter: str):
        """Filter transactions by selected time range."""
        days = self.DATE_FILTERS.get(date_filter)
        if days:
            start_date = timezone.now().date() - timedelta(days=days)
            return queryset.filter(date__gte=start_date)
        return queryset

    def _get_statistics(self, queryset) -> Dict[str, Any]:
        """Compute aggregated statistics for income, expenses, and averages."""
        aggregates = queryset.aggregate(
            total_spent=Sum('amount', filter=Q(amount__lt=0)),
            total_income=Sum('amount', filter=Q(amount__gt=0)),
            avg_transaction=Avg('amount'),
            transaction_count=Count('id'),
        )

        total_spent = aggregates['total_spent'] or Decimal('0')
        total_income = aggregates['total_income'] or Decimal('0')
        avg_transaction = aggregates['avg_transaction'] or Decimal('0')
        transaction_count = aggregates['transaction_count'] or 0

        largest_expense = queryset.filter(amount__lt=0).order_by('amount').first()
        largest_income = queryset.filter(amount__gt=0).order_by('-amount').first()

        return {
            'total_spent': abs(total_spent),
            'total_income': total_income,
            'avg_transaction': abs(avg_transaction),
            'transaction_count': transaction_count,
            'largest_expense': largest_expense,
            'largest_income': largest_income,
            'net_flow': total_income + total_spent,  # total_spent is negative
        }

    def _get_category_breakdown(self, queryset):
        """Compute spending per category for charts."""
        categories = list(
            queryset.filter(amount__lt=0)
            .values('category__name')
            .annotate(
                total=Sum('amount'),
                count=Count('id')
            )
            .order_by('total')
        )
        for cat in categories:
            cat['total'] = float(abs(cat['total']))
            if not cat['category__name']:
                cat['category__name'] = 'Uncategorized'
        return categories

    def _get_monthly_trend(self, queryset):
        """Compute monthly income vs expenses."""
        monthly_totals = list(
            queryset.annotate(month=TruncMonth('date'))
            .values('month')
            .annotate(
                expenses=Sum('amount', filter=Q(amount__lt=0)),
                income=Sum('amount', filter=Q(amount__gt=0)),
                transaction_count=Count('id'),
            )
            .order_by('month')
        )
        for item in monthly_totals:
            item['expenses'] = float(abs(item['expenses'])) if item['expenses'] else 0.0
            item['income'] = float(item['income']) if item['income'] else 0.0
            if item['month']:
                item['month'] = item['month'].isoformat()
        return monthly_totals

    def _get_weekly_pattern(self, queryset):
        """Compute weekly spending amounts."""
        weekly_totals = list(
            queryset.filter(amount__lt=0)
            .annotate(week=TruncWeek('date'))
            .values('week')
            .annotate(total=Sum('amount'))
            .order_by('week')
        )
        for item in weekly_totals:
            item['total'] = float(abs(item['total'])) if item['total'] else 0.0
            if item['week']:
                item['week'] = item['week'].isoformat()
        return weekly_totals
