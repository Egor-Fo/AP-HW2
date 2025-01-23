import logging
import requests
import asyncio
from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.types import FSInputFile, Message, CallbackQuery
from datetime import datetime
import os
from tempfile import NamedTemporaryFile
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
import matplotlib.pyplot as plt
from io import BytesIO
#from config import TOKEN_TG, WEATHER_TOKEN

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("bot.log"),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

TOKEN_TG = os.getenv("TOKEN_TG")
WEATHER_TOKEN = os.getenv("WEATHER_TOKEN")


class UserProfile(StatesGroup):
    weight = State()
    height = State()
    age = State()
    activity = State()
    city = State()


WORKOUT_CALORIES = {
    "бег": 10,
    "ходьба": 6,
    "плавание": 7,
    "йога": 4,
    "теннис": 8,
    "бадминтон": 8,
    "танцы": 7,
}

bot = Bot(token=TOKEN_TG)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
users = {}


def format_label(pct, all_values, measure):
    absolute = int(round(pct / 100.0 * sum(all_values)))
    return f"{pct:.1f}%\n({absolute} {measure})"


def get_weather(city):
    url = f"http://api.openweathermap.org/data/2.5/weather?q={city}&appid={WEATHER_TOKEN}&units=metric"
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        return data["main"]["temp"]
    else:
        raise Exception(f"Ошибка погоды: {response.json().get('message', 'Неизвестная ошибка')}")


