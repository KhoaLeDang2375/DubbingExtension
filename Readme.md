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
git clone https://github.com/KhoaLeDang2375/DubbingExtension/tree/main/My_Dubbing_Extension
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
## Video demo:

<p align="center">
  <a href="https://youtu.be/-GQ69umfJWs">
    <img src="https://img.youtube.com/vi/-GQ69umfJWs/maxresdefault.jpg" width="600">
  </a>
</p>

# V/ Directory structure
```
C:.
|   .gitignore                  # Specifies files/folders for Git to ignore
|   Readme.md                   # Project documentation in Markdown format
|   requirements.txt            # List of Python dependencies for the backend
|
+---backend                     # Backend server handling API and core logic
|   |   .env                     # Environment variables (API keys, configs, secrets)
|   |   main.py                  # Main entry point of the backend
|   |   run.bat                  # Windows batch file to run the backend
|   |
|   +---Handler_Transcript       # Module to handle video transcript processing
|   |   |   Handler_Transcript.py
|   |
|   +---redis_cache              # Module for caching using Redis
|   |   |   cache.py
|   |
|   +---Text_To_Speech           # Module for converting text to speech (TTS)
|   |   |   TextToSpeech.py
|   |
|   +---Translator               # Translation module
|   |   |   genAITranslator.py   # Translation using Generative AI
|   |   |   tempCodeRunnerFile.py # Temporary file (should be removed from repo)
|   |   |   translator.py        # Standard translation implementation
|
+---My_Dubbing_Extension         # Chrome extension for YouTube dubbing
|   |   background.js            # Background script (manages API calls & events)
|   |   content_script.js        # Injected script to interact with YouTube player
|   |   manifest.json            # Chrome extension configuration (permissions, scripts, etc.)
|   |   options.html             # Extension settings page UI
|   |   popup.js                 # Logic for the popup UI
|   |
|   \---assets
|           imgbtn.png           # Icon/button image used by the extension
|
+---out                          # Output and documentation resources
|   +---Install_img              # Installation guide screenshots
|   |       install_1.jpg
|   |       install_2.jpg
|   |       install_3.jpg
|   |       install_4.jpg
|   |       install_5.jpg
|   |
|   \---planuml                  # UML diagrams for architecture/design
|       \---test
|               Backend.png
|               Frontend.png
|               Multiprocessing.png
|               Overview.png
|
\---planuml                      # PlantUML source files
        test.plan
```

