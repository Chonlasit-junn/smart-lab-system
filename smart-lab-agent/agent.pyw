import sys
from PyQt6.QtWidgets import QApplication
from core.agent_core import SmartLabAgent
from core.ui.login_overlay import LoginOverlay

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    agent_logic  = SmartLabAgent()
    login_screen = LoginOverlay(agent_logic)
    login_screen.show()
    sys.exit(app.exec())