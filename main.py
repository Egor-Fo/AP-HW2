import logging
import requests
import asyncio
from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram import BaseMiddleware
from aiogram.types import Update, Message, CallbackQuery
from datetime import datetime
import os
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage

logging.basicConfig(level=logging.INFO)

TOKEN_TG = os.getenv("TOKEN_TG")
OPENWEATHERMAP_API_KEY = os.getenv("OPENWEATHERMAP_API_KEY")

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


def get_weather(city: str) -> float:
    url = f"http://api.openweathermap.org/data/2.5/weather?q={city}&appid={WEATHER_TOKEN}&units=metric"
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        return data["main"]["temp"]
    else:
        raise Exception(f"Ошибка погоды: {response.json().get('message', 'Неизвестная ошибка')}")


def calculate_norms(weight: int, height: int, age: int, activity_minutes: int, temperature: float):
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


@dp.message(Command("set_profile"))
async def set_profile(message: Message, state: FSMContext):
    await message.answer("Введите ваш вес (в кг):")
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
    await message.answer("Бот успешно запущен! 🟢")


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

    await message.answer(f"Вы выпили {users[user_id]['logged_water']} мл воды. Осталось: {remaining} мл.")


@dp.message(Command("log_food"))
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

    await message.answer(
        f"🏋️‍♂️ {workout_type.capitalize()} {duration} минут — {calories_burned} ккал сожжено.\n"
        f"Дополнительно: выпейте {additional_water} мл воды!"
    )


async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
