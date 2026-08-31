"""
Categorization Service for Nigerian Bank Transactions.
Provides tokenized narration cleaning, merchant extraction, direction-aware categorization,
and regex word-boundary keyword matching.
"""
import re
from decimal import Decimal
from typing import Optional, Dict, Any, Tuple
from ..models import Category


class CategorizationService:
    """
    Intelligent categorization engine specialized in Nigerian banking transaction syntax.
    """

    # Common Nigerian Bank technical prefixes and noise tokens to clean out
    NOISE_PATTERNS = [
        r'\b(?:NIP|POS|WEB|TRF|FRM|FIP|NEFT|ACH|AUTOPAY|E-CHANNELS|CHANNEL|IBANK|MBANK|USSD|MOBILE|ATM|PAYMENT TO|PAYMENT FROM|TRANSFER TO|TRANSFER FROM|TRF TO|TRF FRM|DIRECT DEBIT|INSTANT PAYMENT|INTERBANK|ONEBANK TRANSFER FROM|ONEBANK TRANSFER TO|ONEBANK)\b',
        r'\b(?:REF|TRX|RRN|STAN|SESSION|TOKEN|CARD|AUTH|TRACE|TXN|ID|BATCH|SEQ|TERMINAL)[\s:/#]*[A-Z0-9_-]+\b',
        r'\b\d{10,20}\b',  # Account numbers, long transaction reference codes
        r'\b\d{2}[-/]\d{2}[-/]\d{2,4}\b',  # Embedded dates
        r'\b\d{1,2}:\d{2}(?::\d{2})?\b',  # Embedded times
        r'[/\\|#_-]+',  # Noise delimiters
    ]

    # High-confidence merchant & transaction signatures mapping to (Clean Merchant/Payee Name, Category Name)
    MERCHANT_REGISTRY = [
        # Bank Charges, Taxes, Overdraft & Levies
        (r'\b(?:EMTL|E-?LEV[EY]|ELECTRONIC MONEY TRANSFER LEVY)\b', ('Federal EMTL Levy', 'Bank Charges & Fees')),
        (r'\b(?:STAMP DUTY|STAMP-?DUTY)\b', ('Stamp Duty Charge', 'Bank Charges & Fees')),
        (r'\b(?:SMS (?:ALERT|NOTIF|CHARGE)|SMS CHG|ALERT CHG|VAT ON SMS)\b', ('SMS Alert Charge', 'Bank Charges & Fees')),
        (r'\b(?:CARD MAINTENANCE|CARD MAINT|ANNUAL CARD FEE|CARD ISSUANCE)\b', ('Card Maintenance Fee', 'Bank Charges & Fees')),
        (r'\b(?:MAINTENANCE FEE|ACCT MAINT|ACCOUNT MAINTENANCE)\b', ('Account Maintenance Fee', 'Bank Charges & Fees')),
        (r'\b(?:USSD ACCESS FEE|USSD SESSION|USSD CHARGE)\b', ('USSD Session Fee', 'Bank Charges & Fees')),
        (r'\b(?:OVERDRAFT INTEREST|SMART OVERDRAFT|INTEREST APPLICATION|OVERDRAFT FEE)\b', ('Overdraft Interest & Fee', 'Bank Charges & Fees')),
        (r'\b(?:VAT CHARGE|VAT CHG|VALUE ADDED TAX|EXCISE DUTY|BANK CHARGE|COMMISSION|TOKEN FEE)\b', ('Bank VAT & Charges', 'Bank Charges & Fees')),

        # Interest & Capitalization (Inflow/Credit)
        (r'\b(?:CREDIT INTEREST|INTEREST CAPITALIZATION|CAPITALIZATION|INTEREST EARNED)\b', ('Interest Capitalization', 'Income')),

        # Food, Dining, Groceries & Everyday Meals
        (r'\bCHOWDECK\b', ('Chowdeck', 'Food & Dining')),
        (r'\bGLOVO\b', ('Glovo', 'Food & Dining')),
        (r'\bEDEN LIFE\b', ('Eden Life', 'Food & Dining')),
        (r'\b(?:CHICKEN REPUBLIC|CR FOODS)\b', ('Chicken Republic', 'Food & Dining')),
        (r'\b(?:THE PLACE|THEPLACE)\b', ('The Place Restaurant', 'Food & Dining')),
        (r'\bKILIMANJARO\b', ('Kilimanjaro', 'Food & Dining')),
        (r'\bMEGA CHICKEN\b', ('Mega Chicken', 'Food & Dining')),
        (r'\b(?:DOMINO\'?S|DOMINOS PIZZA)\b', ('Dominos Pizza', 'Food & Dining')),
        (r'\bKFC\b', ('KFC', 'Food & Dining')),
        (r'\bSWEET SENSATION\b', ('Sweet Sensation', 'Food & Dining')),
        (r'\bCOLD STONE\b', ('Cold Stone Creamery', 'Food & Dining')),
        (r'\b(?:SHOPRITE|SPAR|PRINCE EBEANO|EBEANO|HUBMART|JUSTRITE|SUPERMARKET|GROCERY|BAKERY|RESTAURANT|EATERY|FOODCOURT|FOODSTUFF)\b', ('Supermarket / Food', 'Food & Dining')),
        (r'\b(?:FOOD|LUNCH|DINNER|BREAKFAST|MEAL|MEALS|SHAWARMA|SNACK|SNACKS|DRINKS|SUYA|MEAT|RICE|BREAD|SOUP|COOKING)\b', ('Food & Dining', 'Food & Dining')),

        # Healthcare, Skincare & Personal Care
        (r'\b(?:PERSONAL CARE|SKINCARE|SKIN CARE|HAIR|HAIRCUT|SALON|BARBING|BARBER|BEAUTY|COSMETICS|MAKEUP|NAILS|SPA|GROOMING|PERFUME|TOILETRIES|SOAP|LOTION|CREAM)\b', ('Personal Care & Grooming', 'Healthcare')),
        (r'\b(?:HOSPITAL|CLINIC|PHARMACY|CHEMIST|MEDPLUS|HEALTHPLUS|MEDICAL|DOCTOR|LAB|DENTAL|DENTIST|OPTICIAN|DRUGS|MEDICINE|HMO|INSURANCE)\b', ('Healthcare & Pharmacy', 'Healthcare')),

        # Utilities & Electricity (DisCos, Telcos, Cable TV)
        (r'\b(?:IKEDC|IKEJA ELECTRIC|EKEDC|EKO ELECTRIC|AEDC|ABUJA ELECTRIC|EEDC|IBEDC|PHEDC|KEDCO)\b', ('Electricity DisCo', 'Utilities')),
        (r'\b(?:BUYPOWER|IRECHARGE|ELECTRICITY|POWER BILL|NEPA|LIGHT BILL)\b', ('Electricity Bill', 'Utilities')),
        (r'\b(?:DSTV|GOTV|SHOWMAX|STARTIMES|MULTICHOICE)\b', ('Cable TV Subscription', 'Utilities')),
        (r'\b(?:SPECTRANET|SMILE|IPNX|FIBER|WATER BILL|WASTE|REFUSE)\b', ('Internet / Water / Waste', 'Utilities')),

        # Airtime & Telecom
        (r'\b(?:MTN AIRTIME|MTN VTU|MTN TOPUP|MTN DATA|MTN)\b', ('MTN Nigeria', 'Airtime & Data')),
        (r'\b(?:AIRTEL AIRTIME|AIRTEL VTU|AIRTEL TOPUP|AIRTEL DATA|AIRTEL)\b', ('Airtel Nigeria', 'Airtime & Data')),
        (r'\b(?:GLO AIRTIME|GLO VTU|GLO TOPUP|GLO DATA|GLOBACOM|GLO)\b', ('Glo Mobile', 'Airtime & Data')),
        (r'\b(?:9MOBILE|ETISALAT)\b', ('9mobile Nigeria', 'Airtime & Data')),
        (r'\b(?:VTU|AIRTIME|DATA BUNDLE|DATA SUB|TOP-?UP|RECHARGE)\b', ('Airtime & Data', 'Airtime & Data')),

        # Mobility, Transport & Fuel
        (r'\b(?:UBER|UBER BV|UBER TRIP)\b', ('Uber', 'Transportation')),
        (r'\b(?:BOLT|BOLT\.EU|TAXIFY)\b', ('Bolt', 'Transportation')),
        (r'\bINDRIVE\b', ('inDrive', 'Transportation')),
        (r'\b(?:TOTALENERGIES|TOTAL FILLING|NNPC|MOBIL|CONOIL|ARDOVA|AP PETROLEUM|OANDO|PETROL|DIESEL|FUEL|GAS)\b', ('Fuel & Petrol Station', 'Transportation')),
        (r'\b(?:AIR PEACE|IBOM AIR|AERO CONTRACTORS|ARIK AIR|DANA AIR|UNITED NIGERIA|FLIGHT|AIRLINE|BRT|FARE|TAXI|CAB|MECHANIC|CAR WASH)\b', ('Transport & Mobility', 'Transportation')),

        # Betting & Entertainment
        (r'\b(?:BET9JA|SPORTYBET|1XBET|BETWAY|MSPORT|PARIPESA|NAIRABET)\b', ('Sports Betting', 'Betting & Entertainment')),
        (r'\b(?:CINEMA|FILMHOUSE|SILVERBIRD|MOVIE|MOVIES|NETFLIX|SPOTIFY|APPLE\.COM|YOUTUBE PREMIUM|GAME|GAMING|PLAYSTATION|TICKET|CONCERT|CLUB|LOUNGE)\b', ('Entertainment & Streaming', 'Betting & Entertainment')),

        # Fintech & Savings / Investment
        (r'\b(?:COWRYWISE|COWRY WISE)\b', ('Cowrywise', 'Savings & Investments')),
        (r'\bPIGGYVEST\b', ('Piggyvest', 'Savings & Investments')),
        (r'\b(?:BAMBOO|CHAKA|RISEVEST|TROVE|STANBIC IBTC ASSET|SHARES|STOCK|MUTUAL FUND|CRYPTO|BINANCE|BYBIT|AJO|ESUSU)\b', ('Investment App', 'Savings & Investments')),

        # Shopping, Fashion & E-Commerce
        (r'\b(?:JUMIA|KONGA|AMAZON|ALIEXPRESS|PAYSTACK|FLUTTERWAVE|MONIEPOINT|OPAY|PALMPAY|KUDA)\b', ('Digital Payment / Shopping', 'Shopping')),
        (r'\b(?:CLOTHES|CLOTHING|SHIRT|TROUSERS|DRESS|SHOES|SHOE|BAG|BAGS|SNEAKERS|THRIFT|OKRIKA|BOUTIQUE|FASHION|ACCESSORIES|WRISTWATCH|GADGET|PHONE|LAPTOP|ELECTRONICS)\b', ('Shopping & Retail', 'Shopping')),

        # Housing & Maintenance
        (r'\b(?:RENT|HOUSE RENT|APARTMENT|ESTATE DUES|SERVICE CHARGE|MORTGAGE|PLUMBER|ELECTRICIAN|CARPENTER|HOME REPAIR)\b', ('Housing & Rent', 'Housing')),

        # Education
        (r'\b(?:SCHOOL|TUITION|SCHOOL FEES|FEES|COURSE|TRAINING|UDEMY|COURSERA|BOOK|BOOKS|EXAM|WAEC|JAMB|CERTIFICATION)\b', ('Education & Courses', 'Education')),
    ]

    @classmethod
    def clean_narration(cls, raw_desc: str) -> str:
        """Strip transaction reference numbers, bank technical codes, and delimiters."""
        if not raw_desc:
            return "Bank Transaction"

        text = raw_desc
        for pattern in cls.NOISE_PATTERNS:
            text = re.sub(pattern, ' ', text, flags=re.IGNORECASE)

        cleaned = re.sub(r'\s+', ' ', text).strip()
        return cleaned if len(cleaned) >= 2 else raw_desc.strip()

    @classmethod
    def extract_merchant(cls, raw_desc: str) -> Optional[str]:
        """Identify known merchant brand or recipient from the narration."""
        for pattern, (merchant_name, _) in cls.MERCHANT_REGISTRY:
            if re.search(pattern, raw_desc, re.IGNORECASE):
                return merchant_name
        return None

    @classmethod
    def categorize_transaction(
        cls,
        raw_desc: str,
        amount: Decimal,
        categories: Dict[str, Category]
    ) -> Tuple[Optional[Category], Optional[str]]:
        """
        Categorize transaction using merchant registry, direction awareness,
        and regex word boundary matching against category keywords and category names.
        
        Returns:
            Tuple of (matched_Category_model, detected_merchant_name)
        """
        raw_desc_str = (raw_desc or "").strip()
        raw_desc_upper = raw_desc_str.upper()
        clean_name = cls.extract_merchant(raw_desc_upper)

        # 1. High-confidence merchant registry match
        if clean_name:
            for pattern, (merchant, target_cat_name) in cls.MERCHANT_REGISTRY:
                if merchant == clean_name:
                    # Overdraft fee check: if amount is negative, ensure Bank Charges
                    if 'overdraft' in raw_desc_upper.lower() or 'interest application' in raw_desc_upper.lower():
                        if amount < 0:
                            target_cat_name = 'Bank Charges & Fees'
                    target_cat = cls._find_category_by_name(target_cat_name, categories)
                    if target_cat:
                        return target_cat, clean_name

        # 2. Inflow / Income Direction-Aware Check (amount > 0)
        if amount > 0:
            if any(w in raw_desc_upper for w in ['SALARY', 'PAYROLL', 'ALLOWANCE', 'WAGES', 'STIPEND']):
                cat = cls._find_category_by_name('Income', categories)
                if cat:
                    return cat, clean_name or "Salary Inflow"
            if any(w in raw_desc_upper for w in ['INTEREST', 'CAPITALIZATION', 'DIVIDEND', 'INVESTMENT RETURN', 'COUPON']):
                cat = cls._find_category_by_name('Income', categories) or cls._find_category_by_name('Savings & Investments', categories)
                if cat:
                    return cat, clean_name or "Interest / Investment"
            if any(w in raw_desc_upper for w in ['REFUND', 'REVERSAL', 'CHARGEBACK', 'CASHBACK']):
                cat = cls._find_category_by_name('Income', categories)
                if cat:
                    return cat, clean_name or "Refund / Reversal"
            if any(w in raw_desc_upper for w in ['TRF', 'TRANSFER', 'NIP', 'FRM', 'FROM', 'INFLOW', 'LODGEMENT', 'CREDIT', 'ONEBANK']):
                cat = cls._find_category_by_name('Transfers & P2P', categories) or cls._find_category_by_name('Income', categories)
                if cat:
                    return cat, clean_name or "Inflow Transfer"

        # 3. Bank Charges detection for debits (amount < 0)
        if amount < 0:
            if any(w in raw_desc_upper for w in ['LEVY', 'DUTY', 'STAMP', 'SMS', 'MAINT', 'MAINTENANCE', 'USSD', 'VAT', 'CHG', 'CHARGE', 'COMMISSION', 'OVERDRAFT']):
                cat = cls._find_category_by_name('Bank Charges & Fees', categories) or cls._find_category_by_name('Utilities', categories)
                if cat:
                    return cat, clean_name or "Bank Charge"

        # 4. Dynamic Keyword Matching with Word Boundaries (checks category keywords AND category name words)
        desc_lower = raw_desc_str.lower()
        for cat_name, cat in categories.items():
            # Build full keyword candidate set: explicit keywords + category name tokens
            candidate_keywords = set(cat.keyword_list)
            # Add category name and individual words (e.g. 'food', 'dining', 'healthcare', 'care')
            clean_cat_name = cat.name.lower().replace('&', ' ').replace('/', ' ')
            for part in clean_cat_name.split():
                if len(part) >= 3 and part not in ('and', 'the', 'for'):
                    candidate_keywords.add(part)

            for kw in candidate_keywords:
                kw_str = kw.strip().lower()
                if not kw_str or len(kw_str) < 2:
                    continue
                kw_regex = r'\b' + re.escape(kw_str) + r'\b'
                if re.search(kw_regex, desc_lower):
                    return cat, clean_name

        # 5. Outflow Transfer fallback (TRF / TRANSFER / NIP / ONEBANK to someone)
        if amount < 0:
            if any(w in raw_desc_upper for w in ['TRF', 'TRANSFER', 'NIP', 'ONEBANK', 'TO', 'OUTFLOW', 'DEBIT', 'POS', 'WEB', 'PAYMENT']):
                transfers_cat = cls._find_category_by_name('Transfers & P2P', categories) or cls._find_category_by_name('Shopping', categories)
                if transfers_cat:
                    return transfers_cat, clean_name or "Transfer Out"

        # 6. Ultimate fallback to 'Other' or first available category
        fallback = cls._find_category_by_name('Other', categories)
        return fallback, clean_name

    @staticmethod
    def _find_category_by_name(name: str, categories: Dict[str, Category]) -> Optional[Category]:
        """Flexible matching of category name against available categories dictionary."""
        if not categories:
            return None

        name_clean = name.lower().replace('&', 'and').strip()

        # 1. Exact match
        if name.lower() in categories:
            return categories[name.lower()]

        # 2. Normalized 'and' vs '&'
        for k, cat in categories.items():
            k_clean = k.lower().replace('&', 'and').strip()
            if name_clean == k_clean:
                return cat

        # 3. Substring match
        for k, cat in categories.items():
            k_clean = k.lower().replace('&', 'and').strip()
            if name_clean in k_clean or k_clean in name_clean:
                return cat

        # 4. First word match (e.g. 'food' in 'Food & Dining', 'bank' in 'Bank Charges', 'health' in 'Healthcare')
        first_word = name_clean.split()[0] if name_clean else ''
        if len(first_word) >= 3:
            for k, cat in categories.items():
                if first_word in k.lower():
                    return cat

        return None
