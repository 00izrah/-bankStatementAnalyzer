# Bank Statement Analyzer 📊🇳🇬

A robust, secure Django web application for parsing, categorizing, and visualizing Nigerian bank statements (PDF).

## Features

- 📑 **Universal PDF Statement Parsing**: Automatically extracts transactions, balances, dates, and amounts across Nigerian banks (GTBank, Access Bank, Zenith, UBA, Kuda, Moniepoint, etc.).
- 🏷️ **Smart Auto-Categorization**: Categorizes transactions based on keyword heuristics and user-configurable custom categories.
- 📈 **Financial Dashboard & Analytics**: Interactive charts showing monthly income vs. expenses, category spending distribution, and weekly trends via Chart.js.
- 🔒 **Security & Multi-Tenant Scoping**: User isolation, hash-based duplicate prevention, strict CSRF/method checks, and audit logging.
- ⚡ **Clean Architecture**: Decoupled service layer (`UploadService`, `AnalyticsService`, `AuditLogger`) with comprehensive unit & integration tests.

---

## Quick Start

### 1. Prerequisites
- Python 3.10+
- Virtualenv

### 2. Installation

```bash
# Clone repository
git clone https://github.com/00izrah/-bankStatementAnalyzer.git
cd -bankStatementAnalyzer

# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Environment Configuration

Create a `.env` file in the project root:

```env
DJANGO_SECRET_KEY=your-strong-random-secret-key-here
DJANGO_DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1
```

### 4. Database Setup & Seeding

```bash
# Run migrations
python manage.py migrate

# Seed default Nigerian financial categories
python manage.py create_default_categories

# Create a superuser (optional)
python manage.py createsuperuser
```

### 5. Run Development Server

```bash
python manage.py runserver
```

Visit `http://127.0.0.1:8000` in your browser.

---

## Running Tests

Execute the automated test suite with:

```bash
python manage.py test core
```

---

## Project Structure

```
├── bankstatements/          # Django project settings & URL routing
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py
├── core/                    # Core business application
│   ├── models.py            # Category, UploadedFile, Transaction
│   ├── views.py             # HTTP handlers (thin controllers)
│   ├── forms.py             # Form validation & user-scoped querysets
│   ├── validators.py        # PDF & file safety validators
│   ├── parsers/             # BaseStatementParser & UniversalBankParser
│   ├── services/            # UploadService, AnalyticsService, AuditLogger
│   └── tests/               # Unit and integration test suite
├── templates/               # HTML templates (Tailwind & Chart.js)
├── requirements.txt         # Pinned Python dependencies
└── manage.py
```

---

## License

MIT License
