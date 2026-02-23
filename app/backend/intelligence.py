import spacy
from typing import List, Dict, Optional, Any
import os
from openai import AsyncOpenAI
import google.generativeai as genai
import json
import aiohttp
from abc import ABC, abstractmethod
from anthropic import AsyncAnthropic

# Load Spacy model once
try:
    nlp = spacy.load("en_core_web_sm")
except OSError:
    # Fallback or re-raise with instruction
    print("Warning: Spacy model 'en_core_web_sm' not found. Local intelligence will be limited.")
    nlp = None

class LocalIntelligence:
    def __init__(self):
        self.nlp = nlp

    def extract_entities(self, text: str) -> Dict[str, List[str]]:
        if not self.nlp: return {"PERSON": [], "ORG": [], "GPE": [], "TITLE": []}

        doc = self.nlp(text)
        entities = {
            "PERSON": [],
            "ORG": [],
            "GPE": [],
            "TITLE": []
        }

        for ent in doc.ents:
            if ent.label_ in entities:
                if ent.text not in entities[ent.label_]:
                    entities[ent.label_].append(ent.text)
        return entities

    def analyze_relevance_local(self, context: str, keywords: List[str]) -> Dict[str, Any]:
        if not self.nlp:
            # Fallback simple string matching if nlp failed to load
            score = 0
            matches = []
            lower_ctx = context.lower()
            for kw in keywords:
                if kw.lower() in lower_ctx:
                    matches.append({"keyword": kw, "match_type": "direct", "context": "..."})
                    score += 30
            return {"score": min(score, 70), "matches": matches, "method": "local_simple"}

        doc = self.nlp(context.lower())
        found_matches = []
        score = 0

        context_lower = context.lower()
        for kw in keywords:
            kw_lower = kw.lower()
            if kw_lower in context_lower:
                found_matches.append({"keyword": kw, "match_type": "direct", "context": "..."})
                score += 30
            else:
                kw_doc = self.nlp(kw_lower)
                kw_lemma = " ".join([token.lemma_ for token in kw_doc])
                context_lemma = " ".join([token.lemma_ for token in doc])
                if kw_lemma in context_lemma:
                     found_matches.append({"keyword": kw, "match_type": "lemma", "context": "..."})
                     score += 20

        final_score = min(score, 70)
        return {
            "score": final_score,
            "matches": found_matches,
            "method": "local_nlp"
        }

class BaseRemoteProvider(ABC):
    def __init__(self, api_key: str = None):
        self.api_key = api_key

    @abstractmethod
    async def analyze(self, context: str, keywords: List[str], person_name: str = None) -> Optional[Dict[str, Any]]:
        pass

    def _build_prompt(self, context: str, keywords: List[str], person_name: str = None) -> str:
        return f"""
        Analyze the following text snippet to determine if the email associated with it is a relevant lead.

        Context: "{context}"
        Keywords to match: {json.dumps(keywords)}
        Person Name (if known): {person_name or "Unknown"}

        Task:
        1. Determine if the person mentioned matches the keywords semantically (e.g. "CTO" matches "engineering").
        2. Assign a relevance score (0-100).
        3. Extract the person's Job Title if present.
        4. Extract the Company Name if present.

        Return JSON only:
        {{
            "relevance_score": <int>,
            "job_title": <string or null>,
            "company_name": <string or null>,
            "semantic_matches": [<list of strings matching keywords>],
            "reasoning": <short string>
        }}
        """

class OpenAIProvider(BaseRemoteProvider):
    def __init__(self, api_key: str):
        super().__init__(api_key)
        self.client = AsyncOpenAI(api_key=api_key)

    async def analyze(self, context: str, keywords: List[str], person_name: str = None) -> Optional[Dict[str, Any]]:
        prompt = self._build_prompt(context, keywords, person_name)
        try:
            response = await self.client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "You are a lead qualification expert. Output JSON only."},
                    {"role": "user", "content": prompt}
                ],
                response_format={ "type": "json_object" }
            )
            content = response.choices[0].message.content
            return json.loads(content)
        except Exception as e:
            print(f"OpenAI Error: {e}")
            return None

class GeminiProvider(BaseRemoteProvider):
    def __init__(self, api_key: str):
        super().__init__(api_key)
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel('gemini-1.5-flash')

    async def analyze(self, context: str, keywords: List[str], person_name: str = None) -> Optional[Dict[str, Any]]:
        prompt = self._build_prompt(context, keywords, person_name)
        try:
            response = await self.model.generate_content_async(
                f"You are a lead qualification expert. Output JSON only.\n\n{prompt}"
            )
            content = response.text
            # Strip markdown code blocks
            if content.startswith("```json"):
                content = content[7:]
            elif content.startswith("```"):
                content = content[3:]
            if content.endswith("```"):
                content = content[:-3]
            return json.loads(content.strip())
        except Exception as e:
            print(f"Gemini Error: {e}")
            return None

class AnthropicProvider(BaseRemoteProvider):
    def __init__(self, api_key: str):
        super().__init__(api_key)
        self.client = AsyncAnthropic(api_key=api_key)

    async def analyze(self, context: str, keywords: List[str], person_name: str = None) -> Optional[Dict[str, Any]]:
        prompt = self._build_prompt(context, keywords, person_name)
        try:
            message = await self.client.messages.create(
                model="claude-3-haiku-20240307",
                max_tokens=1024,
                system="You are a lead qualification expert. Output JSON only.",
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            content = message.content[0].text
            # Extract JSON from potential chatter
            start = content.find('{')
            end = content.rfind('}') + 1
            if start != -1 and end != -1:
                return json.loads(content[start:end])
            return json.loads(content)
        except Exception as e:
            print(f"Anthropic Error: {e}")
            return None

class OllamaProvider(BaseRemoteProvider):
    def __init__(self, api_key: str = None):
        super().__init__(api_key) # API key might not be needed but keeps interface consistent
        self.base_url = "http://localhost:11434/api/generate"

    async def analyze(self, context: str, keywords: List[str], person_name: str = None) -> Optional[Dict[str, Any]]:
        prompt = self._build_prompt(context, keywords, person_name)
        try:
            async with aiohttp.ClientSession() as session:
                payload = {
                    "model": "llama3", # Default to llama3, user needs it pulled
                    "prompt": f"You are a lead qualification expert. Output JSON only.\n{prompt}",
                    "format": "json",
                    "stream": False
                }
                async with session.post(self.base_url, json=payload) as response:
                    if response.status != 200:
                        print(f"Ollama Error: Status {response.status}")
                        return None
                    data = await response.json()
                    return json.loads(data.get("response", "{}"))
        except Exception as e:
            print(f"Ollama Error: {e}")
            return None

class RemoteIntelligence:
    def __init__(self, provider: str = "openai", api_key: str = None):
        self.provider_name = provider
        self.provider_instance: Optional[BaseRemoteProvider] = None

        if provider == "openai":
            if api_key: self.provider_instance = OpenAIProvider(api_key)
        elif provider == "gemini":
            if api_key: self.provider_instance = GeminiProvider(api_key)
        elif provider == "anthropic":
            if api_key: self.provider_instance = AnthropicProvider(api_key)
        elif provider == "ollama":
            self.provider_instance = OllamaProvider(api_key) # API key optional/unused

    async def analyze_relevance_semantic(self, context: str, keywords: List[str], person_name: str = None) -> Optional[Dict[str, Any]]:
        if not self.provider_instance:
            return None
        return await self.provider_instance.analyze(context, keywords, person_name)
