"""
Language Model Handler - Mistral 7B
Supports both Ollama (recommended) and Transformers deployment
"""

import os
import json

# Choose deployment method
USE_OLLAMA = os.getenv("USE_OLLAMA", "true").lower() == "true"

if USE_OLLAMA:
    import requests
    
    class LanguageModel:
        def __init__(self):
            self.url = "http://localhost:11434/api/generate"
            self.model = os.getenv("LLM_MODEL", "mistral")
            print(f"🤖 LLM: Ollama/{self.model} (Optimized llama.cpp)")
        
        def generate(self, prompt: str, max_tokens: int = 512) -> str:
            """Generate response using Ollama"""
            try:
                response = requests.post(
                    self.url,
                    json={
                        "model": self.model,
                        "prompt": prompt,
                        "stream": False,
                        "options": {
                            "temperature": float(os.getenv("LLM_TEMPERATURE", "0.3")),
                            "num_predict": max_tokens
                        }
                    },
                    timeout=60
                )
                
                if response.status_code == 200:
                    result = response.json()
                    return result.get("response", "")
                else:
                    print(f"❌ Ollama error: {response.status_code}")
                    return self._fallback_response()
            
            except Exception as e:
                print(f"❌ LLM generation error: {e}")
                return self._fallback_response()
        
        def _fallback_response(self) -> str:
            """Fallback response if LLM fails"""
            return json.dumps({
                "immediate_response": "I'm having trouble processing your request. Could you please rephrase that?",
                "intent": "general_inquiry",
                "entities": {},
                "needs_clarification": True,
                "actions": []
            })

else:
    from transformers import AutoTokenizer, AutoModelForCausalLM
    import torch
    
    class LanguageModel:
        def __init__(self):
            model_name = os.getenv("LLM_MODEL", "mistralai/Mistral-7B-Instruct-v0.2")
            print(f"🔄 Loading {model_name} with Transformers...")
            
            self.tokenizer = AutoTokenizer.from_pretrained(model_name)
            self.model = AutoModelForCausalLM.from_pretrained(
                model_name,
                torch_dtype=torch.float16,
                device_map="auto",
                low_cpu_mem_usage=True
            )
            
            print(f"✅ Model loaded on {self.model.device}")
            print(f"🤖 LLM: Transformers/{model_name}")
        
        def generate(self, prompt: str, max_tokens: int = 512) -> str:
            """Generate response using Transformers"""
            try:
                inputs = self.tokenizer(prompt, return_tensors="pt").to(self.model.device)
                
                with torch.no_grad():
                    outputs = self.model.generate(
                        **inputs,
                        max_new_tokens=max_tokens,
                        temperature=float(os.getenv("LLM_TEMPERATURE", "0.7")),
                        do_sample=True,
                        top_p=0.9,
                        pad_token_id=self.tokenizer.eos_token_id
                    )
                
                response = self.tokenizer.decode(outputs[0], skip_special_tokens=True)
                
                # Extract only the generated part (after prompt)
                generated_text = response[len(prompt):].strip()
                
                return generated_text
            
            except Exception as e:
                print(f"❌ LLM generation error: {e}")
                return self._fallback_response()
        
        def _fallback_response(self) -> str:
            """Fallback response if LLM fails"""
            return json.dumps({
                "immediate_response": "I'm having trouble processing your request. Could you please rephrase that?",
                "intent": "general_inquiry",
                "entities": {},
                "needs_clarification": True,
                "actions": []
            })

# Create singleton instance
llm = LanguageModel()