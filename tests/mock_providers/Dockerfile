FROM python:3.11.16-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 MOCK_PROVIDER_HOST=0.0.0.0
WORKDIR /app
COPY mock_providers /app/mock_providers
COPY fixtures/providers /app/fixtures/providers
USER 65532:65532
EXPOSE 9080
CMD ["python", "-m", "mock_providers.server"]
