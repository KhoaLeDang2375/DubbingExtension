const CHUNK_PREFETCH_COUNT = 3;

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

// 👉 3. Gửi message để lấy audio từ các chunk
function getAudioChunkViaBackground(videoId, chunkIds, need_translator) {
  return new Promise((resolve, reject) => {
    chrome.runtime.sendMessage({
      type: "GET_TTS_URL",
      videoId: videoId,
      list_chunks_id: chunkIds,
      need_translator: need_translator
    }, (response) => {
      if (chrome.runtime.lastError) {
        console.error(`❌ Lỗi Chrome Messaging:`, chrome.runtime.lastError);
        return reject(new Error("Lỗi Chrome Messaging: " + chrome.runtime.lastError.message));
      }
      if (!response || !response.audioChunks || !Array.isArray(response.audioChunks)) {
        console.error(`❌ Response hoặc audioChunks không hợp lệ:`, response);
        return reject(new Error("Response hoặc audioChunks không hợp lệ"));
      }
      try {
        const blobs = response.audioChunks.map(chunk => {
          if (!chunk.audioData) {
            console.error(`❌ [Chunk ${chunk.chunk_id}] Thiếu audioData`);
            return null;
          }
          const byteArray = new Uint8Array(chunk.audioData);
          return { chunk_id: chunk.chunk_id, blob: new Blob([byteArray], { type: "audio/webm; codecs=opus" }) };
        }).filter(chunk => chunk !== null);
        resolve(blobs);
      } catch (err) {
        console.error(`❌ Lỗi khi xử lý audioChunks:`, err);
        reject(new Error("Lỗi khi xử lý dữ liệu âm thanh"));
      }
    });
  });
}

