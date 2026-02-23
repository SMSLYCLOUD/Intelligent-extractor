# Intelligent Lead Extractor AI System

An advanced AI-powered lead extraction specialist. This system intelligently discovers, validates, and scores email leads from websites based on provided keywords with maximum accuracy and efficiency.

## Features

-   **Intelligent Extraction**: Uses advanced regex and Context-Aware analysis to find explicit and obfuscated emails (e.g., `user [at] domain`).
-   **Hybrid Intelligence**:
    -   **Local**: Spacy NLP for entity recognition (Person, Org) and keyword matching.
    -   **Remote**: Supports OpenAI (GPT), Google Gemini, Anthropic (Claude), and Local LLMs (Ollama) for semantic relevance scoring.
-   **Advanced Crawling**:
    -   **Fast Mode**: High-speed HTTP crawling.
    -   **Deep Mode**: Browser-based crawling (Playwright) for JavaScript-heavy sites.
-   **Persistence**: Saves extraction jobs and leads to a local SQLite database for history tracking.
-   **Frontend Dashboard**: Modern UI with history view, CSV export, and real-time status updates.
-   **Validation**: DNS/MX record verification to ensure email deliverability.

## Requirements

-   Python 3.9+
-   API Keys (OpenAI, Gemini, Anthropic) optional but recommended.
-   Ollama (optional) for local LLM support.

## Installation

1.  Clone the repository.
2.  Install dependencies:
    ```bash
    pip install -r requirements.txt
    ```
3.  Install browser binaries for Playwright:
    ```bash
    playwright install
    ```
4.  Install the local NLP model:
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
    -   `GEMINI_API_KEY`: Your Google Gemini key.
    -   `ANTHROPIC_API_KEY`: Your Anthropic key.
    -   `MAX_DEPTH`: Default crawling depth.
    -   `HOST`/`PORT`: Server configuration.

## Usage

1.  Start the application:
    ```bash
    python run.py
    ```
2.  Open your browser and navigate to `http://localhost:8000`.
3.  Choose your **AI Provider** and enter API keys if needed.
4.  Select **Crawler Type** (Fast or Deep).
5.  Enter the target Website URL and Keywords (e.g., "CTO, Marketing, Engineering").
6.  Click "Start Extraction".
7.  View results in real-time, browse **History**, or **Export to CSV**.

## Architecture

-   **`run.py`**: Entry point script.
-   **`app/backend/`**:
    -   `main.py`: FastAPI application, endpoints, and WebSocket logic.
    -   `crawler.py`: `FastCrawler` (aiohttp) and `DeepCrawler` (playwright).
    -   `extractor.py`: Enhanced regex and logic for finding emails.
    -   `intelligence.py`: Unified interface for OpenAI, Gemini, Anthropic, and Ollama.
    -   `database.py` & `db_models.py`: SQLite database configuration and models.
    -   `validator.py`: Email syntax and DNS validation.
    -   `models.py`: Pydantic data models.
-   **`app/frontend/static/`**:
    -   `index.html`: Modernized single-page application using Tailwind CSS.

## Testing

Run the local extraction test to verify logic without crawling:

```bash
python test_extraction.py
```
