# UtecVis · API de T5 en Hugging Face Spaces (SDK Docker, hardware gratis "CPU basic").
FROM python:3.11-slim

# Spaces corre el contenedor con el usuario 1000
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user PATH=/home/user/.local/bin:$PATH HF_HOME=/home/user/.cache/huggingface PYTHONUNBUFFERED=1
WORKDIR /home/user/app

COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt
# el modelo se descarga al construir la imagen: al despertar, el Space solo lo carga (no lo baja de nuevo)
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('intfloat/multilingual-e5-base')"

COPY --chown=user . .
EXPOSE 7860
CMD ["gunicorn", "--bind", "0.0.0.0:7860", "--workers", "1", "--threads", "4", "--timeout", "180", "server:app"]
