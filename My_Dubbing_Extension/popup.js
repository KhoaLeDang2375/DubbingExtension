       // Đối tượng quản lý cài đặt
        const SettingsManager = {
            // Các khóa lưu trữ
            STORAGE_KEYS: {
                SOURCE_LANG: 'sourceLanguage',
                TARGET_LANG: 'targetLanguage',
                SPEAKER_VOICE: 'speakerVoice',
                TRANSLATOR_ENGINE: 'translatorEngine'
            },

            // Các giá trị mặc định
            DEFAULT_VALUES: {
                sourceLanguage: 'auto',
                targetLanguage: 'vi',
                speakerVoice: 'vi-VN-HoaiMyNeural',
                translatorEngine: 'AzureTranslator'
            },

            // Khởi tạo khi trang được tải
            init() {
                this.loadSettings();
                this.bindEvents();
            },

            // Gắn kết các sự kiện
            bindEvents() {
                const form = document.getElementById('settingsForm');
                form.addEventListener('submit', (e) => {
                    e.preventDefault();
                    this.saveSettings();
                });
            },

            // Tải cài đặt từ chrome.storage.sync
            async loadSettings() {
                try {
                    const result = await chrome.storage.sync.get(Object.values(this.STORAGE_KEYS));
                    
                    // Áp dụng giá trị đã lưu hoặc giá trị mặc định
                    Object.keys(this.DEFAULT_VALUES).forEach(key => {
                        const element = document.getElementById(key);
                        if (element) {
                            element.value = result[key] || this.DEFAULT_VALUES[key];
                        }
                    });

                    console.log('Đã tải cài đặt:', result);
                } catch (error) {
                    console.error('Lỗi khi tải cài đặt:', error);
                    this.setDefaultValues();
                }
            },

            // Đặt giá trị mặc định nếu không thể tải từ storage
            setDefaultValues() {
                Object.keys(this.DEFAULT_VALUES).forEach(key => {
                    const element = document.getElementById(key);
                    if (element) {
                        element.value = this.DEFAULT_VALUES[key];
                    }
                });
            },

            // Lưu cài đặt vào chrome.storage.sync
            async saveSettings() {
                try {
                    // Vô hiệu hóa nút lưu trong khi đang xử lý
                    const saveButton = document.getElementById('saveButton');
                    saveButton.disabled = true;
                    saveButton.innerHTML = '⏳ Đang lưu...';

                    // Thu thập dữ liệu từ form
                    const settings = {};
                    Object.keys(this.DEFAULT_VALUES).forEach(key => {
                        const element = document.getElementById(key);
                        if (element) {
                            settings[key] = element.value || this.DEFAULT_VALUES[key];
                        }
                    });

                    // Lưu vào chrome storage
                    await chrome.storage.sync.set(settings);

                    // Hiển thị thông báo thành công
                    this.showSuccessMessage();

                    console.log('Đã lưu cài đặt:', settings);

                } catch (error) {
                    console.error('Lỗi khi lưu cài đặt:', error);
                    alert('Có lỗi xảy ra khi lưu cài đặt. Vui lòng thử lại!');
                } finally {
                    // Khôi phục nút lưu
                    const saveButton = document.getElementById('saveButton');
                    saveButton.disabled = false;
                    saveButton.innerHTML = '💾 Lưu cài đặt';
                }
            },

            // Hiển thị thông báo thành công
            showSuccessMessage() {
                const successMessage = document.getElementById('successMessage');
                successMessage.classList.add('show');
                
                // Tự động ẩn thông báo sau 3 giây
                setTimeout(() => {
                    successMessage.classList.remove('show');
                }, 3000);
            }
        };

        // Khởi động ứng dụng khi DOM đã sẵn sàng
        document.addEventListener('DOMContentLoaded', () => {
            SettingsManager.init();
        });

        // Xử lý lỗi toàn cục
        window.addEventListener('error', (event) => {
            console.error('Lỗi JavaScript:', event.error);
        });

