/* Shared WebSocket lifecycle and optional automatic reconnection. */
(() => {
  "use strict";

  class WebSocketClient {
    constructor(url, handlers = {}, options = {}) {
      this.url = url;
      this.handlers = handlers;
      this.autoReconnect = options.autoReconnect === true;
      this.reconnectDelay = options.reconnectDelay ?? 2500;
      this.socket = null;
      this.reconnectTimer = null;
      this.closedManually = false;
    }

    connect() {
      this.closedManually = false;
      clearTimeout(this.reconnectTimer);
      if (this.socket && (this.socket.readyState === WebSocket.OPEN ||
          this.socket.readyState === WebSocket.CONNECTING)) {
        this.socket.close();
      }

      try {
        const socket = new WebSocket(this.url);
        this.socket = socket;
        socket.addEventListener("open", event => {
          if (this.socket !== socket) return;
          this.handlers.onOpen?.(event);
        });
        socket.addEventListener("message", event => {
          if (this.socket === socket) this.handlers.onMessage?.(event);
        });
        socket.addEventListener("error", event => {
          if (this.socket === socket) this.handlers.onError?.(event);
        });
        socket.addEventListener("close", event => {
          if (this.socket !== socket) return;
          this.socket = null;
          this.handlers.onClose?.(event);
          if (this.autoReconnect && !this.closedManually) this.scheduleReconnect();
        });
      } catch (error) {
        this.handlers.onError?.(error);
        if (this.autoReconnect && !this.closedManually) this.scheduleReconnect();
      }
    }

    scheduleReconnect() {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = setTimeout(() => this.connect(), this.reconnectDelay);
    }

    disconnect(code = 1000, reason = "Manually disconnected") {
      this.closedManually = true;
      clearTimeout(this.reconnectTimer);
      if (this.socket) this.socket.close(code, reason);
    }
  }

  window.WebSocketClient = WebSocketClient;
})();
