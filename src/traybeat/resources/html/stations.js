"use strict";

const TYPES = ["webradio", "separator", "folder", "playlist"];
const treeElement = document.getElementById("station-tree");
const editorElement = document.getElementById("editor");
const statusElement = document.getElementById("status");
const addItemButton = document.getElementById("add-item");

let config = { stations: [] };
let selectedItem = null;
let draggedItem = null;
let loadSucceeded = false;
let validationErrorsByPath = new Map();

function element(tag, text) {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = text;
    return node;
}

function setStatus(message, kind = "") {
    statusElement.textContent = message;
    statusElement.className = kind;
}

function makeButton(text, action, className = "") {
    const node = element("button", text);
    node.type = "button";
    if (className) node.className = className;
    node.addEventListener("click", action);
    return node;
}

function newItem(type = "webradio") {
    const item = { type };
    if (type !== "separator") item.caption = "";
    if (type === "webradio") {
        item.url = "";
        item.volumeDelta = 0;
    } else if (type === "playlist") {
        item.path = "";
        item.volumeDelta = 0;
    } else if (type === "folder") {
        item.items = [];
    }
    return item;
}

function displayName(item) {
    if (!item || typeof item !== "object" || Array.isArray(item)) return "Invalid entry";
    if (item.type === "separator") return "Separator";
    const caption = typeof item.caption === "string" ? item.caption.trim() : "";
    return caption || `Untitled ${String(item.type ?? "entry")}`;
}

function childrenOf(item) {
    return item.type === "folder" && Array.isArray(item.items) ? item.items : [];
}

function findLocation(target, items = config.stations, parentItem = null) {
    if (!Array.isArray(items)) return null;
    for (let index = 0; index < items.length; index += 1) {
        const item = items[index];
        if (item === target) return { array: items, index, parentItem };
        if (item && item.type === "folder" && Array.isArray(item.items)) {
            const result = findLocation(target, item.items, item);
            if (result) return result;
        }
    }
    return null;
}

function containsItem(parent, target) {
    if (parent === target) return true;
    if (!parent || typeof parent !== "object" || parent.type !== "folder" || !Array.isArray(parent.items)) return false;
    return parent.items.some(child => containsItem(child, target));
}

function getDropPlacement(item, event, row) {
    const rect = row.getBoundingClientRect();
    const ratio = (event.clientY - rect.top) / Math.max(rect.height, 1);
    if (item.type === "folder" && ratio >= 0.25 && ratio <= 0.75) return "inside";
    return ratio < 0.5 ? "before" : "after";
}

function clearDropIndicators() {
    document.querySelectorAll(".drop-before, .drop-after, .drop-inside").forEach(node => {
        node.classList.remove("drop-before", "drop-after", "drop-inside");
    });
}

function moveItem(source, target, placement) {
    if (!source || !target || typeof source !== "object" || typeof target !== "object" || source === target) return false;
    if (placement === "inside" && target.type !== "folder") return false;
    if (containsItem(source, target)) {
        setStatus("An item cannot be moved into itself or one of its descendants.", "error");
        return false;
    }

    const sourceLocation = findLocation(source);
    if (!sourceLocation) return false;
    sourceLocation.array.splice(sourceLocation.index, 1);

    if (placement === "inside") {
        if (!Array.isArray(target.items)) target.items = [];
        target.items.push(source);
    } else {
        const targetLocation = findLocation(target);
        if (!targetLocation) {
            // Restore the item if the target unexpectedly cannot be found.
            sourceLocation.array.splice(sourceLocation.index, 0, source);
            return false;
        }
        targetLocation.array.splice(
            targetLocation.index + (placement === "after" ? 1 : 0),
            0,
            source,
        );
    }

    selectedItem = source;
    renderTree();
    renderEditor();
    setStatus("Item moved. Save the configuration to apply the changes.");
    return true;
}

function containsArray(parent, targetList) {
    if (!parent || parent.type !== "folder" || !Array.isArray(parent.items)) return false;
    if (parent.items === targetList) return true;
    return parent.items.some(child => containsArray(child, targetList));
}

function moveItemToListEnd(source, targetList) {
    if (!source || !Array.isArray(targetList)) return;
    if (containsArray(source, targetList)) {
        setStatus("An item cannot be moved into itself or one of its descendants.", "error");
        return;
    }
    const sourceLocation = findLocation(source);
    if (!sourceLocation) return;
    sourceLocation.array.splice(sourceLocation.index, 1);
    targetList.push(source);
    selectedItem = source;
    renderTree();
    renderEditor();
    setStatus("Item moved. Save the configuration to apply the changes.");
}

