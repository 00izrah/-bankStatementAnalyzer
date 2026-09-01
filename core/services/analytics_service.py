from decimal import Decimal
from datetime import timedelta
from typing import Dict, Any, Optional, List
from django.db.models import Sum, Q, Avg, Count, Min, Max
from django.db.models.functions import TruncMonth, TruncWeek
from django.core.paginator import Paginator
from django.utils import timezone
from ..models import Transaction, UploadedFile, Category


from .categorization_service import CategorizationService


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

    def get_dashboard_data(
        self,
        date_filter: str = 'all',
        page: int = 1,
        page_size: int = 25,
        search_query: str = '',
        category_filter: str = ''
    ) -> Dict[str, Any]:
        """Compute all data needed to render the financial dashboard with pagination and search."""
        user_files = UploadedFile.objects.filter(user=self.user).order_by('-uploaded_at')
        base_queryset = Transaction.objects.filter(uploaded_file__user=self.user)

        # Apply date range filtering
        transactions = self._apply_date_filter(base_queryset, date_filter)

        # Compute key statistics
        stats = self._get_statistics(transactions)

        # Compute category breakdown
        categories = self._get_category_breakdown(transactions)

        # Compute top merchants
        top_merchants = self._get_top_merchants(transactions)

        # Compute monthly trend
        monthly_totals = self._get_monthly_trend(transactions)

        # Compute weekly pattern
        weekly_totals = self._get_weekly_pattern(transactions)

        # Compute financial insights
        insights = self._get_financial_insights(stats, transactions, date_filter)

        # Recent high-value transactions (largest debits)
        high_value_transactions = transactions.filter(amount__lt=0).order_by('amount')[:5]

        # Apply search and category filtering for transaction table
        table_queryset = transactions.select_related('category', 'uploaded_file').order_by('-date')
        if search_query:
            table_queryset = table_queryset.filter(
                Q(description__icontains=search_query) |
                Q(notes__icontains=search_query)
            )
        if category_filter:
            if category_filter == 'uncategorized':
                table_queryset = table_queryset.filter(category__isnull=True)
            elif category_filter.isdigit():
                table_queryset = table_queryset.filter(category_id=int(category_filter))

        paginator = Paginator(table_queryset, page_size)
        transactions_page = paginator.get_page(page)

        # User-accessible categories for filter dropdown
        user_categories = Category.objects.filter(
            Q(user=self.user) | Q(is_system=True)
        ).order_by('name')

        return {
            'files': user_files,
            'transactions': transactions_page,
            'stats': stats,
            'insights': insights,
            'categories': categories,
            'top_merchants': top_merchants,
            'monthly_totals': monthly_totals,
            'weekly_totals': weekly_totals,
            'high_value_transactions': high_value_transactions,
            'date_filter': date_filter,
            'search_query': search_query,
            'category_filter': category_filter,
            'user_categories': user_categories,
        }

    def _apply_date_filter(self, queryset, date_filter: str):
        """Filter transactions by selected time range."""
        days = self.DATE_FILTERS.get(date_filter)
        if days:
            start_date = timezone.now().date() - timedelta(days=days)
            return queryset.filter(date__gte=start_date)
        return queryset

    def _get_statistics(self, queryset) -> Dict[str, Any]:
        """Compute aggregated statistics for income, expenses, bank fees, and averages."""
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

        # Bank charges & levies breakdown
        bank_charges_total = queryset.filter(
            amount__lt=0
        ).filter(
            Q(category__name__icontains='Bank Charges') |
            Q(notes__icontains='Levy') |
            Q(notes__icontains='Stamp Duty') |
            Q(notes__icontains='SMS Alert') |
            Q(notes__icontains='Maintenance Fee')
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0')
        bank_charges_total = abs(bank_charges_total)
        real_spending = max(Decimal('0'), abs(total_spent) - bank_charges_total)

        return {
            'total_spent': abs(total_spent),
            'real_spending': real_spending,
            'bank_charges_total': bank_charges_total,
            'total_income': total_income,
            'avg_transaction': abs(avg_transaction),
            'transaction_count': transaction_count,
            'largest_expense': largest_expense,
            'largest_income': largest_income,
            'net_flow': total_income + total_spent,  # total_spent is negative
        }

    def _get_financial_insights(self, stats: Dict[str, Any], queryset, date_filter: str) -> Dict[str, Any]:
        """Calculate high-level financial health indicators, savings rates, and recurring expenses."""
        income = stats['total_income']
        spent = stats['total_spent']

        # Savings Rate & Health Badge
        if income > Decimal('0'):
            savings_rate = round(float(((income - spent) / income) * 100), 1)
        else:
            savings_rate = 0.0

        if savings_rate >= 40:
            health_status = 'Excellent'
            health_color = 'emerald'
        elif savings_rate >= 20:
            health_status = 'Healthy'
            health_color = 'indigo'
        elif savings_rate >= 5:
            health_status = 'Moderate'
            health_color = 'amber'
        else:
            health_status = 'Deficit / High Spend'
            health_color = 'rose'

        # Daily Burn Rate
        days = self.DATE_FILTERS.get(date_filter)
        if not days:
            date_bounds = queryset.aggregate(min_date=Min('date'), max_date=Max('date'))
            min_date = date_bounds['min_date']
            max_date = date_bounds['max_date']
            if min_date and max_date:
                days = max(1, (max_date - min_date).days + 1)
            else:
                days = 30

        daily_burn_rate = round(float(spent / Decimal(str(days))), 2) if days > 0 else 0.0

        # Recurring charges detection (Bills, utilities, subscriptions, recurring fees)
        recurring_queryset = queryset.filter(
            amount__lt=0
        ).filter(
            Q(category__name__in=['Utilities', 'Airtime & Data', 'Bank Charges & Fees']) |
            Q(notes__icontains='Subscription') |
            Q(notes__icontains='Electric') |
            Q(notes__icontains='Charge') |
            Q(notes__icontains='Levy')
        )
        recurring_total = recurring_queryset.aggregate(total=Sum('amount'))['total'] or Decimal('0')
        recurring_total = abs(recurring_total)

        # Peak spending day of week
        debit_transactions = queryset.filter(amount__lt=0).values('date', 'amount')
        day_totals = {0: Decimal('0'), 1: Decimal('0'), 2: Decimal('0'), 3: Decimal('0'), 4: Decimal('0'), 5: Decimal('0'), 6: Decimal('0')}
        day_names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']

        for t in debit_transactions:
            d = t['date']
            day_totals[d.weekday()] += abs(t['amount'])

        peak_day_idx = max(day_totals, key=day_totals.get)
        peak_day_name = day_names[peak_day_idx]
        peak_day_amount = day_totals[peak_day_idx]

        return {
            'savings_rate': savings_rate,
            'health_status': health_status,
            'health_color': health_color,
            'daily_burn_rate': daily_burn_rate,
            'recurring_total': recurring_total,
            'peak_day_name': peak_day_name,
            'peak_day_amount': peak_day_amount,
        }

    def _get_top_merchants(self, queryset) -> List[Dict[str, Any]]:
        """Extract top merchants/recipients by total expenditure."""
        debits = queryset.filter(amount__lt=0).values('description', 'notes', 'amount')
        merchant_totals = {}
        for txn in debits:
            notes = txn.get('notes') or ''
            if 'Merchant: ' in notes:
                merchant = notes.split('Merchant: ')[1].strip()
            else:
                merchant = CategorizationService.extract_merchant(txn['description']) or 'Other Payees'

            merchant_totals[merchant] = merchant_totals.get(merchant, Decimal('0')) + abs(txn['amount'])

        sorted_merchants = sorted(
            [{'name': m, 'total': float(t)} for m, t in merchant_totals.items() if m != 'Other Payees'],
            key=lambda x: x['total'],
            reverse=True
        )[:5]
        return sorted_merchants

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
        total_spending = sum(abs(cat['total']) for cat in categories) or Decimal('1')
        for cat in categories:
            cat_total = abs(cat['total'])
            cat['total'] = float(cat_total)
            cat['percentage'] = round(float((cat_total / total_spending) * 100), 1)
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
