# Bank Statement Analyzer - Product Documentation

## Table of Contents
1. [Overview](#overview)
2. [Features](#features)
3. [System Requirements](#system-requirements)
4. [Installation](#installation)
5. [User Guide](#user-guide)
6. [Technical Architecture](#technical-architecture)
7. [API Reference](#api-reference)
8. [Database Schema](#database-schema)
9. [Supported Banks](#supported-banks)
10. [Troubleshooting](#troubleshooting)
11. [Contributing](#contributing)
12. [License](#license)

## Overview

The Bank Statement Analyzer is a comprehensive web application designed to help users analyze their financial data by uploading bank statements in PDF format. The application automatically parses transactions, categorizes them, and provides detailed insights through interactive visualizations and reports.

### Key Benefits
- **Automated Transaction Processing**: Upload PDF statements and get instant transaction extraction
- **Smart Categorization**: Automatic categorization of transactions with customizable categories
- **Visual Analytics**: Interactive charts and graphs for spending analysis
- **Multi-Bank Support**: Compatible with major Nigerian banks
- **Secure Data Handling**: Encrypted storage and secure file processing

## Features

### Core Features
- **PDF Statement Upload**: Support for multiple bank statement formats
- **Transaction Extraction**: Automatic parsing of transaction data from PDFs
- **Smart Categorization**: AI-powered transaction categorization with user customization
- **Interactive Dashboard**: Real-time financial insights and visualizations
- **Category Management**: Create and manage custom transaction categories
- **Transaction Editing**: Manual categorization and note-taking for transactions

### Analytics & Reporting
- **Monthly Spending Trends**: Track income and expenses over time
- **Category Distribution**: Visual breakdown of spending by category
- **Weekly Patterns**: Identify spending patterns throughout the week
- **Key Metrics**: Total spending, income, averages, and largest transactions
- **Date Range Filtering**: Analyze data for specific time periods

### User Management
- **User Authentication**: Secure login and registration system
- **Password Reset**: Email-based password recovery
- **User Profiles**: Personal account management
- **Data Privacy**: User-specific data isolation

## System Requirements

### Server Requirements
- Python 3.8 or higher
- Django 5.0+
- SQLite (default) or PostgreSQL

### Dependencies
```
Django==5.0.3
python-dotenv==1.0.1
pdfplumber==0.10.4
pandas==2.2.1
matplotlib==3.8.3
pillow==10.2.0
django-crispy-forms==2.1
crispy-tailwind==1.0.0
```

## Installation

### Local Development Setup

1. **Clone the Repository**
```bash
git clone <repository-url>
cd bank-statement-analyzer
```

2. **Create Virtual Environment**
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. **Install Dependencies**
```bash
pip install -r requirements.txt
```

4. **Environment Configuration**
Create a `.env` file in the project root:
```env
DJANGO_SECRET_KEY=your-secret-key-here
DJANGO_DEBUG=True
```

5. **Database Setup**
```bash
python manage.py makemigrations
python manage.py migrate
python manage.py create_default_categories
```

6. **Create Superuser**
```bash
python manage.py createsuperuser
```

7. **Run Development Server**
```bash
python manage.py runserver
```

### Production Deployment

1. **Environment Variables**
```env
DJANGO_SECRET_KEY=production-secret-key
DJANGO_DEBUG=False
ALLOWED_HOSTS=yourdomain.com
DATABASE_URL=postgresql://user:pass@localhost/dbname
```

2. **Static Files**
```bash
python manage.py collectstatic
```

3. **Database Migration**
```bash
python manage.py migrate
```

## User Guide

### Getting Started

1. **Registration**
   - Visit the homepage
   - Click "Sign Up"
   - Fill in your details
   - Verify your email (if configured)

2. **First Statement Upload**
   - Navigate to "Upload Statement"
   - Select your bank from the dropdown
   - Choose your PDF statement file
   - Click "Upload Statement"

3. **Dashboard Overview**
   - View your financial summary
   - Explore interactive charts
   - Review recent transactions
   - Filter data by date range

### Statement Upload Process

1. **Supported File Types**: PDF files only
2. **File Size Limit**: Maximum 10MB
3. **Bank Selection**: Choose your bank from the supported list
4. **Processing Time**: Usually 10-30 seconds depending on file size
5. **Error Handling**: Clear error messages for unsupported formats

### Category Management

1. **Default Categories**
   - Food & Dining
   - Transportation
   - Utilities
   - Entertainment
   - Shopping
   - Healthcare
   - Education
   - Housing
   - Income
   - Other

2. **Custom Categories**
   - Create personalized categories
   - Add keywords for automatic categorization
   - Edit existing categories
   - Set category descriptions

3. **Transaction Editing**
   - Manually categorize transactions
   - Add notes to transactions
   - Bulk category updates

### Dashboard Features

1. **Key Metrics Cards**
   - Total spending
   - Total income
   - Average transaction amount
   - Largest expense/income

2. **Interactive Charts**
   - Monthly income vs expenses trend
   - Category distribution pie chart
   - Weekly spending pattern
   - Hover tooltips with detailed information

3. **Transaction Table**
   - Recent transactions list
   - Color-coded amounts
   - Category badges
   - Edit functionality

4. **Date Filtering**
   - Last 30 days
   - Last 3 months
   - Last 6 months
   - Last year
   - All time

## Technical Architecture

### Backend Architecture
- **Framework**: Django 5.0
- **Database**: SQLite (development), PostgreSQL (production)
- **File Processing**: pdfplumber for PDF parsing
- **Authentication**: Django's built-in auth system
- **Forms**: Django Crispy Forms with Tailwind CSS

### Frontend Architecture
- **CSS Framework**: Tailwind CSS
- **JavaScript**: Vanilla JS with Chart.js
- **Charts**: Chart.js for data visualization
- **Icons**: Lucide React icons
- **Responsive Design**: Mobile-first approach

### File Structure
```
bankstatements/
├── core/                   # Main application
│   ├── models.py          # Database models
│   ├── views.py           # View controllers
│   ├── forms.py           # Form definitions
│   ├── urls.py            # URL routing
│   ├── parsers/           # PDF parsing modules
│   └── management/        # Django commands
├── templates/             # HTML templates
├── static/               # Static files
├── media/                # Uploaded files
└── requirements.txt      # Dependencies
```

### Security Features
- CSRF protection
- SQL injection prevention
- File upload validation
- User data isolation
- Secure password hashing

## API Reference

### Models

#### User
Django's built-in User model for authentication.

#### Category
```python
class Category(models.Model):
    name = models.CharField(max_length=50)
    description = models.TextField(blank=True)
    keywords = models.TextField()
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    is_system = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
```

#### UploadedFile
```python
class UploadedFile(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    file = models.FileField(upload_to='statements/')
    uploaded_at = models.DateTimeField(auto_now_add=True)
    bank_name = models.CharField(max_length=100)
    processed = models.BooleanField(default=False)
```

#### Transaction
```python
class Transaction(models.Model):
    uploaded_file = models.ForeignKey(UploadedFile, on_delete=models.CASCADE)
    date = models.DateField()
    description = models.TextField()
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    category = models.ForeignKey(Category, on_delete=models.SET_NULL)
    balance = models.DecimalField(max_digits=12, decimal_places=2)
    notes = models.TextField(blank=True)
```

### Views

#### Dashboard View
- **URL**: `/dashboard/`
- **Method**: GET
- **Authentication**: Required
- **Parameters**: `date_range` (optional)
- **Returns**: Dashboard with analytics and charts

#### Upload View
- **URL**: `/upload/`
- **Method**: GET, POST
- **Authentication**: Required
- **File Types**: PDF
- **Max Size**: 10MB

#### Category Management
- **URL**: `/categories/`
- **Method**: GET, POST
- **Authentication**: Required
- **Actions**: Create, view categories

## Database Schema

### Entity Relationship Diagram
```
User (Django Auth)
├── UploadedFile (1:N)
│   └── Transaction (1:N)
│       └── Category (N:1)
└── Category (1:N)
```

### Key Relationships
- Users can have multiple uploaded files
- Each uploaded file contains multiple transactions
- Transactions belong to categories
- Users can create custom categories
- System categories are shared across users

## Supported Banks

### Currently Supported
1. **Access Bank**
   - Statement format: DD-MMM-YY
   - Columns: Date, Description, Debit, Credit, Balance

2. **Zenith Bank**
   - Statement format: DD/MM/YYYY
   - Columns: Date, Description, Debit, Credit, Balance

3. **GTBank (Guaranty Trust Bank)**
   - Statement format: DD-MMM-YYYY
   - Columns: Date, Description, Debit, Credit, Balance

4. **UBA (United Bank for Africa)**
   - Statement format: DD/MM/YYYY
   - Columns: Date, Description, Debit, Credit, Balance

### Adding New Banks
To add support for a new bank:

1. Create a new parser in `core/parsers/`
2. Extend `BaseStatementParser`
3. Implement `parse_page()` method
4. Add to `BANK_PARSERS` dictionary
5. Test with sample statements

## Troubleshooting

### Common Issues

#### PDF Upload Fails
- **Cause**: Unsupported PDF format or corrupted file
- **Solution**: Ensure PDF is from supported bank and not password-protected

#### No Transactions Extracted
- **Cause**: PDF format not recognized by parser
- **Solution**: Check if bank is supported, verify PDF quality

#### Charts Not Loading
- **Cause**: JavaScript errors or missing data
- **Solution**: Check browser console, ensure transactions exist

#### Login Issues
- **Cause**: Incorrect credentials or session expired
- **Solution**: Reset password or clear browser cache

### Error Messages

#### "No parser available for [Bank Name]"
- Bank not supported yet
- Check supported banks list
- Contact support for new bank requests

#### "Error processing statement"
- PDF format issue
- File corruption
- Parser error

### Performance Issues

#### Slow Dashboard Loading
- Large number of transactions
- Complex date range queries
- Solution: Use date filtering, pagination

#### File Upload Timeout
- Large PDF files
- Slow internet connection
- Solution: Compress PDF, check connection

## License

This project is licensed under the MIT License. See the LICENSE file for details.

### Third-Party Libraries
- Django: BSD License
- Chart.js: MIT License
- Tailwind CSS: MIT License
- pdfplumber: MIT License

## Support

### Documentation
- Product documentation: This file
- API documentation: Available in code comments
- User guides: Available in application

--

**Last Updated**: January 2025
**Version**: 1.0.0
**Maintainer**: Development Team