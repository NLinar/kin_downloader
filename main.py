import os
import sys
import threading
import subprocess
import base64
import json
from PyQt5.QtWidgets import (QApplication, QMainWindow, QHeaderView, QComboBox, QProgressBar, QLabel, QTableView,
                             QFileDialog, QMessageBox, QMenu, QAction)
from PyQt5.QtGui import QStandardItemModel, QStandardItem, QIcon, QPixmap
from PyQt5.QtCore import Qt
from main_window_ui import Ui_MainWindow
from setting import Ui_Settings
from downloader import Worker
from style import style_sheet_1, style_sheet_2


# Класс главного окна
class MainWindow(QMainWindow, Ui_MainWindow):
    def __init__(self):
        super().__init__()
        self.setupUi(self)

        self.resolution_files = []  # Список разрешений
        self.newly_added_files = []  # Список новых файлов
        self.new_file_indices = None  # Индексы новых файлов
        self.settings_dialog = None  # Диалог настроек
        self.file_paths = []  # Список путей к файлам
        self.not_downloaded_files = []  # Список не загруженных файлов
        self.stop_threads = threading.Event()  # Событие остановки потоков
        self.threads = []  # Список потоков
        self.finish_status = False  # Флаг завершения загрузки
        self.new_not_downloaded_files = []  # Список новых не загруженных файлов
        self.worker = None  # Ссылка на worker

        # Путь к файлу настроек
        self.settings_file = "settings.json"
        self.ensure_settings_file()

        self.resolution_map = {
            "1080": (1920, 1080),
            "720": (1280, 720),
            "480": (852, 480),
            "360": (640, 360),
            # ============
            "1020": (1920, 1020),
            "680": (1280, 680),
            "452": (854, 452),
            "340": (640, 340),
        }

        self.model = QStandardItemModel(0, 4)

        headers = ["Название", "Качество", "Загрузка", "Статус"]
        self.model.setHorizontalHeaderLabels(headers)

        self.tableView.setModel(self.model)

        self.tableView.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)

        self.header = self.tableView.horizontalHeader()
        self.header.setSectionResizeMode(0, QHeaderView.Interactive)
        self.header.resizeSection(0, int(self.tableView.width() * 2.8))

        self.tableView.verticalHeader().hide()
        self.tableView.setSelectionBehavior(QTableView.SelectRows)
        self.tableView.setSelectionMode(QTableView.ExtendedSelection)

        self.tableView.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tableView.customContextMenuRequested.connect(self.show_context_menu)

        self.setAcceptDrops(True)
        # меню
        self.action_3.triggered.connect(self.open_settings)
        # кнопки
        self.pushButton.clicked.connect(self.open_file_dialog)
        self.pushButton_2.clicked.connect(self.start_thread)
        self.pushButton_3.clicked.connect(self.clear_table_and_array)

        self.tableView.setStyleSheet(style_sheet_1)

