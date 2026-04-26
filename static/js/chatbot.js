(function () {
  if (window.__marketLensChatbotInitialized) return;
  window.__marketLensChatbotInitialized = true;

  const script = document.currentScript;
  const pageName = (script && script.dataset && script.dataset.page) || window.location.pathname;
  const isEnabled = !script || script.dataset.enabled !== "false";
  if (!isEnabled) return;

  const root = document.createElement("div");
  root.innerHTML = `
    <button class="ml-chatbot-fab" id="mlChatFab" aria-label="Open assistant">💬</button>
    <section class="ml-chatbot-panel" id="mlChatPanel" aria-label="MarketLens assistant">
      <header class="ml-chatbot-head">
        <div>
          <div class="ml-chatbot-title">MarketLens Assistant</div>
          <div class="ml-chatbot-sub">Context-aware fintech helper</div>
        </div>
        <button class="ml-chatbot-close" id="mlChatClose" type="button">Close</button>
      </header>
      <div class="ml-chatbot-messages" id="mlChatMessages"></div>
      <div class="ml-chatbot-input-row">
        <input class="ml-chatbot-input" id="mlChatInput" placeholder="Ask: What does RSI mean?" />
        <button class="ml-chatbot-send" id="mlChatSend" type="button">Send</button>
      </div>
    </section>
  `;
  document.body.appendChild(root);

  const fab = document.getElementById("mlChatFab");
  const panel = document.getElementById("mlChatPanel");
  const closeBtn = document.getElementById("mlChatClose");
  const messages = document.getElementById("mlChatMessages");
  const input = document.getElementById("mlChatInput");
  const send = document.getElementById("mlChatSend");
  const history = [];

  const initialMessageByPage = (() => {
    const p = pageName.toLowerCase();
    if (p.includes("dashboard")) return "You are on Dashboard. Ask about watchlist, RSI, MA20/MA50, and BUY/SELL/HOLD signals.";
    if (p.includes("market")) return "You are on Market Data. Ask about stock catalog, prices, or adding stocks to watchlist.";
    if (p.includes("home")) return "You are on Home. Ask what MarketLens does, how signals work, or beginner finance questions.";
    return "Ask me about charts, indicators, stock signals, and company basics.";
  })();

  function addMessage(text, role) {
    const el = document.createElement("div");
    el.className = `ml-chat-msg ${role}`;
    el.textContent = text;
    messages.appendChild(el);
    messages.scrollTop = messages.scrollHeight;
    return el;
  }

  function getPageContext() {
    const context = {};
    const tickerEl = document.getElementById("sTicker");
    const signalEl = document.getElementById("sSignal");
    const rsiEl = document.getElementById("sRsi");
    const maEl = document.getElementById("sMa");

    if (tickerEl && tickerEl.textContent.trim() && tickerEl.textContent.trim() !== "-") context.ticker = tickerEl.textContent.trim();
    if (signalEl && signalEl.textContent.trim() && signalEl.textContent.trim() !== "-") context.signal = signalEl.textContent.trim();
    if (rsiEl && rsiEl.textContent.trim() && rsiEl.textContent.trim() !== "-") context.rsi = rsiEl.textContent.trim();
    if (maEl && maEl.textContent.includes("/")) {
      const [ma20, ma50] = maEl.textContent.split("/");
      context.ma20 = ma20.trim();
      context.ma50 = ma50.trim();
    }

    const tickerInput = document.getElementById("ticker-input");
    if (!context.ticker && tickerInput && tickerInput.value.trim()) context.ticker = tickerInput.value.trim().toUpperCase();
    return context;
  }

  async function askServer(message) {
    const res = await fetch("/api/chatbot", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message,
        page: window.location.pathname,
        data: getPageContext(),
        history: history.slice(-10),
      }),
    });
    const data = await res.json();
    return data.reply || "I can help you understand stock charts, indicators (RSI, MA20, MA50), signals (BUY/SELL/HOLD), and basic company info.";
  }

  async function sendMessage() {
    const text = input.value.trim();
    if (!text) return;
    addMessage(text, "user");
    history.push({ role: "user", content: text });
    input.value = "";

    const typing = addMessage("Bot is typing...", "bot");
    try {
      const reply = await askServer(text);
      typing.textContent = reply;
      history.push({ role: "assistant", content: reply });
    } catch (_error) {
      const fallback = "I'm having trouble responding right now.";
      typing.textContent = fallback;
      history.push({ role: "assistant", content: fallback });
    }
  }

  fab.addEventListener("click", function () {
    const opening = !panel.classList.contains("open");
    panel.classList.toggle("open");
    if (opening && messages.children.length === 0) {
      addMessage(initialMessageByPage, "bot");
    }
  });
  closeBtn.addEventListener("click", function () {
    panel.classList.remove("open");
  });
  send.addEventListener("click", sendMessage);
  input.addEventListener("keydown", function (e) {
    if (e.key === "Enter") {
      e.preventDefault();
      sendMessage();
    }
  });
})();
