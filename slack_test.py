# slack_test.py
import os
import requests
from dotenv import load_dotenv

load_dotenv(override=True)
token = os.getenv("SLACK_BOT_TOKEN")
channel = os.getenv("SLACK_CHANNEL_ID")
print("토큰 로드됨:", bool(token), "| 채널 ID 로드됨:", bool(channel))

resp = requests.post(
    "https://slack.com/api/chat.postMessage",
    headers={"Authorization": f"Bearer {token}"},
    json={"channel": channel, "text": "Slack 연결 테스트"},
    timeout=10,
)
print(resp.json())  # {'ok': True, ...} 이면 성공, 아니면 'error' 항목을 확인