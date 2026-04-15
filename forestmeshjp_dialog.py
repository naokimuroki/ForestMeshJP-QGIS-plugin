import os
from qgis.PyQt import uic
from qgis.PyQt.QtWidgets import QDialog, QFileDialog
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtCore import Qt

from qgis.gui import QgsMapToolExtent, QgsRubberBand
from qgis.core import QgsWkbTypes, QgsGeometry

from .mesh_engine import run_engine
from .mesh_worker import MeshWorker

FORM_CLASS, _ = uic.loadUiType(
    os.path.join(os.path.dirname(__file__), "forestmeshjp_dialog.ui")
)


class ForestMeshJPDialog(QDialog, FORM_CLASS):

    def __init__(self, iface):
        super().__init__()
        self.iface = iface
        self.setupUi(self)

        # =========================
        # 状態管理
        # =========================
        self.selected_extent = None
        self.worker = None

        # =========================
        # UI初期化
        # =========================
        self.progressBar.setValue(0)

        # =========================
        # 赤枠（安定版）
        # =========================
        self.rb = QgsRubberBand(self.iface.mapCanvas(), QgsWkbTypes.PolygonGeometry)
        self.rb.setColor(QColor(255, 0, 0))
        self.rb.setFillColor(QColor(0, 0, 0, 0))
        self.rb.setWidth(2)

        # =========================
        # ボタン接続
        # =========================
        self.pushButton_run.clicked.connect(self.execute)
        self.pushButton_browse.clicked.connect(self.browse_file)
        self.pushButton_selectExtent.clicked.connect(self.start_extent_tool)

        # =========================
        # 範囲選択ツール
        # =========================
        self.tool = QgsMapToolExtent(self.iface.mapCanvas())
        self.tool.extentChanged.connect(self.on_extent_selected)

    # =========================================================
    # 保存先
    # =========================================================
    def browse_file(self):
        path, _ = QFileDialog.getSaveFileName(
            self,
            "保存先を選択",
            "",
            "GeoPackage (*.gpkg);;Shapefile (*.shp)"
        )
        if path:
            self.lineEdit_output.setText(path)

    # =========================================================
    # 範囲選択開始
    # =========================================================
    def start_extent_tool(self):
        self.iface.mapCanvas().setMapTool(self.tool)

    # =========================================================
    # 範囲確定 + 赤枠表示
    # =========================================================
    def on_extent_selected(self, rect):

        self.selected_extent = rect
        self.iface.mapCanvas().unsetMapTool(self.tool)

        # 安全描画（QGISバージョン差対策）
        self.rb.reset()
        self.rb.setToGeometry(QgsGeometry.fromRect(rect), None)

        # 表示
        self.textBrowser_extent.setText(
            f"{rect.xMinimum():.2f}, {rect.yMinimum():.2f} → "
            f"{rect.xMaximum():.2f}, {rect.yMaximum():.2f}"
        )

    # =========================================================
    # 進捗更新
    # =========================================================
    def update_progress(self, val):
        self.progressBar.setValue(int(val))

    # =========================================================
    # 実行
    # =========================================================
    def execute(self):

        print("=== EXECUTE START ===")

        self.progressBar.setValue(0)

        # =========================
        # 範囲チェック
        # =========================
        if not self.selected_extent or self.selected_extent.isEmpty():
            self.iface.messageBar().pushWarning(
                "ForestMeshJP",
                "範囲が選択されていません"
            )
            return

        # =========================
        # EPSG取得
        # =========================
        text = self.comboBox_epsg.currentText()

        try:
            epsg = None if text == "自動判定" else int(text.split("（")[0])
        except Exception:
            epsg = None

        # =========================
        # 入力
        # =========================
        z = self.spinBox_zoom.value()
        output_path = self.lineEdit_output.text()

        # =========================
        # Worker初期化
        # =========================
        self.worker = MeshWorker(
            run_engine,
            self.iface,
            z,
            epsg,
            self.selected_extent,
            output_path
        )

        # =========================
        # シグナル接続（重要）
        # =========================
        self.worker.progress.connect(self.update_progress)
        self.worker.finished.connect(self.on_finished)

        # ★エラー表示追加（超重要）
        self.worker.error.connect(
            lambda e: self.iface.messageBar().pushCritical("ForestMeshJP", e)
        )

        # =========================
        # スタート
        # =========================
        self.worker.start()

    # =========================================================
    # 完了
    # =========================================================
    def on_finished(self, result):

        print("=== FINISHED ===")

        self.progressBar.setValue(100)

        self.iface.messageBar().pushSuccess(
            "ForestMeshJP",
            "処理完了"
        )

    # =========================================================
    # クローズ処理
    # =========================================================
    def closeEvent(self, event):

        # 赤枠削除
        self.rb.reset()

        # Worker安全停止
        if self.worker and self.worker.isRunning():
            self.worker.terminate()
            self.worker.wait(1000)

        event.accept()