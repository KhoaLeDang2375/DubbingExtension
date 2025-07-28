// Hàm lấy video ID YouTube
function getYouTubeVideoId() {
  const url = window.location.href;

  const patterns = [
    /v=([a-zA-Z0-9_-]{11})/,
    /youtu\.be\/([a-zA-Z0-9_-]{11})/,
    /embed\/([a-zA-Z0-9_-]{11})/,
    /shorts\/([a-zA-Z0-9_-]{11})/
  ];

  for (const pattern of patterns) {
    const match = url.match(pattern);
    if (match && match[1]) return match[1];
  }

  return null;
}

// Inject button vào player controls
function injectButton() {
  // Tránh chèn lại nếu đã có
  if (document.getElementById("tts-dubber-btn")) return;

  const container = document.querySelector(".ytp-right-controls");
  if (!container) return; // chưa có player

  const btn = document.createElement("button");
  btn.id = "tts-dubber-btn";
  btn.innerText = "🎙️ Bật lồng tiếng";
  btn.style.cssText = `
    padding: 6px 10px;
    margin-left: 12px;
    background: #cc0000;
    color: white;
    border: none;
    border-radius: 4px;
    cursor: pointer;
    font-size: 14px;
  `;

  btn.addEventListener("click", async () => {
    console.log("[TTS] Kích hoạt theo dõi video...");

    const video = document.querySelector("video");
    if (!video) {
      alert("❌ Không tìm thấy video.");
      return;
    }
    video.muted = true; // Mute default audio
    video.pause()
    const videoId = getYouTubeVideoId();
    if (!videoId) {
      alert("❌ Không lấy được video ID.");
      return;
    }

    chrome.runtime.sendMessage({ type: "GET_TTS_URL", videoId }, (response) => {
    if (response && response.audioData) {
      const byteArray = new Uint8Array(response.audioData);
      const audioBlob = new Blob([byteArray], { type: "audio/wav" });
      const audioUrl = URL.createObjectURL(audioBlob);

      const ttsAudio = new Audio(audioUrl);
      ttsAudio.crossOrigin = "anonymous";
      video.play()
      // 👇 Play ngay trong click để tránh bị Chrome chặn
      ttsAudio.play().then(() => {
        console.log("✅ TTS Audio playing");

        // Đồng bộ với video
        video.addEventListener("play", () => {
          ttsAudio.currentTime = video.currentTime;
          ttsAudio.play();
        });

        video.addEventListener("pause", () => ttsAudio.pause());
        video.addEventListener("seeked", () => {
          ttsAudio.currentTime = video.currentTime;
        });

        alert("🔊 Lồng tiếng đã được kích hoạt!");
      }).catch((err) => {
        console.warn("⚠️ Không thể play audio:", err);
        alert("⚠️ Chrome không cho phép tự động phát âm thanh. Hãy tương tác lại.");
      });
    } else {
      alert("❌ Không thể lấy audio từ backend.");
    }
  });
});
  container.appendChild(btn);
}

// Theo dõi URL thay đổi (SPA)
let lastUrl = location.href;
new MutationObserver(() => {
  if (location.href !== lastUrl) {
    lastUrl = location.href;
    setTimeout(injectButton, 1000); // chờ một chút cho DOM sẵn sàng
  }
}).observe(document, { subtree: true, childList: true });

// Inject ban đầu
setInterval(injectButton, 1500);