function renderTreeList(items, parentElement, listPath) {
    const list = element("ul");
    list.className = "tree" + (listPath === "stations" ? " tree-root" : "");
    list.setAttribute("role", "group");

    list.addEventListener("dragover", event => {
        if (draggedItem && event.target === list) {
            event.preventDefault();
            event.dataTransfer.dropEffect = "move";
        }
    });
    list.addEventListener("drop", event => {
        if (!draggedItem || event.target !== list) return;
        event.preventDefault();
        event.stopPropagation();
        moveItemToListEnd(draggedItem, items);
        draggedItem = null;
        clearDropIndicators();
    });

    if (!items.length) {
        const empty = element("li", "Empty list — drop an item here");
        empty.className = "tree-empty";
        empty.addEventListener("dragover", event => {
            if (!draggedItem) return;
            event.preventDefault();
            empty.classList.add("drag-over");
        });
        empty.addEventListener("dragleave", () => empty.classList.remove("drag-over"));
        empty.addEventListener("drop", event => {
            if (!draggedItem) return;
            event.preventDefault();
            event.stopPropagation();
            empty.classList.remove("drag-over");
            moveItemToListEnd(draggedItem, items);
            draggedItem = null;
            clearDropIndicators();
        });
        list.appendChild(empty);
    }

    items.forEach((item, index) => {
        const itemPath = `${listPath}[${index}]`;
        const itemIsObject = Boolean(item && typeof item === "object" && !Array.isArray(item));
        const itemType = itemIsObject ? item.type : null;
        const itemErrors = validationErrorsByPath.get(itemPath) || [];
        const listItem = element("li");
        listItem.className = "tree-item";

        const row = element("div");
        row.className = "tree-row" + (item === selectedItem ? " selected" : "") + (itemErrors.length ? " invalid" : "");
        row.draggable = itemIsObject;
        row.tabIndex = 0;
        row.setAttribute("role", "treeitem");
        row.setAttribute("aria-selected", item === selectedItem ? "true" : "false");
        row.setAttribute("aria-label", itemErrors.length
            ? `${displayName(item)}. Validation errors: ${itemErrors.join("; ")}`
            : displayName(item));

        const symbol = element("span", itemType === "folder" ? "▾" : itemType === "separator" ? "─" : "•");
        symbol.className = "node-symbol";
        symbol.setAttribute("aria-hidden", "true");
        const name = element("span", displayName(item));
        name.className = "node-name";
        const type = element("span", TYPES.includes(itemType) ? itemType : "invalid");
        type.className = "node-type";
        row.append(symbol, name, type);

        if (itemErrors.length) {
            const marker = element("span", "!");
            marker.className = "node-error";
            marker.title = itemErrors.join("\n");
            marker.setAttribute("role", "img");
            marker.setAttribute("aria-label", "Validation errors: " + itemErrors.join("; "));
            row.appendChild(marker);
        }

        row.addEventListener("click", () => {
            selectedItem = itemIsObject ? item : null;
            renderTree();
            renderEditor();
            if (!itemIsObject) {
                setStatus("This entry is not an object and cannot be edited. Its validation error is shown in the tree.", "error");
            }
        });
        row.addEventListener("keydown", event => {
            if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                selectedItem = itemIsObject ? item : null;
                renderTree();
                renderEditor();
                if (!itemIsObject) {
                    setStatus("This entry is not an object and cannot be edited. Its validation error is shown in the tree.", "error");
                }
            }
        });
        row.addEventListener("dragstart", event => {
            if (!itemIsObject) {
                event.preventDefault();
                return;
            }
            draggedItem = item;
            event.dataTransfer.effectAllowed = "move";
            event.dataTransfer.setData("text/plain", "traybeat-station");
            row.classList.add("dragging");
        });
        row.addEventListener("dragend", () => {
            draggedItem = null;
            clearDropIndicators();
            renderTree();
        });
        row.addEventListener("dragover", event => {
            if (!draggedItem || !itemIsObject || draggedItem === item) return;
            const placement = getDropPlacement(item, event, row);
            if (placement === "inside" && containsItem(draggedItem, item)) return;
            event.preventDefault();
            event.stopPropagation();
            event.dataTransfer.dropEffect = "move";
            clearDropIndicators();
            row.classList.add(placement === "inside" ? "drop-inside" : placement === "before" ? "drop-before" : "drop-after");
        });
        row.addEventListener("dragleave", event => {
            if (!row.contains(event.relatedTarget)) {
                row.classList.remove("drop-before", "drop-after", "drop-inside");
            }
        });
        row.addEventListener("drop", event => {
            if (!draggedItem || !itemIsObject || draggedItem === item) return;
            event.preventDefault();
            event.stopPropagation();
            const placement = getDropPlacement(item, event, row);
            moveItem(draggedItem, item, placement);
            draggedItem = null;
            clearDropIndicators();
        });

        listItem.appendChild(row);
        if (itemType === "folder") {
            const childItems = Array.isArray(item.items) ? item.items : [];
            listItem.appendChild(renderTreeList(childItems, listItem, `${itemPath}.items`));
        }
        list.appendChild(listItem);
    });

    parentElement.appendChild(list);
    return list;
}

