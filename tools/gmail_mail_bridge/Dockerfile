# Gmail mail bridge — deploy where SMTP is allowed (Railway / Fly / VPS)
# Put your Gmail App Password HERE (not on Render).

FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt pyproject.toml README.md ./
COPY app ./app
COPY backend ./backend
COPY tools ./tools
COPY configs ./configs
RUN pip install --no-cache-dir -r requirements.txt && pip install --no-cache-dir -e .
EXPOSE 8090
CMD ["uvicorn", "tools.gmail_mail_bridge.main:app", "--host", "0.0.0.0", "--port", "8090"]
