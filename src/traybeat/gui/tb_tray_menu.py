"""Context menu abstraction on top of the dbusmenu D-Bus layer."""

from __future__ import annotations

from collections.abc import Callable
from enum import Enum
from typing import Any

from dbus_next.aio.message_bus import MessageBus
from dbus_next.signature import Variant

from .tb_icon_source import IconSource, TB_Icon
from .tb_status_notifier_item import DBUSMENU_PATH, TB_DBusMenu, TB_DBusMenuNode

_MODIFIERS = {
    "ctrl": "Control",
    "control": "Control",
    "alt": "Alt",
    "shift": "Shift",
    "super": "Super",
    "meta": "Super",
    "win": "Super",
}


class TB_ToggleType(str, Enum):
    """Toggle behaviour of a menu item."""

    NONE = ""
    CHECKMARK = "checkmark"
    RADIO = "radio"


class TB_Disposition(str, Enum):
    """Hint how the host should present a menu item."""

    NORMAL = "normal"
    INFORMATIVE = "informative"
    WARNING = "warning"
    ALERT = "alert"


def _parse_shortcut(text: str) -> list[list[str]]:
    """Convert "Ctrl+Q" or "Ctrl+K, Ctrl+C" into the dbusmenu ``aas`` form."""
    chords: list[list[str]] = []
    for chord in text.split(","):
        keys = [part.strip() for part in chord.split("+") if part.strip()]
        if keys:
            chords.append([_MODIFIERS.get(key.lower(), key) for key in keys])
    return chords


