from qgis.PyQt.QtCore import QThread, pyqtSignal
import traceback


class MeshWorker(QThread):

    progress = pyqtSignal(int)
    finished = pyqtSignal(object)
    error = pyqtSignal(str)

    def __init__(
        self,
        run_engine,
        iface,
        z,
        user_epsg,
        extent,
        output_path
    ):
        super().__init__()

        self.run_engine = run_engine
        self.iface = iface
        self.z = z
        self.user_epsg = user_epsg
        self.extent = extent
        self.output_path = output_path

    def run(self):

        try:
            print("=== MeshWorker START ===")

            result = self.run_engine(
                iface=self.iface,
                z=self.z,
                user_epsg=self.user_epsg,
                extent=self.extent,
                output_path=self.output_path,
                progress_callback=self.progress.emit
            )

            print("=== MeshWorker DONE ===")

            self.finished.emit(result)

        except Exception:
            err = traceback.format_exc()
            print("=== MeshWorker ERROR ===")
            print(err)
            self.error.emit(err)