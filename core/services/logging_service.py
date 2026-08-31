import logging
import json
from functools import wraps
import traceback
from django.utils import timezone
from django.conf import settings

# Configure logger
logger = logging.getLogger('bankstatements')


class AuditLogger:
    """Service for audit logging of user actions."""
    
    @staticmethod
    def log_upload(user, filename, file_size, success=True, error=None, transaction_count=0):
        """Log file upload attempt."""
        log_data = {
            'action': 'file_upload',
            'user_id': user.id if user else None,
            'username': user.username if user else 'anonymous',
            'filename': filename,
            'file_size': file_size,
            'success': success,
            'transaction_count': transaction_count,
            'timestamp': timezone.now().isoformat(),
        }
        
        if error:
            log_data['error'] = str(error)
            logger.error(f"Upload failed: {json.dumps(log_data)}")
        else:
            logger.info(f"Upload successful: {json.dumps(log_data)}")
        
        return log_data

    @staticmethod
    def log_delete(user, file_id, transaction_count):
        """Log file deletion."""
        log_data = {
            'action': 'file_delete',
            'user_id': user.id if user else None,
            'username': user.username if user else 'anonymous',
            'file_id': file_id,
            'transaction_count': transaction_count,
            'timestamp': timezone.now().isoformat(),
        }
        logger.info(f"Delete: {json.dumps(log_data)}")
        return log_data

    @staticmethod
    def log_transaction_edit(user, transaction_id, changes):
        """Log transaction edit."""
        log_data = {
            'action': 'transaction_edit',
            'user_id': user.id if user else None,
            'username': user.username if user else 'anonymous',
            'transaction_id': transaction_id,
            'changes': changes,
            'timestamp': timezone.now().isoformat(),
        }
        logger.info(f"Transaction edit: {json.dumps(log_data)}")
        return log_data

    @staticmethod
    def log_error(user, action, error, context=None):
        """Log an error with context."""
        log_data = {
            'action': action,
            'user_id': user.id if user else None,
            'username': user.username if user else 'anonymous',
            'error': str(error),
            'traceback': traceback.format_exc(),
            'context': context or {},
            'timestamp': timezone.now().isoformat(),
        }
        logger.error(f"Error: {json.dumps(log_data)}")
        return log_data


def log_exceptions(action_name):
    """Decorator to log exceptions in views."""
    def decorator(func):
        @wraps(func)
        def wrapper(request, *args, **kwargs):
            try:
                return func(request, *args, **kwargs)
            except Exception as e:
                user = request.user if request.user.is_authenticated else None
                AuditLogger.log_error(user, action_name, e, {
                    'path': request.path,
                    'method': request.method,
                    'args': args,
                    'kwargs': kwargs,
                })
                raise
        return wrapper
    return decorator