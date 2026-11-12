"""Tray icon abstraction on top of the StatusNotifierItem D-Bus layer."""

from __future__ import annotations

import asyncio
import itertools
import os
from collections.abc import Callable
from enum import Enum

from dbus_next.aio.message_bus import MessageBus
from dbus_next.constants import BusType

from .tb_icon_source import IconSource, TB_Icon
from .tb_status_notifier_item import (
    SNI_PATH,
    TB_StatusNotifierItem,
    TB_StatusNotifierWatcherClient,
)
from .tb_tray_menu import TB_TrayMenu


class TB_TrayCategory(str, Enum):
    """StatusNotifierItem categories."""

    APPLICATION = "ApplicationStatus"
    COMMUNICATIONS = "Communications"
    SYSTEM_SERVICES = "SystemServices"
    HARDWARE = "Hardware"


class TB_TrayStatus(str, Enum):
    """StatusNotifierItem states."""

    PASSIVE = "Passive"
    ACTIVE = "Active"
    NEEDS_ATTENTION = "NeedsAttention"


class TB_TrayIcon:
    """System tray icon with context menu; setters may be called from any thread."""

    _counter = itertools.count(1)

    def __init__(
        self,
        app_id: str,
        title: str = "",
        category: TB_TrayCategory = TB_TrayCategory.APPLICATION,
    ) -> None:
        """Create the icon; call ``start`` inside the asyncio loop to show it."""
        self.on_activate: Callable[[int, int], None] | None = None
        self.on_secondary_activate: Callable[[int, int], None] | None = None
        self.on_context_menu: Callable[[int, int], None] | None = None
        self.on_scroll: Callable[[int, str], None] | None = None
        self.on_xdg_activation_token: Callable[[str], None] | None = None

        self._service_name = f"org.kde.StatusNotifierItem-{os.getpid()}-{next(TB_TrayIcon._counter)}"
        self._item = TB_StatusNotifierItem(app_id, title, category.value)
        self._item.on_activate = self._handle_activate
        self._item.on_secondary_activate = self._handle_secondary_activate
        self._item.on_context_menu = self._handle_context_menu
        self._item.on_scroll = self._handle_scroll
        self._item.on_xdg_activation_token = self._handle_xdg_activation_token

        self._menu = TB_TrayMenu()
        self._menu.set_dispatcher(self._post)
        self._item.set_menu_path(self._menu.path)

        self._bus: MessageBus | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._watcher: TB_StatusNotifierWatcherClient | None = None

    @property
    def menu(self) -> TB_TrayMenu:
        """Return the context menu."""
        return self._menu

    # ------------------------------------------------------------------ lifecycle

    async def start(self) -> None:
        """Connect to the session bus, export the objects and register with the watcher."""
        if self._bus is not None:
            return
        self._loop = asyncio.get_running_loop()
        bus = await MessageBus(bus_type=BusType.SESSION).connect()
        bus.export(SNI_PATH, self._item)
        self._menu.export(bus)
        await bus.request_name(self._service_name)
        self._watcher = TB_StatusNotifierWatcherClient(bus, self._service_name)
        await self._watcher.start_monitoring()
        await self._watcher.register()
        self._bus = bus

    async def stop(self) -> None:
        """Remove the icon and disconnect from the bus."""
        bus = self._bus
        if bus is None:
            return
        self._bus = None
        if self._watcher is not None:
            self._watcher.stop_monitoring()
            self._watcher = None
        self._menu.unexport(bus)
        bus.unexport(SNI_PATH, self._item)
        bus.disconnect()
        await bus.wait_for_disconnect()
        self._loop = None

    # -------------------------------------------------------------------- setters

    def set_icon(self, icon: IconSource) -> None:
        """Set the main icon from a theme name, file path, image bytes or PIL image."""
        resolved = TB_Icon.of(icon)
        name, pixmaps = resolved.name, resolved.to_pixmaps()
        self._post(lambda: self._item.set_icon(name, pixmaps))

    def set_overlay_icon(self, icon: IconSource | None = None) -> None:
        """Set the overlay icon drawn on top of the main icon (None removes it)."""
        resolved = TB_Icon.of(icon)
        name, pixmaps = resolved.name, resolved.to_pixmaps()
        self._post(lambda: self._item.set_overlay_icon(name, pixmaps))

    def set_attention_icon(self, icon: IconSource | None = None) -> None:
        """Set the icon shown while the status is NeedsAttention (None removes it)."""
        resolved = TB_Icon.of(icon)
        name, pixmaps = resolved.name, resolved.to_pixmaps()
        self._post(lambda: self._item.set_attention_icon(name, pixmaps))

    def set_title(self, title: str) -> None:
        """Set the icon title."""
        self._post(lambda: self._item.set_title(title))

    def set_status(self, status: TB_TrayStatus) -> None:
        """Set the icon status."""
        self._post(lambda: self._item.set_status(status.value))

    def set_tooltip(self, title: str, description: str = "", icon: IconSource | None = None) -> None:
        """Set the tooltip text and an optional tooltip icon."""
        resolved = TB_Icon.of(icon)
        name, pixmaps = resolved.name, resolved.to_pixmaps()
        self._post(lambda: self._item.set_tooltip(title, description, name, pixmaps))

    def set_icon_accessible_desc(self, description: str) -> None:
        """Set the accessible description of the icon for screen readers."""
        self._post(lambda: self._item.set_icon_accessible_desc(description))

    def set_attention_accessible_desc(self, description: str) -> None:
        """Set the accessible description of the attention icon."""
        self._post(lambda: self._item.set_attention_accessible_desc(description))

    def set_label(self, label: str, guide: str = "") -> None:
        """Set a text shown next to the icon (only some hosts display it)."""
        self._post(lambda: self._item.set_label(label, guide))

    def set_ordering_index(self, index: int) -> None:
        """Set the sort index among tray items (only some hosts use it)."""
        self._post(lambda: self._item.set_ordering_index(index))

    def set_icon_theme_path(self, path: str) -> None:
        """Add a directory searched for themed icons."""
        self._post(lambda: self._item.set_icon_theme_path(path))

    def set_menu_on_activate(self, value: bool) -> None:
        """Let the host open the menu on left click instead of calling ``on_activate``."""
        self._post(lambda: self._item.set_item_is_menu(value))

    # ------------------------------------------------------------------ internals

    def _post(self, func: Callable[[], None]) -> None:
        """Run ``func`` in the asyncio thread; calls keep their order (FIFO)."""
        loop = self._loop
        if loop is None:
            func()
        else:
            loop.call_soon_threadsafe(func)

    def _handle_activate(self, x: int, y: int) -> None:
        """Forward a primary activation to ``on_activate``."""
        if self.on_activate is not None:
            self.on_activate(x, y)

    def _handle_secondary_activate(self, x: int, y: int) -> None:
        """Forward a secondary activation to ``on_secondary_activate``."""
        if self.on_secondary_activate is not None:
            self.on_secondary_activate(x, y)

    def _handle_context_menu(self, x: int, y: int) -> None:
        """Forward a context menu request to ``on_context_menu``."""
        if self.on_context_menu is not None:
            self.on_context_menu(x, y)

    def _handle_xdg_activation_token(self, token: str) -> None:
        """Forward an xdg-activation token to ``on_xdg_activation_token``."""
        if self.on_xdg_activation_token is not None:
            self.on_xdg_activation_token(token)

    def _handle_scroll(self, delta: int, orientation: str) -> None:
        """Forward a scroll event to ``on_scroll``."""
        if self.on_scroll is not None:
            self.on_scroll(delta, orientation)
