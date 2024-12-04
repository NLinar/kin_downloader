import json
import os
import sys
from PyQt5.QtWidgets import QFileDialog, QApplication, QMainWindow
from setting_window_ui import Ui_MainWindow

class Ui_Settings(QMainWindow):
    def __init__(self):
        super().__init__()
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)
        self.settings_file = 'settings.json'
        self.quality_mapping = {
            "Высокое": "High",
            "Среднее": "Medium",
            "Низкое": "Low"
        }
        self.quality_reverse_mapping = {v: k for k, v in self.quality_mapping.items()}
        self.initUI()
        self.load_settings()

    def initUI(self):
        # Подключаем функции к кнопкам
        self.ui.pushButton.clicked.connect(self.select_ffmpeg)
        self.ui.pushButton_5.clicked.connect(self.select_4decrypt)
        self.ui.pushButton_6.clicked.connect(self.select_temp_folder)
        self.ui.pushButton_7.clicked.connect(self.select_save_folder)
        self.ui.pushButton_4.clicked.connect(self.save_settings)

        # Добавляем варианты выбора качества видео
        self.ui.comboBox.addItems(self.quality_reverse_mapping.values())

    def select_ffmpeg(self):
        file_name, _ = QFileDialog.getOpenFileName(self, "Выбрать ffmpeg.exe", "", "Executable Files (*.exe)")
        if file_name:
            self.ui.lineEdit.setText(file_name)

    def select_4decrypt(self):
        file_name, _ = QFileDialog.getOpenFileName(self, "Выбрать 4decrypt.exe", "", "Executable Files (*.exe)")
        if file_name:
            self.ui.lineEdit_4.setText(file_name)

    def select_temp_folder(self):
        folder_name = QFileDialog.getExistingDirectory(self, "Выбрать временную папку")
        if folder_name:
            self.ui.lineEdit_5.setText(folder_name)

    def select_save_folder(self):
        folder_name = QFileDialog.getExistingDirectory(self, "Выбрать папку для сохранения видео")
        if folder_name:
            self.ui.lineEdit_6.setText(folder_name)

    def save_settings(self):
        settings = {
            "ffmpeg_path": self.ui.lineEdit.text(),
            "4decrypt_path": self.ui.lineEdit_4.text(),
            "temp_folder": self.ui.lineEdit_5.text(),
            "save_folder": self.ui.lineEdit_6.text(),
            "video_quality": self.quality_mapping[self.ui.comboBox.currentText()]
        }

        with open(self.settings_file, 'w', encoding='utf-8') as f:
            json.dump(settings, f, ensure_ascii=False, indent=4)

    def load_settings(self):
        if os.path.exists(self.settings_file):
            with open(self.settings_file, 'r', encoding='utf-8') as f:
                settings = json.load(f)

            self.ui.lineEdit.setText(settings.get("ffmpeg_path", ""))
            self.ui.lineEdit_4.setText(settings.get("4decrypt_path", ""))
            self.ui.lineEdit_5.setText(settings.get("temp_folder", ""))
            self.ui.lineEdit_6.setText(settings.get("save_folder", ""))
            quality = self.quality_reverse_mapping.get(settings.get("video_quality", "High"), "Высокое")
            self.ui.comboBox.setCurrentText(quality)

    def closeEvent(self, event):
        # Проверяем, заполнены ли настройки
        if not self.ui.lineEdit.text() or not self.ui.lineEdit_4.text() or not self.ui.lineEdit_5.text() or not self.ui.lineEdit_6.text():
            QApplication.quit()  # Завершаем приложение
            sys.exit()  # Прекращаем выполнение программы
        super().closeEvent(event)

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = Ui_Settings()
    window.show()
    sys.exit(app.exec_())
