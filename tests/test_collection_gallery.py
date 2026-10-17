"""Every released real-photo set can be browsed card-by-card in Telegram."""
from pathlib import Path

import pytest
from PIL import Image

from dolce_empire import bot
from dolce_empire.service import GameError


def callbacks(markup):
    return [button.callback_data for row in markup.inline_keyboard for button in row]


def test_all_verified_sets_have_full_unique_browsable_portraits():
    gallery = bot.collection_gallery()
    assert len(gallery) >= 4
    rarities = {row["rarity"] for row in gallery}
    assert {"rare", "epic", "legendary"} <= rarities
    seen_art = set()
    for index, release in enumerate(gallery):
        cards = bot.collection_cards(index)
        assert len(cards) == release["size"]
        assert all(card["collection_id"] == release["id"] for card in cards)
        assert [card["card_number"] for card in cards] == list(range(1, len(cards) + 1))
        for card in cards:
            path = bot.Path(__file__).resolve().parents[1] / card["image_path"]
            assert path.is_file(), path
            assert path not in seen_art, f"Repeated card image: {path}"
            seen_art.add(path)
            with Image.open(path) as picture:
                assert picture.size == (900, 1200)
        banner = bot.Path(__file__).resolve().parents[1] / release["banner"]
        assert banner.is_file()
        with Image.open(banner) as picture:
            assert picture.size == (1600, 900)


class PhotoMessage:
    def __init__(self):
        self.sent = []

    async def answer_photo(self, image, **kwargs):
        self.sent.append((image, kwargs))


@pytest.mark.asyncio
async def test_set_banner_links_to_real_card_gallery_and_back():
    event = PhotoMessage()
    await bot.show_sets(event, 0)
    banner, options = event.sent[-1]
    assert Path(banner.path).is_file()
    assert "setcard:0:0" in callbacks(options["reply_markup"])

    await bot.show_set_card(event, 0, 0)
    card, options = event.sent[-1]
    assert Path(card.path).is_file()
    assert "Фото 1/" in options["caption"]
    assert "setcard:0:1" in callbacks(options["reply_markup"])
    last = len(bot.collection_cards(0)) - 1
    assert f"setcard:0:{last}" in callbacks(options["reply_markup"])
    assert "sets:0" in callbacks(options["reply_markup"])
    assert "nav:roll" in callbacks(options["reply_markup"])

    await bot.show_set_card(event, 0, last)
    last_card, options = event.sent[-1]
    assert last_card.path != card.path
    assert f"Фото {last + 1}/{last + 1}" in options["caption"]


@pytest.mark.asyncio
async def test_photos_edit_in_place_from_banner_to_card_and_back(monkeypatch):
    class ExistingPhoto:
        photo = [object()]

        def __init__(self):
            self.edits = []

        async def edit_media(self, **kwargs):
            self.edits.append(kwargs)

    class PhotoCallback:
        def __init__(self):
            self.message = ExistingPhoto()
            self.answers = []
            self.data = "setcard:0:0"

        async def answer(self, *args, **kwargs):
            self.answers.append((args, kwargs))

    monkeypatch.setattr(bot, "CallbackQuery", PhotoCallback)
    monkeypatch.setattr(bot, "Message", ExistingPhoto)

    event = PhotoCallback()
    await bot.show_sets(event, 0)
    await bot.setcard_callback(event)
    await bot.show_sets(event, 0)

    assert len(event.message.edits) == 3
    assert len(event.answers) == 3
    banner1, card, banner2 = [x["media"].media.path for x in event.message.edits]
    assert banner1 == banner2
    assert card != banner1
    assert Path(card).is_file()
    assert "setcard:0:1" in callbacks(event.message.edits[1]["reply_markup"])


@pytest.mark.asyncio
async def test_repeated_same_photo_does_not_send_a_duplicate(monkeypatch):
    class NotModified(Exception):
        pass

    class ExistingPhoto:
        photo = [object()]

        async def edit_media(self, **kwargs):
            raise NotModified("Bad Request: message is not modified")

    class CapturingBot:
        def __init__(self):
            self.sent = []

        async def send_photo(self, *args, **kwargs):
            self.sent.append((args, kwargs))

    class PhotoCallback:
        def __init__(self):
            self.message = ExistingPhoto()
            self.bot = CapturingBot()
            self.from_user = type("User", (), {"id": 123})()
            self.answers = []

        async def answer(self, *args, **kwargs):
            self.answers.append((args, kwargs))

    monkeypatch.setattr(bot, "TelegramBadRequest", NotModified)
    monkeypatch.setattr(bot, "CallbackQuery", PhotoCallback)
    monkeypatch.setattr(bot, "Message", ExistingPhoto)
    event = PhotoCallback()
    await bot.show_set_card(event, 0, 0)
    assert len(event.answers) == 1
    assert event.bot.sent == []


@pytest.mark.asyncio
async def test_invalid_pages_and_missing_artwork_fail_closed(tmp_path):
    with pytest.raises(GameError, match="коллекции"):
        bot.collection_cards(-1)
    with pytest.raises(GameError, match="коллекции"):
        bot.collection_cards(10_000)
    with pytest.raises(GameError, match="карточки"):
        await bot.show_set_card(PhotoMessage(), 0, 10_000)
    with pytest.raises(GameError, match="Фото временно недоступно"):
        await bot.show_gallery_image(
            PhotoMessage(), tmp_path / "missing.png", "caption", None
        )


@pytest.mark.asyncio
async def test_bad_photo_callback_indices_are_rejected():
    class Callback:
        def __init__(self, data):
            self.data = data

    for data in ("setcard:", "setcard:0:", "setcard:x:1", "setcard:-1:0",
                 "setcard:0:1:extra", "setcard:0:/start"):
        with pytest.raises(GameError, match="Неверный номер"):
            await bot.setcard_callback(Callback(data))