function renderTree() {
    const errors = validateConfig(config);
    treeElement.replaceChildren();
    addItemButton.disabled = !selectedItem || typeof selectedItem !== "object";
    if (!config || typeof config !== "object" || !Array.isArray(config.stations)) {
        treeElement.appendChild(element("p", "The configuration does not contain a stations array."));
        return errors;
    }
    renderTreeList(config.stations, treeElement, "stations");
    return errors;
}

function addField(parent, labelText, value, inputType, update, placeholder) {
    const label = element("label", labelText);
    const input = element("input");
    input.type = inputType;
    input.value = value === null || value === undefined ? "" : String(value);
    input.placeholder= placeholder;
    if (inputType === "number") input.step = "1";
    input.addEventListener("input", () => {
        if (inputType === "number") {
            const raw = input.value.trim();
            update(raw === "" ? null : Number(raw));
        } else {
            update(input.value);
        }
        const errors = renderTree();
        if (errors.length) {
            setStatus(`${errors.length} validation error(s) found. Hover over a red marker in the tree for details.`, "error");
        } else {
            setStatus("No validation errors. Changes have not been saved yet.");
        }
    });
    label.appendChild(input);
    parent.appendChild(label);
}

function addStationImageField(parent, item,update) {
    const label = element("label", "Station image");
    const input = element("input");
    input.type = "text";
    input.placeholder = "Image URL";
    input.autocomplete = "off";
    input.value = typeof item.imageUrl === "string" ? item.imageUrl : "";

    /*
    const preview = element("div");
    preview.className = "favicon-preview";
    preview.hidden = true;
    preview.setAttribute("aria-live", "polite");
    const image = element("img");
    image.alt = "Station image preview";
    image.hidden = true;
    const message = element("span", "Enter an image source to preview the station image.");
    message.className = "favicon-preview-status";
    preview.append(image, message);
*/
    function updatePreview() {
        const value = input.value.trim();
        image.onload = () => {
            image.hidden = false;
            message.textContent = "Preview";
        };
        image.onerror = () => {
            image.hidden = true;
            message.textContent = "The image could not be loaded. Check the image source.";
        };
        if (!value) {
            image.removeAttribute("src");
            image.hidden = true;
            message.textContent = "Enter an image source to preview the station image.";
            preview.hidden = true;
            return;
        }
        preview.hidden = false;
        message.textContent = "Loading preview…";
        image.hidden = true;
        image.src = value;
    }

    input.addEventListener("input", () => {
        item.favicon = input.value;
        //updatePreview();
        update(input.value);
        const errors = renderTree();
        if (errors.length) {
            setStatus(`${errors.length} validation error(s) found. Hover over a red marker in the tree for details.`, "error");
        } else {
            setStatus("No validation errors. Changes have not been saved yet.");
        }
    });

//    label.append(input, preview);
    parent.appendChild(label);
    parent.appendChild(input);
    
    //updatePreview();
}

function replaceSelectedType(type) {
    if (!selectedItem || !TYPES.includes(type)) return;
    const oldItem = selectedItem;
    const replacement = newItem(type);

    // Preserve the opaque application-owned identifier without displaying or validating it.
    if (Object.hasOwn(oldItem, "uniqueId")) replacement.uniqueId = oldItem.uniqueId;
    if (type !== "separator" && oldItem.type !== "separator") {
        replacement.caption = oldItem.caption ?? "";
    }

    const location = findLocation(oldItem);
    if (!location) return;
    location.array[location.index] = replacement;
    selectedItem = replacement;
    renderTree();
    renderEditor();
    setStatus("Item type changed. Save the configuration to apply the changes.");
}