// 👉 5. Inject nút vào giao diện YouTube
function injectButton() {
  if (document.getElementById("tts-dubber-btn")) return;

  const container = document.querySelector(".ytp-right-controls");
  if (!container) return;

  const iconUrl = chrome.runtime.getURL('assets/imgbtn.png');

  const buttonHTML = `
    <div class="youtube-dubbing-button" id="tts-dubber-btn">
      <div class="youtube-dubbing-container">
        <div class="youtube-dubbing-logo">
          <img src="${iconUrl}" alt="youtube-dubbing">
        </div>
      </div>
    </div>`;

  container.insertAdjacentHTML('beforeend', buttonHTML);

  const btn = document.getElementById("tts-dubber-btn");
  btn.addEventListener("click", async () => {
    const video = document.querySelector("video");
    if (!video) return alert("❌ Không tìm thấy video.");
    video.muted = true;
    video.pause();

    const videoId = getYouTubeVideoId();
    if (!videoId) return alert("❌ Không thể lấy video ID.");

    try {
      const { list_chunks, need_translator } = await getTotalChunks(videoId);
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

  let state = {
    currentChunkIndex: 0
  };
  const pendingChunks = {};
  let sourceBuffer;
  let isAudioPlaying = false;

  audio.onplay = () => console.log("✅ [Audio] Bắt đầu phát.");
  audio.onpause = () => console.log("⏸️ [Audio] Tạm dừng.");
  audio.onended = () => {
    isAudioPlaying = false;
    console.log("🔚 Audio ended");
  };
  audio.onerror = (e) => {
    const err = audio.error;
    const message =
      err?.code === 1 ? "MEDIA_ERR_ABORTED" :
      err?.code === 2 ? "MEDIA_ERR_NETWORK" :
      err?.code === 3 ? "MEDIA_ERR_DECODE" :
      err?.code === 4 ? "MEDIA_ERR_SRC_NOT_SUPPORTED" :
      "Lỗi không xác định.";
    console.error(`❌ [Audio] Lỗi khi phát: code=${err?.code} → ${message}`);
  };

  mediaSource.addEventListener("sourceopen", async () => {
    try {
      sourceBuffer = mediaSource.addSourceBuffer('audio/webm; codecs=opus');
      sourceBuffer.mode = 'sequence';
      console.log("✅ [MediaSource] sourceBuffer đã được khởi tạo.");
      setupChunkQueue(mediaSource, sourceBuffer, chunkList, videoId, state, pendingChunks, need_translator, audio);
      sourceBuffer.addEventListener("error", (e) => {
        console.error("❌ SourceBuffer error:", e);
      });
      sourceBuffer.addEventListener("updateend", async function onceStartPlayback() {
        if (!isAudioPlaying && audio.buffered.length > 0 && audio.buffered.end(0) > 0) {
          try {
            await video.play();
            await audio.play();
            isAudioPlaying = true;
            console.log("🔊 Audio started");
          } catch (err) {
            isAudioPlaying = false;
            console.error("❌ audio.play() error:", err);
            if (err.name === "NotAllowedError") {
              console.warn("⚠️ Trình duyệt chặn auto-play, yêu cầu tương tác người dùng.");
            }
          }
          sourceBuffer.removeEventListener("updateend", onceStartPlayback);
        }
      });
    } catch (err) {
      console.error("❌ [MediaSource] Lỗi khi mở source:", err);
    }
  });

  video.addEventListener("pause", () => {
    if (isAudioPlaying) {
      audio.pause();
      isAudioPlaying = false;
      console.log("⏸️ [Sync] Video pause → Audio pause");
    }
  });

  video.addEventListener("play", () => {
    if (!isAudioPlaying) {
      audio.currentTime = video.currentTime;
      isAudioPlaying = true;
      audio.play().catch(err => {
        console.warn("⚠️ Audio resume failed:", err);
      });
    }
  });

  video.addEventListener("seeked", () => {
    alert("⚠️ Không hỗ trợ tua khi đang dùng chế độ lồng tiếng TTS.");
    video.currentTime = audio.currentTime;
  });

  alert("🔊 Đã bật lồng tiếng TTS!");
}

// 👉 7. Tải và nạp chunk vào SourceBuffer
async function setupChunkQueue(mediaSource, sourceBuffer, chunkList, videoId, state, pendingChunks, need_translator, audio) {
  const requestedChunks = new Set();
  const appendedChunks = new Set();
  const appendQueue = [];
  const PREFETCH_COUNT = CHUNK_PREFETCH_COUNT;
  const RETRY_LIMIT = 3;
  const BUFFER_MONITOR_INTERVAL = 1000;

  async function fetchChunks(chunkIds, retryCount = 0) {
    const filteredIds = chunkIds.filter(id => (!requestedChunks.has(id) && !appendedChunks.has(id)));
    if (filteredIds.length === 0) return;

    filteredIds.forEach(id => requestedChunks.add(id));
    try {
      const blobs = await getAudioChunkViaBackground(videoId, filteredIds, need_translator);
      const bufferPromises = blobs.map(chunk =>
        chunk.blob.arrayBuffer().then(buffer => {
          pendingChunks[chunk.chunk_id] = buffer;
        }).catch(err => {
          console.error(`❌ Buffer error for ${chunk.chunk_id}:`, err);
        })
      );
      await Promise.all(bufferPromises);

      if (appendQueue.length < PREFETCH_COUNT) {
        appendNextChunk();
      }
    } catch (e) {
      console.error("❌ Lỗi tải chunk:", e);
      if (retryCount < RETRY_LIMIT) {
        setTimeout(() => fetchChunks(chunkIds, retryCount + 1), 1000);
      } else {
        console.error(`❌ Bỏ qua sau ${RETRY_LIMIT} lần:`, chunkIds);
        // FIX: Không tăng state.currentChunkIndex, để appendNextChunk quản lý
        filteredIds.forEach(id => requestedChunks.delete(id));
        appendNextChunk();
      }
    }
  }

  async function processAppendQueue() {
    if (mediaSource.readyState !== "open" || sourceBuffer.updating || appendQueue.length === 0) {
      return;
    }
    const { chunkId, buffer } = appendQueue.shift();
    try {
      sourceBuffer.appendBuffer(buffer);
      delete pendingChunks[chunkId];
      appendedChunks.add(chunkId);
      appendNextChunk();
    } catch (e) {
      console.error(`❌ Append error for ${chunkId}:`, e);
      setTimeout(() => processAppendQueue(), 100);
    }
  }

  async function appendNextChunk() {
    if (state.currentChunkIndex >= chunkList.length) return;

    while (appendQueue.length < PREFETCH_COUNT && state.currentChunkIndex < chunkList.length) {
      const chunkId = `${videoId}_${chunkList[state.currentChunkIndex]}`;
      if (pendingChunks[chunkId] && !appendedChunks.has(chunkId) && !appendQueue.some(item => item.chunkId === chunkId)) {
        appendQueue.push({ chunkId, buffer: pendingChunks[chunkId]});
      } else if (!pendingChunks[chunkId] && !appendedChunks.has(chunkId)) {
        fetchChunks([chunkId]);
        break;
      } else {
        state.currentChunkIndex++;
      }
    }

    processAppendQueue();

    // FIX: Kiểm tra chunk bị bỏ sót trước khi prefetch xa
    const nextToPrefetch = [];
    for (let i = state.currentChunkIndex; i < state.currentChunkIndex + PREFETCH_COUNT && i < chunkList.length; i++) {
      const nextChunkId = `${videoId}_${chunkList[i]}`;
      if (!pendingChunks[nextChunkId] && !requestedChunks.has(nextChunkId) && !appendedChunks.has(nextChunkId)) {
        nextToPrefetch.push(nextChunkId);
      }
    }
    if (nextToPrefetch.length > 0) {
      fetchChunks(nextToPrefetch);
    }
  }

  sourceBuffer.addEventListener("updateend", () => {
    processAppendQueue();
  });

  const bufferMonitor = setInterval(() => {
    if (sourceBuffer.updating || audio.buffered.length === 0) return;
    const missingChunks = [];
    for (let i = state.currentChunkIndex; i < state.currentChunkIndex + PREFETCH_COUNT && i < chunkList.length; i++) {
      const chunkId = `${videoId}_${chunkList[i]}`;
      if (!pendingChunks[chunkId] && !appendedChunks.has(chunkId) && !requestedChunks.has(chunkId)) {
        missingChunks.push(chunkId);
      }
    }
    if (missingChunks.length > 0) {
      fetchChunks(missingChunks);
    }
    appendNextChunk();
  }, BUFFER_MONITOR_INTERVAL);

  const initialChunkIds = [];
  for (let i = state.currentChunkIndex; i < state.currentChunkIndex + PREFETCH_COUNT && i < chunkList.length; i++) {
    const chunkId = `${videoId}_${chunkList[i]}`;
    if (!pendingChunks[chunkId]) initialChunkIds.push(chunkId);
  }

  await fetchChunks(initialChunkIds);
  appendNextChunk();

  audio.addEventListener("ended", () => clearInterval(bufferMonitor));
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