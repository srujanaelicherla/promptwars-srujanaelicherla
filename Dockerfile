# LabLink API image. Build from the repository root.
# Supported host: Render free Web Service (Docker). Cloud Run is unused.
# Do not bake GEMINI_API_KEY, service-account JSON, or test auth into the image.
# Set those as Render environment variables or secret files in the dashboard.

FROM python:3.12-slim-bookworm

RUN useradd --system --uid 10001 --create-home --home-dir /home/lablink --shell /usr/sbin/nologin lablink \
    && mkdir -p /app \
    && chown lablink:lablink /app

WORKDIR /app

COPY --chown=lablink:lablink backend/pyproject.toml /app/pyproject.toml
COPY --chown=lablink:lablink backend/app /app/app

USER lablink
ENV PATH="/home/lablink/.local/bin:${PATH}"
RUN python -m pip install --user --no-cache-dir --upgrade pip \
    && python -m pip install --user --no-cache-dir .

ENV LABLINK_ENV=production \
    LABLINK_AUTH_MODE=firebase \
    LABLINK_PERSISTENCE=firestore \
    PYTHONUNBUFFERED=1 \
    PORT=8080

EXPOSE 8080

# Render (and similar) set PORT. Bind 0.0.0.0. No --reload. Docs/ReDoc stay disabled in app.main.
CMD ["sh", "-c", "python -m uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
