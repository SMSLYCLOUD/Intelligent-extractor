import spacy
from typing import List, Dict, Optional
import os
from openai import AsyncOpenAI
import json

# Load Spacy model once
try:
    nlp = spacy.load("en_core_web_sm")
except OSError:
    raise OSError("Spacy model 'en_core_web_sm' not found. Please run 'python -m spacy download en_core_web_sm' to install it.")

class LocalIntelligence:
    def __init__(self):
        self.nlp = nlp

    def extract_entities(self, text: str) -> Dict[str, List[str]]:
        doc = self.nlp(text)
        entities = {
            "PERSON": [],
            "ORG": [],
            "GPE": [], # Geopolitical entity (Location)
            "TITLE": [] # Job titles (heuristic)
        }

        for ent in doc.ents:
            if ent.label_ in entities:
                if ent.text not in entities[ent.label_]:
                    entities[ent.label_].append(ent.text)

        return entities

    def analyze_relevance_local(self, context: str, keywords: List[str]) -> Dict[str, any]:
        """
        Analyzes context against keywords using basic matching and lemma overlap.
        Returns a score and matched keywords.
        """
        doc = self.nlp(context.lower())
        found_matches = []
        score = 0

        # Simple keyword matching
        context_lower = context.lower()
        for kw in keywords:
            kw_lower = kw.lower()
            if kw_lower in context_lower:
                found_matches.append({"keyword": kw, "match_type": "direct", "context": "..."})
                score += 30 # Base score for direct match
            else:
                # Check for lemma match
                kw_doc = self.nlp(kw_lower)
                kw_lemma = " ".join([token.lemma_ for token in kw_doc])
                context_lemma = " ".join([token.lemma_ for token in doc])
                if kw_lemma in context_lemma:
                     found_matches.append({"keyword": kw, "match_type": "lemma", "context": "..."})
                     score += 20

        # Cap local score contribution to avoid overconfidence without semantic understanding
        final_score = min(score, 70)

        return {
            "score": final_score,
            "matches": found_matches,
            "method": "local_nlp"
        }

class RemoteIntelligence:
    def __init__(self, api_key: str):
        self.client = None
        if api_key:
            self.client = AsyncOpenAI(api_key=api_key)

    async def analyze_relevance_semantic(self, context: str, keywords: List[str], person_name: str = None) -> Dict[str, any]:
        """
        Uses OpenAI to analyze the semantic relevance of the context.
        """
        if not self.client:
            return None

        prompt = f"""
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

        try:
            response = await self.client.chat.completions.create(
                model="gpt-3.5-turbo", # Use a cost-effective model
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
