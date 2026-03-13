# 🎬 Terabox Downloader Telegram Bot

A Telegram bot that downloads Terabox videos and sends them directly in chat.

---

## ✨ Features

- 📥 Download videos from any Terabox-family link
- 📤 Send videos directly in Telegram (up to 50 MB)
- 🔗 For larger files, provides a direct download link
- 🔄 Automatic fallback to a public resolver API
- 🧹 Auto-cleanup of temporary files after upload

---

## 🚀 Setup

### 1. Create a Telegram Bot

1. Open [@BotFather](https://t.me/BotFather) on Telegram
2. Send `/newbot` and follow the prompts
3. Copy your **Bot Token**

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure environment

```bash
cp .env.example .env
# Edit .env and paste your BOT_TOKEN
```

### 4. Run the bot

```bash
python bot.py
```

---

## 📁 Project Structure

```
terabox_bot/
├── bot.py            # Telegram bot logic & handlers
├── downloader.py     # Terabox download engine
├── requirements.txt  # Python dependencies
├── .env.example      # Environment variable template
└── README.md
```

---

## 🌐 Supported Terabox Domains

| Domain |
|--------|
| terabox.com |
| teraboxapp.com |
| 1024terabox.com |
| terabox.fun |
| terafileshare.com |
| mirrobox.com |
| nephobox.com |
| 4funbox.co |
| momerybox.com |
| tibibox.com |

---

## ☁️ Deploy on a Server (Optional)

### Systemd service (Linux)

```ini
# /etc/systemd/system/terabox-bot.service
[Unit]
Description=Terabox Telegram Bot
After=network.target

[Service]
WorkingDirectory=/path/to/terabox_bot
ExecStart=/usr/bin/python3 bot.py
EnvironmentFile=/path/to/terabox_bot/.env
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable terabox-bot
sudo systemctl start terabox-bot
```

### Docker

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD ["python", "bot.py"]
```

```bash
docker build -t terabox-bot .
docker run -d --env-file .env terabox-bot
```

---

## ⚠️ Notes

- Telegram bots can upload files up to **50 MB** via the Bot API.
  Larger files are shared as direct download links instead.
- Terabox download links may expire after some time.
- For high-traffic deployments, consider using the **Telegram Bot API server**
  locally to increase the upload limit to 2 GB.

---

## 📜 License

MIT
