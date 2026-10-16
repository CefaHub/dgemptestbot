"""Regression coverage: Spotlight browsing uses one Telegram message at a time."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from dolce_empire import bot


class FakeMessage:
    def __init__(self, photo=True):
        self.photo = [object()] if photo else None
        self.edit_media = AsyncMock()
        self.edit_caption = AsyncMock()
        self.answer_photo = AsyncMock()
        self.answer = AsyncMock()


class FakeCallback:
    def __init__(self, photo=True):
        self.message = FakeMessage(photo=photo)
        self.bot = SimpleNamespace(send_photo=AsyncMock(), send_message=AsyncMock())
        self.from_user = SimpleNamespace(id=123)
        self.answer = AsyncMock()


def patch_types(monkeypatch):
    monkeypatch.setattr(bot, "CallbackQuery", FakeCallback)
    monkeypatch.setattr(bot, "Message", FakeMessage)


@pytest.mark.asyncio
async def test_command_sends_only_first_set(monkeypatch):
    patch_types(monkeypatch)
    event = FakeMessage()
    await bot.show_spotlight(event)
    event.answer_photo.assert_awaited_once()
    caption = event.answer_photo.await_args.kwargs["caption"]
    assert "ILLIT" in caption and "1/2" in caption
    markup = event.answer_photo.await_args.kwargs["reply_markup"]
    callbacks = [btn.callback_data for row in markup.inline_keyboard for btn in row]
    assert "spotlight:1" in callbacks


@pytest.mark.asyncio
async def test_arrows_edit_existing_photo_no_extra_messages(monkeypatch):
    patch_types(monkeypatch)
    event = FakeCallback(photo=True)
    await bot.show_spotlight(event, 1)
    event.answer.assert_awaited_once()
    event.message.edit_media.assert_awaited_once()
    event.bot.send_photo.assert_not_awaited()
    event.bot.send_message.assert_not_awaited()
    media = event.message.edit_media.await_args.kwargs["media"]
    assert "aespa" in media.caption
    assert "2/2" in media.caption
    markup = event.message.edit_media.await_args.kwargs["reply_markup"]
    nav = markup.inline_keyboard[0]
    assert [b.callback_data for b in nav] == ["spotlight:0", "spotlight:0"]


@pytest.mark.asyncio
async def test_main_menu_button_opens_one_photo(monkeypatch):
    patch_types(monkeypatch)
    event = FakeCallback(photo=False)
    await bot.show_spotlight(event, 0)
    event.bot.send_photo.assert_awaited_once()
    event.bot.send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_invalid_spotlight_page(monkeypatch):
    patch_types(monkeypatch)
    with pytest.raises(bot.GameError):
        await bot.show_spotlight(FakeCallback(), 2)
