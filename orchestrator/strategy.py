import os
from enum import Enum
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

class Intent(Enum):
    CODING = "CODING"
    CHAT = "CHAT"
    RESEARCH = "RESEARCH"
    UNKNOWN = "UNKNOWN"

class Strategy:
    """
    The 'Judge' of the system. Decides which AI provider to use.
    Uses a lightweight model to classify intent.
    Reference: Neural-Home Infrastructure Blueprint v3.0 - Phase 3
    """
    
    def __init__(self):
        # Initialize Google GenAI for intent classification (Gemini Flash)
        self.api_key = os.getenv("GOOGLE_API_KEY")
        if self.api_key:
            genai.configure(api_key=self.api_key)
            self.model = genai.GenerativeModel('gemini-1.5-flash')
        else:
            print("Warning: GOOGLE_API_KEY not found. Intent classification will fallback to heuristics.")
            self.model = None

    def classify_intent(self, query):
        """
        Classifies the user query into CODING, CHAT, or RESEARCH.
        """
        if not self.model:
            # Fallback heuristics
            lower_query = query.lower()
            if any(k in lower_query for k in ['code', 'python', 'function', 'class', 'bug', 'error', 'fix']):
                return Intent.CODING
            return Intent.CHAT

        try:
            prompt = f"""
            Classify the following user query into exactly one of these categories: CODING, CHAT, RESEARCH.
            
            Query: "{query}"
            
            Category:
            """
            response = self.model.generate_content(prompt)
            text = response.text.strip().upper()
            
            if "CODING" in text: return Intent.CODING
            if "RESEARCH" in text: return Intent.RESEARCH
            if "CHAT" in text: return Intent.CHAT
            
            return Intent.CHAT # Default
            
        except Exception as e:
            print(f"Error during intent classification: {e}")
            return Intent.CHAT

    def decide_route(self, user_query, gpu_status_green):
        """
        Decides which provider to route the request to.
        Returns: (provider_name, model_name)
        """
        intent = self.classify_intent(user_query)
        print(f"Detected Intent: {intent.name}")
        
        if intent == Intent.CODING:
            if gpu_status_green:
                # Local GPU is free, use Ollama
                return "ollama", "qwen2.5-coder-32b"
            else:
                # GPU busy, offload to Cloud (Qwen via API or fallback)
                return "qwen", "qwen-turbo" # Hypothetical mapping
                
        elif intent == Intent.CHAT:
            # Chat is cheap, use Flash or Groq
            return "gemini", "gemini-1.5-flash"
            
        elif intent == Intent.RESEARCH:
             # Research might need more context or internet access
             return "gemini", "gemini-1.5-pro"
             
        # Default fallback
        return "gemini", "gemini-1.5-flash"
