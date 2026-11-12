"""D-Bus layer for the StatusNotifierItem and DBusMenu specifications (dbus_next).

Note: no ``from __future__ import annotations`` here, because dbus_next reads
the D-Bus type signatures from the (string) annotations at runtime.
"""

import asyncio
import logging
from collections.abc import Callable
from typing import Any

from dbus_next.aio.message_bus import MessageBus
from dbus_next.constants import MessageType, PropertyAccess
from dbus_next.errors import DBusError
from dbus_next.message import Message
from dbus_next.service import ServiceInterface, dbus_property, method, signal
from dbus_next.signature import Variant

log = logging.getLogger(__name__)

SNI_INTERFACE = "org.kde.StatusNotifierItem"
SNI_PATH = "/StatusNotifierItem"
NO_MENU_PATH = "/NO_DBUSMENU"
DBUSMENU_INTERFACE = "com.canonical.dbusmenu"
DBUSMENU_PATH = "/MenuBar"
WATCHER_PATH = "/StatusNotifierWatcher"
WATCHER_NAMES = ("org.kde.StatusNotifierWatcher", "org.freedesktop.StatusNotifierWatcher")

Pixmap = tuple[int, int, bytes]
"""Icon pixmap as (width, height, ARGB32 data in network byte order)."""


def _pixmaps_to_wire(pixmaps: list[Pixmap]) -> list[list[Any]]:
    """Convert pixmap tuples into the list form dbus_next expects for ``a(iiay)``."""
    return [[width, height, data] for width, height, data in pixmaps]


