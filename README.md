# FLCL - File Logical Classifier Launcher

A desktop application with a Fooly Cooly theme that automatically organizes files in a folder based on their extension. It features an initial scan for existing files and real-time monitoring for new ones.

---

### ✨ Final Application Demonstration

![](https://i.imgur.com/d1dYKGV.gif) 

---

### 🚀 Key Features

- **Themed GUI:** A stylish and responsive dark-mode interface inspired by the anime FLCL, featuring an animated GIF.
- **Real-Time Monitoring:** Uses `watchdog` to instantly detect and organize new files.
- **Initial Scan:** Organizes all existing files in the folder when monitoring starts.
- **Customizable Rules:** Easily configure which file extensions go into which folders by editing the `config.json` file.
- **Standalone Executable:** Packaged with PyInstaller, allowing anyone to run the app without installing Python or any dependencies.
- **Custom Icon & Font:** For a complete and polished look.

---

### 🛠️ Tech Stack

- **Python 3**
- **GUI:** CustomTkinter, Pillow
- **Core Logic:** Watchdog
- **Packaging:** PyInstaller

---

### 💻 How to Use

#### For Users (The Easy Way)

1.  Go to the [**Releases Page**](https://github.com/shwdan/FLCL-File-Organizer/releases).
2.  Download the `FLCL_File_Organizer.zip` file from the latest release.
3.  Unzip the file.
4.  Double-click `FLCL_File_Organizer.exe` to run the application. No installation needed!

#### For Developers (From Source)

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/shwdan/FLCL-File-Organizer.git
    cd FLCL-File-Organizer
    ```

2.  **Set up a virtual environment:**
    ```bash
    python -m venv venv
    .\venv\Scripts\activate
    ```

3.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Run the application:**
    ```bash
    python app.py
    ```

---

### 📦 Building the Executable

To create your own `.exe`, run the following command. Note: The window icon may not display correctly in the final `.exe` due to a known issue with Tkinter and PyInstaller, but the file icon will be correct.

```bash
pyinstaller --name "FLCL_File_Organizer" --onefile --windowed --icon="icon.ico" --add-data "haruko.gif;." --add-data "custom_font.ttf;." --add-data "config.json;." --add-data "icon.png;." app.py
```
---

### 📄 License

This project is licensed under the MIT License.