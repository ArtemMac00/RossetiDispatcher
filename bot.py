import logging
import asyncio
import vk_api
from vk_api.bot_longpoll import VkBotLongPoll, VkBotEventType
from vk_api.keyboard import VkKeyboard, VkKeyboardColor
import aiohttp
from typing import Dict, List
import time
from concurrent.futures import ThreadPoolExecutor

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

VK_TOKEN = ""  # Токен группы
GROUP_ID = 0  # ID группы

# Центры муниципальных округов Вологодской области
VOLOGDA_REGION_LOCATIONS = {
    # Города
    "бабаево": {"lat": 59.3833, "lon": 35.9500, "type": "город"},
    "белозерск": {"lat": 60.0333, "lon": 37.7833, "type": "город"},
    "великий устюг": {"lat": 60.7585, "lon": 46.3044, "type": "город"},
    "вологда": {"lat": 59.3000, "lon": 39.9000, "type": "город"},
    "вытегра": {"lat": 61.0000, "lon": 36.4500, "type": "город"},
    "грязовец": {"lat": 58.8833, "lon": 40.2500, "type": "город"},
    "кириллов": {"lat": 59.8667, "lon": 38.3833, "type": "город"},
    "никольск": {"lat": 59.5333, "lon": 45.4500, "type": "город"},
    "сокол": {"lat": 59.4667, "lon": 40.1167, "type": "город"},
    "тотьма": {"lat": 59.9833, "lon": 42.7667, "type": "город"},
    "устюжна": {"lat": 58.8333, "lon": 36.4333, "type": "город"},
    "харовск": {"lat": 59.9500, "lon": 40.2000, "type": "город"},
    "череповец": {"lat": 59.0000, "lon": 38.0000, "type": "город"},
    
    # Поселки
    "вожега": {"lat": 60.4667, "lon": 40.2167, "type": "поселок"},
    "кадуй": {"lat": 59.2000, "lon": 37.1500, "type": "поселок"},
    "чагода": {"lat": 59.1667, "lon": 35.3333, "type": "поселок"},
    "шексна": {"lat": 59.2167, "lon": 38.5000, "type": "поселок"},
    
    # Села
    "верховажье": {"lat": 60.7167, "lon": 41.9833, "type": "село"},
    "кичменгский городок": {"lat": 59.9833, "lon": 45.7833, "type": "село"},
    "липин бор": {"lat": 60.3667, "lon": 37.9333, "type": "село"},
    "нюксеница": {"lat": 60.4167, "lon": 44.2333, "type": "село"},
    "сямжа": {"lat": 60.0167, "lon": 41.0667, "type": "село"},
    "тарногский городок": {"lat": 60.5000, "lon": 43.5833, "type": "село"},
    "устье": {"lat": 59.6500, "lon": 39.7167, "type": "село"},
    "шуйское": {"lat": 59.2500, "lon": 40.6667, "type": "село"},
    "имени бабушкина": {"lat": 59.7500, "lon": 43.1167, "type": "село"},
}

class WeatherAnalyzer:
    def __init__(self):
        self.base_url = "https://api.open-meteo.com/v1/forecast"

    async def get_weather_data(self, lat: float, lon: float) -> Dict:
        try:
            params = {
                'latitude': lat,
                'longitude': lon,
                'current': [
                    'temperature_2m', 'wind_speed_10m', 'wind_gusts_10m',
                    'relative_humidity_2m', 'precipitation', 'weather_code',
                    'pressure_msl', 'cloud_cover'
                ],
                'timezone': 'Europe/Moscow'
            }

            async with aiohttp.ClientSession() as session:
                async with session.get(self.base_url, params=params, timeout=10) as response:
                    response.raise_for_status()
                    return await response.json()
        except Exception as e:
            logger.error(f"Ошибка получения данных погоды: {e}")
            return None

