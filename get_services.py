import requests
import os
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("PRMOTION_API_KEY")
url = f"https://api.prmotion.me/v1?key={API_KEY}&action=services"

response = requests.get(url)
services = response.json()

print("🔍 УСЛУГИ ДЛЯ TELEGRAM:\n")
print("=" * 60)

for service in services:
    name = service['name'].lower()
    category = service.get('category', '').lower()
    
    # Ищем Telegram
    if "telegram" in name or "telegram" in category:
        # Пропускаем бесплатные
        if "free" not in name:
            print(f"✅ ID: {service['service']} | {service['name']}")
            print(f"   💰 Цена: {service.get('rate', '?')}")
            print(f"   📊 Мин: {service.get('min', '?')} | Макс: {service.get('max', '?')}")
            print("-" * 40)

# Если ничего не нашлось, покажи категории всех услуг
if not any("telegram" in s['name'].lower() or "telegram" in s.get('category', '').lower() for s in services):
    print("❌ Услуги Telegram не найдены.")
    print("\n📂 Доступные категории:")
    categories = set()
    for service in services:
        if 'category' in service:
            categories.add(service['category'])
    for cat in sorted(categories):
        print(f"   - {cat}")