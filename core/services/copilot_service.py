"""
Copilot Service for Bank Statement Analyzer.

Provides an AI-powered financial assistant using Groq's Llama 3.1 inference.
Implements a dual-engine approach: exact Django ORM queries for arithmetic
and vector similarity search for fuzzy/semantic lookups.
"""
import json
import logging
from datetime import date, timedelta
from decimal import Decimal
from typing import List, Dict, Any, Optional

from django.conf import settings
from django.db.models import Sum, Count, Avg, Q
from django.db.models.functions import TruncMonth

from ..models import Transaction, Category, UploadedFile
from .vector_store import VectorStoreService

logger = logging.getLogger('bankstatements')


# Tool definitions for Groq function calling
FINANCIAL_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_spending_summary",
            "description": (
                "Get exact spending/income totals from the user's bank transactions. "
                "Use this for ANY question involving sums, totals, averages, counts, "
                "or comparisons of monetary amounts. Returns precise database-computed values."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "start_date": {
                        "type": ["string", "null"],
                        "description": "Start date filter in YYYY-MM-DD format, or null for all time.",
                    },
                    "end_date": {
                        "type": ["string", "null"],
                        "description": "End date filter in YYYY-MM-DD format, or null for all time.",
                    },
                    "category_name": {
                        "type": ["string", "null"],
                        "description": "Filter by category name (e.g. 'Food & Dining', 'Transportation', 'Utilities'), or null for all categories.",
                    },
                    "transaction_type": {
                        "type": ["string", "null"],
                        "enum": ["debit", "credit", "all", None],
                        "description": "Filter by transaction direction: 'debit' for expenses, 'credit' for income, 'all' for both.",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_transactions",
            "description": (
                "Search for specific transactions by semantic meaning or list recent transactions. "
                "Use this to find transactions matching a description, merchant, "
                "or activity (e.g. 'Uber rides', 'grocery shopping', 'salary payments', "
                "'that large transfer in December'). Returns individual matching transactions."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": ["string", "null"],
                        "description": "Natural language search query describing the transactions to find, or null/empty to list recent transactions.",
                    },
                    "top_k": {
                        "type": ["integer", "null"],
                        "description": "Number of results to return (default 5, max 20).",
                    },
                    "start_date": {
                        "type": ["string", "null"],
                        "description": "Optional start date filter in YYYY-MM-DD format, or null.",
                    },
                    "end_date": {
                        "type": ["string", "null"],
                        "description": "Optional end date filter in YYYY-MM-DD format, or null.",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_category_breakdown",
            "description": (
                "Get a breakdown of spending/income grouped by category. "
                "Use this when the user wants to see where their money goes, "
                "compare categories, or get a spending distribution overview."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "start_date": {
                        "type": ["string", "null"],
                        "description": "Start date filter in YYYY-MM-DD format, or null for all time.",
                    },
                    "end_date": {
                        "type": ["string", "null"],
                        "description": "End date filter in YYYY-MM-DD format, or null for all time.",
                    },
                    "transaction_type": {
                        "type": ["string", "null"],
                        "enum": ["debit", "credit", "all", None],
                        "description": "Filter by direction. Default is 'debit' (expenses).",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_monthly_trends",
            "description": (
                "Get month-by-month totals for income and expenses. "
                "Use this when the user asks about trends over time, "
                "monthly comparisons, or spending patterns."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "num_months": {
                        "type": ["integer", "null"],
                        "description": "Number of recent months to include (default 6).",
                    },
                },
                "required": [],
            },
        },
    },
]


SYSTEM_PROMPT = """You are a smart, friendly Nigerian financial assistant embedded in the Bank Statement Analyzer app. Your role is to help users understand their bank statement data by answering questions about their transactions, spending patterns, and financial habits.

IMPORTANT RULES:
1. Always use the provided tools to get real data. NEVER make up numbers or transactions.
2. For any question involving totals, sums, averages, or counts → use get_spending_summary or get_category_breakdown.
3. For questions about specific transactions or merchants → use search_transactions.
4. For trend/pattern questions → use get_monthly_trends.
5. Format currency as ₦ (Naira) with commas (e.g., ₦1,234,567.89).
6. Be concise but informative. Use bullet points and tables for clarity.
7. When citing specific transactions, mention the date, description, and amount.
8. If the data is insufficient or empty, say so honestly instead of guessing.
9. Do NOT provide financial advice or recommend investments. Stick to analyzing the data.
10. If the user's question is ambiguous, interpret it reasonably and state your interpretation."""


class CopilotService:
    """
    AI Financial Copilot powered by Groq's Llama 3.1 / GPT-OSS models.

    Combines exact database queries (for math) with semantic vector search
    (for fuzzy merchant/memo lookups) via LLM tool calling.

    Usage:
        copilot = CopilotService(user)
        response = copilot.chat("How much did I spend on food last month?")
    """

    def __init__(self, user):
        self.user = user
        self.vector_store = VectorStoreService(user)
        self._client = None

    @property
    def client(self):
        """Lazy-load the Groq client."""
        if self._client is None:
            if not settings.GROQ_API_KEY:
                raise ValueError(
                    "GROQ_API_KEY is not configured. "
                    "Add it to your .env file: GROQ_API_KEY=your_key_here"
                )
            from groq import Groq
            self._client = Groq(api_key=settings.GROQ_API_KEY)
        return self._client

    # ------------------------------------------------------------------
    # LLM Execution with Fallback & Budget Optimization
    # ------------------------------------------------------------------

    def _prune_messages_for_budget(self, messages: List[Any], max_chars: int = 12000) -> List[Any]:
        """
        Ensure total payload characters do not exceed model TPM / context budget.
        Trims intermediate tool result payloads if they are excessively large.
        """
        total_len = 0
        for m in messages:
            if isinstance(m, dict):
                total_len += len(str(m.get("content", "")))
            elif hasattr(m, "content") and m.content:
                total_len += len(str(m.content))

        if total_len <= max_chars:
            return messages

        pruned = []
        for m in messages:
            if isinstance(m, dict) and m.get("role") == "tool":
                content = str(m.get("content", ""))
                if len(content) > 1000:
                    pruned.append({
                        **m,
                        "content": content[:1000] + "... [trimmed for token budget]"
                    })
                else:
                    pruned.append(m)
            else:
                pruned.append(m)
        return pruned

    def _call_llm_with_fallback(
        self,
        messages: List[Any],
        tools: Optional[List[Dict]] = None,
        max_tokens: int = 1024,
        temperature: float = 0.3,
    ):
        """
        Executes a chat completion call with automatic model cascade fallback
        and rate limit / token limit handling.
        """
        primary_model = getattr(settings, 'COPILOT_LLM_MODEL', 'openai/gpt-oss-120b')
        fallback_model = getattr(settings, 'COPILOT_FALLBACK_MODEL', 'openai/gpt-oss-20b')

        candidates = [primary_model, fallback_model, 'openai/gpt-oss-20b', 'qwen/qwen3.8-27b']
        models_to_try = []
        for m in candidates:
            if m and m not in models_to_try:
                models_to_try.append(m)

        last_error = None
        current_messages = self._prune_messages_for_budget(messages)

        for idx, model_name in enumerate(models_to_try):
            try:
                call_kwargs = {
                    "model": model_name,
                    "messages": current_messages,
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                }
                if tools:
                    call_kwargs["tools"] = tools
                    call_kwargs["tool_choice"] = "auto"

                return self.client.chat.completions.create(**call_kwargs)

            except Exception as e:
                err_str = str(e).lower()
                last_error = e
                logger.warning(
                    f"Copilot model '{model_name}' failed with: {e}. "
                    f"Attempting fallback ({idx + 1}/{len(models_to_try)})..."
                )

                if "429" in err_str or "rate_limit" in err_str:
                    time.sleep(1.2)

                if "413" in err_str or "too large" in err_str or "rate_limit" in err_str:
                    current_messages = self._prune_messages_for_budget(messages, max_chars=7500)

        raise last_error

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def chat(
        self,
        user_message: str,
        chat_history: Optional[List[Dict[str, str]]] = None,
    ) -> Dict[str, Any]:
        """
        Process a user message and return an AI-generated response.

        Supports multi-turn tool calling (e.g. model calling multiple tools
        sequentially to synthesize complex multi-part insights).

        Args:
            user_message: The user's question or request.
            chat_history: Previous conversation messages for context.

        Returns:
            Dict with keys: answer, sources, tool_calls_made.
        """
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]

        # Add conversation history (limited to prevent token overflow)
        if chat_history:
            messages.extend(chat_history[-settings.COPILOT_MAX_HISTORY:])

        messages.append({"role": "user", "content": user_message})

        tool_calls_made = []
        sources = []
        max_turns = 4
        turn = 0
        answer = None

        try:
            while turn < max_turns:
                turn += 1

                # Call LLM with tool capabilities enabled and fallback cascade
                response = self._call_llm_with_fallback(
                    messages=messages,
                    tools=FINANCIAL_TOOLS,
                    max_tokens=1024,
                    temperature=0.3,
                )

                response_message = response.choices[0].message

                # If no tool calls were requested, we have our final text answer!
                if not response_message.tool_calls:
                    answer = response_message.content
                    break

                # The model requested one or more tool calls
                messages.append(response_message)

                for tool_call in response_message.tool_calls:
                    fn_name = tool_call.function.name
                    try:
                        fn_args = json.loads(tool_call.function.arguments) if tool_call.function.arguments else {}
                    except Exception:
                        fn_args = {}

                    logger.info(
                        f"Copilot tool call (turn {turn}): {fn_name}({fn_args}) "
                        f"for user {self.user.id}"
                    )

                    # Execute the tool
                    result = self._execute_tool(fn_name, fn_args)
                    tool_calls_made.append({
                        "tool": fn_name,
                        "args": fn_args,
                    })

                    # Track sources from search results
                    if fn_name == "search_transactions" and isinstance(result, list):
                        sources.extend(result)

                    # Add tool result to message history
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": json.dumps(result, default=str),
                    })
            else:
                # If loop ended after max_turns, request a final summary
                final_response = self._call_llm_with_fallback(
                    messages=messages,
                    max_tokens=1024,
                    temperature=0.3,
                )
                answer = final_response.choices[0].message.content

            return {
                "answer": answer or "I couldn't generate a response. Please try again with a specific question.",
                "sources": sources,
                "tool_calls_made": tool_calls_made,
            }

        except Exception as e:
            err_str = str(e).lower()
            logger.error(f"Copilot error for user {self.user.id}: {e}")
            if "rate_limit" in err_str or "429" in err_str or "413" in err_str or "too large" in err_str:
                user_msg = (
                    "⚠️ The AI processing quota was exceeded for this minute on the on-demand service tier. "
                    "Please wait a few seconds and try again, or ask a more specific question."
                )
            else:
                user_msg = f"Sorry, I encountered an error: {str(e)}. Please check that your GROQ_API_KEY is configured correctly."

            return {
                "answer": user_msg,
                "sources": [],
                "tool_calls_made": tool_calls_made,
            }

    def generate_dashboard_ai_summary(
        self,
        date_filter: str = 'all',
        force_refresh: bool = False,
    ) -> Dict[str, Any]:
        """
        Generate a structured AI executive summary, main concerns, and financial improvement
        tips tailored to the user's uploaded statement data.
        """
        from django.core.cache import cache
        from .analytics_service import AnalyticsService

        cache_key = f"dashboard_ai_summary_user_{self.user.id}_{date_filter}"
        if not force_refresh:
            cached = cache.get(cache_key)
            if cached:
                return cached

        # Fetch calculated analytics metrics
        analytics = AnalyticsService(self.user)
        data = analytics.get_dashboard_data(date_filter=date_filter)

        stats = data['stats']
        insights = data['insights']
        top_cats = data.get('categories', [])[:4]
        top_merchants = data.get('top_merchants', [])[:4]
        total_txns = stats.get('transaction_count', 0)

        if total_txns == 0:
            return {
                "available": False,
                "message": "No transactions found for this time period. Upload a bank statement to generate AI financial insights.",
            }

        # Build financial snapshot context for prompt
        cat_lines = [
            f"- {c.get('category__name') or c.get('name') or 'Uncategorized'}: ₦{float(c['total']):,.2f} ({c.get('percentage', 0)}%)"
            for c in top_cats
        ]
        merchant_lines = [
            f"- {m.get('name', 'Payee')}: ₦{float(m['total']):,.2f}"
            for m in top_merchants
        ]

        prompt_context = f"""
Financial Data Snapshot:
- Date Filter Period: {date_filter}
- Total Transactions: {total_txns}
- Total Income: ₦{float(stats['total_income']):,.2f}
- Total Expenses: ₦{float(stats['total_spent']):,.2f}
- Net Cash Flow: ₦{float(stats['net_flow']):,.2f}
- Net Savings Rate: {insights.get('savings_rate', 0)}%
- Computed Health Status: {insights.get('health_status', 'Moderate')}
- Daily Burn Rate: ₦{float(insights.get('daily_burn_rate', 0)):,.2f}
- Total Bank Charges & Levies: ₦{float(stats.get('bank_charges_total', 0)):,.2f}

Top Spending Categories:
{chr(10).join(cat_lines) if cat_lines else "None recorded"}

Top Payees / Merchants:
{chr(10).join(merchant_lines) if merchant_lines else "None recorded"}
"""

        system_instruction = """You are a senior Nigerian personal finance analyst. Analyze the user's financial snapshot and provide an executive summary, top vulnerability/risk flags, and high-impact strategic improvement tips in strict JSON.

JSON Schema format:
{
  "summary": "2-3 concise sentences summarizing income vs spending, savings rate, and overall cash trajectory.",
  "concerns": [
    {
      "title": "Short title (e.g. Bank Fee Drain, High Food Concentration)",
      "detail": "1 sentence explanation citing the actual number from data.",
      "severity": "high" or "medium" or "low"
    }
  ],
  "tips": [
    {
      "title": "Actionable recommendation title",
      "detail": "1-2 practical sentences tailored to Nigerian context.",
      "potential_impact": "Estimated impact or benefit"
    }
  ]
}

Provide 2-3 concerns and 2-3 tips. Do NOT include markdown code blocks or commentary, output ONLY the raw JSON."""

        try:
            response = self._call_llm_with_fallback(
                messages=[
                    {"role": "system", "content": system_instruction},
                    {"role": "user", "content": prompt_context}
                ],
                max_tokens=1000,
                temperature=0.2,
            )
            raw_content = response.choices[0].message.content.strip()
            # Clean up if markdown code fence is present
            if raw_content.startswith("```json"):
                raw_content = raw_content[7:]
            if raw_content.startswith("```"):
                raw_content = raw_content[3:]
            if raw_content.endswith("```"):
                raw_content = raw_content[:-3]

            parsed_data = json.loads(raw_content.strip())
            parsed_data["available"] = True
            parsed_data["date_filter"] = date_filter

            # Cache for 1 hour
            cache.set(cache_key, parsed_data, timeout=3600)
            return parsed_data

        except Exception as e:
            logger.error(f"Error generating dashboard AI summary: {e}")
            fallback = self._generate_fallback_summary(stats, insights, top_cats, date_filter)
            fallback["available"] = True
            return fallback

    def _generate_fallback_summary(self, stats, insights, top_cats, date_filter) -> Dict[str, Any]:
        """Deterministic fallback summary if LLM call is unavailable."""
        income = stats.get('total_income', Decimal('0'))
        spent = stats.get('total_spent', Decimal('0'))
        net_flow = stats.get('net_flow', Decimal('0'))
        savings_rate = insights.get('savings_rate', 0.0)

        concerns = []
        tips = []

        if net_flow < 0:
            concerns.append({
                "title": "Negative Cash Flow",
                "detail": f"Outflows exceed inflows by ₦{abs(float(net_flow)):,.2f}.",
                "severity": "high"
            })
            tips.append({
                "title": "Expense Audit",
                "detail": "Review your top discretionary spending categories and limit non-essential transfers.",
                "potential_impact": "Restore positive net cash flow"
            })

        bank_fees = float(stats.get('bank_charges_total', 0))
        if bank_fees > 1000:
            concerns.append({
                "title": "Accumulating Bank Fees",
                "detail": f"₦{bank_fees:,.2f} was spent on SMS, stamp duty, and transfer levies.",
                "severity": "medium"
            })
            tips.append({
                "title": "Consolidate Transactions",
                "detail": "Batch small daily transfers to minimize the ₦50 EMTL levy and multiple session charges.",
                "potential_impact": "Save up to ₦3,000 monthly on levies"
            })

        if top_cats and len(top_cats) > 0:
            top_cat_name = top_cats[0].get('category__name') or top_cats[0].get('name') or 'Top Category'
            top_cat_pct = top_cats[0].get('percentage', 0)
            if top_cat_pct > 40:
                concerns.append({
                    "title": f"High {top_cat_name} Concentration",
                    "detail": f"{top_cat_name} accounts for {top_cat_pct}% of total expenses.",
                    "severity": "medium"
                })

        if not tips:
            tips.append({
                "title": "Automate Savings",
                "detail": "Aim to set aside at least 15-20% of income right after inflow into a locked high-yield savings account.",
                "potential_impact": "Grow emergency reserve"
            })

        grade = "A" if savings_rate >= 20 else ("B" if savings_rate >= 10 else ("C" if savings_rate >= 0 else "D"))

        return {
            "summary": f"Your total income was ₦{float(income):,.2f} against expenses of ₦{float(spent):,.2f}, resulting in a net position of ₦{float(net_flow):,.2f} with a {savings_rate}% savings rate.",
            "health_grade": grade,
            "health_label": insights.get('health_status', 'Moderate'),
            "concerns": concerns,
            "tips": tips,
            "date_filter": date_filter,
        }

    # ------------------------------------------------------------------
    # Tool execution
    # ------------------------------------------------------------------

    def _execute_tool(self, fn_name: str, fn_args: Dict) -> Any:
        """Route tool calls to the appropriate handler with robust name cleaning and argument filtering."""
        # Sanitize LLM function name artifacts (e.g. 'search_transactions<|channel|>commentary')
        clean_name = (fn_name or "").split("<")[0].split("|")[0].strip()

        handlers = {
            "get_spending_summary": self._tool_spending_summary,
            "search_transactions": self._tool_search_transactions,
            "get_category_breakdown": self._tool_category_breakdown,
            "get_monthly_trends": self._tool_monthly_trends,
        }

        handler = handlers.get(clean_name)
        if not handler:
            return {"error": f"Unknown tool: {clean_name}"}

        try:
            return handler(**fn_args)
        except Exception as e:
            logger.error(f"Tool {clean_name} error: {e}")
            return {"error": str(e)}

    def _get_base_queryset(self) -> 'QuerySet':
        """Get the user-scoped transaction queryset."""
        return Transaction.objects.filter(
            uploaded_file__user=self.user
        ).select_related('category')

    def _apply_date_filters(self, qs, start_date=None, end_date=None):
        """Apply optional date range filters."""
        if start_date:
            qs = qs.filter(date__gte=start_date)
        if end_date:
            qs = qs.filter(date__lte=end_date)
        return qs

    def _tool_spending_summary(
        self,
        start_date=None,
        end_date=None,
        category_name=None,
        transaction_type="all",
        **kwargs,
    ) -> Dict:
        """Execute get_spending_summary tool."""
        qs = self._get_base_queryset()
        qs = self._apply_date_filters(qs, start_date, end_date)

        if category_name:
            qs = qs.filter(
                Q(category__name__icontains=category_name)
            )

        if transaction_type == "debit":
            qs = qs.filter(amount__lt=0)
        elif transaction_type == "credit":
            qs = qs.filter(amount__gt=0)

        agg = qs.aggregate(
            total=Sum('amount'),
            count=Count('id'),
            average=Avg('amount'),
        )

        # Also get the top 5 largest transactions in this filter
        top_transactions = list(
            qs.order_by('amount' if transaction_type == 'debit' else '-amount')[:5]
            .values('date', 'description', 'amount', 'category__name')
        )

        return {
            "total": str(agg['total'] or Decimal('0')),
            "count": agg['count'],
            "average": str(agg['average'] or Decimal('0')),
            "filters_applied": {
                "start_date": start_date,
                "end_date": end_date,
                "category": category_name,
                "type": transaction_type,
            },
            "top_transactions": [
                {
                    "date": str(t['date']),
                    "description": t['description'][:60],
                    "amount": str(t['amount']),
                    "category": t['category__name'] or "Uncategorized",
                }
                for t in top_transactions
            ],
        }

    def _tool_search_transactions(
        self,
        query="",
        top_k=5,
        start_date=None,
        end_date=None,
        transaction_type=None,
        **kwargs,
    ) -> List[Dict]:
        """Execute search_transactions tool via vector store with token-compact payloads."""
        if top_k is None:
            top_k = 5
        else:
            try:
                top_k = min(max(1, int(top_k)), 10)
            except Exception:
                top_k = 5

        query_str = (query or "").strip()

        # If query is empty, return recent transactions from database
        if not query_str:
            qs = self._get_base_queryset()
            qs = self._apply_date_filters(qs, start_date, end_date)
            if transaction_type == "debit":
                qs = qs.filter(amount__lt=0)
            elif transaction_type == "credit":
                qs = qs.filter(amount__gt=0)

            results = [
                {
                    "date": str(t.date),
                    "description": t.description[:70],
                    "amount": str(t.amount),
                    "category": t.category.name if t.category else "Uncategorized",
                }
                for t in qs[:top_k]
            ]
            return results

        raw_results = self.vector_store.search(
            query=query_str,
            top_k=top_k,
            date_from=start_date,
            date_to=end_date,
        )

        # If vector store is empty or returned no hits, fall back to ORM text search
        if not raw_results:
            qs = self._get_base_queryset()
            qs = self._apply_date_filters(qs, start_date, end_date)
            if transaction_type == "debit":
                qs = qs.filter(amount__lt=0)
            elif transaction_type == "credit":
                qs = qs.filter(amount__gt=0)

            qs = qs.filter(description__icontains=query_str)[:top_k]

            results = [
                {
                    "date": str(t.date),
                    "description": t.description[:70],
                    "amount": str(t.amount),
                    "category": t.category.name if t.category else "Uncategorized",
                }
                for t in qs
            ]
            return results

        return [
            {
                "date": str(r.get("date", "")),
                "description": (r.get("description") or "")[:70],
                "amount": str(r.get("amount", "")),
                "category": r.get("category", "Uncategorized"),
            }
            for r in raw_results[:top_k]
        ]

    def _tool_category_breakdown(
        self,
        start_date=None,
        end_date=None,
        transaction_type="debit",
        **kwargs,
    ) -> Dict:
        """Execute get_category_breakdown tool."""
        qs = self._get_base_queryset()
        qs = self._apply_date_filters(qs, start_date, end_date)

        if transaction_type == "debit":
            qs = qs.filter(amount__lt=0)
        elif transaction_type == "credit":
            qs = qs.filter(amount__gt=0)

        breakdown = list(
            qs.values('category__name')
            .annotate(
                total=Sum('amount'),
                count=Count('id'),
            )
            .order_by('total')  # Most negative (biggest expense) first
        )

        return {
            "categories": [
                {
                    "category": item['category__name'] or "Uncategorized",
                    "total": str(item['total']),
                    "count": item['count'],
                }
                for item in breakdown
            ],
            "filters_applied": {
                "start_date": start_date,
                "end_date": end_date,
                "type": transaction_type,
            },
        }

    def _tool_monthly_trends(self, num_months=6, **kwargs) -> Dict:
        """Execute get_monthly_trends tool."""
        num_months = min(int(num_months), 24)

        qs = self._get_base_queryset()

        monthly = list(
            qs.annotate(month=TruncMonth('date'))
            .values('month')
            .annotate(
                income=Sum('amount', filter=Q(amount__gt=0)),
                expenses=Sum('amount', filter=Q(amount__lt=0)),
                count=Count('id'),
            )
            .order_by('-month')[:num_months]
        )

        return {
            "months": [
                {
                    "month": str(item['month'].strftime('%Y-%m') if item['month'] else 'Unknown'),
                    "income": str(item['income'] or Decimal('0')),
                    "expenses": str(item['expenses'] or Decimal('0')),
                    "transaction_count": item['count'],
                }
                for item in reversed(monthly)
            ],
        }
