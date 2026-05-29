FROM python:3.12-slim

RUN useradd --create-home --shell /bin/bash migradiff

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY migra/ ./migra/
COPY pyproject.toml README.md ./

RUN pip install --no-cache-dir .

USER migradiff

ENTRYPOINT ["migra"]
