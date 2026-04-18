from qgis.PyQt.QtWidgets import QAction
from qgis.PyQt.QtGui import QIcon
from .forestmeshjp_dialog import ForestMeshJPDialog
import os

class ForestMeshJPPlugin:

    def __init__(self, iface):
        self.iface = iface
        self.action = None

    def initGui(self):
        icon_path = os.path.join(os.path.dirname(__file__), "icon.png")

        self.action = QAction(QIcon(icon_path), "", self.iface.mainWindow())
        self.action.setToolTip("ForestMeshJP")  
        self.action.triggered.connect(self.run)

        self.iface.addToolBarIcon(self.action)
        self.iface.addPluginToMenu("&ForestMeshJP", self.action)

    def unload(self):
        self.iface.removeToolBarIcon(self.action)
        self.iface.removePluginMenu("&ForestMeshJP", self.action)

    def run(self):
        self.dlg = ForestMeshJPDialog(self.iface)
        self.dlg.show()