class TB_MenuItem:
    """A single menu entry; items with children act as submenus."""

    def __init__(
        self,
        label: str = "",
        callback: Callable[[TB_MenuItem], None] | None = None,
        *,
        enabled: bool = True,
        visible: bool = True,
        icon: IconSource | None = None,
        shortcut: str = "",
        disposition: TB_Disposition = TB_Disposition.NORMAL,
        toggle_type: TB_ToggleType = TB_ToggleType.NONE,
        checked: bool = False,
        separator: bool = False,
        user_data: Any = None,
    ) -> None:
        """Create an item; prefer ``add_item`` / ``add_separator`` of a parent instead."""
        self.callback = callback
        self.user_data: Any = user_data
        """Arbitrary application data attached to this item (never sent over D-Bus)."""
        self._menu: TB_TrayMenu | None = None
        self._parent: TB_MenuItem | None = None
        self._id = -1
        self._children: list[TB_MenuItem] = []
        self._label = label
        self._enabled = enabled
        self._visible = visible
        self._icon = TB_Icon.of(icon)
        self._shortcut = shortcut
        self._disposition = disposition
        self._toggle_type = toggle_type
        self._checked = checked
        self._separator = separator
        self._sent_keys: set[str] = set()

    # ------------------------------------------------------------------ accessors

    @property
    def id(self) -> int:
        """Return the dbusmenu id (-1 while not attached to a menu)."""
        return self._id

    @property
    def children(self) -> tuple[TB_MenuItem, ...]:
        """Return the child items."""
        return tuple(self._children)

    @property
    def label(self) -> str:
        """Return the label."""
        return self._label

    @label.setter
    def label(self, value: str) -> None:
        """Set the label and update the host."""
        self._label = value
        self._changed()

    @property
    def enabled(self) -> bool:
        """Return whether the item is clickable."""
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        """Enable or disable the item."""
        self._enabled = value
        self._changed()

    @property
    def visible(self) -> bool:
        """Return whether the item is shown."""
        return self._visible

    @visible.setter
    def visible(self, value: bool) -> None:
        """Show or hide the item."""
        self._visible = value
        self._changed()

    @property
    def icon(self) -> TB_Icon:
        """Return the item icon."""
        return self._icon

    @icon.setter
    def icon(self, value: IconSource | None) -> None:
        """Set the icon from a theme name, file path, image bytes or PIL image."""
        self._icon = TB_Icon.of(value)
        self._changed()

    @property
    def shortcut(self) -> str:
        """Return the displayed shortcut, e.g. "Ctrl+Q"."""
        return self._shortcut

    @shortcut.setter
    def shortcut(self, value: str) -> None:
        """Set the displayed shortcut (display only, the host does not trigger it)."""
        self._shortcut = value
        self._changed()

    @property
    def disposition(self) -> TB_Disposition:
        """Return the presentation hint."""
        return self._disposition

    @disposition.setter
    def disposition(self, value: TB_Disposition) -> None:
        """Set the presentation hint."""
        self._disposition = value
        self._changed()

    @property
    def checked(self) -> bool:
        """Return the toggle state of checkmark/radio items."""
        return self._checked

    @checked.setter
    def checked(self, value: bool) -> None:
        """Set the toggle state."""
        self._checked = value
        self._changed()

    # ------------------------------------------------------------------ tree API

    def append(self, item: TB_MenuItem):
        self._append(item)
        return item

    def add_item(
        self,
        label: str,
        callback: Callable[[TB_MenuItem], None] | None = None,
        *,
        enabled: bool = True,
        visible: bool = True,
        icon: IconSource | None = None,
        shortcut: str = "",
        disposition: TB_Disposition = TB_Disposition.NORMAL,
        toggle_type: TB_ToggleType = TB_ToggleType.NONE,
        checked: bool = False,
        user_data: Any = None,
    ) -> TB_MenuItem:
        """Append a child item and return it; add children to it to build a submenu."""
        item = TB_MenuItem(
            label,
            callback,
            enabled=enabled,
            visible=visible,
            icon=icon,
            shortcut=shortcut,
            disposition=disposition,
            toggle_type=toggle_type,
            checked=checked,
            user_data=user_data,
        )
        self._append(item)
        return item

    def add_separator(self) -> TB_MenuItem:
        """Append a separator line and return it."""
        item = TB_MenuItem(separator=True)
        self._append(item)
        return item

    def remove_item(self, item: TB_MenuItem) -> None:
        """Remove a direct child item."""
        if item not in self._children:
            return
        self._children.remove(item)
        item._parent = None
        if self._menu is not None:
            self._menu._detach(item)  # pyright: ignore[reportPrivateUsage]
            self._menu._notify_layout(self._id)  # pyright: ignore[reportPrivateUsage]

    def clear(self) -> None:
        """Remove all child items."""
        children, self._children = self._children, []
        for item in children:
            item._parent = None
            if self._menu is not None:
                self._menu._detach(item)  # pyright: ignore[reportPrivateUsage]
        if self._menu is not None:
            self._menu._notify_layout(self._id)  # pyright: ignore[reportPrivateUsage]

    # ------------------------------------------------------------------ internals

    def _append(self, item: TB_MenuItem) -> None:
        """Attach ``item`` as last child and announce the layout change."""
        item._parent = self
        self._children.append(item)
        if self._menu is not None:
            self._menu._attach(item)  # pyright: ignore[reportPrivateUsage]
            self._menu._notify_layout(self._id)  # pyright: ignore[reportPrivateUsage]

    def _changed(self) -> None:
        """Announce changed properties of this item to the host."""
        if self._menu is not None:
            self._menu._notify_properties(self)  # pyright: ignore[reportPrivateUsage]

    def _click(self) -> None:
        """Toggle checkmark items and run the callback."""
        if self._toggle_type is TB_ToggleType.CHECKMARK:
            self.checked = not self._checked
        if self.callback is not None:
            self.callback(self)

    def _properties(self) -> dict[str, Variant]:
        """Return the non-default dbusmenu properties of this item."""
        if self._separator:
            properties = {"type": Variant("s", "separator"), "visible": Variant("b", self._visible)}
        else:
            properties = {
                "label": Variant("s", self._label.replace("_", "__")),
                "enabled": Variant("b", self._enabled),
                "visible": Variant("b", self._visible),
            }
            if self._icon.name:
                properties["icon-name"] = Variant("s", self._icon.name)
            if self._icon.has_image:
                properties["icon-data"] = Variant("ay", self._icon.to_png())
            if self._shortcut:
                properties["shortcut"] = Variant("aas", _parse_shortcut(self._shortcut))
            if self._disposition is not TB_Disposition.NORMAL:
                properties["disposition"] = Variant("s", self._disposition.value)
            if self._toggle_type is not TB_ToggleType.NONE:
                properties["toggle-type"] = Variant("s", self._toggle_type.value)
                properties["toggle-state"] = Variant("i", int(self._checked))
            if self._children:
                properties["children-display"] = Variant("s", "submenu")
        self._sent_keys = set(properties)
        return properties

    def _to_node(self) -> TB_DBusMenuNode:
        """Convert this item and its children into dbusmenu nodes."""
        return TB_DBusMenuNode(self._id, self._properties(), [child._to_node() for child in self._children])


