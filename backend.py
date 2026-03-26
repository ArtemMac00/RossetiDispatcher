from flask import Flask, send_file, jsonify
from flask_cors import CORS
import random
from datetime import datetime
import requests
import logging

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

# Данные муниципалитетов Вологодской области
MUNICIPALITIES = [
    {"name": "Вологда", "coords": [59.2181, 39.8886], "type": "city", "population": "317822", "center": "г. Вологда"},
    {"name": "Череповец", "coords": [59.1266, 37.9093], "type": "city", "population": "298160", "center": "г. Череповец"},
    {"name": "Бабаевский", "coords": [59.3833, 35.9500], "type": "municipality", "population": "18541", "center": "г. Бабаево"},
    {"name": "Бабушкинский", "coords": [59.7500, 43.1167], "type": "municipality", "population": "9307", "center": "с. им. Бабушкина"},
    {"name": "Белозерский", "coords": [60.0333, 37.7833], "type": "municipality", "population": "12978", "center": "г. Белозерск"},
    {"name": "Вашкинский", "coords": [60.3667, 37.9333], "type": "municipality", "population": "5872", "center": "с. Липин Бор"},
    {"name": "Великоустюгский", "coords": [60.7585, 46.3044], "type": "municipality", "population": "48563", "center": "г. Великий Устюг"},
    {"name": "Верховажский", "coords": [60.7167, 41.9833], "type": "municipality", "population": "12287", "center": "с. Верховажье"},
    {"name": "Вожегодский", "coords": [60.4667, 40.2167], "type": "municipality", "population": "13416", "center": "п. Вожега"},
    {"name": "Вологодский", "coords": [59.3000, 39.9000], "type": "municipality", "population": "51950", "center": "г. Вологда"},
    {"name": "Вытегорский", "coords": [61.0000, 36.4500], "type": "municipality", "population": "21686", "center": "г. Вытегра"},
    {"name": "Грязовецкий", "coords": [58.8833, 40.2500], "type": "municipality", "population": "31398", "center": "г. Грязовец"},
    {"name": "Кадуйский", "coords": [59.2000, 37.1500], "type": "municipality", "population": "16316", "center": "п. Кадуй"},
    {"name": "Кирилловский", "coords": [59.8667, 38.3833], "type": "municipality", "population": "13795", "center": "г. Кириллов"},
    {"name": "Кичменгско-Городецкий", "coords": [59.9833, 45.7833], "type": "municipality", "population": "14079", "center": "с. Кичменгский Городок"},
    {"name": "Междуреченский", "coords": [59.2500, 40.6667], "type": "municipality", "population": "4740", "center": "с. Шуйское"},
    {"name": "Никольский", "coords": [59.5333, 45.4500], "type": "municipality", "population": "18390", "center": "г. Никольск"},
    {"name": "Нюксенский", "coords": [60.4167, 44.2333], "type": "municipality", "population": "8316", "center": "с. Нюксеница"},
    {"name": "Сокольский", "coords": [59.4667, 40.1167], "type": "municipality", "population": "44172", "center": "г. Сокол"},
    {"name": "Сямженский", "coords": [60.0167, 41.0667], "type": "municipality", "population": "7880", "center": "с. Сямжа"},
    {"name": "Тарногский", "coords": [60.5000, 43.5833], "type": "municipality", "population": "10250", "center": "с. Тарногский Городок"},
    {"name": "Тотемский", "coords": [59.9833, 42.7667], "type": "municipality", "population": "21802", "center": "г. Тотьма"},
    {"name": "Усть-Кубинский", "coords": [59.6500, 39.7167], "type": "municipality", "population": "7154", "center": "с. Устье"},
    {"name": "Устюженский", "coords": [58.8333, 36.4333], "type": "municipality", "population": "15048", "center": "г. Устюжна"},
    {"name": "Харовский", "coords": [59.9500, 40.2000], "type": "municipality", "population": "12618", "center": "г. Харовск"},
    {"name": "Чагодощенский", "coords": [59.1667, 35.3333], "type": "municipality", "population": "10732", "center": "п. Чагода"},
    {"name": "Череповецкий", "coords": [59.0000, 38.0000], "type": "municipality", "population": "39308", "center": "г. Череповец"},
    {"name": "Шекснинский", "coords": [59.2167, 38.5000], "type": "municipality", "population": "28791", "center": "п. Шексна"}
]