# ======================================================================================================================

    # Выбор качества
    def on_combobox_changed(self, row):
        combo_box = self.tableView.indexWidget(self.model.index(row, 1))
        if combo_box:
            selected_value = combo_box.currentText()
            selected_value = self.get_resolution(selected_value, self.resolution_map)
            self.resolution_files[row] = selected_value
            print(f"Строка: {row}, выбранное значение: {selected_value}")
            print(f"Разрешения: {self.resolution_files}")  # Выводим содержимое массива
            if self.threads and not self.finish_status:
                self.worker.update_resolution_signal.emit(self.resolution_files)


    # Закрытие программы
    def closeEvent(self, event):
        print("Закрытие окна")
        self.stop_threads.set()  # Останавливаем потоки
        for thread in self.threads:
            thread.join()  # Ждем завершения всех потоков
        os._exit(0)

    # Удаление выделенных строк
    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Delete:
            selected_indices = self.tableView.selectionModel().selectedRows()
            if selected_indices:
                self.delete_selected_rows()

    # Изменение размера 0 столбца при запуске
    def showEvent(self, event):
        super().showEvent(event)
        self.resize_table_columns()

    # Изменение размера 0 столбца при изменении размера окна
    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.resize_table_columns()

    # Изменение размера 0 столбца
    def resize_table_columns(self):
        total_width = self.tableView.viewport().width()
        self.header.resizeSection(0, int(total_width * 0.6))

    # Обработка перетаскивания
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.accept()
        else:
            event.ignore()

    # Обработка перетаскивания
    def dropEvent(self, event):
        duplicate_found = False  # Флаг для отслеживания дубликатов
        new_files_added = False  # Флаг для отслеживания, были ли добавлены новые файлы
        priority_quality = self.get_priority_quality()
        for url in event.mimeData().urls():
            file_path = url.toLocalFile()
            if file_path.endswith('.kin'):
                with open(file_path, 'r', encoding='utf-8') as file:
                    file_data = json.load(file)
                    for entry in file_data:
                        # Проверяем, есть ли уже этот файл в self.file_paths
                        if entry in self.file_paths:
                            duplicate_found = True
                        else:
                            # Если файл новый, добавляем его
                            new_files_added = True
                            self.file_paths.append(entry)
                            self.add_file_to_table(entry, priority_quality)
                            self.newly_added_files.append(entry)

        # Определяем, какое сообщение показать
        if duplicate_found and new_files_added:  # Если добавлены новые файлы, но есть дубликаты
            info_dialog = QMessageBox()
            info_dialog.setIcon(QMessageBox.Information)
            info_dialog.setWindowTitle("Предупреждение")
            info_dialog.setText("Некоторые файлы уже присутствуют в таблице и не были добавлены повторно.")
            info_dialog.setStandardButtons(QMessageBox.Ok)
            info_dialog.exec_()
        elif duplicate_found:  # Если нет новых файлов
            no_files_dialog = QMessageBox()
            no_files_dialog.setIcon(QMessageBox.Critical)
            no_files_dialog.setWindowTitle("Ошибка")
            no_files_dialog.setText("Все файлы, которые вы пытались добавить, уже присутствуют в таблице.")
            no_files_dialog.setStandardButtons(QMessageBox.Ok)
            no_files_dialog.exec_()

        if self.threads and not self.finish_status:
            self.worker.update_signal.emit(self.newly_added_files)  # Отправляем новые файлы в поток
            self.newly_added_files = []

        if not self.threads or self.finish_status:
            self.pushButton_2.setEnabled(True)
            self.pushButton_3.setEnabled(True)
        # print(f"file_paths: {self.file_paths}")

    # ======================================================================================================================

    # Открытие контекстного меню
    def show_context_menu(self, position):
        index = self.tableView.indexAt(position)  # Получаем индекс строки и столбца
        if not index.isValid():
            return  # Если клик вне строки, ничего не делаем

        row = index.row()
        status_label = self.tableView.indexWidget(
            self.model.index(row, 3))  # Получаем виджет статуса (последняя колонка)

        if not status_label or status_label.text() != "Загружено":
            return  # Если статус не "Загружено", ничего не делаем

        video_title = self.model.item(row, 0).text()  # Название видео (первая колонка)

        with open('settings.json', 'r', encoding='utf-8') as f:
            settings = json.load(f)
        save_folder = settings.get("save_folder", "")
        if not os.path.exists(save_folder):
            print("Папка сохранения не найдена!")
            return None

        # Создаем меню
        menu = QMenu(self)

        folder_icon = ("iVBORw0KGgoAAAANSUhEUgAAADAAAAAwCAYAAABXAvmHAAAACXBIWXMAAAsTAAALEwEAmpwYAAAAuElEQVR4nO2YsQ2DMBRE3"
                       "xxQZ4asl3FCwWQoErDARZFcJY2Jbb4l7knX3+No/MEYY4z55QbMwA7oYB50UP71R/FuJObC8uESeyWBMAl9JZc7sFaUV8rng0"
                       "7A2FqgpYSAJVeiRKC1xPMMgZYS61kCNdHRPhaojLxAMPICwcgLBCMvEIy8QDDyAsHICwQjLxCMLrfA1uiicNqjfuqgqErOKmM"
                       "6IqmzLMBAJkOy7eF32lKX7PLGGGOuwxuSeuZIueXxRgAAAABJRU5ErkJggg==")

        player_icon = ("iVBORw0KGgoAAAANSUhEUgAAADAAAAAwCAYAAABXAvmHAAAACXBIWXMAAAsTAAALEwEAmpwYAAAA/0lEQVR4nO2ZMQrCQBBFX"
                       "+UNbGJtIehNbD2LZ/EGWtjaeBLPEBRNm+LbJE0gsLtRdxbnwZQb/mNmYNmA4ziORZbAGWgAZa4GOAGLmPB3A8E1qDpU4mwgrE"
                       "bqGCJgYWw0Us8QgeGh3Cg2jwt8GHkHMiPvQCBXYEPBHRDQAgdgnp43r0BfD2APzCLOmxLo6wbsIr5hTqCvKfshCwJT9kNWBFL"
                       "3Q9YEYvdDlgW2JQoUO0JtyUt8BdaRwU0IhM65OYFirxJtyZe5C7BKz5lf4FvIBTIj70Bm9HcdeCXcLE097p4MBNWU5/VF9zNB"
                       "xqoGKgKpOlsL4/TqsgSHdxzH4We8AYi/f7uN0r1+AAAAAElFTkSuQmCC")

        player_pixmap = QPixmap()
        player_pixmap.loadFromData(base64.b64decode(player_icon))
        folder_pixmap = QPixmap()
        folder_pixmap.loadFromData(base64.b64decode(folder_icon))

        # Создаём действия с иконками
        open_action = QAction(QIcon(player_pixmap), "Открыть видео", self)
        show_folder_action = QAction(QIcon(folder_pixmap), "Показать папку", self)

        # Добавляем действия в меню
        menu.addAction(open_action)
        menu.addAction(show_folder_action)

        # Показываем меню в позиции клика
        action = menu.exec_(self.tableView.viewport().mapToGlobal(position))

        # Обработка действий меню
        if action == open_action:
            self.open_video(video_title)
        elif action == show_folder_action:
            self.show_folder(save_folder)

    def open_video(self, title):
        try:
            # Читаем настройки
            with open('settings.json', 'r', encoding='utf-8') as f:
                settings = json.load(f)
            save_folder = settings.get("save_folder", "")

            if not os.path.exists(save_folder):
                print("Папка сохранения не найдена!")
                return

            # Получаем все файлы в папке
            files_in_folder = os.listdir(save_folder)
            # print(f"В папке {save_folder} найдено {len(files_in_folder)} файлов.")

            # Сравниваем по частичному совпадению
            for file_name in files_in_folder:
                if title in file_name:  # Если название частично совпадает
                    video_path = os.path.join(save_folder, file_name)  # Полный путь к видео

                    # Открываем видео
                    if os.name == 'nt':  # Windows
                        os.startfile(video_path)
                    elif os.name == 'posix':  # macOS/Linux
                        subprocess.run(['open' if sys.platform == 'darwin' else 'xdg-open', video_path])
                    return  # Видео найдено и открыто, выходим из метода

            print("Видео не найдено в папке сохранения.")
        except Exception as e:
            print(f"Ошибка при открытии видео: {e}")

    def show_folder(self, save_folder):
        try:
            abs_path = os.path.abspath(save_folder)  # Абсолютный путь к папке

            if os.name == 'nt':  # Windows
                subprocess.run(['explorer', abs_path])  # Открыть папку в проводнике
            elif os.name == 'posix':  # macOS/Linux
                subprocess.run(['open' if sys.platform == 'darwin' else 'xdg-open', abs_path])  # Открыть папку
        except Exception as e:
            print(f"Ошибка при открытии папки: {e}")

    # Добавление файлов в таблицу
    def add_file_to_table(self, entry, priority_quality):
        row_count = self.model.rowCount()
        self.model.insertRow(row_count)
        self.tableView.setRowHeight(row_count, 10)
        for column, item_data in enumerate([entry['Title'], ', '.join(eval(entry['Quality'])), "", ""]):
            item = QStandardItem(item_data)
            if column == 0:
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
            if column == 1:
                combo_box = QComboBox()
                available_qualities = eval(entry['Quality'])
                # Определите, какое качество выбрать в зависимости от приоритета
                if priority_quality == "High":
                    selected_quality = max(available_qualities, key=int)  # Максимальное качество
                elif priority_quality == "Medium":
                    # Второе по величине качество
                    selected_quality = sorted(available_qualities, key=int)[-2]
                elif priority_quality == "Low":
                    selected_quality = min(available_qualities, key=int)  # Минимальное качество
                else:
                    selected_quality = available_qualities[0]  # По умолчанию первое качество
                combo_box.addItems(available_qualities)  # Добавляем качества в выпадающий список
                combo_box.setCurrentText(selected_quality)  # Устанавливаем выбранный качество
                self.resolution_files.append(self.get_resolution(selected_quality, self.resolution_map))  # Сохраняем выбранный качество

                # Отправляем выбранный качество в поток
                if self.threads and not self.finish_status:
                    self.worker.update_resolution_signal.emit(self.resolution_files)

                combo_box.currentIndexChanged.connect(lambda index, row=row_count: self.on_combobox_changed(row))

                # print(f"resolution_files: {self.resolution_files}")
                self.tableView.setIndexWidget(self.model.index(row_count, column), combo_box)
            elif column == 2:
                progress_bar = QProgressBar()
                progress_bar.setValue(0)
                self.tableView.setIndexWidget(self.model.index(row_count, column), progress_bar)
            elif column == 3:
                speed_label = QLabel("Не загружен")
                speed_label.setAlignment(Qt.AlignCenter)
                self.tableView.setIndexWidget(self.model.index(row_count, column), speed_label)
            else:
                self.model.setItem(row_count, column, item)

        self.tableView.indexWidget(self.model.index(row_count, 2)).setStyleSheet(style_sheet_2)

    # Проверка и создание settings.json
    def ensure_settings_file(self):
        if not os.path.exists(self.settings_file):
            # Создаем файл с базовым шаблоном, если его нет
            default_settings = {
                "ffmpeg_path": "",
                "4decrypt_path": "",
                "temp_folder": "",
                "save_folder": "",
                "video_quality": ""
            }
            with open(self.settings_file, 'w', encoding='utf-8') as f:
                json.dump(default_settings, f, indent=4, ensure_ascii=False)

        # Проверяем заполненность данных в файле
        with open(self.settings_file, 'r', encoding='utf-8') as f:
            settings = json.load(f)
            if any(not value for value in settings.values()):  # Если есть пустые значения
                QMessageBox.warning(self, "Настройки", "Необходимо заполнить пути перед использованием!")
                self.open_settings()  # Открываем окно настроек

    def get_priority_quality(self):
        with open('settings.json', 'r') as f:
            settings = json.load(f)
        return settings['video_quality']

    def get_resolution(self, selected_quality, resolution_map):
        return resolution_map.get(selected_quality, (640, 360))

    def open_settings(self):
        self.settings_dialog = Ui_Settings()
        self.settings_dialog.setWindowModality(Qt.ApplicationModal)
        main_window_rect = self.geometry()
        dialog_rect = self.settings_dialog.geometry()

        x = main_window_rect.center().x() - dialog_rect.width() / 2
        y = main_window_rect.center().y() - dialog_rect.height() / 2

        self.settings_dialog.setGeometry(int(x), int(y), dialog_rect.width(), dialog_rect.height())
        self.settings_dialog.show()

    def open_file_dialog(self):
        # print("open_file_dialog")
        priority_quality = self.get_priority_quality()
        options = QFileDialog.Options()
        options |= QFileDialog.ReadOnly
        file_names, _ = QFileDialog.getOpenFileNames(self, "Выбрать файлы", "", "KIN Files (*.kin)", options=options)
        if file_names:
            duplicate_found = False
            new_files_added = False
            for file_name in file_names:
                with open(file_name, 'r', encoding='utf-8') as file:
                    file_data = json.load(file)
                    for entry in file_data:
                        # Проверяем, есть ли уже этот файл в self.file_paths
                        if entry in self.file_paths:
                            duplicate_found = True
                        else:
                            # Если файл новый, добавляем его
                            new_files_added = True
                            self.file_paths.append(entry)
                            self.add_file_to_table(entry, priority_quality)
                            self.newly_added_files.append(entry)

            # Определяем, какое сообщение показать
            if duplicate_found and new_files_added:
                info_dialog = QMessageBox()
                info_dialog.setIcon(QMessageBox.Information)
                info_dialog.setWindowTitle("Предупреждение")
                info_dialog.setText("Некоторые файлы уже присутствуют в таблице и не были добавлены повторно.")
                info_dialog.setStandardButtons(QMessageBox.Ok)
                info_dialog.exec_()
            elif duplicate_found:
                no_files_dialog = QMessageBox()
                no_files_dialog.setIcon(QMessageBox.Critical)
                no_files_dialog.setWindowTitle("Ошибка")
                no_files_dialog.setText("Все файлы, которые вы пытались добавить, уже присутствуют в таблице.")
                no_files_dialog.setStandardButtons(QMessageBox.Ok)
                no_files_dialog.exec_()

            if self.threads and not self.finish_status:
                self.worker.update_signal.emit(self.newly_added_files)
                self.newly_added_files = []

            if not self.threads or self.finish_status:
                self.pushButton_2.setEnabled(True)
                self.pushButton_3.setEnabled(True)

    def clear_table_and_array(self):
        self.pushButton_2.setEnabled(False)
        self.pushButton_3.setEnabled(False)
        self.model.removeRows(0, self.model.rowCount())
        self.file_paths.clear()
        self.resolution_files.clear()
        print("Таблица и массив очищены")

    # Запуск потока
    def start_thread(self):
        try:
            self.pushButton_2.setEnabled(False)
            self.pushButton_3.setEnabled(False)

            self.new_file_indices = []
            self.new_file_indices = [self.file_paths.index(file) for file in self.newly_added_files if
                                     file in self.file_paths]
            # print(f"new_file_indices: {self.new_file_indices}")

            self.worker = Worker(self.file_paths, self.resolution_files, self.new_file_indices,
                                 self.stop_threads)  # Сохраняем ссылку на worker
            self.worker.progress_signal.connect(self.update_progress)
            self.worker.status_signal.connect(self.update_status)
            self.worker.finished_signal.connect(self.on_finished)

            thread = threading.Thread(target=self.worker.run)
            self.threads.append(thread)
            thread.start()
            self.newly_added_files = []
        except Exception as e:
            print(f"Error_thread: {e}")

    # Обновление прогресса
    def update_progress(self, file_index, progress):
        try:
            combo_box = self.tableView.indexWidget(self.model.index(file_index, 1))
            progress_bar = self.tableView.indexWidget(self.model.index(file_index, 2))
            status_label = self.tableView.indexWidget(self.model.index(file_index, 3))
            if combo_box:
                combo_box.setEnabled(False)
            if progress_bar:
                status_label.setStyleSheet("color: black;")
                status_label.setText("Идет загрузка...")
                progress_bar.setValue(progress)
        except Exception as e:
            print(f"Error_progress: {e}")

    # Обновление статуса
    def update_status(self, file_index, status):
        try:
            status_label = self.tableView.indexWidget(self.model.index(file_index, 3))
            if status_label:
                status_label.setText(status)
                if status == "Загружено":
                    status_label.setStyleSheet("color: #006400;")  # темно-зеленый (#8B0000 - темно-красный)
        except Exception as e:
            print(f"Error_status: {e}")

    # Обработка завершения
    def on_finished(self, status):
        self.finish_status = status
        if self.finish_status:
            self.pushButton_2.setEnabled(True)
            self.pushButton_3.setEnabled(True)

    # Удаление выделенных строк
    def delete_selected_rows(self):
        selected_indices = self.tableView.selectionModel().selectedRows()
        indices_to_remove = []

        for index in sorted(selected_indices, reverse=True):
            status_label = self.tableView.indexWidget(self.model.index(index.row(), 3))
            if status_label and status_label.text() in ["Идет загрузка...", "Декодирование", "Объединение"]:
                print(f"Строка {index.row() + 1} в процессе, удаление запрещено.")
            elif status_label and status_label.text() == "Загружено" and not self.finish_status:
                print(f"Строка {index.row() + 1} завершена но процесс не завершен, удаление запрещено.")
            else:
                indices_to_remove.append(index.row())

        # Удаление строк из модели и списка
        for row in sorted(indices_to_remove, reverse=True):
            self.model.removeRow(row)
            del self.file_paths[row]
            del self.resolution_files[row]

        if self.threads and not self.finish_status:
            self.worker.remove_signal.emit(indices_to_remove)

        # Проверка состояния кнопок
        if not self.file_paths:
            self.pushButton_2.setEnabled(False)
            self.pushButton_3.setEnabled(False)

        # print(f"delete_selected_rows: {self.file_paths}")


if __name__ == '__main__':
    app = QApplication(sys.argv)
    mainWindow = MainWindow()
    mainWindow.show()
    sys.exit(app.exec_())
