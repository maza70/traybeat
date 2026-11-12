/*
 * Music Player connection and controls.
 * Adjust the URLs below to match your backend API.
 */
const PLAYER_CONFIG = {
  // WebSocket endpoint that broadcasts JSON messages.
  WEBSOCKET_URL: "ws://{WEBSOCKET_HOST}:{WEBSOCKET_PORT}/ws",

  // Base URL or path used to load cover images. The cover filename from
  // the "meta" message is appended to this value.
  COVER_BASE_URL: "/api/cover/",

  // GET endpoints for player controls. Use {action} only if your API has
  // one generic endpoint; otherwise configure each control separately.
  CONTROL_URLS: {
    next:        "/api/player?cmd=next",
    prev:        "/api/player?cmd=prev",
    stop:        "/api/player?cmd=stop",
    pause:       "/api/player?cmd=pause",
    play:        "/api/player?cmd=play",
    volume_up:   "/api/player?cmd=vol_up",
    volume_down: "/api/player?cmd=vol_down"
  },

  // Optional headers for GET requests, e.g. { "Authorization": "Bearer ..." }.
  CONTROL_HEADERS: {},

  // Set to true to reconnect automatically after a dropped WebSocket.
  AUTO_RECONNECT: true,
  RECONNECT_DELAY_MS: 2500
};

const elements = {
  cover: document.getElementById("cover"),
  blurCover: document.getElementById("blurCover"),
  title: document.getElementById("title"),
  artist: document.getElementById("artist"),
  stationType: document.getElementById("stationType"),
  type: document.getElementById("type"),
  state: document.getElementById("state"),
  caption: document.getElementById("caption"),
  volume: document.getElementById("volume"),
  volumeDelta: document.getElementById("volumeDelta"),
  playlistIndex: document.getElementById("playlistIndex"),
  playlistLength: document.getElementById("playlistLength"),
  playlist_cards: document.querySelectorAll(".playlist_card"),
  
  volumeFill: document.getElementById("volumeFill"),
  volumePercent: document.getElementById("volumePercent"),
  connectionDot: document.getElementById("connectionDot"),
  connectionText: document.getElementById("connectionText"),
  error: document.getElementById("error")
};


function setConnection(connected, message) {
  elements.connectionDot.classList.toggle("connected", connected);
  elements.connectionText.textContent = message;
}

function makeCoverUrl(filename) {
  if (!filename) return "";
  // Absolute URLs are accepted as-is; otherwise use COVER_BASE_URL.
  try {
    return new URL(filename).href;
  } catch (_) {
    return PLAYER_CONFIG.COVER_BASE_URL.replace(/\/?$/, "/") + filename.replace(/^\/+/, "");
  }
}

function updateCover(filename) {
  const url = makeCoverUrl(filename);
  if (!url) return;
  elements.cover.src = url;
  elements.blurCover.style.backgroundImage = `url("${url.replace(/"/g, '\\"')}")`;
  elements.cover.onerror = () => {
    elements.cover.removeAttribute("src");
    elements.blurCover.style.backgroundImage = "";
  };
}

function handleMeta(message) {
  AppUtils.setText(elements.title, message.title, "Unknown title");
  AppUtils.setText(elements.artist, message.artist, "Unknown artist");
  if (message.cover) updateCover(message.cover);
}

function handlePlayerInfo(message) {
  const station = message.station || {};
  AppUtils.setText(elements.type, station.type);
  AppUtils.setText(elements.stationType, station.type ? station.type.toUpperCase() : "NOW PLAYING");
  AppUtils.setText(elements.caption, station.caption);
  AppUtils.setText(elements.volumeDelta, station.volumeDelta);
  AppUtils.setText(elements.volume, message.volume);
  AppUtils.setText(elements.state, message.state);
  AppUtils.setText(elements.playlistIndex, message.playlist_index);
  AppUtils.setText(elements.playlistLength, message.playlist_length);
  if ( station.type =="playlist")  {
    elements.playlist_cards.forEach(element => {
      element.style.display = "";
    });
    
  } else {
    elements.playlist_cards.forEach(element => {
      element.style.display = "none";
    });
  
  }

  

  const volume = Number(message.volume);
  if (Number.isFinite(volume)) {
    const boundedVolume = Math.max(0, Math.min(100, volume));
    elements.volumeFill.style.width = `${boundedVolume}%`;
    elements.volumePercent.textContent = `${boundedVolume}%`;
  } else {
    elements.volumeFill.style.width = "0%";
    elements.volumePercent.textContent = "—";
  }

  elements.error.textContent = message.error || "";
}

function handleMessage(event) {
  let message;
  try {
    message = JSON.parse(event.data);
  } catch (error) {
    console.warn("Ignoring invalid WebSocket JSON:", error);
    return;
  }

  if (message.data_type === "meta") {
    handleMeta(message);
  } else if (message.data_type === "player_info") {
    handlePlayerInfo(message);
  } else {
    console.debug("Unknown player message:", message);
  }
}

function connectWebSocket() {
  if (!PLAYER_CONFIG.WEBSOCKET_URL) {
    setConnection(false, "WebSocket URL not configured");
    return;
  }

  const client = new WebSocketClient(PLAYER_CONFIG.WEBSOCKET_URL, {
    onOpen: () => setConnection(true, "Connected"),
    onMessage: handleMessage,
    onError: () => setConnection(false, "Connection error"),
    onClose: () => setConnection(false, "Disconnected")
  }, {
    autoReconnect: PLAYER_CONFIG.AUTO_RECONNECT,
    reconnectDelay: PLAYER_CONFIG.RECONNECT_DELAY_MS
  });
  client.connect();
}

async function sendControl(action) {
  const url = PLAYER_CONFIG.CONTROL_URLS[action];
  if (!url) {
    elements.error.textContent = `No URL configured for control: ${action}`;
    return;
  }

  try {
    // Controls intentionally use HTTP GET, as requested.
    const response = await fetch(url, {
      method: "GET",
      headers: PLAYER_CONFIG.CONTROL_HEADERS,
      cache: "no-store"
    });
    if (!response.ok) {
      throw new Error(`HTTP ${response.status} ${response.statusText}`);
    }
    elements.error.textContent = "";
  } catch (error) {
    console.error(`Control "${action}" failed:`, error);
    elements.error.textContent = `Control failed (${action}): ${error.message}`;
  }
}

document.querySelectorAll("[data-control]").forEach((button) => {
  button.addEventListener("click", () => sendControl(button.dataset.control));
});

connectWebSocket();