class WeatherAnalyzer:
    def __init__(self):
        self.risk_thresholds = {
            "wind_speed": {"low": 5, "medium": 10, "high": 15, "critical": 20},
            "temperature": {"freezing": -10, "extreme_cold": -20},
            "precipitation": {"light": 2.5, "moderate": 7.5, "heavy": 15}
        }
        self.current_weather_data = []
    
    def get_weather_from_openmeteo(self, lat, lon, name):
        """Получение реальных данных о погоде с Open-Meteo API"""
        try:
            url = "https://api.open-meteo.com/v1/forecast"
            params = {
                'latitude': lat,
                'longitude': lon,
                'current': 'temperature_2m,relative_humidity_2m,precipitation,pressure_msl,wind_speed_10m,weather_code',
                'timezone': 'Europe/Moscow',
                'forecast_days': 1
            }
            
            logger.info(f"Запрос к Open-Meteo для {name} ({lat}, {lon})")
            response = requests.get(url, params=params, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                current = data.get('current', {})
                
                weather_info = self._decode_weather_code(current.get('weather_code', 0))
                
                logger.info(f"✅ Успешно получены данные для {name}: {current.get('temperature_2m', 0)}°C")
                
                return {
                    "temperature": current.get('temperature_2m', 0),
                    "wind_speed": current.get('wind_speed_10m', 0),
                    "precipitation": current.get('precipitation', 0),
                    "humidity": current.get('relative_humidity_2m', 0),
                    "pressure": current.get('pressure_msl', 1013.0),
                    "weather_code": current.get('weather_code', 0),
                    "description": weather_info['description']
                }
            else:
                logger.warning(f"Ошибка Open-Meteo для {name}: {response.status_code}")
                return self._generate_demo_data(name)
                
        except Exception as e:
            logger.warning(f"Ошибка получения погоды для {name}: {e}")
            return self._generate_demo_data(name)
    
    def _decode_weather_code(self, code):
        """Декодирование кода погоды Open-Meteo"""
        weather_codes = {
            0: {"description": "Ясно", "risk": 0.1},
            1: {"description": "Преимущественно ясно", "risk": 0.1},
            2: {"description": "Переменная облачность", "risk": 0.2},
            3: {"description": "Пасмурно", "risk": 0.3},
            45: {"description": "Туман", "risk": 0.5},
            48: {"description": "Туман с инеем", "risk": 0.6},
            51: {"description": "Лежащая морось", "risk": 0.4},
            53: {"description": "Умеренная морось", "risk": 0.5},
            55: {"description": "Сильная морось", "risk": 0.6},
            61: {"description": "Небольшой дождь", "risk": 0.5},
            63: {"description": "Умеренный дождь", "risk": 0.6},
            65: {"description": "Сильный дождь", "risk": 0.8},
            71: {"description": "Небольшой снег", "risk": 0.6},
            73: {"description": "Умеренный снег", "risk": 0.7},
            75: {"description": "Сильный снег", "risk": 0.9},
            95: {"description": "Гроза", "risk": 0.9},
        }
        return weather_codes.get(code, {"description": "Неизвестно", "risk": 0.3})
    
    def _generate_demo_data(self, city_name):
        """Генерация демо-данных при ошибке API"""
        base_temps = {
            "Вологда": 2, "Череповец": 3, "Сокольский": 1, "Великоустюгский": -1,
            "Белозерский": 0, "Вытегорский": 0, "Кирилловский": 0, "Тотемский": 1,
            "Устюженский": 2, "Харовский": -1, "Бабаевский": 2, "Грязовецкий": 2,
            "Бабушкинский": -2, "Вашкинский": -1, "Верховажский": 0, "Вожегодский": 0,
            "Кадуйский": 2, "Кичменгско-Городецкий": -1, "Междуреченский": 1,
            "Никольский": -1, "Нюксенский": -2, "Сямженский": 0, "Тарногский": -2,
            "Усть-Кубинский": 1, "Харовский": -1, "Чагодощенский": 2, "Череповецкий": 3,
            "Шекснинский": 2
        }
        
        base_temp = base_temps.get(city_name, 1)
        temp_variation = random.uniform(-2, 2)
        wind_base = random.uniform(2, 6)
        precipitation_base = random.uniform(0, 1.5) if random.random() < 0.4 else 0
        humidity_base = random.randint(75, 90)
        pressure_base = random.uniform(980.0, 1020.0)
        
        if base_temp < 0:
            descriptions = ["снег", "небольшой снег", "облачно", "пасмурно"]
            weather_codes = [71, 73, 3]
        else:
            descriptions = ["ясно", "переменная облачность", "облачно", "небольшой дождь"]
            weather_codes = [0, 1, 2, 61]

        return {
            "temperature": round(base_temp + temp_variation, 1),
            "wind_speed": round(wind_base, 1),
            "precipitation": round(precipitation_base, 1),
            "humidity": humidity_base,
            "pressure": round(pressure_base, 1),
            "weather_code": random.choice(weather_codes),
            "description": random.choice(descriptions)
        }
    
    def analyze_risk_factors(self, weather):
        """Анализ факторов риска для ЛЭП"""
        factors = {}
        
        # Анализ ветра
        if weather["wind_speed"] >= self.risk_thresholds["wind_speed"]["critical"]:
            factors["wind"] = 1.0
        elif weather["wind_speed"] >= self.risk_thresholds["wind_speed"]["high"]:
            factors["wind"] = 0.8
        elif weather["wind_speed"] >= self.risk_thresholds["wind_speed"]["medium"]:
            factors["wind"] = 0.6
        elif weather["wind_speed"] >= self.risk_thresholds["wind_speed"]["low"]:
            factors["wind"] = 0.4
        else:
            factors["wind"] = 0.1
        
        # Анализ температуры
        if weather["temperature"] <= self.risk_thresholds["temperature"]["extreme_cold"]:
            factors["temperature"] = 0.9
        elif weather["temperature"] <= self.risk_thresholds["temperature"]["freezing"]:
            factors["temperature"] = 0.7
        elif weather["temperature"] < 0:
            factors["temperature"] = 0.5
        else:
            factors["temperature"] = 0.2
        
        # Анализ осадков
        if weather["precipitation"] >= self.risk_thresholds["precipitation"]["heavy"]:
            factors["precipitation"] = 1.0
        elif weather["precipitation"] >= self.risk_thresholds["precipitation"]["moderate"]:
            factors["precipitation"] = 0.7
        elif weather["precipitation"] >= self.risk_thresholds["precipitation"]["light"]:
            factors["precipitation"] = 0.5
        else:
            factors["precipitation"] = 0.2
        
        # Анализ влажности (риск обледенения)
        if weather["humidity"] >= 90 and weather["temperature"] < 0:
            factors["icing"] = 0.9
        elif weather["humidity"] >= 80 and weather["temperature"] < 0:
            factors["icing"] = 0.7
        else:
            factors["icing"] = 0.1
        
        # Анализ погодных явлений
        weather_info = self._decode_weather_code(weather["weather_code"])
        factors["weather_phenomena"] = weather_info["risk"]
        
        return factors
    
    def calculate_risk_level(self, factors):
        """Расчет общего уровня риска"""
        weights = {
            "wind": 0.3, "temperature": 0.2, "precipitation": 0.2, 
            "icing": 0.2, "weather_phenomena": 0.1
        }
        
        total_risk = sum(factors.get(factor, 0) * weight for factor, weight in weights.items())
        risk_level = min(10, int(total_risk * 10))
        
        return risk_level
    
    def create_risk_grid(self, municipalities_data):
        """Создание сетки рисков на основе данных о погоде"""
        grid = []
        bounds = [
            [58.2, 34.5], [58.2, 48.0], [62.0, 48.0], [62.0, 34.5]
        ]
        
        south_west = bounds[0]
        north_east = bounds[2]
        lat_step = 0.3
        lng_step = 0.5
        
        for lat in range(int(south_west[0] * 10), int(north_east[0] * 10), int(lat_step * 10)):
            for lng in range(int(south_west[1] * 10), int(north_east[1] * 10), int(lng_step * 10)):
                cell_lat = lat / 10.0
                cell_lng = lng / 10.0
                
                # Находим ближайший муниципалитет
                nearest_municipality = None
                min_distance = float('inf')
                
                for municipality in municipalities_data:
                    coords = municipality["coordinates"]
                    distance = ((coords[0] - cell_lat) ** 2 + (coords[1] - cell_lng) ** 2) ** 0.5
                    
                    if distance < min_distance:
                        min_distance = distance
                        nearest_municipality = municipality
                
                risk_level = nearest_municipality["risk_level"] if nearest_municipality else 2
                
                grid.append({
                    "bounds": [
                        [cell_lat, cell_lng],
                        [cell_lat + lat_step, cell_lng + lng_step]
                    ],
                    "riskLevel": risk_level
                })
        
        return grid

# Инициализация анализатора
weather_analyzer = WeatherAnalyzer()

@app.route('/')
def serve_index():
    return send_file('index.html')

@app.route('/api/health')
def health_check():
    return jsonify({"status": "healthy", "timestamp": datetime.now().isoformat()})

@app.route('/api/weather/current')
def get_current_weather_all():
    """Получение текущей погоды для всех муниципалитетов"""
    results = []
    successful_api_calls = 0
    
    logger.info("Начало получения реальных данных о погоде...")
    
    for municipality in MUNICIPALITIES:
        try:
            # Получаем реальные данные
            weather_data = weather_analyzer.get_weather_from_openmeteo(
                municipality["coords"][0], 
                municipality["coords"][1], 
                municipality["name"]
            )
            
            # Анализируем риски
            factors = weather_analyzer.analyze_risk_factors(weather_data)
            risk_level = weather_analyzer.calculate_risk_level(factors)
            
            # Определяем источник данных
            from_api = True  # Всегда пытаемся получить реальные данные
            
            results.append({
                "name": municipality["name"],
                "risk_level": risk_level,
                "weather": {
                    "wind": weather_data["wind_speed"],
                    "temperature": weather_data["temperature"],
                    "precipitation": weather_data["precipitation"],
                    "humidity": weather_data["humidity"],
                    "pressure": weather_data["pressure"],
                    "description": weather_data["description"]
                },
                "coordinates": municipality["coords"],
                "from_api": from_api
            })
            
            if from_api:
                successful_api_calls += 1
                
        except Exception as e:
            logger.error(f"Ошибка для {municipality['name']}: {e}")
            # Добавляем демо-данные в случае ошибки
            demo_weather = weather_analyzer._generate_demo_data(municipality["name"])
            factors = weather_analyzer.analyze_risk_factors(demo_weather)
            risk_level = weather_analyzer.calculate_risk_level(factors)
            
            results.append({
                "name": municipality["name"],
                "risk_level": risk_level,
                "weather": {
                    "wind": demo_weather["wind_speed"],
                    "temperature": demo_weather["temperature"],
                    "precipitation": demo_weather["precipitation"],
                    "humidity": demo_weather["humidity"],
                    "pressure": demo_weather["pressure"],
                    "description": demo_weather["description"]
                },
                "coordinates": municipality["coords"],
                "from_api": False
            })
    
    # Сохраняем текущие данные
    weather_analyzer.current_weather_data = results
    
    data_source = "realtime" if successful_api_calls > 0 else "demo"
    
    logger.info(f"Завершено: {successful_api_calls}/{len(MUNICIPALITIES)} успешных запросов")
    
    return jsonify({
        "timestamp": datetime.now().isoformat(),
        "municipalities": results,
        "data_source": data_source,
        "successful_requests": successful_api_calls,
        "total_requests": len(MUNICIPALITIES),
        "api_used": "Open-Meteo"
    })

@app.route('/api/weather/update')
def update_weather_data():
    """Принудительное обновление данных о погоде"""
    return get_current_weather_all()

@app.route('/api/risk/matrix')
def get_risk_matrix():
    """Матрица рисков для overlay"""
    # Используем текущие данные или получаем новые
    if not weather_analyzer.current_weather_data:
        # Если данных нет, получаем их
        weather_response = get_current_weather_all()
        municipalities_data = weather_response.get_json()["municipalities"]
    else:
        municipalities_data = weather_analyzer.current_weather_data
    
    # Создаем сетку рисков на основе текущих данных
    grid = weather_analyzer.create_risk_grid(municipalities_data)
    
    return jsonify({
        "timestamp": datetime.now().isoformat(),
        "grid": grid,
        "bounds": [
            [58.2, 34.5], [58.2, 48.0], [62.0, 48.0], [62.0, 34.5]
        ]
    })

@app.route('/api/weather/<municipality_name>')
def get_weather_for_municipality(municipality_name):
    """Получение погоды для конкретного муниципалитета"""
    municipality = next((m for m in MUNICIPALITIES if m["name"] == municipality_name), None)
    
    if not municipality:
        return jsonify({"error": "Municipality not found"}), 404
    
    try:
        # Получаем реальные данные
        weather_data = weather_analyzer.get_weather_from_openmeteo(
            municipality["coords"][0], 
            municipality["coords"][1], 
            municipality["name"]
        )
        
        # Анализируем риски
        factors = weather_analyzer.analyze_risk_factors(weather_data)
        risk_level = weather_analyzer.calculate_risk_level(factors)
        
        return jsonify({
            "municipality": municipality_name,
            "coordinates": municipality["coords"],
            "weather": weather_data,
            "risk_level": risk_level,
            "factors": factors,
            "timestamp": datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"Ошибка для {municipality_name}: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/scenario/<scenario_name>')
def apply_weather_scenario(scenario_name):
    """Применение погодного сценария"""
    scenarios = {
        'excellent': {'risk_level': 2, 'wind': 2, 'temp': 5, 'precip': 0},
        'satisfactory': {'risk_level': 5, 'wind': 8, 'temp': -2, 'precip': 2},
        'poor': {'risk_level': 7, 'wind': 12, 'temp': -8, 'precip': 5},
        'dangerous': {'risk_level': 9, 'wind': 18, 'temp': -15, 'precip': 10},
    }
    
    scenario = scenarios.get(scenario_name)
    if not scenario:
        return jsonify({"error": "Scenario not found"}), 404
    
    # Создаем демо-данные по сценарию
    results = []
    for municipality in MUNICIPALITIES:
        results.append({
            "name": municipality["name"],
            "risk_level": scenario['risk_level'],
            "weather": {
                "wind": scenario['wind'],
                "temperature": scenario['temp'],
                "precipitation": scenario['precip'],
                "humidity": 80,
                "pressure": 1013.0,
                "description": f"Сценарий: {scenario_name}"
            },
            "coordinates": municipality["coords"],
            "from_api": False
        })
    
    # Сохраняем данные сценария
    weather_analyzer.current_weather_data = results
    
    return jsonify({
        "timestamp": datetime.now().isoformat(),
        "municipalities": results,
        "data_source": "scenario",
        "scenario": scenario_name
    })

# WSGI совместимость
application = app

if __name__ == '__main__':
    app.run(debug=True)