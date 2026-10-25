import os
import shutil
import subprocess
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, FSInputFile

# Укажите токен вашего бота
TOKEN = "YOUR_BOT_TOKEN"

bot = Bot(token=TOKEN)
dp = Dispatcher()

# Определяем шаги FSM (конечного автомата)
class ConvertState(StatesGroup):
    waiting_for_py_file = State()
    waiting_for_icon = State()
    waiting_for_format = State()

# Хранилище данных пользователей (на хостинге лучше использовать БД, но для примера сойдет словарь)
user_data_store = {}

@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "👋 Привет! Я бот-компилятор.\n\n"
        "1️⃣ Отправь мне свой файл с расширением **.py**."
    )
    await state.set_state(ConvertState.waiting_for_py_file)

# 1. Шаг: Принимаем .py файл
@dp.message(ConvertState.waiting_for_py_file, F.document)
async def handle_py_file(message: types.Message, state: FSMContext):
    document = message.document
    
    if not document.file_name.endswith('.py'):
        await message.answer("❌ Пожалуйста, отправьте файл именно с расширением **.py**.")
        return

    user_id = message.from_user.id
    user_dir = os.path.join("temp", str(user_id))
    os.makedirs(user_dir, exist_ok=True)

    file_path = os.path.join(user_dir, document.file_name)
    file_info = await bot.get_file(document.file_id)
    await bot.download_file(file_info.file_path, file_path)

    # Сохраняем путь в состояние пользователя
    await state.update_data(py_file=file_path, py_name=document.file_name)

    # Переходим к запросу иконки
    await state.set_state(ConvertState.waiting_for_icon)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏩ Пропустить (без иконки)", callback_data="skip_icon")]
    ])
    
    await message.answer(
        "✅ Скрипт получен!\n\n"
        "2️⃣ Теперь отправь **иконку** для приложения (картинку в формате **.ico** или **.png**).\n"
        "Или нажми кнопку ниже, чтобы собрать без иконки.",
        reply_markup=keyboard
    )

# 2. Шаг: Принимаем иконку (если отправили фото или документ)
@dp.message(ConvertState.waiting_for_icon, F.document | F.photo)
async def handle_icon(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    user_dir = os.path.join("temp", str(user_id))
    
    icon_path = ""
    if message.document:
        if not message.document.file_name.lower().endswith(('.ico', '.png', '.jpg', '.jpeg')):
            await message.answer("❌ Неверный формат. Отправьте файл картинки (.ico или .png).")
            return
        icon_path = os.path.join(user_dir, message.document.file_name)
        file_info = await bot.get_file(message.document.file_id)
        await bot.download_file(file_info.file_path, icon_path)
    elif message.photo:
        # Берем фото наилучшего качества
        photo = message.photo[-1]
        icon_path = os.path.join(user_dir, "icon.png")
        file_info = await bot.get_file(photo.file_id)
        await bot.download_file(file_info.file_path, icon_path)

    await state.update_data(icon_file=icon_path)
    await ask_format(message, state)

# Пропуск иконки по кнопке
@dp.callback_query(F.data == "skip_icon", ConvertState.waiting_for_icon)
async def skip_icon(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(icon_file=None)
    await callback.message.edit_text("⏩ Иконка пропущена.")
    # Отправляем сообщение с выбором формата
    await ask_format_callback(callback.message, state)
    await callback.answer()

async def ask_format(message: types.Message, state: FSMContext):
    await state.set_state(ConvertState.waiting_for_format)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🪟 Конвертировать в EXE (Windows)", callback_data="conv_exe")],
        [InlineKeyboardButton(text="🤖 Конвертировать в APK (Android)", callback_data="conv_apk")]
    ])
    await message.answer("3️⃣ Выберите конечный формат для компиляции:", reply_markup=keyboard)

async def ask_format_callback(message: types.Message, state: FSMContext):
    await state.set_state(ConvertState.waiting_for_format)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🪟 Конвертировать в EXE (Windows)", callback_data="conv_exe")],
        [InlineKeyboardButton(text="🤖 Конвертировать в APK (Android)", callback_data="conv_apk")]
    ])
    await message.answer("3️⃣ Выберите конечный формат для компиляции:", reply_markup=keyboard)

# 3. Шаг: Обработка выбора формата и компиляция
@dp.callback_query(F.data.startswith("conv_"), ConvertState.waiting_for_format)
async def process_conversion(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    py_file = data.get("py_file")
    icon_file = data.get("icon_file")
    action = callback.data.split("_")[1]

    user_id = callback.from_user.id
    user_dir = os.path.join("temp", str(user_id))

    await callback.message.edit_text("⏳ Идет сборка приложения, пожалуйста, подождите...")

    if action == "exe":
        try:
            # Формируем команду для PyInstaller
            cmd = ["pyinstaller", "--onefile", "--noconsole"]
            
            # Если есть иконка, добавляем ее в аргументы
            if icon_file and os.path.exists(icon_file):
                # PyInstaller для EXE лучше всего принимает именно .ico файлы
                cmd.extend(["--icon", icon_file])
            
            cmd.append(py_file)

            # Запуск сборки
            subprocess.run(cmd, check=True)
            
            base_name = os.path.splitext(os.path.basename(py_file))[0]
            exe_path = os.path.join("dist", f"{base_name}.exe")

            if os.path.exists(exe_path):
                await callback.message.answer_document(
                    FSInputFile(exe_path), 
                    caption="🎉 Готово! Ваш EXE файл успешно собран."
                )
            else:
                await callback.message.answer("❌ Ошибка: скомпилированный EXE файл не найден.")
        except subprocess.CalledProcessError as e:
            await callback.message.answer(f"❌ Ошибка сборки через PyInstaller:\n`{e}`")
        except Exception as e:
            await callback.message.answer(f"❌ Произошла ошибка: {e}")

    elif action == "apk":
        await callback.message.answer(
            "⚠️ Сборка APK требует окружения Buildozer (Linux / Docker).\n"
            "Здесь вы можете подключить свой Docker-контейнер с Buildozer, передав ему пути к `py_file` и `icon_file`."
        )

    # Очистка временных файлов пользователя после работы
    try:
        if os.path.exists(user_dir):
            shutil.rmtree(user_dir)
    except Exception:
        pass

    await state.clear()
    await callback.answer()

if __name__ == "__main__":
    import asyncio
    print("Бот запущен на хостинге...")
    asyncio.run(dp.start_polling(bot))