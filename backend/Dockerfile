FROM python:3.12-slim

# ansible + openssh-client give the container real Ansible/SSH capability out of the box.
RUN apt-get update && apt-get install -y --no-install-recommends \
    openssh-client git curl \
    && pip install --no-cache-dir ansible-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN mkdir -p data/ansible

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
