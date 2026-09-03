"""Tests for entry setup and teardown."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from aqualia import async_reload_entry, async_setup_entry, async_unload_entry
from aqualia.const import DOMAIN


def _hass() -> MagicMock:
    hass = MagicMock()
    hass.data = {}
    hass.config_entries.async_forward_entry_setups = AsyncMock()
    hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)
    hass.config_entries.async_reload = AsyncMock()

    async def _executor(func, *args):
        return func(*args)

    hass.async_add_executor_job = _executor
    return hass


def _entry() -> MagicMock:
    entry = MagicMock()
    entry.entry_id = "abc"
    entry.data = {"nif": "12345678A", "password": "pw"}
    entry.options = {}
    return entry


class TestSetupEntry:
    @pytest.mark.asyncio
    async def test_stores_coordinator_and_forwards_platforms(self):
        hass, entry = _hass(), _entry()
        coordinator = MagicMock()
        coordinator.async_config_entry_first_refresh = AsyncMock()
        with patch("aqualia.AqualiaClient"), patch(
            "aqualia.AqualiaDataUpdateCoordinator", return_value=coordinator
        ):
            assert await async_setup_entry(hass, entry) is True

        assert hass.data[DOMAIN]["abc"] is coordinator
        hass.config_entries.async_forward_entry_setups.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_registers_reload_listener_for_options_changes(self):
        hass, entry = _hass(), _entry()
        coordinator = MagicMock()
        coordinator.async_config_entry_first_refresh = AsyncMock()
        with patch("aqualia.AqualiaClient"), patch(
            "aqualia.AqualiaDataUpdateCoordinator", return_value=coordinator
        ):
            await async_setup_entry(hass, entry)

        entry.add_update_listener.assert_called_once_with(async_reload_entry)
        entry.async_on_unload.assert_called_once()

    @pytest.mark.asyncio
    async def test_closes_client_when_first_refresh_fails(self):
        """A failed setup must not leak the requests session."""
        hass, entry = _hass(), _entry()
        client = MagicMock()
        coordinator = MagicMock()
        coordinator.async_config_entry_first_refresh = AsyncMock(
            side_effect=RuntimeError("no hay red")
        )
        with patch("aqualia.AqualiaClient", return_value=client), patch(
            "aqualia.AqualiaDataUpdateCoordinator", return_value=coordinator
        ):
            with pytest.raises(RuntimeError):
                await async_setup_entry(hass, entry)

        client.close.assert_called_once()
        assert DOMAIN not in hass.data


class TestUnloadEntry:
    @pytest.mark.asyncio
    async def test_pops_coordinator_and_closes_client(self):
        hass, entry = _hass(), _entry()
        coordinator = MagicMock()
        hass.data[DOMAIN] = {"abc": coordinator}

        assert await async_unload_entry(hass, entry) is True
        assert hass.data[DOMAIN] == {}
        coordinator.client.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_keeps_coordinator_when_platform_unload_fails(self):
        hass, entry = _hass(), _entry()
        hass.config_entries.async_unload_platforms = AsyncMock(return_value=False)
        coordinator = MagicMock()
        hass.data[DOMAIN] = {"abc": coordinator}

        assert await async_unload_entry(hass, entry) is False
        assert hass.data[DOMAIN] == {"abc": coordinator}
        coordinator.client.close.assert_not_called()


class TestReloadEntry:
    @pytest.mark.asyncio
    async def test_reloads_the_entry(self):
        hass, entry = _hass(), _entry()
        await async_reload_entry(hass, entry)
        hass.config_entries.async_reload.assert_awaited_once_with("abc")
