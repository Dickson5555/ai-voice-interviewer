(() => {
  "use strict";

  // ---------------- DOM ----------------
  const orb        = document.getElementById("orb");
  const statusEl   = document.getElementById("status");
  const startBtn   = document.getElementById("startBtn");
  const panel      = document.getElementById("panel");
  const panelBody  = document.getElementById("transcript");
  const panelClose = document.getElementById("panelClose");
  const panelToggle= document.getElementById("panelToggle");
  const scoreEl    = document.getElementById("scoreValue");
  const resetBtn   = document.getElementById("resetBtn");
  const endBtn     = document.getElementById("endBtn");

  // ---------------- Config ----------------
  const WS_URL = (() => {
    const proto = location.protocol === "https:" ? "wss:" : "ws:";
    return `${proto}//${location.host}/ws`;
  })();

  const STATE = {
    IDLE: "idle",
    LISTENING: "listening",
    THINKING: "thinking",
    SPEAKING: "speaking",
  };

  // ---------------- Orb control ----------------
  function setOrbState(state) {
    orb.dataset.state = state;
    const labels = {
      [STATE.IDLE]: "Ready",
      [STATE.LISTENING]: "Listening…",
      [STATE.THINKING]: "Thinking…",
      [STATE.SPEAKING]: "AI Speaking…",
    };
    statusEl.textContent = labels[state] || "Ready";
  }

  // ---------------- Transcript helpers ----------------
  function openPanel() { panel.classList.add("is-open"); }
  function closePanel() { panel.classList.remove("is-open"); }
  function togglePanel() { panel.classList.toggle("is-open"); }

  function addBubble(text, kind = "ai", tag = "") {
    const el = document.createElement("div");
    el.className = `bubble bubble--${kind}`;
    if (tag) {
      const t = document.createElement("span");
      t.className = "bubble__tag";
      t.textContent = tag;
      el.appendChild(t);
    }
    el.appendChild(document.createTextNode(text));
    panelBody.appendChild(el);
    panelBody.scrollTop = panelBody.scrollHeight;
  }

  function clearTranscript() {
    panelBody.innerHTML = "";
    scoreEl.textContent = "0";
  }

  // ---------------- Speech Recognition (STT) ----------------
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  let recognition = null;
  let listening = false;

  if (SR) {
    recognition = new SR();
    recognition.continuous = false;
    recognition.interimResults = false;
    recognition.lang = "en-US";

    recognition.onresult = (event) => {
      const transcript = event.results[0][0].transcript?.trim();
      listening = false;
      if (!transcript) return;
      addBubble(transcript, "user", "You");
      setOrbState(STATE.THINKING);
      send({ action: "answer", message: transcript });
    };

    recognition.onerror = (e) => {
      listening = false;
      console.warn("Speech recognition error:", e.error);
      // Fall back to idle so user can retry.
      setOrbState(STATE.IDLE);
    };

    recognition.onend = () => {
      listening = false;
      // Only revert to idle if we're not mid-flow.
      if (orb.dataset.state === STATE.LISTENING) setOrbState(STATE.IDLE);
    };
  }

  function startListening() {
    if (!recognition) {
      console.warn("SpeechRecognition not supported in this browser.");
      return;
    }
    if (listening) return;
    try {
      listening = true;
      setOrbState(STATE.LISTENING);
      recognition.start();
    } catch (e) {
      listening = false;
      console.warn("Failed to start recognition:", e);
    }
  }

  // ---------------- Speech Synthesis (TTS) ----------------
  function speak(text, onDone) {
    if (!("speechSynthesis" in window) || !text) {
      onDone && onDone();
      return;
    }
    // Cancel anything currently playing.
    window.speechSynthesis.cancel();

    const utt = new SpeechSynthesisUtterance(text);
    utt.rate = 1.0;
    utt.pitch = 1.0;
    utt.volume = 1.0;

    utt.onstart = () => setOrbState(STATE.SPEAKING);
    utt.onend   = () => {
      setOrbState(STATE.IDLE);
      onDone && onDone();
    };
    utt.onerror = () => {
      setOrbState(STATE.IDLE);
      onDone && onDone();
    };

    window.speechSynthesis.speak(utt);
  }

  // ---------------- WebSocket ----------------
  let socket = null;
  let reconnectTimer = null;
  let interviewActive = false;

  function connect() {
    socket = new WebSocket(WS_URL);

    socket.addEventListener("open", () => {
      console.log("WS connected");
    });

    socket.addEventListener("message", (event) => {
      let data;
      try { data = JSON.parse(event.data); }
      catch { return; }

      handleServerMessage(data);
    });

    socket.addEventListener("close", () => {
      console.log("WS closed");
      if (interviewActive) {
        setOrbState(STATE.IDLE);
        statusEl.textContent = "Disconnected";
        scheduleReconnect();
      }
    });

    socket.addEventListener("error", (e) => {
      console.warn("WS error:", e);
    });
  }

  function scheduleReconnect() {
    if (reconnectTimer) return;
    reconnectTimer = setTimeout(() => {
      reconnectTimer = null;
      connect();
    }, 2000);
  }

  function send(payload) {
    if (!socket || socket.readyState !== WebSocket.OPEN) {
      console.warn("Socket not open, dropping payload:", payload);
      return;
    }
    socket.send(JSON.stringify(payload));
  }

  // ---------------- Server message dispatch ----------------
  function handleServerMessage(data) {
    switch (data.type) {
      case "interview": {
        interviewActive = true;
        startBtn.disabled = true;

        if (data.reaction)     addBubble(data.reaction, "ai", "Reaction");
        if (data.feedback)     addBubble(data.feedback, "ai", "Feedback");
        if (typeof data.score === "number") {
          scoreEl.textContent = String(data.score);
          addBubble(`Score: ${data.score}/10`, "meta");
        }
        if (data.next_question) addBubble(data.next_question, "ai", "Question");

        const speech = [data.reaction, data.feedback, data.next_question]
          .filter(Boolean).join(" ");
        speak(speech, () => {
          // After AI finishes, listen for the candidate.
          setTimeout(startListening, 400);
        });
        break;
      }

      case "error":
        console.warn("Server error:", data.message);
        setOrbState(STATE.IDLE);
        break;

      case "ended":
        addBubble(data.message, "ai", "System");
        interviewActive = false;
        startBtn.disabled = false;
        setOrbState(STATE.IDLE);
        break;

      default:
        console.warn("Unknown message type:", data);
    }
  }

  // ---------------- UI wiring ----------------
  startBtn.addEventListener("click", () => {
    startBtn.disabled = true;
    openPanel();
    clearTranscript();
    setOrbState(STATE.THINKING);
    send({ action: "start" });
  });

  resetBtn.addEventListener("click", () => {
    clearTranscript();
    setOrbState(STATE.THINKING);
    send({ action: "reset" });
  });

  endBtn.addEventListener("click", () => {
    send({ action: "end" });
    interviewActive = false;
    window.speechSynthesis?.cancel();
    setOrbState(STATE.IDLE);
    startBtn.disabled = false;
  });

  panelClose.addEventListener("click", closePanel);
  panelToggle.addEventListener("click", togglePanel);

  // ---------------- Boot ----------------
  connect();
  setOrbState(STATE.IDLE);
})();