class TB_StatusNotifierItem(ServiceInterface):
    """D-Bus object implementing ``org.kde.StatusNotifierItem`` (SNI)."""

    def __init__(self, item_id: str, title: str = "", category: str = "ApplicationStatus") -> None:
        """Create the item with a unique id, a title and a category."""
        super().__init__(SNI_INTERFACE)
        self._category = category
        self._item_id = item_id
        self._title = title
        self._status = "Active"
        self._icon_theme_path = ""
        self._menu_path = NO_MENU_PATH
        self._item_is_menu = False
        self._icon_name = ""
        self._icon_pixmaps: list[Pixmap] = []
        self._overlay_icon_name = ""
        self._overlay_icon_pixmaps: list[Pixmap] = []
        self._attention_icon_name = ""
        self._attention_icon_pixmaps: list[Pixmap] = []
        self._tooltip: tuple[str, list[Pixmap], str, str] = ("", [], "", "")
        self._icon_accessible_desc = ""
        self._attention_accessible_desc = ""
        self._label = ""
        self._label_guide = ""
        self._ordering_index = 0

        self.on_activate: Callable[[int, int], None] | None = None
        self.on_secondary_activate: Callable[[int, int], None] | None = None
        self.on_context_menu: Callable[[int, int], None] | None = None
        self.on_scroll: Callable[[int, str], None] | None = None
        self.on_xdg_activation_token: Callable[[str], None] | None = None

    # ------------------------------------------------------------------ properties

    @dbus_property(access=PropertyAccess.READ)
    def Category(self) -> "s":  # type: ignore
        """Return the item category."""
        return self._category

    @dbus_property(access=PropertyAccess.READ)
    def Id(self) -> "s":  # type: ignore
        """Return the application specific item id."""
        return self._item_id

    @dbus_property(access=PropertyAccess.READ)
    def Title(self) -> "s":  # type: ignore
        """Return the item title."""
        return self._title

    @dbus_property(access=PropertyAccess.READ)
    def Status(self) -> "s":  # type: ignore
        """Return the item status (Passive, Active or NeedsAttention)."""
        return self._status

    @dbus_property(access=PropertyAccess.READ)
    def WindowId(self) -> "i":  # type: ignore
        """Return the associated window id (0 if none)."""
        return 0

    @dbus_property(access=PropertyAccess.READ)
    def IconThemePath(self) -> "s":  # type: ignore
        """Return an additional icon theme search path."""
        return self._icon_theme_path

    @dbus_property(access=PropertyAccess.READ)
    def Menu(self) -> "o":  # type: ignore
        """Return the object path of the dbusmenu."""
        return self._menu_path

    @dbus_property(access=PropertyAccess.READ)
    def ItemIsMenu(self) -> "b":  # type: ignore
        """Return True if the host should show the menu on primary activation."""
        return self._item_is_menu

    @dbus_property(access=PropertyAccess.READ)
    def IconName(self) -> "s":  # type: ignore
        """Return the themed icon name."""
        return self._icon_name

    @dbus_property(access=PropertyAccess.READ)
    def IconPixmap(self) -> "a(iiay)":  # type: ignore
        """Return the icon pixmaps."""
        return _pixmaps_to_wire(self._icon_pixmaps)

    @dbus_property(access=PropertyAccess.READ)
    def OverlayIconName(self) -> "s":  # type: ignore
        """Return the themed overlay icon name."""
        return self._overlay_icon_name

    @dbus_property(access=PropertyAccess.READ)
    def OverlayIconPixmap(self) -> "a(iiay)":  # type: ignore
        """Return the overlay icon pixmaps."""
        return _pixmaps_to_wire(self._overlay_icon_pixmaps)

    @dbus_property(access=PropertyAccess.READ)
    def AttentionIconName(self) -> "s":  # type: ignore
        """Return the themed attention icon name."""
        return self._attention_icon_name

    @dbus_property(access=PropertyAccess.READ)
    def AttentionIconPixmap(self) -> "a(iiay)":  # type: ignore
        """Return the attention icon pixmaps."""
        return _pixmaps_to_wire(self._attention_icon_pixmaps)

    @dbus_property(access=PropertyAccess.READ)
    def AttentionMovieName(self) -> "s":  # type: ignore
        """Return the attention animation name (unused)."""
        return ""

    @dbus_property(access=PropertyAccess.READ)
    def ToolTip(self) -> "(sa(iiay)ss)":  # type: ignore
        """Return the tooltip as (icon name, pixmaps, title, description)."""
        icon_name, pixmaps, title, description = self._tooltip
        return [icon_name, _pixmaps_to_wire(pixmaps), title, description]

    @dbus_property(access=PropertyAccess.READ)
    def IconAccessibleDesc(self) -> "s":  # type: ignore
        """Return the accessible description of the icon (Ayatana extension)."""
        return self._icon_accessible_desc

    @dbus_property(access=PropertyAccess.READ)
    def AttentionAccessibleDesc(self) -> "s":  # type: ignore
        """Return the accessible description of the attention icon (Ayatana extension)."""
        return self._attention_accessible_desc

    @dbus_property(access=PropertyAccess.READ)
    def XAyatanaLabel(self) -> "s":  # type: ignore
        """Return the text shown next to the icon (Ayatana extension)."""
        return self._label

    @dbus_property(access=PropertyAccess.READ)
    def XAyatanaLabelGuide(self) -> "s":  # type: ignore
        """Return the widest expected label text for layout (Ayatana extension)."""
        return self._label_guide

    @dbus_property(access=PropertyAccess.READ)
    def XAyatanaOrderingIndex(self) -> "u":  # type: ignore
        """Return the sort index among tray items (Ayatana extension)."""
        return self._ordering_index

    # --------------------------------------------------------------------- methods

    @method()
    def ContextMenu(self, x: "i", y: "i") -> None:  # type: ignore
        """Handle a context menu request at screen position (x, y)."""
        if self.on_context_menu is not None:
            self.on_context_menu(x, y)  # type: ignore

    @method()
    def Activate(self, x: "i", y: "i") -> None:  # type: ignore
        """Handle a primary activation (left click) at (x, y)."""
        if self.on_activate is not None:
            self.on_activate(x, y)  # type: ignore

    @method()
    def SecondaryActivate(self, x: "i", y: "i") -> None:  # type: ignore
        """Handle a secondary activation (middle click) at (x, y)."""
        if self.on_secondary_activate is not None:
            self.on_secondary_activate(x, y)  # type: ignore

    @method()
    def Scroll(self, delta: "i", orientation: "s") -> None:  # type: ignore
        """Handle a scroll event ("vertical" or "horizontal")."""
        if self.on_scroll is not None:
            self.on_scroll(delta, orientation)  # type: ignore

    @method()
    def ProvideXdgActivationToken(self, token: "s") -> None:  # type: ignore
        """Receive an xdg-activation token that allows focusing a window on Wayland."""
        if self.on_xdg_activation_token is not None:
            self.on_xdg_activation_token(token)  # type: ignore

    @method()
    def XAyatanaSecondaryActivate(self, timestamp: "u") -> None:  # type: ignore
        """Handle a secondary activation without coordinates (Ayatana extension)."""
        if self.on_secondary_activate is not None:
            self.on_secondary_activate(0, 0)

    # --------------------------------------------------------------------- signals

    @signal()
    def NewTitle(self) -> None:
        """Signal: the title changed."""

    @signal()
    def NewIcon(self) -> None:
        """Signal: the icon changed."""

    @signal()
    def NewAttentionIcon(self) -> None:
        """Signal: the attention icon changed."""

    @signal()
    def NewOverlayIcon(self) -> None:
        """Signal: the overlay icon changed."""

    @signal()
    def NewToolTip(self) -> None:
        """Signal: the tooltip changed."""

    @signal()
    def NewStatus(self) -> "s":  # type: ignore
        """Signal: the status changed."""
        return self._status

    @signal()
    def NewIconThemePath(self) -> "s":  # type: ignore
        """Signal: the icon theme path changed."""
        return self._icon_theme_path

    @signal()
    def NewMenu(self) -> None:
        """Signal: the menu object path changed."""

    @signal()
    def XAyatanaNewLabel(self) -> "ss":  # type: ignore
        """Signal: the label or its guide changed (Ayatana extension)."""
        return [self._label, self._label_guide]

    # ------------------------------------------------------------------ Python API

    def _changed(self, **properties: Any) -> None:
        """Emit PropertiesChanged for the given D-Bus properties."""
        self.emit_properties_changed(properties)

    def set_title(self, title: str) -> None:
        """Set the title and emit NewTitle."""
        self._title = title
        self.NewTitle()  # type: ignore
        self._changed(Title=title)

    def set_status(self, status: str) -> None:
        """Set the status and emit NewStatus."""
        self._status = status
        self.NewStatus()  # type: ignore
        self._changed(Status=status)

    def set_icon(self, name: str = "", pixmaps: list[Pixmap] | None = None) -> None:
        """Set the icon by theme name and/or pixmaps and emit NewIcon."""
        self._icon_name = name
        self._icon_pixmaps = pixmaps or []
        self.NewIcon()  # type: ignore
        self._changed(IconName=name, IconPixmap=_pixmaps_to_wire(self._icon_pixmaps))

    def set_overlay_icon(self, name: str = "", pixmaps: list[Pixmap] | None = None) -> None:
        """Set the overlay icon and emit NewOverlayIcon."""
        self._overlay_icon_name = name
        self._overlay_icon_pixmaps = pixmaps or []
        self.NewOverlayIcon()  # type: ignore
        self._changed(
            OverlayIconName=name,
            OverlayIconPixmap=_pixmaps_to_wire(self._overlay_icon_pixmaps),
        )

    def set_attention_icon(self, name: str = "", pixmaps: list[Pixmap] | None = None) -> None:
        """Set the attention icon and emit NewAttentionIcon."""
        self._attention_icon_name = name
        self._attention_icon_pixmaps = pixmaps or []
        self.NewAttentionIcon()  # type: ignore
        self._changed(
            AttentionIconName=name,
            AttentionIconPixmap=_pixmaps_to_wire(self._attention_icon_pixmaps),
        )

    def set_tooltip(self, title: str, description: str = "", icon_name: str = "", pixmaps: list[Pixmap] | None = None) -> None:
        """Set the tooltip and emit NewToolTip."""
        self._tooltip = (icon_name, pixmaps or [], title, description)
        self.NewToolTip()  # type: ignore
        self._changed(ToolTip=[icon_name, _pixmaps_to_wire(self._tooltip[1]), title, description])

    def set_icon_accessible_desc(self, description: str) -> None:
        """Set the accessible description of the icon."""
        self._icon_accessible_desc = description
        self._changed(IconAccessibleDesc=description)

    def set_attention_accessible_desc(self, description: str) -> None:
        """Set the accessible description of the attention icon."""
        self._attention_accessible_desc = description
        self._changed(AttentionAccessibleDesc=description)

    def set_label(self, label: str, guide: str = "") -> None:
        """Set the text next to the icon and emit XAyatanaNewLabel."""
        self._label = label
        self._label_guide = guide
        self.XAyatanaNewLabel()  # type: ignore
        self._changed(XAyatanaLabel=label, XAyatanaLabelGuide=guide)

    def set_ordering_index(self, index: int) -> None:
        """Set the sort index among tray items."""
        self._ordering_index = index
        self._changed(XAyatanaOrderingIndex=index)

    def set_icon_theme_path(self, path: str) -> None:
        """Set an extra icon theme path and emit NewIconThemePath."""
        self._icon_theme_path = path
        self.NewIconThemePath()  # type: ignore
        self._changed(IconThemePath=path)

    def set_menu_path(self, path: str) -> None:
        """Set the dbusmenu object path and emit NewMenu."""
        self._menu_path = path
        self.NewMenu()  # type: ignore
        self._changed(Menu=path)

    def set_item_is_menu(self, value: bool) -> None:
        """Tell the host whether primary activation should open the menu."""
        self._item_is_menu = value
        self._changed(ItemIsMenu=value)


