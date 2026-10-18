"""Fail-closed validation for complete member sets with traceable real photo sources."""
import hashlib
import json
from urllib.parse import urlsplit, unquote
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SETS_FILE = ROOT / 'assets' / 'collections' / 'verified_sets.json'
SOURCES_FILE = ROOT / 'tools' / 'photo_sources.json'


def canonical_photo_page(page):
    parsed = urlsplit(page)
    return (parsed.netloc.lower(), unquote(parsed.path).replace('_', ' ').strip().casefold())


def validate_photo_sets(cards):
    manifest = json.loads(SETS_FILE.read_text(encoding='utf-8'))
    source_data = json.loads(SOURCES_FILE.read_text(encoding='utf-8'))
    source_index = {'card_' + s['id']: s for s in source_data['cards']}
    allowed_ids = set()
    all_source_images = set()
    all_source_urls = set()
    all_source_fingerprints = set()
    member_photo_registry = set()
    checksums = set()

    if not manifest.get('sets'):
        raise ValueError('No verified photo sets are available')
    for series in manifest['sets']:
        group = series['group']
        expected = series['expected_members']
        members = [c for c in cards if c.get('collection_id') == series['set_id']]
        if len(members) != len(expected) or len(members) != len(set(expected)):
            raise ValueError(f'Incomplete photo set {group}: {len(members)} / {len(expected)}')
        if {c['idol'].upper() for c in members} != set(expected):
            raise ValueError(f'Duplicate or incorrect member in {group}')
        if any(c['group'] != group or c['era'] != series['era']
               or c['rarity'] != series['rarity'] for c in members):
            raise ValueError(f'Mixed rarity or release metadata in {group}')
        if sorted(c['card_number'] for c in members) != list(range(1, len(expected) + 1)):
            raise ValueError(f'Invalid card numbering in {group}')
        for c in members:
            if c.get('set_id') != series['set_id'] or c.get('source_collection') != series['source_collection']:
                raise ValueError(f'Card not tagged with its verified source series: {c["id"]}')
            if c['id'] in allowed_ids or c.get('card_total') != len(expected):
                raise ValueError(f'Duplicate or incomplete card in {group}')
            source = source_index.get(c['id'])
            if source is None or source['member'] != c['idol'].upper():
                raise ValueError(f'Missing unique member source for {c["id"]}')
            if source['group'] != group:
                raise ValueError(f'Member source does not match group {group}')
            # Old released sets predate explicit session IDs, but every new
            # set with one must keep precisely the same session on each card.
            session_id = series.get('photo_session_id')
            if session_id and source.get('photo_session_id') != session_id:
                raise ValueError(f'Mixed photo sessions in published collection: {c["id"]}')
            # Legacy SPOTLIGHT sets are documented single-event photo series.
            # New curated sets may use different approved photographers, but
            # must visibly share the SAME editorial collection and one rarity.
            mode = series.get('source_mode', 'event')
            if mode == 'event':
                if source['author'] != series['photographer']:
                    raise ValueError(f'Mixed photographers in {group}')
            elif mode == 'curated':
                if not source.get('author') or not source.get('license'):
                    raise ValueError(f'Missing credited/rights-approved photo source: {c["id"]}')
                if source.get('license_review') != 'confirmed':
                    raise ValueError(f'Unapproved image rights for {c["id"]}')
            else:
                raise ValueError(f'Unknown photo source mode: {mode}')
            # Photo identity is global, not specific to a rarity, frame,
            # or set. Never re-issue the SAME source image as another card.
            # Canonicalize Wikimedia file paths so a URL query / encoding
            # change cannot masquerade as a new collectible.
            photo_id = unquote(source['page'].split('File:', 1)[-1]).replace('_', ' ').strip().casefold()
            source_url_path = unquote(urlsplit(source['photo']).path).replace('_', ' ').casefold()
            # Require one event identifier for same-event releases. A named
            # editorial photo collection is allowed to mix approved sources.
            if series.get('source_mode', 'event') == 'event':
                if series['source_key'].replace('_', ' ').casefold() not in photo_id:
                    raise ValueError(f'Mixed shooting dates/collections in {group}: {photo_id}')
            # For generic source sites, compare the full page location (not
            # just a filename which might coincide on unrelated providers).
            source_page_key = canonical_photo_page(source['page'])
            if source_page_key in all_source_images or source_url_path in all_source_urls:
                raise ValueError(f'Reused source photograph across cards or rarities: {photo_id}')
            all_source_images.add(source_page_key)
            all_source_urls.add(source_url_path)
            # Optional original-file hashes are strongly recommended for
            # future releases; catch reuploads under a second filename.
            original_hash = source.get('source_sha256')
            if original_hash:
                if original_hash in all_source_fingerprints:
                    raise ValueError(f'Reused photo binary under another rarity: {c["id"]}')
                all_source_fingerprints.add(original_hash)
            group_member = (group.casefold(), c['idol'].casefold(), photo_id)
            if group_member in member_photo_registry:
                raise ValueError(f'Same idol photo reused as a new card: {c["id"]}')
            member_photo_registry.add(group_member)
            path = ROOT / c['image_path']
            if not path.is_file():
                raise ValueError(f'Card has no rendered photo: {path}')
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if digest in checksums:
                raise ValueError(f'An identical card image is reused: {path}')
            checksums.add(digest)
            allowed_ids.add(c['id'])
        banner = ROOT / series['banner_path']
        if not banner.is_file():
            raise ValueError(f'Banner missing for {group}: {banner}')
    if {c['id'] for c in cards} != allowed_ids or len(cards) != len(allowed_ids):
        raise ValueError('Unverified or duplicated cards found in live catalog')
    return len(allowed_ids)