def calculate_norms(weight, height, age, activity_minutes, temperature):
    water_goal = weight * 30 + (activity_minutes // 30) * 500
    if temperature > 25:
        water_goal += 500
    calorie_goal = 10 * weight + 6.25 * height - 5 * age + 200
    return water_goal, calorie_goal


def get_food_info(product_name):
    url = f"https://world.openfoodfacts.org/cgi/search.pl?action=process&search_terms={product_name}&json=true"
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        products = data.get('products', [])
        if products:
            first_product = products[0]
            return {
                'name': first_product.get('product_name', 'Неизвестно'),
                'calories': first_product.get('nutriments', {}).get('energy-kcal_100g', 0)
            }
        return None
    print(f"Ошибка: {response.status_code}")
    return None


def plot_water_stat(water_goal, logged_water):
    labels = ['Выпито за сегодня', 'Осталось до дневной цели']
    values = [logged_water, max(0, water_goal - logged_water)]

    fig, ax = plt.subplots()
    ax.pie(values, labels=labels, autopct=lambda p: format_label(p, values, 'мл'), startangle=90, colors=['#4CAF50', '#FF9800'])
    ax.axis('equal')
    plt.title('Прогресс по воде')

    buf = BytesIO()
    plt.savefig(buf, format='png')
    plt.close(fig)
    buf.seek(0)
    return buf


def plot_calorie_stat(logged_calories, burned_calories, calorie_goal):
    remaining_calories = max(0, calorie_goal - (logged_calories - burned_calories))

    labels = ['Потреблено за сегодня', 'Сожжено за сегодня', 'Осталось до дневной цели']
    values = [logged_calories, burned_calories, remaining_calories]

    fig, ax = plt.subplots()
    ax.pie(values, labels=labels, autopct=lambda p: format_label(p, values, 'ккал'), startangle=90, colors=['#FFA07A', '#90EE90', '#ADD8E6'])
    ax.axis('equal')
    plt.title('Прогресс по калориям')

    buf = BytesIO()
    plt.savefig(buf, format='png')
    plt.close(fig)
    buf.seek(0)
    return buf


@dp.message(Command("set_profile"))
async def set_profile(message: Message, state: FSMContext):
    await message.answer("Введите ваш вес (в кг):")
    logger.info(f"Команда /set_profile вызвана пользователем")
    await state.set_state(UserProfile.weight)


@dp.message(UserProfile.weight)
async def set_weight(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Введите корректное число для веса.")
        return
    await state.update_data(weight=int(message.text))
    await message.answer("Введите ваш рост (в см):")
    await state.set_state(UserProfile.height)


@dp.message(UserProfile.height)
async def set_height(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Введите корректное число для роста.")
        return
    await state.update_data(height=int(message.text))
    await message.answer("Введите ваш возраст:")
    await state.set_state(UserProfile.age)


@dp.message(UserProfile.age)
async def set_age(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Введите корректное число для возраста.")
        return
    await state.update_data(age=int(message.text))
    await message.answer("Сколько минут активности у вас в день?")
    await state.set_state(UserProfile.activity)


@dp.message(UserProfile.activity)
async def set_activity(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Введите корректное число для активности.")
        return
    await state.update_data(activity=int(message.text))
    await message.answer("В каком городе вы находитесь?")
    await state.set_state(UserProfile.city)


@dp.message(UserProfile.city)
async def set_city(message: Message, state: FSMContext):
    city = message.text
    await state.update_data(city=city)
    data = await state.get_data()
    weight = data["weight"]
    height = data["height"]
    age = data["age"]
    activity = data["activity"]

    try:
        temperature = get_weather(city)
    except Exception as e:
        await message.answer(f"Не удалось получить данные о погоде: {e}")
        return

    water_goal, calorie_goal = calculate_norms(weight, height, age, activity, temperature)

    users[message.from_user.id] = {
        "weight": weight,
        "height": height,
        "age": age,
        "activity": activity,
        "city": city,
        "temperature": temperature,
        "water_goal": water_goal,
        "calorie_goal": calorie_goal,
    }

    await message.answer(
        f"Профиль успешно сохранён!\n"
        f"Температура в {city}: {temperature}°C\n"
        f"Ваша норма воды: {water_goal:.1f} мл\n"
        f"Ваша норма калорий: {calorie_goal:.1f} ккал"
    )
    await state.clear()


@dp.message(Command("start"))
async def start_command(message: Message):
    logger.info(f"Команда /start вызвана пользователем")
    await message.answer("Добро пожаловать!")


@dp.message(Command("check_progress"))
async def check_progress(message: Message):
    user_id = message.from_user.id
    if user_id not in users:
        await message.answer("Сначала настройте профиль с помощью команды /set_profile.")
        return

    water_goal = users[user_id]["water_goal"]
    logged_water = users[user_id].get("logged_water", 0)
    remaining_water = max(0, water_goal - logged_water)

    calorie_goal = users[user_id]["calorie_goal"]
    logged_calories = users[user_id].get("logged_calories", 0)
    burned_calories = users[user_id].get("burned_calories", 0)
    calorie_balance = calorie_goal - (logged_calories - burned_calories)
    logger.info(f"Команда /check_progress вызвана пользователем")
    await message.answer(
        f"📊 Прогресс:\n\n"
        f"💧 Вода:\n"
        f"- Выпито: {logged_water} мл из {water_goal} мл.\n"
        f"- Осталось: {remaining_water} мл.\n\n"
        f"🔥 Калории:\n"
        f"- Потреблено: {logged_calories:.1f} ккал из {calorie_goal} ккал.\n"
        f"- Сожжено: {burned_calories} ккал.\n"
        f"- Баланс: {calorie_balance:.1f} ккал."
    )


@dp.message(Command("log_water"))
async def log_water(message: Message):
    user_id = message.from_user.id
    if user_id not in users:
        await message.answer("Сначала настройте профиль с помощью команды /set_profile.")
        return

    args = message.text.split()
    if len(args) < 2 or not args[1].isdigit():
        await message.answer("Введите количество выпитой воды в мл. Например: /log_water 200")
        return

    water_amount = int(args[1])
    users[user_id]["logged_water"] = users[user_id].get("logged_water", 0) + water_amount
    remaining = max(0, users[user_id]["water_goal"] - users[user_id]["logged_water"])
    logger.info(f"Команда /log_water вызвана пользователем")
    await message.answer(f"Вы выпили {users[user_id]['logged_water']} мл воды. Осталось: {remaining} мл.")


@dp.message(Command("log_food"))
async def log_food(message: Message):
    user_id = message.from_user.id

    if user_id not in users:
        await message.answer("Сначала настройте профиль с помощью команды /set_profile.")
        return

    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("Введите название продукта. Например: /log_food банан")
        return

    product_name = args[1]
    food_info = get_food_info(product_name)
    if not food_info:
        await message.answer(f"Не удалось найти информацию о продукте '{product_name}'.")
        return

    product_name = food_info['name']
    calories_per_100g = food_info['calories']
    logger.info(f"Команда /log_food вызвана пользователем")
    await message.answer(f"{product_name} — {calories_per_100g} ккал на 100 г. Сколько грамм вы съели?")

    @dp.message(lambda msg: msg.text.isdigit())
    async def log_grams(msg: Message):
        grams = int(msg.text)
        calories = (calories_per_100g / 100) * grams
        users[user_id]["logged_calories"] = users[user_id].get("logged_calories", 0) + calories
        balance = users[user_id]["calorie_goal"] - users[user_id]["logged_calories"]
        await msg.answer(
            f"Вы съели {calories:.1f} ккал. Записано в дневник.\n"
            f"Осталось до цели: {balance:.1f} ккал."
        )


@dp.message(Command("log_workout"))
async def log_workout(message: Message):
    user_id = message.from_user.id
    if user_id not in users:
        await message.answer("Сначала настройте профиль с помощью команды /set_profile.")
        return

    args = message.text.split(maxsplit=2)
    if len(args) < 3 or not args[2].isdigit():
        await message.answer("Введите тип тренировки и её продолжительность в минутах. Например: /log_workout бег 30")
        return

    workout_type = args[1].lower()
    duration = int(args[2])

    if workout_type not in WORKOUT_CALORIES:
        await message.answer(f"Неизвестный тип тренировки: {workout_type}. Доступные тренировки: {', '.join(WORKOUT_CALORIES.keys())}")
        return

    calories_burned = WORKOUT_CALORIES[workout_type] * duration
    additional_water = round(duration * 6)

    users[user_id]["burned_calories"] = users[user_id].get("burned_calories", 0) + calories_burned
    users[user_id]["logged_water"] = users[user_id].get("logged_water", 0) + additional_water
    logger.info(f"Команда /log_workout вызвана пользователем")
    await message.answer(
        f"🏋️‍♂️ {workout_type.capitalize()} {duration} минут — {calories_burned} ккал сожжено.\n"
        f"Дополнительно: выпейте {additional_water} мл воды!"
    )


@dp.message(Command("water_stat"))
async def water_stat(message: Message):
    user_id = message.from_user.id
    if user_id not in users:
        await message.answer("Сначала настройте профиль с помощью команды /set_profile.")
        return

    water_goal = users[user_id]["water_goal"]
    logged_water = users[user_id].get("logged_water", 0)

    buf = plot_water_stat(water_goal, logged_water)
    file_data = buf.getvalue()
    buf.close()
    with NamedTemporaryFile(delete=False, suffix=".png") as temp:
        temp.write(file_data)
        temp_path = temp.name
    logger.info(f"Команда /water_stat вызвана пользователем")
    photo = FSInputFile(path=temp_path, filename="water_stat.png")
    await message.answer_document(document=photo, caption="Ваш прогресс по воде 📊")
    buf.close()


@dp.message(Command("food_stat"))
async def food_stat(message: Message):
    user_id = message.from_user.id
    if user_id not in users:
        await message.answer("Сначала настройте профиль с помощью команды /set_profile.")
        return

    calorie_goal = users[user_id]["calorie_goal"]
    logged_calories = users[user_id].get("logged_calories", 0)
    burned_calories = users[user_id].get("burned_calories", 0)

    buf = plot_calorie_stat(logged_calories, burned_calories, calorie_goal)
    file_data = buf.getvalue()
    buf.close()
    with NamedTemporaryFile(delete=False, suffix=".png") as temp:
        temp.write(file_data)
        temp_path = temp.name
    logger.info(f"Команда /food_stat вызвана пользователем")
    photo = FSInputFile(path=temp_path, filename="food_stat.png")
    await message.answer_document(document=photo, caption="Ваш прогресс по калориям 📊")
    buf.close()


async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