MENU_PROPERTY_DEFAULTS: dict[str, Variant] = {
    "type": Variant("s", "standard"),
    "label": Variant("s", ""),
    "enabled": Variant("b", True),
    "visible": Variant("b", True),
    "icon-name": Variant("s", ""),
    "icon-data": Variant("ay", b""),
    "shortcut": Variant("aas", []),
    "toggle-type": Variant("s", ""),
    "toggle-state": Variant("i", -1),
    "children-display": Variant("s", ""),
    "disposition": Variant("s", "normal"),
}
"""Default values of the dbusmenu item properties as defined by the specification."""


class TB_DBusMenuNode:
    """Plain data node describing one dbusmenu item and its children."""

    def __init__(
        self,
        item_id: int,
        properties: dict[str, Variant] | None = None,
        children: "list[TB_DBusMenuNode] | None" = None,
    ) -> None:
        """Create a node with an id, dbusmenu properties and child nodes."""
        self.id = item_id
        self.properties: dict[str, Variant] = properties or {}
        self.children: list[TB_DBusMenuNode] = children or []


class TB_DBusMenu(ServiceInterface):
    """D-Bus object implementing ``com.canonical.dbusmenu``."""

    def __init__(self, root_provider: Callable[[], TB_DBusMenuNode]) -> None:
        """Create the interface; ``root_provider`` returns the current menu tree."""
        super().__init__(DBUSMENU_INTERFACE)
        self._root_provider = root_provider
        self._revision = 0
        self.on_event: Callable[[int, str, Any, int], None] | None = None
        self.on_about_to_show: Callable[[int], bool] | None = None

    # --------------------------------------------------------------------- helpers

    def _index(self) -> dict[int, TB_DBusMenuNode]:
        """Return all nodes of the current tree keyed by id."""
        index: dict[int, TB_DBusMenuNode] = {}
        stack = [self._root_provider()]
        while stack:
            node = stack.pop()
            index[node.id] = node
            stack.extend(node.children)
        return index

    @staticmethod
    def _filter(properties: dict[str, Variant], names: list[str]) -> dict[str, Variant]:
        """Return only the requested properties (all if ``names`` is empty)."""
        if not names:
            return dict(properties)
        return {key: value for key, value in properties.items() if key in names}

    def _pack(self, node: TB_DBusMenuNode, depth: int, names: list[str]) -> list[Any]:
        """Serialize a node as the ``(ia{sv}av)`` layout struct."""
        children: list[Variant] = []
        if depth != 0:
            child_depth = depth - 1 if depth > 0 else depth
            children = [Variant("(ia{sv}av)", self._pack(child, child_depth, names)) for child in node.children]
        return [node.id, self._filter(node.properties, names), children]

    def _handle_event(self, item_id: int, event_id: str, data: Any, timestamp: int) -> None:
        """Forward an item event to the registered callback."""
        if self.on_event is not None:
            self.on_event(item_id, event_id, data, timestamp)

    def _about_to_show(self, item_id: int) -> bool:
        """Ask the callback whether the layout below ``item_id`` needs an update."""
        if self.on_about_to_show is None:
            return False
        return bool(self.on_about_to_show(item_id))

    # ------------------------------------------------------------------ properties

    @dbus_property(access=PropertyAccess.READ)
    def Version(self) -> "u":  # type: ignore
        """Return the dbusmenu protocol version."""
        return 3

    @dbus_property(access=PropertyAccess.READ)
    def TextDirection(self) -> "s":  # type: ignore
        """Return the text direction ("ltr" or "rtl")."""
        return "ltr"

    @dbus_property(access=PropertyAccess.READ)
    def Status(self) -> "s":  # type: ignore
        """Return the menu status ("normal" or "notice")."""
        return "normal"

    @dbus_property(access=PropertyAccess.READ)
    def IconThemePath(self) -> "as":  # type: ignore
        """Return additional icon theme paths for menu icons."""
        return []  # type: ignore

    # --------------------------------------------------------------------- methods

    @method()
    def GetLayout(self, parent_id: "i", recursion_depth: "i", property_names: "as") -> "u(ia{sv}av)":  # type: ignore
        """Return the menu revision and the layout below ``parent_id``."""
        node = self._index().get(parent_id)  # type: ignore
        if node is None:
            raise DBusError("org.freedesktop.DBus.Error.InvalidArgs", f"Unknown menu item {parent_id}")
        return [self._revision, self._pack(node, recursion_depth, property_names)]  # type: ignore

    @method()
    def GetGroupProperties(self, ids: "ai", property_names: "as") -> "a(ia{sv})":  # type: ignore
        """Return the properties of several items (all items if ``ids`` is empty)."""
        index = self._index()
        wanted = list(ids) if ids else list(index)  # type: ignore # type: ignore
        return [[i, self._filter(index[i].properties, property_names)] for i in wanted if i in index]  # type: ignore

    @method()
    def GetProperty(self, item_id: "i", name: "s") -> "v":  # type: ignore
        """Return a single property of an item."""
        node = self._index().get(item_id)  # type: ignore
        if node is None or name not in MENU_PROPERTY_DEFAULTS:
            raise DBusError("org.freedesktop.DBus.Error.InvalidArgs", f"Unknown property {name} of item {item_id}")
        return node.properties.get(name, MENU_PROPERTY_DEFAULTS[name])  # type: ignore

    @method()
    def Event(self, item_id: "i", event_id: "s", data: "v", timestamp: "u") -> None:  # type: ignore
        """Handle an event (e.g. "clicked") sent to an item."""
        self._handle_event(item_id, event_id, data.value, timestamp)  # type: ignore

    @method()
    def EventGroup(self, events: "a(isvu)") -> "ai":  # type: ignore
        """Handle several events at once and return the ids that were not found."""
        index = self._index()
        missing: list[int] = []
        for item_id, event_id, data, timestamp in events:  # type: ignore
            if item_id in index:
                self._handle_event(item_id, event_id, data.value, timestamp)  # type: ignore
            else:
                missing.append(item_id)  # type: ignore
        return missing

    @method()
    def AboutToShow(self, item_id: "i") -> "b":  # type: ignore
        """Called before a submenu is shown; return True if the layout needs a refresh."""
        return self._about_to_show(item_id)  # type: ignore

    @method()
    def AboutToShowGroup(self, ids: "ai") -> "aiai":  # type: ignore
        """Group variant of AboutToShow; return (ids needing an update, unknown ids)."""
        index = self._index()
        updates = [i for i in ids if i in index and self._about_to_show(i)]  # type: ignore
        errors = [i for i in ids if i not in index]  # type: ignore
        return [updates, errors]  # type: ignore

    # --------------------------------------------------------------------- signals

    @signal()
    def ItemsPropertiesUpdated(self, updated: list[Any], removed: list[Any]) -> "a(ia{sv})a(ias)":  # type: ignore
        """Signal: properties of some items changed or were removed."""
        return [updated, removed]

    @signal()
    def LayoutUpdated(self, revision: int, parent: int) -> "ui":  # type: ignore
        """Signal: the layout below ``parent`` changed."""
        return [revision, parent]

    @signal()
    def ItemActivationRequested(self, item_id: int, timestamp: int) -> "iu":  # type: ignore
        """Signal: the application asks the host to activate an item."""
        return [item_id, timestamp]

    # ------------------------------------------------------------------ Python API

    def notify_layout_changed(self, parent_id: int = 0) -> None:
        """Bump the revision and emit LayoutUpdated for ``parent_id``."""
        self._revision += 1
        self.LayoutUpdated(self._revision, parent_id)  # type: ignore

    def notify_properties_changed(
        self,
        updated: list[tuple[int, dict[str, Variant]]],
        removed: list[tuple[int, list[str]]] | None = None,
    ) -> None:
        """Emit ItemsPropertiesUpdated for (id, properties) pairs and (id, names) removals."""
        self.ItemsPropertiesUpdated(  # type: ignore
            [[item_id, props] for item_id, props in updated],
            [[item_id, names] for item_id, names in (removed or [])],
        )


