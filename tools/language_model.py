"""
Language Model Handler - Mistral 7B
Uses Ollama only (LangChain-compatible)
"""

import os
import json
from typing import Optional, List
import requests
from langchain.llms.base import LLM

# =============================
# Ollama LLM
# =============================
class OllamaLLM(LLM):
    model_name: str = "mistral"
    temperature: float = 0.3
    max_tokens: int = 512
    url: str = "http://localhost:11434/api/generate"

    def __init__(
        self,
        model_name: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs,
    ):
        # Pass values to Pydantic base class
        super().__init__(
            model_name=model_name or os.getenv("LLM_MODEL", "mistral"),
            temperature=temperature or float(os.getenv("LLM_TEMPERATURE", 0.3)),
            max_tokens=max_tokens or 512,
            **kwargs
        )
        print(f"🤖 LLM: Ollama/{self.model_name} (Optimized llama.cpp)")

    def _call(self, prompt: str, stop: Optional[List[str]] = None) -> str:
        """LangChain-compatible call"""
        try:
            payload = {
                "model": self.model_name,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": self.temperature,
                    "num_predict": self.max_tokens
                }
            }
            resp = requests.post(self.url, json=payload, timeout=60)
            if resp.status_code == 200:
                return resp.json().get("response", "")
            else:
                print(f"❌ Ollama error: {resp.status_code}")
                return self._fallback_response()
        except Exception as e:
            print(f"❌ LLM generation error: {e}")
            return self._fallback_response()

    def _fallback_response(self) -> str:
        return json.dumps({
            "immediate_response": "I'm having trouble processing your request. Could you please rephrase that?",
            "intent": "general_inquiry",
            "entities": {},
            "needs_clarification": True,
            "actions": []
        })

    @property
    def _llm_type(self) -> str:
        return "ollama"


# =============================
# Singleton LLM instance
# =============================
llm = OllamaLLM()
