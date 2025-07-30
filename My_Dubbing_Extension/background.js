class Dubbing {
    constructor(videoId, statusElement = null) {
        this.videoId = videoId;
        this.statusElement = statusElement;
    }

    async init(list_chunks_id, need_translator= true) {
        try {
            const settings = await this.loadSettings();
            const payload = this.buildPayload(settings,list_chunks_id,need_translator);
            const audioBlob = await this.sendRequest(payload);
            return audioBlob;
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

    buildPayload(settings, list_chunks_id,need_translator = true) {
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
            const arrayBuffer = await response.arrayBuffer();
            if (arrayBuffer.byteLength === 0) {
            console.error("❌ Dữ liệu âm thanh rỗng từ server");
            throw new Error("Dữ liệu âm thanh rỗng");
            }
            const uint8Array = new Uint8Array(arrayBuffer);
            console.log(`[Background] Kích thước arrayBuffer: ${arrayBuffer.byteLength}`);
            return { audioData: Array.from(uint8Array) };
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
                const { audioData } = await dubbing.init(request.list_chunks_id, request.need_translator);
                console.log(`[Background] Kích thước audioData gửi đi cho chunk ${request.list_chunks_id}: ${audioData.byteLength}`);
                console.log("[Background] audioData type:", audioData.constructor.name);
                sendResponse({ audioData });
            } catch (error) {
                sendResponse({ error: error.message || "Unknown error" });
            }
        }

        else if (request.type === "GET_TOTAL_CHUNK") {
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