function deleteSelectedItem() {
    if (!selectedItem) return;
    if (!confirm("Delete this station and all of its child items?")) return;
    const location = findLocation(selectedItem);
    if (!location) return;
    location.array.splice(location.index, 1);
    selectedItem = location.parentItem;
    renderTree();
    renderEditor();
    setStatus("Item deleted. Save the configuration to apply the changes.");
}

function addRootItem() {
    if (!config || typeof config !== "object" || !Array.isArray(config.stations)) {
        config = { stations: [] };
    }
    const item = newItem();
    config.stations.push(item);
    selectedItem = item;
    renderTree();
    renderEditor();
    setStatus("New root item added. Complete its properties and save the configuration.");
}

function addItem() {
    if (!selectedItem || typeof selectedItem !== "object") return;
    const item = newItem();

    if (selectedItem.type === "folder") {
        if (!Array.isArray(selectedItem.items)) selectedItem.items = [];
        selectedItem.items.push(item);
    } else {
        const location = findLocation(selectedItem);
        if (!location) {
            setStatus("The selected item could not be located in the tree.", "error");
            return;
        }
        location.array.splice(location.index + 1, 0, item);
    }

    selectedItem = item;
    renderTree();
    renderEditor();
    setStatus("New item added. Complete its properties and save the configuration.");
}

function renderEditor() {
    editorElement.replaceChildren();
    if (!selectedItem || typeof selectedItem !== "object" || Array.isArray(selectedItem)) {
        editorElement.appendChild(element("h2", "Edit station"));
        editorElement.appendChild(element("p", "Select a station in the tree, or add a new root item."));
        const hint = element("p", "Drag and drop items to reorder them. Drop an item in the middle of a folder row to move it into that folder. Use Add item to add a child to a selected folder, or to insert a sibling after another selected item.");
        hint.className = "hint";
        editorElement.appendChild(hint);
        return;
    }

    editorElement.appendChild(element("h2", `Edit ${selectedItem.type}`));
    const typeLabel = element("label", "Type");
    const typeSelect = element("select");
    TYPES.forEach(value => {
        const option = element("option", value);
        option.value = value;
        option.selected = selectedItem.type === value;
        typeSelect.appendChild(option);
    });
    typeSelect.addEventListener("change", () => replaceSelectedType(typeSelect.value));
    typeLabel.appendChild(typeSelect);
    editorElement.appendChild(typeLabel);

    const item = selectedItem;
    if (item.type !== "separator") {
        addField(editorElement, "Caption", item.caption, "text", value => item.caption = value);
    }

    if (item.type === "webradio") {
        addField(editorElement, "Stream URL", item.url, "url", value => item.url = value,"Url of the webradio stream");
        addField(editorElement, "Station image", item.imageUrl, "url", value => item.imageUrl = value,"file://, http:// or https:// png,jpg,gif,webp image");
        //addStationImageField(editorElement, item,value => item.imageUrl = value);
        addField(editorElement, "Volume gain (%)", item.volumeDelta ?? 0, "number", value => item.volumeDelta = value);
    } else if (item.type === "playlist") {
        addField(editorElement, "Playlist path", item.path, "text", value => item.path = value);
        addField(editorElement, "Volume gain (%)", item.volumeDelta ?? 0, "number", value => item.volumeDelta = value);
    } else if (item.type === "folder") {
        const hint = element("p", "Folder items can contain stations, playlists, separators, and nested folders. Select this folder and use Add item to append a child.");
        hint.className = "hint";
        editorElement.appendChild(hint);
    } else if (item.type === "separator") {
        const hint = element("p", "A separator has no editable properties.");
        hint.className = "hint";
        editorElement.appendChild(hint);
    }

    const actions = element("div");
    actions.className = "editor-actions";
    actions.appendChild(makeButton("Delete item", deleteSelectedItem, "danger"));
    editorElement.appendChild(actions);
}

function isAbsoluteUri(value) {
    if (typeof value !== "string" || value.trim() === "") return false;
    try {
        const parsed = new URL(value);
        return /^[A-Za-z][A-Za-z0-9+.-]*:/.test(value) && Boolean(parsed.protocol);
    } catch {
        return false;
    }
}

