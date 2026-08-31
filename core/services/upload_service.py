from django.db import transaction, models
from django.db.utils import IntegrityError
from decimal import Decimal
from typing import List, Dict, Any, Tuple, Optional
import os

from ..models import UploadedFile, Transaction, Category, calculate_file_hash
from ..validators import validate_uploaded_file, FileValidationError
from ..parsers import BANK_PARSERS, get_parser_for_file
from .categorization_service import CategorizationService
from .logging_service import AuditLogger, logger


class UploadError(Exception):
    """Custom exception for upload errors."""
    pass


class UploadService:
    """Service for handling file uploads and transaction processing."""
    
    def __init__(self, user):
        self.user = user
        self.stats = {
            'transactions_created': 0,
            'duplicates_skipped': 0,
            'categorized_count': 0,
            'validation_errors': [],
            'balance_errors': 0,
        }

    def process_upload(self, file, replace_existing=False) -> Tuple[UploadedFile, Dict[str, Any]]:
        """
        Process an uploaded file with full validation and transaction management.
        
        Returns:
            Tuple of (UploadedFile, stats_dict)
        
        Raises:
            FileValidationError: If file validation fails
            UploadError: If processing fails
        """
        # Validate file first
        validate_uploaded_file(file)
        
        # Calculate file hash for duplicate detection
        file_hash = calculate_file_hash(file)
        
        # Check for duplicate file upload
        if not replace_existing:
            existing = UploadedFile.objects.filter(
                user=self.user, 
                file_hash=file_hash
            ).first()
            if existing:
                raise UploadError(
                    f'This file has already been uploaded on {existing.uploaded_at.strftime("%Y-%m-%d %H:%M")}.'
                )
        
        try:
            with transaction.atomic():
                # Delete existing files if replacing
                if replace_existing:
                    self._delete_existing_files()
                
                # Create upload record
                uploaded_file = self._create_upload_record(file, file_hash)
                
                # Parse and process transactions
                transactions = self._parse_file(uploaded_file)
                
                # Bulk create transactions
                self._bulk_create_transactions(uploaded_file, transactions)
                
                # Update upload record
                uploaded_file.processed = True
                uploaded_file.transaction_count = self.stats['transactions_created']
                uploaded_file.save()
                
                # Log success
                AuditLogger.log_upload(
                    self.user,
                    file.name,
                    file.size,
                    success=True,
                    transaction_count=self.stats['transactions_created']
                )
                
                return uploaded_file, self.stats
                
        except IntegrityError as e:
            logger.error(f"Database integrity error during upload: {e}")
            AuditLogger.log_upload(
                self.user, file.name, file.size, 
                success=False, error=str(e)
            )
            raise UploadError('A database error occurred while saving transactions.')
        
        except Exception as e:
            logger.error(f"Upload processing error: {e}")
            AuditLogger.log_upload(
                self.user, file.name, file.size,
                success=False, error=str(e)
            )
            raise

    def _delete_existing_files(self):
        """Delete all existing files for user."""
        old_files = UploadedFile.objects.filter(user=self.user)
        for old_file in old_files:
            try:
                if old_file.file and os.path.exists(old_file.file.path):
                    os.remove(old_file.file.path)
            except Exception as e:
                logger.warning(f"Could not delete file {old_file.file.path}: {e}")
        old_files.delete()

    def _create_upload_record(self, file, file_hash) -> UploadedFile:
        """Create the upload record."""
        uploaded_file = UploadedFile(
            user=self.user,
            file=file,
            file_hash=file_hash,
            original_filename=file.name,
            file_size=file.size,
        )
        uploaded_file.save()
        return uploaded_file

    def _parse_file(self, uploaded_file: UploadedFile) -> List[Dict[str, Any]]:
        """Parse the uploaded file and extract transactions."""
        parser_class = get_parser_for_file(uploaded_file.file.path)
        if not parser_class:
            raise UploadError('No parser available for processing statements.')
        
        parser = parser_class(uploaded_file.file.path)
        transactions = parser.parse()
        
        # Get parsing stats
        parsing_stats = parser.get_parsing_stats()
        self.stats['balance_errors'] = parsing_stats.get('balance_errors', 0)
        
        if not transactions:
            raise UploadError(
                'No transactions could be extracted from the file. '
                'Please ensure this is a valid bank statement file (PDF, Excel, or CSV).'
            )
        
        return transactions

    def _bulk_create_transactions(
        self, 
        uploaded_file: UploadedFile, 
        transactions: List[Dict[str, Any]]
    ):
        """Bulk create transactions with duplicate detection."""
        # Load categories
        categories = {
            cat.name.lower(): cat 
            for cat in Category.objects.filter(
                models.Q(user=self.user) | models.Q(is_system=True)
            )
        }
        
        # Get existing transaction hashes for this user (across all files)
        existing_hashes = set(
            Transaction.objects.filter(
                uploaded_file__user=self.user
            ).values_list('content_hash', flat=True)
        )
        
        # Prepare transactions for bulk create
        transactions_to_create = []
        seen_hashes = set()
        
        for trans_data in transactions:
            # Validate transaction data
            if not self._validate_transaction(trans_data):
                continue
            
            # Generate content hash
            content_hash = Transaction.generate_content_hash(
                trans_data['date'],
                trans_data['description'],
                trans_data['amount'],
                trans_data['balance']
            )
            
            # Skip duplicates
            if content_hash in existing_hashes or content_hash in seen_hashes:
                self.stats['duplicates_skipped'] += 1
                continue
            
            seen_hashes.add(content_hash)
            
            # Find category and clean merchant name using CategorizationService
            category, detected_merchant = CategorizationService.categorize_transaction(
                trans_data['description'],
                trans_data['amount'],
                categories
            )
            if category:
                self.stats['categorized_count'] += 1
            
            notes = f"Merchant: {detected_merchant}" if detected_merchant else trans_data.get('notes', '')

            # Create transaction object (don't save yet)
            transaction_obj = Transaction(
                uploaded_file=uploaded_file,
                date=trans_data['date'],
                description=trans_data['description'],
                amount=trans_data['amount'],
                balance=trans_data['balance'],
                category=category,
                notes=notes,
                content_hash=content_hash,
            )
            transactions_to_create.append(transaction_obj)
        
        # Bulk create in batches
        batch_size = 500
        for i in range(0, len(transactions_to_create), batch_size):
            batch = transactions_to_create[i:i + batch_size]
            Transaction.objects.bulk_create(
                batch,
                ignore_conflicts=True  # Skip any that violate unique constraint
            )
        
        self.stats['transactions_created'] = len(transactions_to_create)

    def _validate_transaction(self, trans_data: Dict[str, Any]) -> bool:
        """Validate transaction data."""
        errors = []
        
        # Check required fields
        if not trans_data.get('date'):
            errors.append('Missing date')
        
        if not trans_data.get('description'):
            errors.append('Missing description')
        
        if trans_data.get('amount') is None:
            errors.append('Missing amount')
        
        # Validate amount is a valid decimal
        try:
            amount = Decimal(str(trans_data.get('amount', 0)))
            if amount == 0:
                errors.append('Zero amount')
        except Exception:
            errors.append('Invalid amount format')
        
        if errors:
            self.stats['validation_errors'].append({
                'transaction': trans_data.get('description', 'Unknown')[:50],
                'errors': errors
            })
            return False
        
        return True

    def _find_category(
        self, 
        trans_data: Dict[str, Any], 
        categories: Dict[str, Category]
    ) -> Optional[Category]:
        """Find the best matching category for a transaction."""
        cat, _ = CategorizationService.categorize_transaction(
            trans_data['description'],
            Decimal(str(trans_data.get('amount', 0))),
            categories
        )
        return cat