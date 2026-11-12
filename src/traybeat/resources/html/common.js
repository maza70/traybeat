/* Shared browser helpers used by the TrayBeat pages. */
(() => {
  "use strict";

  function setText(element, value, fallback = "—") {
    if (!element) return;
    element.textContent = value === null || value === undefined || value === ""
      ? fallback
      : String(value);
  }

  async function payloadToText(data) {
    if (typeof data === "string") return data;
    if (data instanceof Blob) return data.text();
    if (data instanceof ArrayBuffer) return new TextDecoder().decode(data);
    return String(data);
  }

  window.AppUtils = Object.freeze({ setText, payloadToText });
})();
