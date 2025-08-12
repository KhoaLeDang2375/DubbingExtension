class Dubbing {
    constructor(videoId, statusElement = null) {
        this.videoId = videoId;
        this.statusElement = statusElement;
    }

    async init(list_chunks_id, need_translator = true) {
        try {
            const settings = await this.loadSettings();
            const payload = this.buildPayload(settings, list_chunks_id, need_translator);
            const audioChunks = await this.sendRequest(payload);
            return audioChunks; // Trả về danh sách các chunk âm thanh
        } catch (error) {
            console.error("❌ Lỗi trong init():", error);
            this.setStatus("Đã xảy ra lỗi trong quá trình xử lý.");
            throw error;
        }
    }

    loadSettings() {
        return new Promise((resolve) => {
            chrome.storage.sync.get(
                ["sourceLanguage", "targetLanguage", "speakerVoice", "translatorEngine"],
                (result) => {
                    const settings = {
                        sourceLanguage: result.sourceLanguage || 'auto',
                        targetLanguage: result.targetLanguage || 'vi',
                        speakerVoice: result.speakerVoice || 'vi-VN-HoaiMyNeural',
                        translatorEngine: result.translatorEngine || 'AzureTranslator'
                    };
                    console.log("✅ Đã load settings:", settings);
                    resolve(settings);
                }
            );
        });
    }

    buildPayload(settings, list_chunks_id, need_translator = true) {
        const payload = {
            video_id: this.videoId,
            list_chunks_id: list_chunks_id,
            source_language: settings.sourceLanguage,
            target_language: settings.targetLanguage,
            translator: settings.translatorEngine,
            tts_voice: settings.speakerVoice,
            need_translator: need_translator
        };
        console.log("🛠️ Payload đã tạo:", payload);
        return payload;
    }

    async sendRequest(payload) {
        this.setStatus("⏳ Đang gửi yêu cầu và chờ âm thanh từ server...");
        try {
            const response = await fetch("http://127.0.0.1:8000/dubbing", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload)
            });
            if (!response.ok) {
                throw new Error(`Lỗi server: ${response.status}`);
            }
            const jsonResponse = await response.json();
            console.log("✅ [Background] Nhận được phản hồi JSON:", jsonResponse);

            // Xử lý danh sách chunks từ JSON
            const audioChunks = jsonResponse.chunks.map(chunk => {
                if (!chunk.audio_base64 || !chunk.chunk_id) {
                    console.error(`❌ [Chunk ${chunk.chunk_id || 'unknown'}] Thiếu audio_base64 hoặc chunk_id`);
                    throw new Error("Dữ liệu chunk không hợp lệ");
                }
                // Giải mã base64 thành Uint8Array
                const binaryString = atob(chunk.audio_base64);
                const len = binaryString.length;
                const bytes = new Uint8Array(len);
                for (let i = 0; i < len; i++) {
                    bytes[i] = binaryString.charCodeAt(i);
                }
                console.log(`[Background] Kích thước audioData cho chunk ${chunk.chunk_id}: ${bytes.length}`);
                return {
                    chunk_id: chunk.chunk_id,
                    audioData: Array.from(bytes), // Chuyển thành mảng số để tương thích với content_script.js
                };
            });

            if (audioChunks.length === 0) {
                console.error("❌ Không có dữ liệu âm thanh nào trong phản hồi");
                throw new Error("Dữ liệu âm thanh rỗng");
            }

            return audioChunks;
        } catch (error) {
            console.error("❌ Lỗi khi gửi request:", error);
            this.setStatus("Lỗi khi gửi request đến server.");
            throw error;
        }
    }

    setStatus(text) {
        if (this.statusElement) {
            this.statusElement.textContent = text;
        } else {
            console.log("📢 Trạng thái:", text);
        }
    }
}

// 🔁 Lắng nghe message từ content script
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    // Xử lý async trong event listener
    (async () => {
        if (request.type === "GET_TTS_URL") {
            try {
                const dubbing = new Dubbing(request.videoId);
                const audioChunks = await dubbing.init(request.list_chunks_id, request.need_translator);
                console.log("[Background] audioChunks:", audioChunks);
                sendResponse({ audioChunks }); // Trả về danh sách chunks
            } catch (error) {
                sendResponse({ error: error.message || "Unknown error" });
            }
        } else if (request.type === "GET_TOTAL_CHUNK") {
            try {
                const res = await fetch("http://127.0.0.1:8000/video_split", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ video_id: request.videoId })
                });

                if (!res.ok) {
                    throw new Error(`Lỗi server: ${res.status}`);
                }

                const data = await res.json();
                sendResponse({ transcriptInfo: data });
            } catch (error) {
                console.error("❌ Lỗi khi gửi request GET_TOTAL_CHUNK:", error);
                sendResponse({ error: error.message || "Unknown error" });
            }
        }
    })();

    return true; // Bắt buộc để giữ sendResponse cho async
});