from PyQt5.QtWidgets import QDialog, QApplication
from PyQt5.uic import loadUi
import sys

class Ui_Settings(QDialog):
    def __init__(self):
        super().__init__()
        print("cvnxcv")
        loadUi('main_window.ui', self)
