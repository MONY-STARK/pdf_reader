from frontend import App
from PySide6.QtWidgets import QApplication
import sys


app = QApplication(sys.argv)

widget= App()

widget.show()

sys.exit(app.exec())
