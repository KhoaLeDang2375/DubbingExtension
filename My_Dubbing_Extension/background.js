class Dubbing {
    constructor(videoId, statusElement = null) {
        this.videoId = videoId;
        this.statusElement = statusElement; // DOM element để cập nhật trạng thái (nếu có)
    }

    async init() {
        try {
            const settings = await this.loadSettings();
            const payload = this.buildPayload(settings);
            const audioBlob = await this.sendRequest(payload);
            return audioBlob;
        } catch (error) {
            console.error("❌ Lỗi trong init():", error);
            this.setStatus("Đã xảy ra lỗi trong quá trình xử lý.");
            throw error; // để hàm gọi biết đã có lỗi
        }
    }

    loadSettings() {
        return new Promise((resolve, reject) => {
            chrome.storage.sync.get(
                ["sourceLanguage", "targetLanguage", "speakerVoice", "translatorEngine"],
                (result) => {
                    if (chrome.runtime.lastError) {
                        console.error("❌ Lỗi khi load settings:", chrome.runtime.lastError);
                        reject(chrome.runtime.lastError);
                    } else {
                        console.log("✅ Đã load settings:", result);
                        resolve(result);
                    }
                }
            );
        });
    }

    buildPayload(settings) {
        const payload = {
            video_id: this.videoId,
            source_language: settings.sourceLanguage,
            target_language: settings.targetLanguage,
            translator: settings.translatorEngine,
            tts_voice: settings.speakerVoice
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
            const audioBlob = new Blob([arrayBuffer], { type: "audio/wav" });

            const audioUrl = URL.createObjectURL(audioBlob);
            console.log(" Đã nhận audio, tạo URL:", audioUrl);
            return audioUrl;
        } catch (error) {
            console.error(" Lỗi khi gửi request:", error);
            this.setStatus("Lỗi khi gửi request đến server.");
            throw error;
        }
    }

    setStatus(text) {
        if (this.statusElement) {
            this.statusElement.textContent = text;
        } else {
            console.log(" Trạng thái:", text);
        }
    }
}

// Lắng nghe từ content script
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    if (request.type === "GET_TTS_URL") {
        const videoId = request.videoId;
        console.log(" Nhận yêu cầu GET_TTS_URL từ content.js với videoId:", videoId);

        const dubbing = new Dubbing(videoId);

        dubbing.init()
            .then(audioUrl => {
                sendResponse({ audioUrl });
            })
            .catch(error => {
                console.error(" Gửi âm thanh thất bại:", error);
                sendResponse({ error: error.message || "Unknown error" });
            });
        return true; // Bắt buộc để cho phép async sendResponse
    }
});
