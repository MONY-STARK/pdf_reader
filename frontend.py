from PySide6.QtWidgets import QWidget, QMainWindow, QToolBar, QComboBox
from PySide6.QtGui import QAction



class App(QMainWindow):


    def __init__(self):
        super().__init__()

        self.resize(900, 600)

        toolbar = QToolBar()
        self.addToolBar(toolbar)

        

        view_action = QAction("View", self)
        toolbar.addAction(view_action)

        next_action = QAction("Page", self)
        toolbar.addAction(next_action)

        highlight_action = QAction("Highlight", self)
        toolbar.addAction(highlight_action)