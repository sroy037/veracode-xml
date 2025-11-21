FROM python:3.11-slim AS base
ENV PYTHONUNBUFFERED 1
ENV PYTHONDONTWRITEBYTECODE 1
WORKDIR /app

FROM base AS builder-api
COPY requirements.txt /app/
COPY agent/requirements.txt /app/agent/
COPY agent_api/requirements.txt /app/agent_api/
#COPY ui/requirements.txt /app/ui/
COPY web_ui/requirements.txt /app/web_ui/
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir -r agent/requirements.txt
RUN pip install --no-cache-dir -r agent_api/requirements.txt
#RUN pip install --no-cache-dir -r ui/requirements.txt
RUN pip install --no-cache-dir -r web_ui/requirements.txt

# --- Install the veracli package from source ---
COPY . /app/xml_api_cli/
WORKDIR /app/xml_api_cli/
# Install any specific requirements for running the veracli script
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir .

FROM base AS builder-slackbot
COPY slackbot/requirements.txt /app/slackbot/
RUN pip install --no-cache-dir -r slackbot/requirements.txt

FROM base AS final
# --- ADDED THIS LINE: Copies executables like 'uvicorn' ---
COPY --from=builder-api /usr/local/bin/ /usr/local/bin/ 
# ---

COPY --from=builder-api /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder-slackbot /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY . /app
EXPOSE 8000
CMD ["uvicorn", "app.app:app", "--host", "0.0.0.0", "--port", "8000"]