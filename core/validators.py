from django.core.exceptions import ValidationError
from django.conf import settings
import os

try:
    import magic
except ImportError:
    magic = None

# Maximum file size (10 MB)
MAX_FILE_SIZE = getattr(settings, 'MAX_UPLOAD_SIZE', 10 * 1024 * 1024)

# Allowed MIME types
ALLOWED_MIME_TYPES = [
    'application/pdf',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'application/vnd.ms-excel',
    'text/csv',
    'text/plain',
    'application/octet-stream',
]

# Allowed extensions
ALLOWED_EXTENSIONS = ['.pdf', '.xlsx', '.xls', '.csv']


class FileValidationError(ValidationError):
    """Custom exception for file validation errors."""
    pass


def validate_file_size(file):
    """Validate that file size is within limits."""
    if file.size > MAX_FILE_SIZE:
        max_mb = MAX_FILE_SIZE / (1024 * 1024)
        file_mb = file.size / (1024 * 1024)
        raise FileValidationError(
            f'File size ({file_mb:.1f} MB) exceeds maximum allowed size ({max_mb:.1f} MB).'
        )


def validate_file_extension(file):
    """Validate file extension."""
    ext = os.path.splitext(file.name)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise FileValidationError(
            f'File extension "{ext}" is not allowed. Allowed extensions: {", ".join(ALLOWED_EXTENSIONS)}'
        )


def validate_file_content_type(file):
    """Validate file MIME type and magic headers by reading file content."""
    file.seek(0)
    file_header = file.read(2048)
    file.seek(0)
    
    ext = os.path.splitext(file.name)[1].lower()

    try:
        mime = magic.from_buffer(file_header, mime=True) if magic else None
    except Exception:
        mime = None
    
    # Check extension-specific file signatures
    if ext == '.pdf':
        if not file_header.startswith(b'%PDF'):
            raise FileValidationError(
                'Invalid PDF file. The file does not appear to be a valid PDF document.'
            )
    elif ext == '.xlsx':
        if not file_header.startswith(b'PK'):
            raise FileValidationError(
                'Invalid Excel file. The file does not appear to be a valid .xlsx document.'
            )


def validate_not_password_protected(file):
    """Validate that a PDF is not password-protected or encrypted."""
    ext = os.path.splitext(file.name)[1].lower()
    if ext != '.pdf':
        return

    file.seek(0)
    try:
        import pdfplumber
        with pdfplumber.open(file) as pdf:
            if hasattr(pdf, 'doc') and getattr(pdf.doc, 'is_encrypted', False):
                raise FileValidationError(
                    'This PDF statement is password-protected or encrypted. '
                    'Please upload an unlocked PDF statement.'
                )
    except FileValidationError:
        raise
    except Exception as e:
        error_str = str(e).lower()
        if 'password' in error_str or 'encrypt' in error_str:
            raise FileValidationError(
                'This PDF statement is password-protected or encrypted. '
                'Please upload an unlocked PDF statement.'
            )
    finally:
        file.seek(0)


def validate_uploaded_file(file):
    """Run all file validations."""
    errors = []
    
    try:
        validate_file_size(file)
    except FileValidationError as e:
        errors.append(str(e.message))
    
    try:
        validate_file_extension(file)
    except FileValidationError as e:
        errors.append(str(e.message))
    
    try:
        validate_file_content_type(file)
    except FileValidationError as e:
        errors.append(str(e.message))

    # Only run encryption check if file header is valid PDF
    if not errors:
        try:
            validate_not_password_protected(file)
        except FileValidationError as e:
            errors.append(str(e.message))
    
    if errors:
        raise FileValidationError(errors)
    
    return True