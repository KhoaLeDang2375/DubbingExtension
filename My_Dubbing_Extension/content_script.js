const CHUNK_PREFETCH_COUNT = 5;

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
      list_chunks_id: chunkIds, // Gửi danh sách chunk IDs
      need_translator: need_translator
    }, (response) => {
      console.log(`[Content] Response nhận được cho chunks:`, response);
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
          console.log(`[Content] Kích thước audioData cho chunk ${chunk.chunk_id}: ${byteArray.length}`);
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

  let state = {
    currentChunkIndex: 0
  };
  const pendingChunks = {};
  let sourceBuffer;
  let isAudioPlaying = false;
  // Debug audio
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
  console.log("MediaSource state:", mediaSource.readyState);
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

  // Đồng bộ khi video pause/play
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
      audio.play().catch(err => {
        console.warn("⚠️ Audio resume failed:", err);
      });
    }
  });

  // Xử lý khi tua video
video.addEventListener("seeked", () => {
  alert("⚠️ Không hỗ trợ tua khi đang dùng chế độ lồng tiếng TTS.");
  video.currentTime = audio.currentTime; // quay lại đúng vị trí
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

    console.log(` Fetching chunks: ${filteredIds.join(", ")}`);
    filteredIds.forEach(id => requestedChunks.add(id));

    try {
      const blobs = await getAudioChunkViaBackground(videoId, filteredIds, need_translator);
      const bufferPromises = blobs.map(chunk =>
        chunk.blob.arrayBuffer().then(buffer => {
          console.log(`✅ Add pending chunk ${chunk.chunk_id} (${buffer.byteLength} bytes)`);
          pendingChunks[chunk.chunk_id] = buffer;
        }).catch(err => {
          console.error(`❌ Buffer error for ${chunk.chunk_id}:`, err);
        })
      );
      await Promise.all(bufferPromises);

      // B. Khi tải xong, nếu appendQueue còn trống => append ngay
      if (appendQueue.length < PREFETCH_COUNT) {
        appendNextChunk();
      }
    } catch (e) {
      console.error("❌ Lỗi tải chunk:", e);
      if (retryCount < RETRY_LIMIT) {
        setTimeout(() => fetchChunks(chunkIds, retryCount + 1), 1000);
      } else {
        console.error(`❌ Bỏ qua sau ${RETRY_LIMIT} lần:`, chunkIds);
        state.currentChunkIndex++;
        appendNextChunk();
      }
    }
  }

  async function processAppendQueue() {
    console.log(`[Debug] readyState=${mediaSource.readyState}, updating=${sourceBuffer.updating}, queueLen=${appendQueue.length}`);
    if (mediaSource.readyState !== "open" || sourceBuffer.updating || appendQueue.length === 0) {
      return;
    }
    const { chunkId, buffer } = appendQueue.shift();
    console.log(`📦 Appending ${chunkId}, remaining queue=${appendQueue.length}`);
    try {
      sourceBuffer.appendBuffer(buffer);
      delete pendingChunks[chunkId];
      appendedChunks.add(chunkId);
      state.currentChunkIndex++; 
      // B. Gọi appendNextChunk ngay để đảm bảo queue luôn đầy
      appendNextChunk();
    } catch (e) {
      console.error(`❌ Append error for ${chunkId}:`, e);
      setTimeout(() => processAppendQueue(), 100);
    }
  }

  async function appendNextChunk() {
    if (state.currentChunkIndex >= chunkList.length) return;

    // Luôn duyệt để fill appendQueue tới PREFETCH_COUNT
    while (appendQueue.length < PREFETCH_COUNT && state.currentChunkIndex < chunkList.length) {
      const chunkId = `${videoId}_${chunkList[state.currentChunkIndex]}`;
      if (pendingChunks[chunkId] && !appendedChunks.has(chunkId) && !appendQueue.some(item => item.chunkId === chunkId)) {
        appendQueue.push({ chunkId, buffer: pendingChunks[chunkId]});
        console.log(` Queueing ${chunkId} (queue size: ${appendQueue.length})`);
      } else if (!pendingChunks[chunkId]&& !appendedChunks.has(chunkId)) {
        console.log(`⏳ Chunk ${chunkId} chưa có, yêu cầu tải.`);
        fetchChunks([chunkId]);
        break; // chờ tải xong mới tiếp
      } else {
        state.currentChunkIndex++;
      }
    }

    processAppendQueue();

    // C. Prefetch tiếp theo song song (tải trước cả khi buffer còn nhiều)
    const nextToPrefetch = [];
    for (let i = state.currentChunkIndex + appendQueue.length; 
         i < chunkList.length && nextToPrefetch.length < PREFETCH_COUNT; i++) {
      const nextChunkId = `${videoId}_${chunkList[i]}`;
      if (!pendingChunks[nextChunkId] && !requestedChunks.has(nextChunkId)&& !appendedChunks.has(nextChunkId)) {
        nextToPrefetch.push(nextChunkId);
      }
    }
    if (nextToPrefetch.length > 0) {
      fetchChunks(nextToPrefetch);
    }
  }

  sourceBuffer.addEventListener("updateend", () => {
    processAppendQueue();
    logBufferedRanges();
  });

  function logBufferedRanges() {
    const ranges = [];
    for (let i = 0; i < audio.buffered.length; i++) {
      ranges.push(`[${audio.buffered.start(i).toFixed(2)} → ${audio.buffered.end(i).toFixed(2)}]`);
    }
    const bufferedEnd = audio.buffered.length > 0 ? audio.buffered.end(audio.buffered.length - 1) : 0;
    const timeLeft = bufferedEnd - audio.currentTime;
    console.log(`🔄 Buffered ranges: ${ranges.join(", ")} | ⏱️ Time left: ${timeLeft.toFixed(2)}s | Queue size: ${appendQueue.length}`);
  }

  // D. Monitor bộ đệm, nhưng vẫn prefetch ngay cả khi buffer còn nhiều
  const bufferMonitor = setInterval(() => {
    if (sourceBuffer.updating || audio.buffered.length === 0) return;
    appendNextChunk(); // luôn cố gắng fill queue
  }, BUFFER_MONITOR_INTERVAL);

  // Load initial big batch
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