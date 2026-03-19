FROM python:3.12-slim

WORKDIR /app

# Install torch CPU-only first (avoids pulling CUDA variant via sentence-transformers)
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

# Install remaining dependencies
COPY pyproject.toml .
RUN pip install --no-cache-dir $(python -c "import tomllib; f=open('pyproject.toml','rb'); deps=tomllib.load(f)['project']['dependencies']; print(' '.join(deps))")

# Pre-download the embedding model at build time (not runtime)
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

COPY app/ app/

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=3s --start-period=5s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
