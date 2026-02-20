import os
import asyncio
from dataclasses import dataclass
from typing import Dict, List
from io import BytesIO

from PIL import Image, ImageDraw, ImageFont
from aiogram.types import BufferedInputFile

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup


BOT_TOKEN = os.getenv("BOT_TOKEN")


@dataclass
class Item:
    name: str
    brand: str
    sku: str
    price: str
    lead_time: str


USER_ITEMS: Dict[int, List[Item]] = {}


class Form(StatesGroup):
    name = State()
    brand = State()
    sku = State()
    price = State()
    lead_time = State()


def menu_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="➕ Добавить позицию", callback_data="add")
    kb.button(text="↩️ Удалить последнюю", callback_data="pop")
    kb.button(text="🧹 Очистить", callback_data="clear")
    kb.adjust(2, 1)
    return kb.as_markup()


def render_table_png(items: List[Item]) -> BytesIO:
    headers = ["№", "Наименование", "Производитель", "Артикул", "Цена", "Срок поставки"]
    rows = [[str(i), it.name, it.brand, it.sku, it.price, it.lead_time]
            for i, it in enumerate(items, start=1)]

    # Подбор шрифта под Windows / Linux
    font = None
    for font_path in (
        "C:/Windows/Fonts/consola.ttf",   # Windows: Consolas
        "C:/Windows/Fonts/lucon.ttf",     # Windows: Lucida Console
        "C:/Windows/Fonts/cour.ttf",      # Windows: Courier New (иногда)
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",  # Linux
    ):
        try:
            font = ImageFont.truetype(font_path, 20)
            break
        except OSError:
            pass

    if font is None:
        font = ImageFont.load_default()

    padding_x = 14
    padding_y = 10
    border = 2

    # считаем ширины колонок по тексту
    dummy_img = Image.new("RGB", (10, 10))
    d = ImageDraw.Draw(dummy_img)

    def text_w(s: str) -> int:
        bbox = d.textbbox((0, 0), str(s), font=font)
        return bbox[2] - bbox[0]

    def text_h() -> int:
        bbox = d.textbbox((0, 0), "Ag", font=font)
        return bbox[3] - bbox[1]

    row_h = text_h() + padding_y * 2

    # ограничим ширину "Наименование", чтобы не делать гигантские картинки
    max_name_px = 520  # можно менять

    cols = list(zip(*([headers] + rows))) if rows else [headers]
    col_widths = []
    for i, col in enumerate(cols):
        w = max(text_w(x) for x in col) + padding_x * 2
        if headers[i] == "Наименование":
            w = min(w, max_name_px)
        col_widths.append(w)

    # функция подрезки текста по ширине колонки
    def fit_text(s: str, max_px: int) -> str:
        s = str(s)
        if text_w(s) <= max_px:
            return s
        ell = "…"
        while s and text_w(s + ell) > max_px:
            s = s[:-1]
        return s + ell if s else ell

    # размеры картинки
    n_rows = 1 + len(rows)  # заголовок + данные
    width = sum(col_widths) + border * 2
    height = n_rows * row_h + border * 2

    img = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(img)

    # рамка внешняя
    draw.rectangle([0, 0, width - 1, height - 1], outline="black", width=border)

    # вертикальные линии
    x = border
    for w in col_widths[:-1]:
        x += w
        draw.line([(x, border), (x, height - border)], fill="black", width=border)

    # горизонтальные линии
    y = border + row_h
    draw.line([(border, y), (width - border, y)], fill="black", width=border)
    for _ in rows[:-1]:
        y += row_h
        draw.line([(border, y), (width - border, y)], fill="black", width=border)

    # печать ячеек
    def draw_row(y0: int, cells: List[str]):
        x0 = border
        for i, cell in enumerate(cells):
            w = col_widths[i]
            cell_max = w - padding_x * 2
            text = fit_text(cell, cell_max)
            draw.text((x0 + padding_x, y0 + padding_y), text, fill="black", font=font)
            x0 += w

    draw_row(border, headers)
    y = border + row_h
    for r in rows:
        draw_row(y, r)
        y += row_h

    buf = BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


async def start(message: Message):
    USER_ITEMS.setdefault(message.from_user.id, [])
    await message.answer(
        "Ассаляму 'алейкум! Я собираю позиции запчастей в таблицу.\nНажмите «Добавить позицию».",
        reply_markup=menu_kb(),
    )


async def on_add(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(Form.name)
    await callback.message.answer("Введите наименование детали:")


async def on_pop(callback: CallbackQuery):
    await callback.answer()
    items = USER_ITEMS.setdefault(callback.from_user.id, [])
    if items:
        items.pop()

    if not items:
        await callback.message.answer("Текущая таблица: (пока пусто)", reply_markup=menu_kb())
        return

    buf = render_table_png(items)
    await callback.message.answer_photo(
        BufferedInputFile(buf.getvalue(), filename="table.png"),
        caption="Текущая таблица:",
        reply_markup=menu_kb()
    )


async def on_clear(callback: CallbackQuery):
    await callback.answer()
    USER_ITEMS[callback.from_user.id] = []
    await callback.message.answer("Очищено. Таблица пустая.", reply_markup=menu_kb())


async def form_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text.strip())
    await state.set_state(Form.brand)
    await message.answer("Введите производителя:")


async def form_brand(message: Message, state: FSMContext):
    await state.update_data(brand=message.text.strip())
    await state.set_state(Form.sku)
    await message.answer("Введите артикул детали:")


async def form_sku(message: Message, state: FSMContext):
    await state.update_data(sku=message.text.strip())
    await state.set_state(Form.price)
    await message.answer("Введите цену (например: 300):")


async def form_price(message: Message, state: FSMContext):
    raw = message.text.strip()

    if not raw.isdigit():
        await message.answer("Введите цену целым числом (например: 500)")
        return

    price_str = f"{int(raw)} ₽"
    await state.update_data(price=price_str)

    await state.set_state(Form.lead_time)
    await message.answer("Введите срок поставки (например: 2 раб. дня):")


async def form_lead_time(message: Message, state: FSMContext):
    data = await state.get_data()
    item = Item(
        name=data["name"],
        brand=data["brand"],
        sku=data["sku"],
        price=data["price"],
        lead_time=message.text.strip()
    )
    items = USER_ITEMS.setdefault(message.from_user.id, [])
    items.append(item)
    await state.clear()

    buf = render_table_png(items)
    await message.answer_photo(
        BufferedInputFile(buf.getvalue(), filename="table.png"),
        caption="✅ Добавлено!\nТекущая таблица:",
        reply_markup=menu_kb()
    )


async def main():
    bot = Bot(BOT_TOKEN)
    dp = Dispatcher()

    dp.message.register(start, Command("start"))
    dp.callback_query.register(on_add, F.data == "add")
    dp.callback_query.register(on_pop, F.data == "pop")
    dp.callback_query.register(on_clear, F.data == "clear")

    dp.message.register(form_name, Form.name)
    dp.message.register(form_brand, Form.brand)
    dp.message.register(form_sku, Form.sku)
    dp.message.register(form_price, Form.price)
    dp.message.register(form_lead_time, Form.lead_time)

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())