// 👉 1. Lấy video ID từ URL YouTube
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

// 👉 2. Gửi message đến background để lấy danh sách chunk
function getTotalChunks(videoId) {
  return new Promise((resolve, reject) => {
    chrome.runtime.sendMessage({ type: "GET_TOTAL_CHUNK", videoId }, (response) => {
      if (response?.transcriptInfo) {
        resolve({
          list_chunks: response.transcriptInfo.list_chunks,
          need_translator: response.transcriptInfo.need_translator
        });
      } else {
        reject("Không thể lấy danh sách chunk.");
      }
    });
  });
}

// 👉 3. Gửi message để lấy audio từ chunk
function getAudioChunkViaBackground(videoId, chunkId, need_translator) {
  return new Promise((resolve, reject) => {
    chrome.runtime.sendMessage({
      type: "GET_TTS_URL",
      videoId: videoId,
      list_chunks_id: [chunkId],
      need_translator: need_translator
    }, (response) => {
      console.log(`[Content] Response nhận được cho chunk ${chunkId}:`, response.audioData);
      if (chrome.runtime.lastError) {
        console.error(`❌ [Chunk ${chunkId}] Lỗi Chrome Messaging:`, chrome.runtime.lastError);
        return reject(new Error("Lỗi Chrome Messaging: " + chrome.runtime.lastError.message));
      }
      if (!response || !response.audioData) {
        console.error(`❌ [Chunk ${chunkId}] Response hoặc audioData không hợp lệ:`, response);
        return reject(new Error("Response hoặc audioData không hợp lệ"));
      }
      if (response.audioData.byteLength === 0) {
        console.error(`❌ [Chunk ${chunkId}] Dữ liệu audioData rỗng, byteLength: ${response.audioData.byteLength}`);
        return reject(new Error("Dữ liệu âm thanh rỗng"));
      }
      try {
        const byteArray = new Uint8Array(response.audioData);
        console.log(`[Content] Kích thước audioData cho chunk ${chunkId}: ${byteArray.length}`);
        const blob = new Blob([byteArray], { type: "audio/mpeg" });
        const url = URL.createObjectURL(blob);
      } catch (err) {
        console.error(`❌ [Chunk ${chunkId}] Lỗi khi xử lý audioData:`, err);
        reject(new Error("Lỗi khi xử lý dữ liệu âm thanh"));
      }
    });
  });
}

// 👉 4. Tìm chunk tương ứng theo thời gian tua
function findChunkBySeekTime(list_chunks, seekTime) {
  const startTimes = list_chunks.map(Number);
  const index = startTimes.findIndex(start => start > seekTime);
  return index === -1 ? startTimes.length - 1 : Math.max(0, index - 1);
}

// 👉 5. Inject nút vào giao diện YouTube
function injectButton() {
  if (document.getElementById("tts-dubber-btn")) return;

  const container = document.querySelector(".ytp-right-controls");
  if (!container) return;

  const btn = document.createElement("button");
  btn.id = "tts-dubber-btn";
  btn.innerText = "🎙️";
  btn.style.cssText = `
    padding: 6px 10px;
    margin-left: 12px;
    background: #1d4da1;
    color: white;
    border: none;
    border-radius: 4px;
    cursor: pointer;
  `;
  container.appendChild(btn);

  btn.addEventListener("click", async () => {
    const video = document.querySelector("video");
    if (!video) return alert("❌ Không tìm thấy video.");
    video.muted = true;
    video.pause();

    const videoId = getYouTubeVideoId();
    if (!videoId) return alert("❌ Không thể lấy video ID.");

    try {
      const { list_chunks, need_translator } = await getTotalChunks(videoId);
      console.log("✅ Danh sách chunk:", list_chunks);

      startTTSPlayback(video, videoId, list_chunks, need_translator);
    } catch (error) {
      console.error("❌ Lỗi khi khởi động dubbing:", error);
      alert("Lỗi khi lấy dữ liệu lồng tiếng.");
    }
  });
}

