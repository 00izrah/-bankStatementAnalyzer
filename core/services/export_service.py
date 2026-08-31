"""
Service for exporting transaction data into CSV and JSON formats.
"""
import csv
import json
from decimal import Decimal
from django.http import HttpResponse
from django.utils import timezone


class ExportService:
    """Service to export filtered transaction records for spreadsheet & accounting tools."""

    @staticmethod
    def export_csv(queryset, filename_prefix="transactions") -> HttpResponse:
        """Export a queryset of transactions to a CSV response."""
        timestamp = timezone.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{filename_prefix}_{timestamp}.csv"

        response = HttpResponse(content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'

        writer = csv.writer(response)
        # Header row
        writer.writerow(['Date', 'Description', 'Amount (NGN)', 'Balance (NGN)', 'Type', 'Category', 'Notes'])

        for txn in queryset.select_related('category', 'uploaded_file').order_by('-date'):
            txn_type = 'Income' if txn.amount > 0 else 'Expense'
            category_name = txn.category.name if txn.category else 'Uncategorized'
            writer.writerow([
                txn.date.strftime('%Y-%m-%d'),
                txn.description,
                f"{txn.amount:.2f}",
                f"{txn.balance:.2f}",
                txn_type,
                category_name,
                txn.notes or '',
            ])

        return response

    @staticmethod
    def export_json(queryset, filename_prefix="transactions") -> HttpResponse:
        """Export a queryset of transactions to a formatted JSON response."""
        timestamp = timezone.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{filename_prefix}_{timestamp}.json"

        data = []
        for txn in queryset.select_related('category').order_by('-date'):
            data.append({
                'id': txn.id,
                'date': txn.date.isoformat(),
                'description': txn.description,
                'amount': float(txn.amount),
                'balance': float(txn.balance),
                'type': 'income' if txn.amount > 0 else 'expense',
                'category': txn.category.name if txn.category else None,
                'notes': txn.notes,
            })

        response = HttpResponse(json.dumps(data, indent=2), content_type='application/json')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response