class TerrainAnalyzer:
    async def analyze_terrain(self, lat: float, lon: float, location_name: str, location_type: str) -> Dict:
        try:
            async with aiohttp.ClientSession() as session:
                url = f"https://nominatim.openstreetmap.org/reverse"
                params = {'lat': lat, 'lon': lon, 'format': 'json', 'zoom': 10}
                async with session.get(url, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        return self._parse_osm_data(data, location_name, location_type)
                    else:
                        return self._get_default_terrain(location_name, location_type)
        except Exception as e:
            logger.error(f"Ошибка анализа местности: {e}")
            return self._get_default_terrain(location_name, location_type)

    def _parse_osm_data(self, osm_data: Dict, location_name: str, location_type: str) -> Dict:
        display_name = osm_data.get('display_name', '').lower()
        terrain_type = "равнинная местность"
        features = []

        if any(word in display_name for word in ['лес', 'forest', 'wood']):
            terrain_type = "лесная местность"
            features.extend(['деревья near ЛЭП', 'риск падения деревьев', 'ограниченная видимость'])
        elif any(word in display_name for word in ['озеро', 'река', 'водоем', 'lake', 'river']):
            terrain_type = "приозерная местность"
            features.extend(['повышенная влажность', 'туманы', 'коррозионная нагрузка'])
        elif any(word in display_name for word in ['холм', 'гора', 'hill', 'mountain']):
            terrain_type = "холмистая местность"
            features.extend(['перепады высот', 'усиленная ветровая нагрузка'])

        return {
            'type': terrain_type,
            'features': features if features else ['стандартные условия'],
            'location_type': location_type
        }

    def _get_default_terrain(self, location_name: str, location_type: str) -> Dict:
        return {
            'type': 'равнинная местность',
            'features': ['стандартные условия'],
            'location_type': location_type
        }

class RecommendationGenerator:
    def __init__(self):
        self.g4f_available = False
        self.g4f = None

        try:
            import g4f
            self.g4f = g4f
            self.g4f_available = True
            logger.info("✅ g4f успешно подключен (новый API)")
        except Exception as e:
            logger.warning(f"❌ g4f не работает: {e}")

    async def generate_recommendations(self, weather_data: Dict, terrain_data: Dict, location: str) -> str:
        if self.g4f_available:
            try:
                logger.info("🤖 Пробую использовать g4f...")

                prompt = self._create_prompt(weather_data, terrain_data, location)

                loop = asyncio.get_event_loop()
                with ThreadPoolExecutor() as executor:
                    response = await loop.run_in_executor(
                        executor,
                        self._call_g4f_sync,
                        prompt
                    )

                if response and len(response.strip()) > 100:
                    logger.info("✅ g4f успешно сработал")
                    return response[:4000]

                logger.warning("⚠️ g4f вернул слабый ответ")

            except Exception as e:
                logger.error(f"❌ Ошибка g4f: {e}")

        logger.info("🔄 Переключение на локальный анализ")
        return self._generate_local_analysis(weather_data, terrain_data, location)

    def _call_g4f_sync(self, prompt: str) -> str:
        models = ["gpt-4o", "gpt-4", "gpt-3.5-turbo"]

        for model in models:
            try:
                response = self.g4f.ChatCompletion.create(
                    model=model,
                    messages=[{"role": "user", "content": prompt}]
                )

                if response and len(response.strip()) > 50:
                    return response

            except Exception as e:
                logger.warning(f"⚠️ {model} не сработал: {e}")
                continue

        return ""

    def _create_prompt(self, weather_data: Dict, terrain_data: Dict, location: str) -> str:
        """Создание промпта для нейросети"""
        current = weather_data.get('current', {})
        weather_code = current.get('weather_code', 0)
        weather_description = self._decode_weather_code(weather_code)
        
        prompt = f"""Ты - эксперт по анализу рисков для линий электропередач (ЛЭП) в Вологодской области.

МЕСТОПОЛОЖЕНИЕ: {location} ({terrain_data.get('location_type', 'населенный пункт')})
ТИП МЕСТНОСТИ: {terrain_data.get('type', 'неизвестно')}
ОСОБЕННОСТИ МЕСТНОСТИ: {', '.join(terrain_data.get('features', []))}

ТЕКУЩИЕ ПОГОДНЫЕ УСЛОВИЯ:
- Температура: {current.get('temperature_2m', 'N/A')}°C
- Скорость ветра: {current.get('wind_speed_10m', 'N/A')} м/с
- Порывы ветра: {current.get('wind_gusts_10m', 'N/A')} м/с
- Влажность: {current.get('relative_humidity_2m', 'N/A')}%
- Осадки: {current.get('precipitation', 'N/A')} мм
- Давление: {current.get('pressure_msl', 'N/A')} гПа
- Облачность: {current.get('cloud_cover', 'N/A')}%
- Погода: {weather_description}

Сформируй анализ рисков для ЛЭП и рекомендации для ремонтных бригад.

Структура ответа:
1. Оценка текущей ситуации (кратко)
2. Основные риски (перечислить с иконками)
3. Рекомендации для бригад (конкретные действия)
4. Технические мероприятия (что проверить/сделать)
5. Аварийная готовность (уровень готовности)

Используй эмодзи для наглядности. Ответ должен быть практичным и конкретным. Максимум 2000 символов."""
        return prompt

    def _decode_weather_code(self, code: int) -> str:
        weather_codes = {
            0: "Ясно", 1: "Преимущественно ясно", 2: "Переменная облачность", 3: "Пасмурно",
            45: "Туман", 48: "Туман с изморозью", 51: "Легкая морось", 53: "Умеренная морось",
            55: "Сильная морось", 61: "Небольшой дождь", 63: "Умеренный дождь", 65: "Сильный дождь",
            71: "Небольшой снег", 73: "Умеренный снег", 75: "Сильный снег", 80: "Небольшие ливни",
            81: "Умеренные ливни", 82: "Сильные ливни", 85: "Небольшие снегопады", 86: "Сильные снегопады",
            95: "Гроза", 96: "Гроза с градом"
        }
        return weather_codes.get(code, "Неизвестно")

    def _generate_local_analysis(self, weather_data: Dict, terrain_data: Dict, location: str) -> str:
        current = weather_data.get('current', {})
        temp = current.get('temperature_2m', 0)
        wind = current.get('wind_speed_10m', 0)
        gusts = current.get('wind_gusts_10m', 0)
        humidity = current.get('relative_humidity_2m', 0)
        precip = current.get('precipitation', 0)
        cloud = current.get('cloud_cover', 0)
        weather_code = current.get('weather_code', 0)

        risks = []
        recommendations = []
        technical_measures = []

        # Анализ обледенения
        if -10 <= temp <= 0 and humidity > 80:
            risks.append("❄️ ВЫСОКИЙ РИСК ОБЛЕДЕНЕНИЯ ПРОВОДОВ")
            recommendations.append("• Контролировать натяжение проводов")
            recommendations.append("• Подготовить оборудование для удаления наледи")
            technical_measures.append("• Увеличить частоту осмотров участков с высоким риском")
        elif -15 <= temp < -10 and humidity > 70:
            risks.append("❄️ СРЕДНИЙ РИСК ОБЛЕДЕНЕНИЯ")
            recommendations.append("• Контролировать состояние проводов")

        # Анализ ветровой нагрузки
        if gusts > 25 or wind > 20:
            risks.append("💨 КРИТИЧЕСКАЯ ВЕТРОВАЯ НАГРУЗКА")
            recommendations.append("• Ограничить высотные работы")
            recommendations.append("• Проверить крепление опор и арматуры")
            technical_measures.append("• Усилить контроль за состоянием опор")
        elif gusts > 20 or wind > 15:
            risks.append("💨 ВЫСОКАЯ ВЕТРОВАЯ НАГРУЗКА")
            recommendations.append("• Проверить крепление опор")
            recommendations.append("• Ограничить работы на высоте")
        elif gusts > 15 or wind > 10:
            risks.append("💨 УМЕРЕННАЯ ВЕТРОВАЯ НАГРУЗКА")
            recommendations.append("• Учесть ветер при планировании работ")

        # Температурные риски
        if temp < -30:
            risks.append("🥶 ЭКСТРЕМАЛЬНО НИЗКАЯ ТЕМПЕРАТУРА")
            recommendations.append("• Сократить время работ на открытом воздухе")
            recommendations.append("• Обеспечить бригады теплой экипировкой")
            technical_measures.append("• Проверить работу систем обогрева оборудования")
        elif temp < -20:
            risks.append("🥶 ОЧЕНЬ НИЗКАЯ ТЕМПЕРАТУРА")
            recommendations.append("• Использовать утепленную спецодежду")
        elif temp > 35:
            risks.append("🔥 ВЫСОКАЯ ТЕМПЕРАТУРА")
            recommendations.append("• Увеличить частоту перерывов")
            recommendations.append("• Обеспечить питьевой режим")

        # Осадки
        if precip > 10:
            risks.append("🌧️ ИНТЕНСИВНЫЕ ОСАДКИ")
            recommendations.append("• Использовать влагозащищенное оборудование")
            recommendations.append("• Обеспечить дополнительное освещение")
        elif precip > 5:
            risks.append("🌧️ УМЕРЕННЫЕ ОСАДКИ")
            recommendations.append("• Учесть ограничение видимости")

        # Видимость
        if weather_code in [45, 48] or cloud > 90:
            risks.append("🌫️ ОГРАНИЧЕННАЯ ВИДИМОСТЬ")
            recommendations.append("• Использовать сигнальные жилеты и фонари")
            recommendations.append("• Увеличить дистанцию между транспортными средствами")

        # Рекомендации по типу местности
        terrain_type = terrain_data.get('type', '')
        if "лесная" in terrain_type:
            technical_measures.append("• Проверить состояние просек")
            technical_measures.append("• Оценить риск падения деревьев")
        elif "приозерная" in terrain_type:
            technical_measures.append("• Проверить коррозионную защиту")
            recommendations.append("• Учесть возможность туманов")
        elif "холмистая" in terrain_type:
            technical_measures.append("• Проверить устойчивость опор на склонах")
            risks.append("⛰️ СЛОЖНЫЙ РЕЛЬЕФ - усиленный контроль")

        if not risks:
            risks.append("✅ СТАБИЛЬНЫЕ УСЛОВИЯ")
            recommendations.append("• Проводить плановые осмотры")
            recommendations.append("• Соблюдать стандартные меры безопасности")

        weather_desc = self._decode_weather_code(weather_code)

        report = f"""
📊 ОТЧЕТ ДЛЯ: {location}
🎯 ИСТОЧНИК: Локальный анализатор рисков

🏞 ТИП МЕСТНОСТИ: {terrain_data.get('type', 'неизвестно')}
📍 ОСОБЕННОСТИ: {', '.join(terrain_data.get('features', []))}

📈 ТЕКУЩИЕ ПОГОДНЫЕ УСЛОВИЯ:
• 🌡 Температура: {temp}°C
• 💨 Ветер: {wind} м/с (порывы {gusts} м/с)
• 💧 Влажность: {humidity}%
• 🌧 Осадки: {precip} мм
• ☁️ Облачность: {cloud}%
• 🌤 Погода: {weather_desc}

🚨 ВЫЯВЛЕННЫЕ РИСКИ:
{chr(10).join(f'• {risk}' for risk in risks)}

👷‍♂️ РЕКОМЕНДАЦИИ ДЛЯ БРИГАД:
{chr(10).join(recommendations) if recommendations else '• Стандартный режим работы'}

🔧 ТЕХНИЧЕСКИЕ МЕРОПРИЯТИЯ:
{chr(10).join(technical_measures) if technical_measures else '• Провести плановый осмотр оборудования'}
"""
        return report[:4000]

class PowerRiskBotVK:
    def __init__(self, token: str, group_id: int):
        try:
            self.vk_session = vk_api.VkApi(token=token)
            self.vk = self.vk_session.get_api()
            self.group_id = group_id
            
            self.vk.messages.getConversations(count=1)
            logger.info("✅ Успешное подключение к VK API")
            
            self.longpoll = VkBotLongPoll(self.vk_session, group_id)
            logger.info("✅ Long Poll настроен")
            
            self.weather_analyzer = WeatherAnalyzer()
            self.terrain_analyzer = TerrainAnalyzer()
            self.recommendation_generator = RecommendationGenerator()
            
        except Exception as e:
            logger.error(f"❌ Ошибка инициализации: {e}")
            raise

    def get_keyboard(self):
        keyboard = VkKeyboard(one_time=False)
        keyboard.add_button('📋 Помощь', color=VkKeyboardColor.PRIMARY)
        keyboard.add_button('🏙 Список городов', color=VkKeyboardColor.PRIMARY)
        keyboard.add_line()
        keyboard.add_button('🤖 О боте', color=VkKeyboardColor.SECONDARY)
        return keyboard.get_keyboard()

    def send_message(self, user_id: int, message: str, keyboard=None):
        try:
            if len(message) > 4096:
                for i in range(0, len(message), 4096):
                    part = message[i:i+4096]
                    self.vk.messages.send(
                        user_id=user_id,
                        message=part,
                        random_id=int(time.time() * 1000),
                        keyboard=keyboard
                    )
                    time.sleep(0.1)
            else:
                self.vk.messages.send(
                    user_id=user_id,
                    message=message,
                    random_id=int(time.time() * 1000),
                    keyboard=keyboard
                )
            logger.info(f"✅ Сообщение отправлено пользователю {user_id}")
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка отправки сообщения: {e}")
            try:
                self.vk.messages.send(
                    user_id=user_id,
                    message=message,
                    random_id=int(time.time() * 1000)
                )
                logger.info(f"✅ Сообщение отправлено без клавиатуры")
                return True
            except:
                logger.error(f"❌ Не удалось отправить сообщение")
                return False

    def handle_start(self, user_id: int):
        ai_status = "🤖 g4f (ИИ)" if self.recommendation_generator.g4f_available else "⚙️ Локальный анализатор"
        
        welcome_text = f"""
🔌 Бот анализа рисков для ЛЭП Вологодской области

🤖 Режим работы: {ai_status}

Я анализирую ТЕКУЩУЮ погоду и даю рекомендации для:
• Линий электропередач
• Опор ЛЭП
• Ремонтных бригад

📍 Напишите название города из списка:
• Города: Вологда, Череповец, Великий Устюг и др.
• Используйте /cities для полного списка
"""
        self.send_message(user_id, welcome_text, self.get_keyboard())

    def handle_help(self, user_id: int):
        help_text = """
ℹ️ Как пользоваться ботом:

1️⃣ Отправьте название населенного пункта
   Например: "Вологда", "Череповец", "им. Бабушкина"

2️⃣ Бот анализирует:
   • Текущие погодные условия
   • Тип местности
   • Риски для ЛЭП

3️⃣ Получаете рекомендации:
   • Меры безопасности для бригад
   • Технические мероприятия
   • Аварийная готовность

💡 Используйте кнопку "Список городов" для просмотра всех доступных населенных пунктов
"""
        self.send_message(user_id, help_text, self.get_keyboard())

    def handle_cities(self, user_id: int):
        cities_by_type = {"Города": [], "Поселки": [], "Села": []}
        
        for name, data in VOLOGDA_REGION_LOCATIONS.items():
            display_name = name.title()
            if name == "кичменгский городок":
                display_name = "Кичменгский Городок"
            elif name == "тарногский городок":
                display_name = "Тарногский Городок"
            elif name == "имени бабушкина":
                display_name = "им. Бабушкина"
            
            if data['type'] == 'город':
                cities_by_type["Города"].append(display_name)
            elif data['type'] == 'поселок':
                cities_by_type["Поселки"].append(display_name)
            elif data['type'] == 'село':
                cities_by_type["Села"].append(display_name)
        
        cities_text = "📍 Доступные населенные пункты:\n\n"
        for loc_type, locations in cities_by_type.items():
            if locations:
                cities_text += f"📍 {loc_type}:\n"
                cities_text += "\n".join(f"• {loc}" for loc in sorted(locations)) + "\n\n"
        
        cities_text += "💡 Напишите название для анализа"
        self.send_message(user_id, cities_text, self.get_keyboard())

    def handle_about(self, user_id: int):
        ai_status = "✅ Активен" if self.recommendation_generator.g4f_available else "❌ Недоступен"
        
        about_text = f"""
🌤 О боте "Анализ рисков ЛЭП"

Бот создан для оперативного анализа погодных условий и оценки рисков для линий электропередач в Вологодской области.

📊 Источники данных:
• OpenMeteo - актуальные погодные данные
• OpenStreetMap - информация о местности

🤖 Режим ИИ: {ai_status}
• При наличии g4f - используется нейросеть GPT-3.5
• При ошибке - автоматическое переключение на локальный анализатор

🔍 Функции:
• Анализ текущей погоды в реальном времени
• Оценка рисков по 6 категориям
• Рекомендации для ремонтных бригад
• Технические мероприятия по безопасности

👨‍💻 Для энергетиков и служб эксплуатации ЛЭП
"""
        self.send_message(user_id, about_text, self.get_keyboard())

    def get_display_name(self, location_name: str) -> str:
        """Форматирование красивого названия"""
        if location_name == "кичменгский городок":
            return "Кичменгский Городок"
        elif location_name == "тарногский городок":
            return "Тарногский Городок"
        elif location_name == "имени бабушкина":
            return "им. Бабушкина"
        return location_name.title()

    async def analyze_location(self, user_id: int, location_name: str):
        location_data = VOLOGDA_REGION_LOCATIONS[location_name]
        display_name = self.get_display_name(location_name)
        
        self.send_message(user_id, f"🔍 Анализирую {display_name}...")

        try:
            weather_data = await self.weather_analyzer.get_weather_data(
                location_data['lat'], location_data['lon']
            )

            if not weather_data:
                self.send_message(user_id, "❌ Ошибка получения данных о погоде")
                return

            terrain_data = await self.terrain_analyzer.analyze_terrain(
                location_data['lat'], location_data['lon'], display_name, location_data['type']
            )

            if self.recommendation_generator.g4f_available:
                self.send_message(user_id, "🤖 Генерирую рекомендации с помощью ИИ...")
            else:
                self.send_message(user_id, "⚙️ Генерирую рекомендации с помощью локального анализатора...")

            recommendations = await self.recommendation_generator.generate_recommendations(
                weather_data, terrain_data, display_name
            )

            self.send_message(user_id, recommendations, self.get_keyboard())

        except Exception as e:
            logger.error(f"Ошибка анализа: {e}")
            self.send_message(user_id, "❌ Ошибка при анализе. Попробуйте позже.")

    def run(self):
        print("=" * 50)
        print("🤖 VK Бот запущен...")
        print(f"📍 Городов в базе: {len(VOLOGDA_REGION_LOCATIONS)}")
        
        if self.recommendation_generator.g4f_available:
            print("🤖 Режим: g4f (ИИ) + локальный анализатор")
            print("✅ ИИ режим активен")
        else:
            print("⚙️ Режим: локальный анализатор рисков")
            print("⚠️  g4f не доступен. Установите: pip install g4f")
        
        print("✅ Бот готов к работе!")
        print("=" * 50)
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        for event in self.longpoll.listen():
            if event.type == VkBotEventType.MESSAGE_NEW:
                if event.message and event.message.get('text'):
                    user_id = event.message['from_id']
                    message_text = event.message['text'].strip().lower()
                    
                    if message_text in ['/start', 'start', 'начать']:
                        self.handle_start(user_id)
                    elif message_text in ['/help', 'помощь', '📋 помощь']:
                        self.handle_help(user_id)
                    elif message_text in ['/cities', 'города', 'список городов', '🏙 список городов']:
                        self.handle_cities(user_id)
                    elif message_text in ['о боте', '/about', '🤖 о боте']:
                        self.handle_about(user_id)
                    else:
                        if message_text in VOLOGDA_REGION_LOCATIONS:
                            loop.run_until_complete(self.analyze_location(user_id, message_text))
                        else:
                            text = f"❓ Населённый пункт '{message_text}' не найден.\nИспользуйте 'Список городов' для просмотра всех доступных населенных пунктов."
                            self.send_message(user_id, text, self.get_keyboard())

def main():
    if VK_TOKEN == "" or len(VK_TOKEN) < 10:
        print("=" * 50)
        print("❌ ОШИБКА: НЕ УКАЗАН ТОКЕН ГРУППЫ!")
        print("\n📌 ИНСТРУКЦИЯ ПО НАСТРОЙКЕ:")
        print("1. Зайдите в управление группой")
        print("2. В разделе 'Сообщения' включите:")
        print("   • Сообщения сообщества")
        print("   • Чат-бот")
        print("3. В разделе 'Работа с API' создайте ключ")
        print("4. Скопируйте токен в переменную VK_TOKEN")
        print("5. Укажите GROUP_ID вашей группы")
        print("=" * 50)
        return

    if GROUP_ID == 0:
        print("=" * 50)
        print("❌ ОШИБКА: НЕ УКАЗАН GROUP_ID!")
        print("ID группы можно найти в адресе: vk.com/club[ID]")
        print("=" * 50)
        return

    # Проверка установки g4f
    try:
        import g4f
        print("✅ g4f найден - ИИ режим будет доступен")
    except ImportError:
        print("⚠️  g4f не установлен. Для ИИ режима выполните: pip install g4f")
        print("💡 Бот будет работать в режиме локального анализатора")

    try:
        bot = PowerRiskBotVK(VK_TOKEN, GROUP_ID)
        bot.run()
    except Exception as e:
        print(f"❌ Критическая ошибка: {e}")
        print("\n🔧 Проверьте:")
        print("1. Включены ли сообщения в группе")
        print("2. Включен ли режим 'Чат-бот'")
        print("3. Правильность токена и ID группы")

if __name__ == '__main__':
    main()
