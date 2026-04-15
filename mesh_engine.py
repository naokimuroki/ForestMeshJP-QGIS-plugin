from qgis.core import *
from qgis.PyQt.QtCore import QVariant, QCoreApplication, QTimer
import requests
import mapbox_vector_tile
import math
import os

# =========================
# タイル範囲（EPSG:3857）
# =========================
def tile_bounds_3857(x, y, z):
    origin = 2 * math.pi * 6378137 / 2.0
    n = 2 ** z
    res = (2 * origin) / n

    minx = x * res - origin
    maxx = (x + 1) * res - origin

    maxy = origin - y * res
    miny = origin - (y + 1) * res

    return minx, miny, maxx, maxy


# =========================
# メイン処理
# =========================
def run_engine(
    iface,
    z=16,
    user_epsg=None,
    extent=None,
    output_path=None,
    progress_callback=None
):
    canvas = iface.mapCanvas()

    # =========================
    # CRS設定
    # =========================
    crs_src = canvas.mapSettings().destinationCrs()
    crs_3857 = QgsCoordinateReferenceSystem("EPSG:3857")

    if user_epsg is None:
        user_epsg = crs_src.authid()

    crs_out = QgsCoordinateReferenceSystem(user_epsg)

    to_3857 = QgsCoordinateTransform(crs_src, crs_3857, QgsProject.instance())
    to_out = QgsCoordinateTransform(crs_3857, crs_out, QgsProject.instance())

    # =========================
    # extent → 3857
    # =========================
    if extent is None:
        extent = canvas.extent()

    extent_3857 = to_3857.transformBoundingBox(extent)

    xmin = extent_3857.xMinimum()
    ymin = extent_3857.yMinimum()
    xmax = extent_3857.xMaximum()
    ymax = extent_3857.yMaximum()

    # =========================
    # XYZ index
    # =========================
    def xyz(x, y, z):
        origin = 2 * math.pi * 6378137 / 2.0
        res = (2 * origin) / (2 ** z)
        xtile = int((x + origin) / res)
        ytile = int((origin - y) / res)
        return xtile, ytile

    x1, y1 = xyz(xmin, ymax, z)
    x2, y2 = xyz(xmax, ymin, z)

    tiles = [
        (x, y)
        for x in range(min(x1, x2), max(x1, x2) + 1)
        for y in range(min(y1, y2), max(y1, y2) + 1)
    ]

    total = max(len(tiles), 1)

    # =========================
    # メモリレイヤ（プロジェクトには追加せず、計算用として保持）
    # =========================
    layer = QgsVectorLayer(f"Polygon?crs={crs_out.authid()}", "mesh_temp", "memory")
    pr = layer.dataProvider()

    grid = {}
    url_template = "https://rinya-tiles.geospatial.jp/fr_mesh20m_pbf_2025/{z}/{x}/{y}.pbf"

    # =========================
    # タイル処理
    # =========================
    for i, (x, y) in enumerate(tiles):
        # 10タイルごとにQGISに操作権を返す（フリーズ防止）
        if i % 10 == 0:
            QCoreApplication.processEvents()

        if progress_callback:
            progress_callback(int(i / total * 60))

        try:
            r = requests.get(url_template.format(z=z, x=x, y=y), timeout=10)
            if r.status_code != 200:
                continue
            tile = mapbox_vector_tile.decode(r.content)
        except:
            continue

        minx, miny, maxx, maxy = tile_bounds_3857(x, y, z)

        def to_3857_coord(xx, yy, mvt_extent):
            return QgsPointXY(
                minx + (xx / mvt_extent) * (maxx - minx),
                miny + (yy / mvt_extent) * (maxy - miny)
            )

        for lyr in tile.values():
            mvt_extent = float(lyr.get("extent", 4096.0))
            for f in lyr.get("features", []):
                try:
                    if f["geometry"]["type"] != "Polygon":
                        continue

                    ring = f["geometry"]["coordinates"][0]
                    pts = [to_3857_coord(px, py, mvt_extent) for px, py in ring]
                    if pts[0] != pts[-1]: pts.append(pts[0])

                    geom = QgsGeometry.fromPolygonXY([pts])
                    if geom.isEmpty(): continue

                    geom.transform(to_out)
                    if geom.isEmpty(): continue

                    bbox = geom.boundingBox()
                    ix = int(math.floor(bbox.center().x() / 20))
                    iy = int(math.floor(bbox.center().y() / 20))

                    key = (ix, iy)
                    if key not in grid:
                        grid[key] = dict(f.get("properties", {}))
                except:
                    continue

    # =========================
    # フィールド設定
    # =========================
    field_names = set()
    for props in grid.values():
        field_names.update(props.keys())
    
    fields = [QgsField(k, QVariant.String) for k in sorted(list(field_names))]
    pr.addAttributes(fields)
    layer.updateFields()

    # =========================
    # メッシュ生成（フリーズ防止のため一括追加）
    # =========================
    total2 = max(len(grid), 1)
    features = []
    
    for i, ((ix, iy), props) in enumerate(grid.items()):
        if i % 500 == 0:
            QCoreApplication.processEvents()
        
        if progress_callback:
            progress_callback(60 + int(i / total2 * 35))

        rect = QgsRectangle(ix * 20, iy * 20, ix * 20 + 20, iy * 20 + 20)
        feat = QgsFeature(layer.fields())
        feat.setGeometry(QgsGeometry.fromRect(rect))
        
        attrs = [str(props.get(k, "")) for k in layer.fields().names()]
        feat.setAttributes(attrs)
        features.append(feat)

    pr.addFeatures(features)
    layer.updateExtents()

    # =========================
    # GPKG出力
    # =========================
    if output_path:
        if progress_callback: progress_callback(95)
        
        base_name = os.path.splitext(os.path.basename(output_path))[0]
        options = QgsVectorFileWriter.SaveVectorOptions()
        options.driverName = "GPKG"
        options.fileEncoding = "UTF-8"
        options.layerName = base_name

        # 書き出し
        QgsVectorFileWriter.writeAsVectorFormatV3(
            layer,
            output_path,
            QgsProject.instance().transformContext(),
            options
        )

        # メイン処理終了後にレイヤを読み込む
        def finalize():
            loaded = QgsVectorLayer(f"{output_path}|layername={base_name}", base_name, "ogr")
            if loaded.isValid():
                QgsProject.instance().addMapLayer(loaded)
                iface.mapCanvas().setCurrentLayer(loaded)
                iface.mapCanvas().refreshAllLayers()
                iface.mapCanvas().refresh()
            if progress_callback: progress_callback(100)

        # 200ミリ秒後に実行
        QTimer.singleShot(200, finalize)

    return None