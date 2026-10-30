import os
os.environ["GEMINI_API_KEY"] = "hack_f9e53e43bb0e7b872cd9b81de2b7d462b0daa604"
os.environ["XC_LLM_MODEL"] = "gemini/gemini-3.5-flash-lite"

from agents.llm import LLMWrapper

wrapper = LLMWrapper()
print(f"Model: {wrapper.model}")
print(f"Provider: {wrapper.provider}")
print(f"API model: {wrapper.api_model}")
print(f"Configured: {wrapper.is_configured()}")

if wrapper.is_configured():
    try:
        result = wrapper.complete("Say hello in one word", {"type": "object", "properties": {"greeting": {"type": "string"}}, "required": ["greeting"]})
        print(f"LIVE CALL SUCCESS: {result}")
    except Exception as exc:
        print(f"LIVE CALL FAILED: {type(exc).__name__}: {exc}")
else:
    print("Not configured: check GEMINI_API_KEY and model format")
