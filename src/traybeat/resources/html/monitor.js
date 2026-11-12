(() => {
      const $ = id => document.getElementById(id);
      const urlInput = $('url');
      const connectButton = $('connect');
      const disconnectButton = $('disconnect');
      const status = $('status');
      const messages = $('messages');
      const filterInput = $('filter');
      const autoScroll = $('autoscroll');
      let socket = null;
      let received = 0;
      let entries = [];

      function setStatus(text, kind = '') {
        status.textContent = text;
        status.className = 'status ' + kind;
      }

      function addEntry(kind, payload, timestamp = new Date()) {
        const entry = { kind, payload: String(payload), timestamp };
        entries.push(entry);
        render();
      }

      function render() {
        const term = filterInput.value.toLocaleLowerCase();
        const visible = entries.filter(e =>
          e.kind.toLocaleLowerCase().includes(term) ||
          e.payload.toLocaleLowerCase().includes(term)
        );

        messages.replaceChildren();
        if (!visible.length) {
          const empty = document.createElement('div');
          empty.className = 'empty';
          empty.textContent = entries.length ? 'Keine passenden Nachrichten.' : 'Noch keine Nachrichten empfangen.';
          messages.append(empty);
          return;
        }

        for (const entry of visible) {
          const article = document.createElement('article');
          article.className = 'message';

          const meta = document.createElement('div');
          meta.className = 'meta';
          const time = document.createElement('span');
          time.textContent = entry.timestamp.toLocaleTimeString();
          const type = document.createElement('span');
          type.textContent = entry.kind;
          meta.append(time, type);

          const pre = document.createElement('pre');
          pre.className = 'payload';
          pre.textContent = entry.payload;
          article.append(meta, pre);
          messages.append(article);
        }
        if (autoScroll.checked) messages.scrollTop = messages.scrollHeight;
      }

      function connect() {
        const url = urlInput.value.trim();
        if (!/^wss?:\/\//i.test(url)) {
          setStatus('Ungültige URL (ws:// oder wss:// erforderlich)', 'error');
          return;
        }
        if (socket) socket.disconnect();

        try {
          socket = new WebSocketClient(url, {
            onOpen: () => {
              setStatus('Verbunden', 'connected');
              addEntry('SYSTEM', 'WebSocket-Verbindung hergestellt: ' + url);
            },
            onMessage: async event => {
              received++;
              $('count').textContent = received;
              $('last').textContent = new Date().toLocaleTimeString();
              let text;
              try { text = await AppUtils.payloadToText(event.data); }
              catch (error) { text = '[Nachricht konnte nicht dekodiert werden: ' + error + ']'; }
              addEntry('IN', text);
            },
            onError: () => {
              setStatus('Verbindungsfehler', 'error');
              addEntry('SYSTEM', 'WebSocket-Fehler. Details ggf. in der Browser-Konsole.');
            },
            onClose: event => {
              setStatus('Getrennt');
              connectButton.disabled = false;
              disconnectButton.disabled = true;
              addEntry('SYSTEM', `Verbindung geschlossen (Code ${event.code}${event.reason ? ', ' + event.reason : ''}).`);
            }
          });
          socket.connect();
          setStatus('Verbinde …');
          connectButton.disabled = true;
          disconnectButton.disabled = false;
        } catch (error) {
          setStatus('Fehler: ' + error.message, 'error');
          connectButton.disabled = false;
          disconnectButton.disabled = true;
        }
      }

      connectButton.addEventListener('click', connect);
      disconnectButton.addEventListener('click', () => {
        if (socket) socket.disconnect(1000, 'Manuell getrennt');
      });
      $('clear').addEventListener('click', () => {
        entries = [];
        received = 0;
        $('count').textContent = '0';
        $('last').textContent = '–';
        render();
      });
      filterInput.addEventListener('input', render);
      urlInput.addEventListener('keydown', event => { if (event.key === 'Enter') connect(); });
    })();