class TB_TrayMenu(TB_MenuItem):
    """Context menu of a tray icon; also the invisible root item of the menu tree."""

    def __init__(self) -> None:
        """Create an empty menu and its dbusmenu interface."""
        super().__init__()
        self._id = 0
        self._menu = self
        self._items: dict[int, TB_MenuItem] = {0: self}
        self._next_id = 1
        self._dispatch: Callable[[Callable[[], None]], None] = lambda func: func()
        self._dbus_menu = TB_DBusMenu(self._to_node)
        self._dbus_menu.on_event = self._on_event

    def set_dispatcher(self, dispatcher: Callable[[Callable[[], None]], None]) -> None:
        """Set the function that runs D-Bus notifications on the asyncio thread."""
        self._dispatch = dispatcher

    def export(self, bus: MessageBus) -> None:
        """Export the dbusmenu object on ``bus``."""
        bus.export(DBUSMENU_PATH, self._dbus_menu)

    def unexport(self, bus: MessageBus) -> None:
        """Remove the dbusmenu object from ``bus``."""
        bus.unexport(DBUSMENU_PATH, self._dbus_menu)

    @property
    def path(self) -> str:
        """Return the D-Bus object path of the menu."""
        return DBUSMENU_PATH

    def _properties(self) -> dict[str, Variant]:
        """Return the properties of the root item."""
        return {"children-display": Variant("s", "submenu")}

    def _attach(self, item: TB_MenuItem) -> None:
        """Assign ids to ``item`` and its subtree and register them."""
        item._menu = self
        item._id = self._next_id
        self._next_id += 1
        self._items[item._id] = item
        for child in item._children:
            self._attach(child)

    def _detach(self, item: TB_MenuItem) -> None:
        """Unregister ``item`` and its subtree."""
        self._items.pop(item._id, None)
        item._menu = None
        item._id = -1
        for child in item._children:
            self._detach(child)

    def _notify_layout(self, parent_id: int) -> None:
        """Tell the host that the children of ``parent_id`` changed."""
        self._dispatch(lambda: self._dbus_menu.notify_layout_changed(parent_id))

    def _notify_properties(self, item: TB_MenuItem) -> None:
        """Tell the host about changed and removed properties of ``item``."""
        old_keys = set(item._sent_keys)
        properties = item._properties()
        gone = sorted(old_keys - set(properties))
        removed = [(item._id, gone)] if gone else []
        updated = [(item._id, properties)]
        self._dispatch(lambda: self._dbus_menu.notify_properties_changed(updated, removed))

    def _on_event(self, item_id: int, event_id: str, data: Any, timestamp: int) -> None:
        """Run the item action on a "clicked" event."""
        item = self._items.get(item_id)
        if item is not None and event_id == "clicked":
            item._click()
