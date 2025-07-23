document.getElementById("send-btn").addEventListener("click", async () => {
  const videoId = document.getElementById("video-id").value;
  const targetLang = document.getElementById("target-lang").value;
  const translator = document.getElementById("translator").value;
  const status = document.getElementById("status");

  const payload = {
    video_id: videoId,
    target_langugue: targetLang,
    translator: translator
  };

  try {
    status.textContent = "⏳ Đang gửi yêu cầu và chờ âm thanh từ server...";

    const response = await fetch("http://127.0.0.1:8000/dubbing", {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify(payload)
    });

    if (!response.ok) {
      throw new Error(`Lỗi server: ${response.status}`);
    }

    // Nhận dữ liệu dạng binary (BytesIO tương ứng arrayBuffer)
    const arrayBuffer = await response.arrayBuffer();

    // Tạo blob từ buffer. Sửa type tùy backend trả về: 'audio/wav' hoặc 'audio/mpeg'
    const audioBlob = new Blob([arrayBuffer], { type: "audio/wav" });
    const audioUrl = URL.createObjectURL(audioBlob);

    // Tạo audio object và phát
    const audio = new Audio(audioUrl);
    audio.play();

    status.textContent = "✅ Âm thanh đang phát";

    audio.onended = () => {
      URL.revokeObjectURL(audioUrl);
      status.textContent = "✅ Đã phát xong.";
    };

  } catch (error) {
    console.error("Lỗi khi gửi yêu cầu hoặc phát âm thanh:", error);
    status.textContent = "❌ Lỗi khi gửi yêu cầu hoặc phát âm thanh.";
  }
});
