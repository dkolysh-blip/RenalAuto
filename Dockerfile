FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml ./
COPY renalauto ./renalauto
RUN pip install --no-cache-dir .
ENV DB_PATH=/data/renalauto.db
VOLUME /data
EXPOSE 8000
CMD ["python", "-m", "renalauto"]