function validateConfig(document) {
    const errors = [];
    validationErrorsByPath = new Map();

    function reportItem(path, message) {
        const formatted = `${path}: ${message}`;
        errors.push(formatted);
        const current = validationErrorsByPath.get(path) || [];
        current.push(formatted);
        validationErrorsByPath.set(path, current);
    }

    function reportGlobal(message) {
        errors.push(message);
    }

    if (!document || typeof document !== "object" || Array.isArray(document)) {
        reportGlobal("The configuration must be a JSON object.");
        return errors;
    }
    if (!Array.isArray(document.stations)) {
        reportGlobal("stations must be an array.");
        return errors;
    }

    function validateItem(item, path) {
        if (!item || typeof item !== "object" || Array.isArray(item)) {
            reportItem(path, "each station must be an object.");
            return;
        }
        if (typeof item.type !== "string" || !TYPES.includes(item.type)) {
            reportItem(path, `type must be one of ${TYPES.join(", ")}.`);
            return;
        }

        // Field presence is not restricted here. Validate only the values used by each known type.

        if (Object.hasOwn(item, "caption") &&
            item.caption !== null && typeof item.caption !== "string") {
            reportItem(path, "caption must be a string or null.");
        }

        if (item.type === "webradio") {
            if (Object.hasOwn(item, "url")) {
                if (item.url !== null && typeof item.url !== "string") {
                    reportItem(path, "url must be a string or null.");
                } else if (typeof item.url === "string" && !isAbsoluteUri(item.url)) {
                    reportItem(path, "url must be a valid absolute URI.");
                }
            }
            if (Object.hasOwn(item, "favicon") && item.favicon !== null && typeof item.favicon !== "string") {
                reportItem(path, "station image must be a string or null.");
            }
            if (Object.hasOwn(item, "volumeDelta") && !Number.isSafeInteger(item.volumeDelta)) {
                reportItem(path, "volume gain must be an integer.");
            }
        } else if (item.type === "playlist") {
            if (Object.hasOwn(item, "path") && item.path !== null && typeof item.path !== "string") {
                reportItem(path, "path must be a string or null.");
            }
            if (Object.hasOwn(item, "volumeDelta") && !Number.isSafeInteger(item.volumeDelta)) {
                reportItem(path, "volume gain must be an integer.");
            }
        } else if (item.type === "folder") {
            if (Object.hasOwn(item, "items") && item.items !== null && !Array.isArray(item.items)) {
                reportItem(path, "items must be an array or null.");
            }
            if (Array.isArray(item.items)) {
                item.items.forEach((child, index) => validateItem(child, `${path}.items[${index}]`));
            }
        }
    }

    document.stations.forEach((item, index) => validateItem(item, `stations[${index}]`));
    return errors;
}

async function loadConfig() {
    setStatus("Loading configuration…");
    try {
        const response = await fetch("/api/config", { cache: "no-store" });
        const result = await response.json();
        if (!response.ok) throw new Error(result.error || `HTTP ${response.status}`);
        config = result;
        selectedItem = null;
        loadSucceeded = true;
        const errors = renderTree();
        renderEditor();
        if (errors.length) {
            setStatus("The loaded configuration has validation errors. Correct them before saving:\n" + errors.join("\n"), "error");
        } else {
            setStatus("Configuration loaded.");
        }
    } catch (error) {
        loadSucceeded = false;
        setStatus(`Could not load configuration: ${error.message}`, "error");
    }
}

async function saveConfig() {
    if (!loadSucceeded) {
        setStatus("Load a configuration successfully before saving.", "error");
        return;
    }
    const errors = renderTree();
    if (errors.length) {
        alert("Validation errors remain. Please correct the items marked in red before saving.");
        return;
    }

    setStatus("Saving complete configuration…");
    try {
        const response = await fetch("/api/config", {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(config)
        });
        const result = await response.json();
        if (!response.ok) throw new Error(result.error || `HTTP ${response.status}`);
        // Keep the current object references so the selected editor item remains selected.
        setStatus("Configuration saved to the server property.", "success");
    } catch (error) {
        setStatus(`Save failed: ${error.message}`, "error");
    }
}

document.getElementById("add-root").addEventListener("click", addRootItem);
document.getElementById("add-item").addEventListener("click", addItem);
document.getElementById("save").addEventListener("click", saveConfig);
document.getElementById("reload").addEventListener("click", () => {
    if (confirm("Discard unsaved changes and reload the configuration?")) loadConfig();
});

renderTree();
loadConfig();
