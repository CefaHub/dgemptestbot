"""The public GitHub gallery is discoverable from the Telegram bot."""
import pytest

from dolce_empire import bot
from dolce_empire.catalog import all_cards


class DummyMessage:
    def __init__(self):
        self.calls = []

    async def answer(self, text, **kwargs):
        self.calls.append((text, kwargs))


@pytest.mark.asyncio
async def test_gallery_command_shows_real_catalog_and_verified_link():
    message = DummyMessage()
    await bot.gallery_cmd(message)
    assert len(message.calls) == 1
    text, args = message.calls[0]
    assert f"{len(all_cards())}</b>" in text
    assert f"{len(bot.collection_gallery())}</b>" in text
    assert "ILLIT" in text and "aespa" in text
    assert args["parse_mode"] == "HTML"
    buttons = [b for row in args["reply_markup"].inline_keyboard for b in row]
    assert any(x.url == bot.GITHUB_GALLERY_URL for x in buttons)
    assert any(x.callback_data == "nav:sets" for x in buttons)


def test_gallery_link_is_repository_local_and_only_published_sets():
    assert bot.GITHUB_GALLERY_URL == (
        "https://github.com/CefaHub/dgemptestbot/blob/main/GALLERY.md"
    )
    live_ids = {c["collection_id"] for c in all_cards()}
    published_ids = {s["id"] for s in bot.collection_gallery()}
    assert live_ids == published_ids
