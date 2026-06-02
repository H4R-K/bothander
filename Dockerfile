# 1. Base image (Python ka lightweight version)
FROM python:3.11-slim

# 2. Container ke andar working directory set karein
WORKDIR /app

# 3. requirements.txt copy karein aur libraries install karein
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 4. Baaki ka sara code (bot.py, etc.) container me copy karein
COPY . .

# 5. Bot ko run karne ka command (Render isko auto-detect kar lega)
CMD ["python", "bot.py"]