class TB_StatusNotifierWatcherClient:
    """Registers an item with the StatusNotifierWatcher and re-registers if the watcher restarts."""

    def __init__(self, bus: MessageBus, service_name: str) -> None:
        """Create the client for ``service_name`` on the given bus."""
        self._bus = bus
        self._service_name = service_name
        self._tasks: set[asyncio.Task[bool]] = set()
        self._monitoring = False

    async def register(self) -> bool:
        """Register with the first available watcher; return True on success."""
        for watcher in WATCHER_NAMES:
            reply = await self._bus.call(
                Message(
                    destination=watcher,
                    path=WATCHER_PATH,
                    interface=watcher,
                    member="RegisterStatusNotifierItem",
                    signature="s",
                    body=[self._service_name],
                )
            )
            if reply is not None and reply.message_type == MessageType.METHOD_RETURN:
                return True
        log.warning("No StatusNotifierWatcher available; waiting for one to appear")
        return False

    async def start_monitoring(self) -> None:
        """Watch NameOwnerChanged and register again whenever a watcher appears."""
        if self._monitoring:
            return
        self._monitoring = True
        self._bus.add_message_handler(self._on_message)
        await self._bus.call(
            Message(
                destination="org.freedesktop.DBus",
                path="/org/freedesktop/DBus",
                interface="org.freedesktop.DBus",
                member="AddMatch",
                signature="s",
                body=["type='signal',sender='org.freedesktop.DBus',interface='org.freedesktop.DBus',member='NameOwnerChanged'"],
            )
        )

    def stop_monitoring(self) -> None:
        """Stop watching for watcher restarts."""
        if self._monitoring:
            self._bus.remove_message_handler(self._on_message)
            self._monitoring = False

    def _on_message(self, msg: Message) -> None:
        """Re-register when a StatusNotifierWatcher name gets a new owner."""
        if msg.message_type != MessageType.SIGNAL or msg.member != "NameOwnerChanged" or len(msg.body) != 3:
            return
        name, _old_owner, new_owner = msg.body
        if name in WATCHER_NAMES and new_owner:
            task = asyncio.get_running_loop().create_task(self.register())
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)
