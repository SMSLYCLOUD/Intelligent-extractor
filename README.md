# Intelligent Lead Extractor AI System

An advanced AI-powered lead extraction specialist. This system intelligently discovers, validates, and scores email leads from websites based on provided keywords with maximum accuracy and efficiency.

## Features

-   **Intelligent Extraction**: Uses regex and Context-Aware analysis to find explicit and obfuscated emails.
-   **Hybrid Intelligence**:
    -   **Local**: Spacy NLP for entity recognition (Person, Org) and keyword matching.
    -   **Remote**: OpenAI integration for deep semantic relevance scoring (requires API key).
-   **Validation**: DNS/MX record verification to ensure email deliverability.
-   **Smart Crawling**: Prioritizes pages like "Team", "About", "Contact" and handles depth limits.
-   **Frontend Dashboard**: Clean, responsive UI to run extractions and view detailed results.

## Requirements

-   Python 3.9+
-   An OpenAI API Key (optional, but recommended for high-quality semantic analysis)

## Installation

1.  Clone the repository.
2.  Install dependencies:
    ```bash
    pip install -r requirements.txt
    ```
3.  Install the local NLP model:
    ```bash
    python -m spacy download en_core_web_sm
    ```

## Configuration

1.  Copy `.env.example` to `.env`:
    ```bash
    cp .env.example .env
    ```
2.  Edit `.env` to set your defaults (optional):
    -   `OPENAI_API_KEY`: Your OpenAI key.
    -   `MAX_DEPTH`: Default crawling depth.
    -   `HOST`/`PORT`: Server configuration.

## Usage

1.  Start the application:
    ```bash
    python run.py
    ```
2.  Open your browser and navigate to `http://localhost:8000`.
3.  Enter the target Website URL and Keywords (e.g., "CTO, Marketing, Engineering").
4.  (Optional) Provide an OpenAI API Key in the UI if not set in `.env`.
5.  Click "Start Extraction".

## Architecture

-   **`run.py`**: Entry point script.
-   **`app/backend/`**:
    -   `main.py`: FastAPI application and endpoints.
    -   `crawler.py`: Async web crawler with priority logic.
    -   `extractor.py`: Core logic for finding emails and context.
    -   `intelligence.py`: Wrappers for Spacy (Local) and OpenAI (Remote).
    -   `validator.py`: Email syntax and DNS validation.
    -   `models.py`: Pydantic data models.
-   **`app/frontend/static/`**:
    -   `index.html`: Single-page application for the UI.

## Testing

Run the local extraction test to verify logic without crawling:

```bash
python test_extraction.py
```
