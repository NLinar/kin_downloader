from PyQt5.QtWidgets import QMainWindow
from PyQt5.uic import loadUi
import sys

class Ui_Settings(QMainWindow):
    def __init__(self):
        super().__init__()
        loadUi('setting_window.ui', self)
