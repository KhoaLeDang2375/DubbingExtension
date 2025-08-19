# I. Introduction
- Automatically translate and dub YouTube videos into the desired language.
- Process audio in real time using the **MediaSource API**.
- Leverage **GenAI APIs** to enhance translated text.
- Easy to install and use.

# II. Key Features
- Automatically translate video subtitles into multiple languages.
- Generate dubbed audio from translated text using **TTS (Text-to-Speech)**.
- Synchronize with the video to avoid delays or mismatched audio.
- Seamlessly play multiple audio chunks with intelligent prefetching.
- Customize voice settings (male/female voice, speed, tone).
# III/ System architecture:
## 1/Overview extension dubbing
!["Overview extension dubbing"](/out/planuml/test/Overview.png)
## 2/ Frontend interactions
!["Frontend interactions"](/out/planuml/test/Frontend.png)
## 3/Backend interactions
!["Backend interactions"](/out/planuml/test/Backend.png)
## 4/ Multiprocessing module operation
!["Multiprocessing module operation "](/out/planuml/test/Multiprocessing.png)
# IV/ Installation instructions
## Step 1: Clone project
git clone https://github.com/KhoaLeDang2375/DubbingExtension.git
## Step 2: 
### 2.1 Open  Chrome 
### 2.2 Click Extensions 
!["step 2.1"](/out/Install_img/install_1.jpg)
### 2.3: Click Manage extension
!["step 2.2"](/out/Install_img/install_2.jpg)
### 2.4: Turn on  Developer mode.
!["step 2.3"](/out/Install_img/install_3.jpg)
### 2.5 Click load packet and point to project folder
!["step 2.5"](/out/Install_img/install_4.jpg)
!["step 2.5"](/out/Install_img/install_5.jpg)


# V/ How to Use
- Open a YouTube video.
- Select the target language and voice in the extension menu.
- Click Start Dubbing.
- The extension will:
- Retrieve the video subtitles.
- Translate them into your chosen language.
- Generate dubbed audio and play it in sync.
## Video demo:
### original video
<p align="center">
  <a href="https://www.youtube.com/watch?v=3foYyPDp0Ho">
    <img src="https://img.youtube.com/vi/3foYyPDp0Ho/maxresdefault.jpg" width="300">
  </a>
</p>

### Vietnamese dubbing video
<p align="center">
  <a href="https://youtu.be/xw-DwhP32Qs">
    <img src="https://img.youtube.com/vi/xw-DwhP32Qs/maxresdefault.jpg" width="300">
  </a>
</p>

### Japanese dubbing video
<p align="center">
  <a href="https://youtu.be/y7G8E6WUAZE">
    <img src="https://img.youtube.com/vi/y7G8E6WUAZE/maxresdefault.jpg" width="300">
  </a>
</p> 

