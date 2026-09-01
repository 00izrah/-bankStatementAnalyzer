from openai import AsyncOpenAI
import os

client = AsyncOpenAI(
    api_key=os.environ.get("GROQ_API_KEY"),
    base_url="https://api.groq.com/openai/v1",
)

async def generate_answer(query: str, search_results: list[dict], chat_history: list[dict] = None):
    context_parts = []
    for i, res in enumerate(search_results):
        context_parts.append(
            f"--- SOURCE {i+1} [File: {res['source']}] ---\n"
            f"{res['text']}\n"
        )
    context_text = "\n".join(context_parts)

    system_message = (
        "You are an expert academic assistant. Answer the user's question using the provided context "
        "and the conversation history to understand context or pronouns like 'it'. "
        "Every time you mention a fact from a source, cite it at the end of the sentence using [Source X]. "
        "At the end of your answer, provide a 'References' list mapping Source X to the filename. "
        "If the answer is not in the context, say you don't know."
    )

    messages = [{"role": "system", "content": system_message}]

    if chat_history:
        messages.extend(chat_history)

    user_content = f"Context from PDFs:\n{context_text}\n\nQuestion: {query}"
    messages.append({"role": "user", "content": user_content})

    try:
        chat_completion = await client.chat.completions.create(
            messages=messages,
            model="llama-3.1-8b-instant",
        )
        return chat_completion.choices[0].message.content
    except Exception as e:
        return f"Error generating answer: {str(e)}"