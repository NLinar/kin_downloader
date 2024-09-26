import os
import sys
import threading
import json
from PyQt5.QtWidgets import (QApplication, QMainWindow, QHeaderView, QComboBox, QProgressBar, QLabel, QTableView,
                             QFileDialog, QMessageBox)
from PyQt5.QtGui import QStandardItemModel, QStandardItem
from PyQt5.QtCore import Qt
from main_window_ui import Ui_MainWindow
from setting import Ui_Settings
from downloader import Worker


# Класс главного окна
class MainWindow(QMainWindow, Ui_MainWindow):
    def __init__(self):
        super().__init__()
        self.setupUi(self)

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

        self.setAcceptDrops(True)
        # меню
        self.action_3.triggered.connect(self.open_settings)
        # кнопки
        self.pushButton.clicked.connect(self.open_file_dialog)
        self.pushButton_2.clicked.connect(self.start_thread)
        self.pushButton_3.clicked.connect(self.clear_table_and_array)

        style_sheet_1 = """
                QTableView::item:selected {
                    background: #A6BDD7;
                    color: black;
                }
                QTableView::item:selected:!active {
                    background: #A6BDD7;
                    color: black;
                }
                QHeaderView::section {
                    background: #DCDCDC;
                    font-weight: bold;
                    border: none;
                }
                QTableView::item {
                    background: transparent;
                }
            """
        self.tableView.setStyleSheet(style_sheet_1)

# ======================================================================================================================

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
                            self.add_file_to_table(entry)
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
        print(f"file_paths: {self.file_paths}")

    # ======================================================================================================================

    # Добавление файлов в таблицу
    def add_file_to_table(self, entry):
        row_count = self.model.rowCount()
        self.model.insertRow(row_count)
        self.tableView.setRowHeight(row_count, 10)
        for column, item_data in enumerate([entry['Title'], ', '.join(eval(entry['Quality'])), "", ""]):
            item = QStandardItem(item_data)
            if column == 0:
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
            if column == 1:
                combo_box = QComboBox()
                combo_box.addItems(eval(entry['Quality']))
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

        style_sheet_2 = """
            QProgressBar {
                text-align: center;
            }
            QProgressBar::chunk {
                background-color: #2ecc71;
            }
        """
        self.tableView.indexWidget(self.model.index(row_count, 2)).setStyleSheet(style_sheet_2)

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
        options = QFileDialog.Options()
        options |= QFileDialog.ReadOnly
        file_names, _ = QFileDialog.getOpenFileNames(self, "Выбрать файлы", "", "KIN Files (*.kin)", options=options)
        if file_names:
            for file_name in file_names:
                with open(file_name, 'r', encoding='utf-8') as file:
                    file_data = json.load(file)
                    for entry in file_data:
                        self.file_paths.append(entry)
                        self.add_file_to_table(entry)
            print(self.file_paths)
            if not self.threads or self.finish_status:
                self.pushButton_2.setEnabled(True)
                self.pushButton_3.setEnabled(True)

    def clear_table_and_array(self):
        self.pushButton_2.setEnabled(False)
        self.pushButton_3.setEnabled(False)
        self.model.removeRows(0, self.model.rowCount())
        self.file_paths.clear()
        print("Таблица и массив очищены")

    # Запуск потока
    def start_thread(self):
        try:
            self.pushButton_2.setEnabled(False)
            self.pushButton_3.setEnabled(False)

            # for i, entry in enumerate(self.file_paths):
            #     status_label = self.tableView.indexWidget(self.model.index(i, 3))
            #     if status_label.text() != "Загружено":
            #         self.not_downloaded_files.append((i, entry))

            # self.worker = Worker(self.not_downloaded_files, self.stop_threads)  # Сохраняем ссылку на worker

            self.new_file_indices = []
            self.new_file_indices = [self.file_paths.index(file) for file in self.newly_added_files if file in self.file_paths]
            print(self.new_file_indices)

            self.worker = Worker(self.file_paths, self.new_file_indices, self.stop_threads)  # Сохраняем ссылку на worker
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
            progress_bar = self.tableView.indexWidget(self.model.index(file_index, 2))
            status_label = self.tableView.indexWidget(self.model.index(file_index, 3))
            if progress_bar:
                progress_bar.setValue(progress)
                status_label.setStyleSheet("color: black;")
                status_label.setText("Идет загрузка...")
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

        if self.threads and not self.finish_status:
            self.worker.remove_signal.emit(indices_to_remove)

        # Проверка состояния кнопок
        if not self.file_paths:
            self.pushButton_2.setEnabled(False)
            self.pushButton_3.setEnabled(False)

        print(self.file_paths)


if __name__ == '__main__':
    app = QApplication(sys.argv)
    mainWindow = MainWindow()
    mainWindow.show()
    sys.exit(app.exec_())