# VI/ Directory structure
| Path | Description |
|------|-------------|
| [.gitignore](https://github.com/KhoaLeDang2375/DubbingExtension/blob/main/.gitignore) | Specifies files/folders for Git to ignore |
| [Readme.md](https://github.com/KhoaLeDang2375/DubbingExtension/blob/main/Readme.md) | Project documentation in Markdown format |
| [requirements.txt](https://github.com/KhoaLeDang2375/DubbingExtension/blob/main/requirements.txt) | List of Python dependencies for the backend |
| **backend/** | Backend server handling API and core logic |
| [backend/main.py](https://github.com/KhoaLeDang2375/DubbingExtension/blob/main/backend/main.py) | Main entry point of the backend |
| [backend/run.bat](https://github.com/KhoaLeDang2375/DubbingExtension/blob/main/backend/run.bat) | Windows batch file to run the backend |
| **backend/Handler_Transcript/** | Module to handle video transcript processing |
| [backend/Handler_Transcript/Handler_Transcript.py](https://github.com/KhoaLeDang2375/DubbingExtension/blob/main/backend/Handler_Transcript/Handler_Transcript.py) | Main handler for transcripts |
| **backend/redis_cache/** | Module for caching using Redis |
| [backend/redis_cache/cache.py](https://github.com/KhoaLeDang2375/DubbingExtension/blob/main/backend/redis_cache/cache.py) | Redis caching logic |
| **backend/Text_To_Speech/** | Module for converting text to speech (TTS) |
| [backend/Text_To_Speech/TextToSpeech.py](https://github.com/KhoaLeDang2375/DubbingExtension/blob/main/backend/Text_To_Speech/TextToSpeech.py) | TTS conversion logic |
| **backend/Translator/** | Translation module |
| [backend/Translator/genAITranslator.py](https://github.com/KhoaLeDang2375/DubbingExtension/blob/main/backend/Translator/genAITranslator.py) | Translation using Generative AI |
| [backend/Translator/tempCodeRunnerFile.py](https://github.com/KhoaLeDang2375/DubbingExtension/blob/main/backend/Translator/tempCodeRunnerFile.py) | Temporary file (should be removed) |
| [backend/Translator/translator.py](https://github.com/KhoaLeDang2375/DubbingExtension/blob/main/backend/Translator/translator.py) | Standard translation implementation |
| **My_Dubbing_Extension/** | Chrome extension for YouTube dubbing |
| [My_Dubbing_Extension/background.js](https://github.com/KhoaLeDang2375/DubbingExtension/blob/main/My_Dubbing_Extension/background.js) | Background script (manages API calls & events) |
| [My_Dubbing_Extension/content_script.js](https://github.com/KhoaLeDang2375/DubbingExtension/blob/main/My_Dubbing_Extension/content_script.js) | Injected script to interact with YouTube player |
| [My_Dubbing_Extension/manifest.json](https://github.com/KhoaLeDang2375/DubbingExtension/blob/main/My_Dubbing_Extension/manifest.json) | Chrome extension configuration |
| [My_Dubbing_Extension/options.html](https://github.com/KhoaLeDang2375/DubbingExtension/blob/main/My_Dubbing_Extension/options.html) | Extension settings page UI |
| [My_Dubbing_Extension/popup.js](https://github.com/KhoaLeDang2375/DubbingExtension/blob/main/My_Dubbing_Extension/popup.js) | Logic for the popup UI |
| **My_Dubbing_Extension/assets/** | Extension assets |
| [My_Dubbing_Extension/assets/imgbtn.png](https://github.com/KhoaLeDang2375/DubbingExtension/blob/main/My_Dubbing_Extension/assets/imgbtn.png) | Icon/button image used by the extension |
| **out/** | Output and documentation resources |
| **out/Install_img/** | Installation guide screenshots |
| [out/Install_img/install_1.jpg](https://github.com/KhoaLeDang2375/DubbingExtension/blob/main/out/Install_img/install_1.jpg) | Step 1 installation screenshot |
| [out/Install_img/install_2.jpg](https://github.com/KhoaLeDang2375/DubbingExtension/blob/main/out/Install_img/install_2.jpg) | Step 2 installation screenshot |
| [out/Install_img/install_3.jpg](https://github.com/KhoaLeDang2375/DubbingExtension/blob/main/out/Install_img/install_3.jpg) | Step 3 installation screenshot |
| [out/Install_img/install_4.jpg](https://github.com/KhoaLeDang2375/DubbingExtension/blob/main/out/Install_img/install_4.jpg) | Step 4 installation screenshot |
| [out/Install_img/install_5.jpg](https://github.com/KhoaLeDang2375/DubbingExtension/blob/main/out/Install_img/install_5.jpg) | Step 5 installation screenshot |
| **out/planuml/test/** | UML diagrams for architecture/design |
| [out/planuml/test/Backend.png](https://github.com/KhoaLeDang2375/DubbingExtension/blob/main/out/planuml/test/Backend.png) | Backend architecture diagram |
| [out/planuml/test/Frontend.png](https://github.com/KhoaLeDang2375/DubbingExtension/blob/main/out/planuml/test/Frontend.png) | Frontend architecture diagram |
| [out/planuml/test/Multiprocessing.png](https://github.com/KhoaLeDang2375/DubbingExtension/blob/main/out/planuml/test/Multiprocessing.png) | Multiprocessing design diagram |
| [out/planuml/test/Overview.png](https://github.com/KhoaLeDang2375/DubbingExtension/blob/main/out/planuml/test/Overview.png) | System overview diagram |
| **planuml/** | PlantUML source files |
| [planuml/test.plan](https://github.com/KhoaLeDang2375/DubbingExtension/blob/main/planuml/test.plan) | PlantUML test file |
