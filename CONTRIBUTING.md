# Contributing

Thanks for your interest in improving Exam Generator. The project is intended to be useful for training teams, teachers, and maintainers who need source-grounded assessment generation.

## Development Setup

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt pytest
```

Set local environment variables before running the app:

```bash
GPUSTACK_API_KEY=your_api_key_here
GPUSTACK_BASE_URL=https://api.deepseek.com/v1
```

Run tests:

```bash
pytest -q
```

Run the app:

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8833
```

## Contribution Areas

- Document parsing and ingestion pipelines
- Prompt quality and question validation
- RAG retrieval integration
- DOCX/XLSX export improvements
- UI review workflow improvements
- Test coverage and CI hardening
- Documentation and deployment examples

## Pull Request Checklist

- Keep changes focused and easy to review.
- Add or update tests when behavior changes.
- Update README or docs for user-facing changes.
- Do not commit real API keys, private documents, or generated exam files containing sensitive content.