// 👉 6. Khởi động MediaSource và phát tuần tự các chunk
async function startTTSPlayback(video, videoId, chunkList, need_translator) {
  const audio = new Audio();
  const mediaSource = new MediaSource();
  audio.src = URL.createObjectURL(mediaSource);
  audio.crossOrigin = "anonymous";

  let currentChunkIndex = 0;
  const pendingChunks = {};
  let sourceBuffer;
  let isAppending = false;

  // ✅ Gắn sự kiện theo dõi trạng thái audio
  audio.onplay = () => console.log("✅ [Audio] Bắt đầu phát.");
  audio.onpause = () => console.log("⏸️ [Audio] Tạm dừng.");
  audio.onended = () => console.log("🔚 [Audio] Kết thúc phát.");
  audio.onerror = (e) => {
    const err = audio.error;
    const message =
      err?.code === 1 ? "MEDIA_ERR_ABORTED - Người dùng dừng phát."
      : err?.code === 2 ? "MEDIA_ERR_NETWORK - Lỗi mạng khi tải file."
      : err?.code === 3 ? "MEDIA_ERR_DECODE - Không giải mã được file âm thanh (có thể do codec không hỗ trợ hoặc file hỏng)."
      : err?.code === 4 ? "MEDIA_ERR_SRC_NOT_SUPPORTED - Định dạng hoặc codec không được hỗ trợ."
      : "Lỗi không xác định.";
    console.error(`❌ [Audio] Lỗi khi phát: code=${err?.code} → ${message}`);
  };

  // ⏱️ Theo dõi tiến trình audio mỗi 5 giây
  setInterval(() => {
    console.log(`🕒 [Audio Debug] currentTime: ${audio.currentTime.toFixed(2)}s, paused: ${audio.paused}`);
  }, 5000);

  mediaSource.addEventListener("sourceopen", async () => {
    try {
      sourceBuffer = mediaSource.addSourceBuffer('audio/mpeg');
      console.log("✅ [MediaSource] sourceBuffer đã được khởi tạo.");

      sourceBuffer.addEventListener("updateend", async () => {
        isAppending = false;
        console.log(`✅ [Buffer] Đã nạp xong chunk ${currentChunkIndex}`);
        currentChunkIndex++;
        if (currentChunkIndex < chunkList.length) {
          await loadAndAppendChunk(videoId, chunkList, currentChunkIndex, sourceBuffer, pendingChunks, need_translator);
        } else {
          console.log("🔚 [Buffer] Hết chunk, kết thúc media stream.");
          mediaSource.endOfStream();
        }
      });

      await loadAndAppendChunk(videoId, chunkList, currentChunkIndex, sourceBuffer, pendingChunks, need_translator);
      video.play();
      audio.play().then(() => {
        console.log("🔊 [Audio] audio.play() thành công");
      }).catch((err) => {
        console.error("❌ [Audio] audio.play() thất bại:", err);
      });

    } catch (err) {
      console.error("❌ [MediaSource] Lỗi khi mở source:", err);
    }
  });

  video.addEventListener("pause", () => audio.pause());
  video.addEventListener("play", () => {
    audio.currentTime = video.currentTime;
    audio.play();
  });

  // 👉 Tua video → tìm chunk mới phù hợp → tải lại
  video.addEventListener("seeked", async () => {
    const seekTime = video.currentTime;
    const newIndex = findChunkBySeekTime(chunkList, seekTime);
    const chunkId = `${videoId}_${chunkList[newIndex]}`;

    if (newIndex !== currentChunkIndex) {
      console.log("🔁 Tua đến:", seekTime, "→ Chunk:", chunkId);
      currentChunkIndex = newIndex;

      try {
        sourceBuffer.abort();
        sourceBuffer.remove(0, mediaSource.duration || Infinity);
        sourceBuffer.addEventListener("updateend", () => {
          loadAndAppendChunk(videoId, chunkList, currentChunkIndex, sourceBuffer, pendingChunks, need_translator);
        }, { once: true });
      } catch (e) {
        console.warn("⚠️ Không thể reset buffer:", e);
      }
    }
  });

  alert("🔊 Đã bật lồng tiếng TTS!");
}

// 👉 7. Tải và nạp chunk vào SourceBuffer
async function loadAndAppendChunk(videoId, chunkList, index, sourceBuffer, pendingChunks, need_translator) {
  if (index >= chunkList.length) return;
  if (sourceBuffer.updating) return;

  const chunkId = `${videoId}_${chunkList[index]}`;
  if (pendingChunks[chunkId]) {
    sourceBuffer.appendBuffer(pendingChunks[chunkId]);
    return;
  }

  try {
    const blob = await getAudioChunkViaBackground(videoId, chunkId, need_translator);
    const arrayBuffer = await blob.arrayBuffer();
    pendingChunks[chunkId] = arrayBuffer;
    sourceBuffer.appendBuffer(arrayBuffer);
    console.log(`📦 [Chunk] Đã tải và nạp chunk: ${chunkId}`);
  } catch (err) {
    console.error("❌ Lỗi khi tải chunk:", err);
  }
}

// 👉 8. Theo dõi thay đổi URL (YouTube SPA)
let lastUrl = location.href;
new MutationObserver(() => {
  if (location.href !== lastUrl) {
    lastUrl = location.href;
    setTimeout(injectButton, 1000);
  }
}).observe(document, { subtree: true, childList: true });

// 👉 9. Inject ban đầu
setInterval(injectButton, 1500);
