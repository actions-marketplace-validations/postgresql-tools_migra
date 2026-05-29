FROM python:3.12-slim

RUN useradd --create-home --shell /bin/bash migradiff

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY migra/ ./migra/
COPY pyproject.toml README.md ./

RUN pip install --no-cache-dir .

COPY action-entrypoint.sh .
RUN chmod +x action-entrypoint.sh

USER migradiff

ENTRYPOINT ["/app/action-entrypoint.sh"]
