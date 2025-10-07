"""
Language Model Handler - Mistral 7B
Supports both local (Transformers) and Ollama deployment
"""

import os
import json
from typing import Optional

# Choose deployment method
USE_OLLAMA = os.getenv("USE_OLLAMA", "true").lower() == "true"

if USE_OLLAMA:
    import requests
    
    class LanguageModel:
        def __init__(self):
            self.url = "http://localhost:11434/api/generate"
            self.model = "mistral"
        
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
                            "temperature": 0.7,
                            "num_predict": max_tokens
                        }
                    },
                    timeout=30
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
                "immediate_response": "I'm having trouble processing that right now. Could you please try again?",
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
            model_name = "mistralai/Mistral-7B-Instruct-v0.2"
            print(f"🔄 Loading {model_name}...")
            
            self.tokenizer = AutoTokenizer.from_pretrained(model_name)
            self.model = AutoModelForCausalLM.from_pretrained(
                model_name,
                torch_dtype=torch.float16,
                device_map="auto",
                low_cpu_mem_usage=True
            )
            
            print(f"✅ Model loaded on {self.model.device}")
        
        def generate(self, prompt: str, max_tokens: int = 512) -> str:
            """Generate response using Transformers"""
            try:
                inputs = self.tokenizer(prompt, return_tensors="pt").to(self.model.device)
                
                with torch.no_grad():
                    outputs = self.model.generate(
                        **inputs,
                        max_new_tokens=max_tokens,
                        temperature=0.7,
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
                "immediate_response": "I'm having trouble processing that right now. Could you please try again?",
                "intent": "general_inquiry",
                "entities": {},
                "needs_clarification":True,
                "actions": []
            })