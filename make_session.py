"""Одноразово: создаёт SESSION_STRING для юзербота.

Запускайте у себя (или в Google Colab: `!pip install telethon`, затем вставьте этот код).
Код входа вводите только здесь, в консоли, и никому не отправляйте.
SESSION_STRING даёт полный доступ к вашему аккаунту: храните только в переменных окружения.
Отозвать доступ: Telegram -> Настройки -> Устройства -> завершить сеанс.
"""
from telethon.sessions import StringSession
from telethon.sync import TelegramClient

api_id = int(input("API_ID: ").strip())
api_hash = input("API_HASH: ").strip()

with TelegramClient(StringSession(), api_id, api_hash) as client:
    print("\nВаш SESSION_STRING (вставьте в переменные окружения на хостинге):\n")
    print(client.session.save())
