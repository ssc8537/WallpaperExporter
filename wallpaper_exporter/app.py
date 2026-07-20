from __future__ import annotations

import os
import subprocess
import sys
import time
from datetime import datetime, time as datetime_time
from pathlib import Path

from PySide6.QtCore import QDate, QPoint, QRect, QRectF, QSize, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QFont, QFontDatabase, QIcon, QKeySequence, QPainter, QPainterPath, QPixmap, QPolygon
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QDateEdit,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QKeySequenceEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QProgressDialog,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .core import ExportRecord, WallpaperCandidate, WallpaperService, display_size, resolution_label
from .desktop_capture import capture_rendered_desktop, enable_per_monitor_dpi
from .hotkeys import GlobalHotkeyManager
from .video_tools import VideoFrameDialog, extract_video_fractions, format_time, save_qimage
from .workshop import (
    WallpaperEngineController,
    WorkshopProject,
    WorkshopScanner,
    discover_engine_dir,
    discover_workshop_dir,
    project_export_stem,
    scan_project_from_source,
)
from .workshop_ui import ImagePreviewDialog, WorkshopPage


def resource_path(relative: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return base / relative


def open_path(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True) if path.suffix == "" else None
    if sys.platform == "win32":
        os.startfile(str(path))  # type: ignore[attr-defined]
    else:
        QDesktopServices.openUrl(path.as_uri())


class CoverLabel(QWidget):
    clicked = Signal()

    def __init__(self, radius: int = 20, parent=None) -> None:
        super().__init__(parent)
        self._pixmap = QPixmap()
        self._radius = radius
        self.setMinimumSize(320, 180)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_image(self, path: str | Path | None) -> None:
        self._pixmap = QPixmap(str(path)) if path else QPixmap()
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        area = QRectF(self.rect())
        clip = QPainterPath()
        clip.addRoundedRect(area, self._radius, self._radius)
        painter.setClipPath(clip)
        painter.fillRect(self.rect(), QColor("#F5EAF1"))
        if not self._pixmap.isNull():
            target = self.size()
            scaled = self._pixmap.scaled(
                target,
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
            x = (scaled.width() - target.width()) // 2
            y = (scaled.height() - target.height()) // 2
            painter.drawPixmap(self.rect(), scaled, QRect(x, y, target.width(), target.height()))
        else:
            painter.setPen(QColor("#94758A"))
            painter.setFont(QFont("Microsoft YaHei UI", 12))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "等待检测壁纸…")
        painter.setClipping(False)
        painter.setPen(QColor("#FFFFFF"))
        painter.drawRoundedRect(area.adjusted(0.5, 0.5, -0.5, -0.5), self._radius, self._radius)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(event)


class ChibiMascot(QWidget):
    """Code-native original mascot used when raster generation is unavailable."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFixedSize(70, 70)
        self.setToolTip("原创 Q 版樱海小助手")

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#FFFFFF"))
        painter.drawEllipse(2, 2, 66, 66)
        painter.setBrush(QColor("#A9DDF2"))
        painter.drawEllipse(6, 8, 10, 10)
        painter.drawEllipse(55, 4, 7, 7)
        painter.setBrush(QColor("#51436E"))
        painter.drawPolygon(QPolygon([QPoint(10, 20), QPoint(18, 8), QPoint(25, 22)]))
        painter.drawPolygon(QPolygon([QPoint(45, 22), QPoint(53, 8), QPoint(61, 20)]))
        painter.setBrush(QColor("#FFE7DC"))
        painter.drawEllipse(13, 15, 44, 45)
        painter.setBrush(QColor("#F4AFC2"))
        painter.drawEllipse(12, 10, 46, 27)
        painter.drawEllipse(10, 24, 12, 25)
        painter.drawEllipse(49, 24, 11, 25)
        painter.setBrush(QColor("#6D5B91"))
        painter.drawEllipse(25, 35, 5, 7)
        painter.drawEllipse(41, 35, 5, 7)
        painter.setBrush(QColor("#FFFFFF"))
        painter.drawEllipse(27, 36, 2, 2)
        painter.drawEllipse(43, 36, 2, 2)
        painter.setBrush(QColor("#F4AFC2"))
        painter.drawEllipse(19, 44, 7, 3)
        painter.drawEllipse(45, 44, 7, 3)
        painter.setPen(QColor("#B36E8D"))
        painter.drawArc(31, 43, 10, 8, 200 * 16, 140 * 16)


class InfoPill(QFrame):
    def __init__(self, title: str, value: str = "—", parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("infoPill")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(3)
        label = QLabel(title)
        label.setObjectName("muted")
        self.value = QLabel(value)
        self.value.setObjectName("pillValue")
        layout.addWidget(label)
        layout.addWidget(self.value)


class CurrentPage(QWidget):
    export_requested = Signal()
    refresh_requested = Signal()
    choose_requested = Signal()
    open_requested = Signal()
    preview_requested = Signal()
    live_preview_requested = Signal()
    native_4k_requested = Signal()
    previous_requested = Signal()
    next_requested = Signal()
    manage_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(16)

        self.project_name = QLabel("当前项目：等待检测")
        self.project_name.setObjectName("qualityNote")
        self.project_name.setWordWrap(True)
        root.addWidget(self.project_name)

        self.preview = CoverLabel(24)
        self.preview.setMinimumHeight(220)
        root.addWidget(self.preview, 1)

        pills = QHBoxLayout()
        self.resolution = InfoPill("真实分辨率")
        self.image_format = InfoPill("源格式")
        self.file_size = InfoPill("文件大小")
        self.modified = InfoPill("更新时间")
        for pill in (self.resolution, self.image_format, self.file_size, self.modified):
            pills.addWidget(pill)
        root.addLayout(pills)

        self.quality_note = QLabel("保留源文件格式与原始像素，不放大、不二次压缩。")
        self.quality_note.setObjectName("qualityNote")
        root.addWidget(self.quality_note)

        destination = QHBoxLayout()
        self.path = QLineEdit()
        self.path.setReadOnly(True)
        choose = QPushButton("选择保存位置")
        choose.clicked.connect(self.choose_requested)
        destination.addWidget(QLabel("保存到"))
        destination.addWidget(self.path, 1)
        destination.addWidget(choose)
        root.addLayout(destination)

        actions = QHBoxLayout()
        refresh = QPushButton("刷新")
        refresh.setObjectName("secondaryButton")
        refresh.clicked.connect(self.refresh_requested)
        open_folder = QPushButton("打开目录")
        open_folder.setObjectName("secondaryButton")
        open_folder.clicked.connect(self.open_requested)
        preview = QPushButton("快照预览")
        preview.setObjectName("secondaryButton")
        preview.clicked.connect(self.preview_requested)
        live_preview = QPushButton("动态预览")
        live_preview.setObjectName("secondaryButton")
        live_preview.clicked.connect(self.live_preview_requested)
        native_4k = QPushButton("检查原生 4K")
        native_4k.setObjectName("secondaryButton")
        native_4k.setToolTip("只查找项目原始 4K 来源，不会把 2K 软件放大冒充 4K。")
        native_4k.clicked.connect(self.native_4k_requested)
        export = QPushButton("保存当前最高画质壁纸")
        export.setObjectName("primaryButton")
        export.clicked.connect(self.export_requested)
        actions.addWidget(refresh)
        actions.addWidget(open_folder)
        actions.addWidget(preview)
        actions.addWidget(live_preview)
        actions.addWidget(native_4k)
        actions.addStretch()
        root.addLayout(actions)

        navigation = QHBoxLayout()
        previous = QPushButton("← 返回上一张")
        previous.setObjectName("secondaryButton")
        previous.clicked.connect(self.previous_requested)
        next_wallpaper = QPushButton("切换下一张 →")
        next_wallpaper.setObjectName("secondaryButton")
        next_wallpaper.clicked.connect(self.next_requested)
        navigation.addWidget(previous)
        navigation.addWidget(next_wallpaper)
        navigation.addStretch()
        navigation.addWidget(export)
        root.addLayout(navigation)

    def show_candidate(
        self, candidate: WallpaperCandidate | None, project_title: str = "", preview_path: str = "", stale: bool = False
    ) -> None:
        self.preview.set_image(preview_path or (candidate.path if candidate else resource_path("assets/banner.jpg")))
        self.project_name.setText(f"当前 Wallpaper 项目：{project_title}" if project_title else "当前 Wallpaper 项目：无法识别")
        if candidate is None:
            for pill in (self.resolution, self.image_format, self.file_size, self.modified):
                pill.value.setText("未找到")
            self.quality_note.setText("未检测到 WallpaperEngineLockOverride.jpg，请先在 Wallpaper Engine 中启用锁屏覆盖快照。")
            return
        self.resolution.value.setText(candidate.resolution)
        self.image_format.value.setText("JPG" if candidate.image_format == "JPEG" else candidate.image_format)
        self.file_size.value.setText(candidate.size_text)
        self.modified.value.setText(datetime.fromisoformat(candidate.modified_at).strftime("%m-%d %H:%M"))
        if stale:
            self.quality_note.setText("当前项目已经切换，但 Wallpaper Engine 尚未写出新的高画质快照。界面显示项目预览；程序不会把旧快照冒充当前壁纸保存。")
        else:
            self.quality_note.setText("已锁定最高画质策略：原格式、原像素、原始字节复制；格式转换不会被伪装成画质提升。")


class BatchPage(QWidget):
    scan_requested = Signal()
    export_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        top = QHBoxLayout()
        title = QLabel("Windows Themes 静态图片")
        title.setObjectName("pageTitle")
        self.summary = QLabel("尚未扫描")
        self.summary.setObjectName("muted")
        scan = QPushButton("重新扫描")
        scan.setObjectName("secondaryButton")
        scan.clicked.connect(self.scan_requested)
        export = QPushButton("导出已勾选")
        export.setObjectName("primaryButton")
        export.clicked.connect(self.export_requested)
        top.addWidget(title)
        top.addWidget(self.summary)
        top.addStretch()
        top.addWidget(scan)
        top.addWidget(export)
        root.addLayout(top)

        note = QLabel("只列出验证有效的 JPG/PNG；完全相同的文件仅导出一次。高分辨率项目排在前面。")
        note.setObjectName("qualityNote")
        root.addWidget(note)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["选择", "来源", "分辨率", "格式", "大小", "修改时间"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        for column in range(2, 6):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        root.addWidget(self.table, 1)
        self.candidates: list[WallpaperCandidate] = []

    def set_candidates(self, candidates: list[WallpaperCandidate]) -> None:
        self.candidates = candidates
        self.table.setRowCount(len(candidates))
        for row, item in enumerate(candidates):
            check = QCheckBox()
            check.setChecked(True)
            holder = QWidget()
            layout = QHBoxLayout(holder)
            layout.setContentsMargins(8, 0, 8, 0)
            layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(check)
            self.table.setCellWidget(row, 0, holder)
            values = [
                item.source_name,
                item.resolution,
                "JPG" if item.image_format == "JPEG" else item.image_format,
                item.size_text,
                datetime.fromisoformat(item.modified_at).strftime("%Y-%m-%d %H:%M"),
            ]
            for column, value in enumerate(values, start=1):
                cell = QTableWidgetItem(value)
                cell.setToolTip(item.path)
                self.table.setItem(row, column, cell)
        total = sum(item.file_size for item in candidates)
        self.summary.setText(f"{len(candidates)} 张 · {display_size(total)}")

    def selected_candidates(self) -> list[WallpaperCandidate]:
        selected = []
        for row, item in enumerate(self.candidates):
            holder = self.table.cellWidget(row, 0)
            check = holder.findChild(QCheckBox) if holder else None
            if check and check.isChecked():
                selected.append(item)
        return selected


class HistoryPage(QWidget):
    open_record = Signal(str)
    clear_requested = Signal()
    export_filtered_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        top = QHBoxLayout()
        title = QLabel("更新归档与历史")
        title.setObjectName("pageTitle")
        top.addWidget(title)
        top.addStretch()
        root.addLayout(top)

        filters = QHBoxLayout()
        filters.addWidget(QLabel("发现日期"))
        self.start_date = QDateEdit(QDate.currentDate().addMonths(-1))
        self.start_date.setCalendarPopup(True)
        self.end_date = QDateEdit(QDate.currentDate())
        self.end_date.setCalendarPopup(True)
        filters.addWidget(self.start_date)
        filters.addWidget(QLabel("至"))
        filters.addWidget(self.end_date)
        clear = QPushButton("清除记录（不删图片）")
        clear.setObjectName("secondaryButton")
        clear.clicked.connect(self.clear_requested)
        export_filtered = QPushButton("筛选结果另存到…")
        export_filtered.setObjectName("primaryButton")
        export_filtered.clicked.connect(self.export_filtered_requested)
        filters.addStretch()
        filters.addWidget(export_filtered)
        filters.addWidget(clear)
        root.addLayout(filters)

        note = QLabel("程序打开时每 5 秒检查一次当前快照；内容真正变化才自动归档。日期按本程序发现时间筛选。")
        note.setWordWrap(True)
        note.setObjectName("qualityNote")
        root.addWidget(note)

        self.list = QListWidget()
        self.list.itemDoubleClicked.connect(self._activate_item)
        root.addWidget(self.list, 1)
        self.records: list[ExportRecord] = []
        self.start_date.dateChanged.connect(self.refresh_filter)
        self.end_date.dateChanged.connect(self.refresh_filter)

    def set_records(self, records: list[ExportRecord]) -> None:
        self.records = list(reversed(records))
        self.refresh_filter()

    def refresh_filter(self) -> None:
        self.list.clear()
        start = datetime.combine(self.start_date.date().toPython(), datetime_time.min).astimezone()
        end = datetime.combine(self.end_date.date().toPython(), datetime_time.max).astimezone()
        labels = {"success": "✓ 已保存", "duplicate": "○ 已跳过重复", "failed": "! 失败"}
        for record in self.records:
            try:
                discovered = datetime.fromisoformat(record.discovered_at)
            except ValueError:
                continue
            if not (start <= discovered <= end):
                continue
            when = datetime.fromisoformat(record.exported_at).strftime("%Y-%m-%d %H:%M:%S")
            identity = record.original_title or Path(record.target_path).stem
            if record.workshop_id:
                identity += f"  ·  ID {record.workshop_id}"
            text = f"{labels.get(record.status, record.status)}   {identity}\n    {when}   {record.width}×{record.height}   {record.image_format}"
            if record.message:
                text += f"   ·   {record.message}"
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, record.target_path)
            item.setToolTip(record.target_path)
            item.setSizeHint(QSize(0, 62))
            self.list.addItem(item)

    def filtered_success_records(self) -> list[ExportRecord]:
        start = datetime.combine(self.start_date.date().toPython(), datetime_time.min).astimezone()
        end = datetime.combine(self.end_date.date().toPython(), datetime_time.max).astimezone()
        result = []
        seen_hashes = set()
        for record in self.records:
            if record.status != "success" or record.content_hash in seen_hashes:
                continue
            try:
                discovered = datetime.fromisoformat(record.discovered_at)
            except ValueError:
                continue
            if start <= discovered <= end:
                result.append(record)
                seen_hashes.add(record.content_hash)
        return result

    def _activate_item(self, item: QListWidgetItem) -> None:
        self.open_record.emit(item.data(Qt.ItemDataRole.UserRole))


class SettingsPage(QWidget):
    save_requested = Signal(str, str, str, str, bool, str, str, str)
    browse_export = Signal()
    browse_themes = Signal()
    browse_workshop = Signal()
    browse_engine = Signal()
    open_themes = Signal()

    def __init__(self) -> None:
        super().__init__()
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        title = QLabel("设置")
        title.setObjectName("pageTitle")
        root.addWidget(title)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll_host = QWidget()
        scroll_layout = QVBoxLayout(scroll_host)
        scroll_layout.setContentsMargins(0, 0, 8, 0)

        card = QFrame()
        card.setObjectName("settingsCard")
        form = QVBoxLayout(card)
        form.setContentsMargins(24, 24, 24, 24)
        form.setSpacing(16)
        form.addWidget(QLabel("默认导出文件夹"))
        export_row = QHBoxLayout()
        self.export_path = QLineEdit()
        browse_export = QPushButton("浏览")
        browse_export.clicked.connect(self.browse_export)
        export_row.addWidget(self.export_path, 1)
        export_row.addWidget(browse_export)
        form.addLayout(export_row)
        form.addWidget(QLabel("Windows Themes 源目录"))
        themes_row = QHBoxLayout()
        self.themes_path = QLineEdit()
        browse_themes = QPushButton("浏览")
        browse_themes.clicked.connect(self.browse_themes)
        open_themes = QPushButton("打开")
        open_themes.clicked.connect(self.open_themes)
        themes_row.addWidget(self.themes_path, 1)
        themes_row.addWidget(browse_themes)
        themes_row.addWidget(open_themes)
        form.addLayout(themes_row)
        form.addWidget(QLabel("Steam Workshop 431960 目录"))
        workshop_row = QHBoxLayout()
        self.workshop_path = QLineEdit()
        browse_workshop = QPushButton("浏览")
        browse_workshop.clicked.connect(self.browse_workshop)
        workshop_row.addWidget(self.workshop_path, 1)
        workshop_row.addWidget(browse_workshop)
        form.addLayout(workshop_row)
        form.addWidget(QLabel("Wallpaper Engine 安装目录"))
        engine_row = QHBoxLayout()
        self.engine_path = QLineEdit()
        browse_engine = QPushButton("浏览")
        browse_engine.clicked.connect(self.browse_engine)
        engine_row.addWidget(self.engine_path, 1)
        engine_row.addWidget(browse_engine)
        form.addLayout(engine_row)
        self.monitor = QCheckBox("自动保存新的桌面快照（关闭时只手动保存）")
        form.addWidget(self.monitor)

        shortcut_title = QLabel("桌面全局快捷键（即使程序在后台也可使用）")
        shortcut_title.setObjectName("pageTitle")
        form.addWidget(shortcut_title)
        shortcut_grid = QGridLayout()
        self.save_hotkey = QKeySequenceEdit()
        self.next_hotkey = QKeySequenceEdit()
        self.previous_hotkey = QKeySequenceEdit()
        shortcut_grid.addWidget(QLabel("保存当前最高画质壁纸"), 0, 0)
        shortcut_grid.addWidget(self.save_hotkey, 0, 1)
        shortcut_grid.addWidget(QLabel("切换下一张壁纸"), 1, 0)
        shortcut_grid.addWidget(self.next_hotkey, 1, 1)
        shortcut_grid.addWidget(QLabel("返回上一张壁纸"), 2, 0)
        shortcut_grid.addWidget(self.previous_hotkey, 2, 1)
        form.addLayout(shortcut_grid)
        invariant = QLabel("安全承诺：不联网、不修改 Wallpaper Engine、不移动或删除任何源图片；导出永不覆盖已有文件。")
        invariant.setWordWrap(True)
        invariant.setObjectName("qualityNote")
        form.addWidget(invariant)
        save = QPushButton("保存设置")
        save.setObjectName("primaryButton")
        save.clicked.connect(lambda: self.save_requested.emit(
            self.export_path.text(), self.themes_path.text(), self.workshop_path.text(), self.engine_path.text(), self.monitor.isChecked(),
            self.save_hotkey.keySequence().toString(QKeySequence.SequenceFormat.PortableText),
            self.next_hotkey.keySequence().toString(QKeySequence.SequenceFormat.PortableText),
            self.previous_hotkey.keySequence().toString(QKeySequence.SequenceFormat.PortableText),
        ))
        form.addWidget(save, alignment=Qt.AlignmentFlag.AlignRight)
        scroll_layout.addWidget(card)
        scroll_layout.addStretch()
        scroll.setWidget(scroll_host)
        root.addWidget(scroll, 1)


class GlobalShortcutsPage(QWidget):
    save_requested = Signal()
    next_requested = Signal()
    previous_requested = Signal()
    manage_requested = Signal()
    settings_requested = Signal()
    history_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        title = QLabel("桌面全局快捷键")
        title.setObjectName("pageTitle")
        root.addWidget(title)
        note = QLabel("程序在后台或桌面上时也能切换、保存和管理当前壁纸。快捷键可在设置页修改。")
        note.setWordWrap(True)
        note.setObjectName("qualityNote")
        root.addWidget(note)

        actions = QGridLayout()
        actions.setHorizontalSpacing(10)
        actions.setVerticalSpacing(10)
        save = QPushButton("保存当前最高画质壁纸")
        next_wallpaper = QPushButton("切换下一张壁纸")
        previous = QPushButton("返回上一张壁纸")
        manage = QPushButton("在 Wallpaper 中打开 / 管理 / 取消订阅")
        manage.setObjectName("primaryButton")
        save.clicked.connect(self.save_requested)
        next_wallpaper.clicked.connect(self.next_requested)
        previous.clicked.connect(self.previous_requested)
        manage.clicked.connect(self.manage_requested)
        actions.addWidget(save, 0, 0)
        actions.addWidget(next_wallpaper, 0, 1)
        actions.addWidget(previous, 1, 0)
        actions.addWidget(manage, 1, 1)
        root.addLayout(actions)

        self.shortcut_summary = QLabel("")
        self.shortcut_summary.setObjectName("qualityNote")
        self.shortcut_summary.setWordWrap(True)
        root.addWidget(self.shortcut_summary)
        links = QHBoxLayout()
        settings = QPushButton("打开设置")
        history = QPushButton("打开更新与历史")
        settings.clicked.connect(self.settings_requested)
        history.clicked.connect(self.history_requested)
        links.addWidget(settings)
        links.addWidget(history)
        links.addStretch()
        root.addLayout(links)
        root.addStretch()

    def set_shortcuts(self, save: str, next_key: str, previous: str) -> None:
        self.shortcut_summary.setText(
            f"当前快捷键：保存 {save or '未设置'} · 下一张 {next_key or '未设置'} · 上一张 {previous or '未设置'}"
        )


class MainWindow(QMainWindow):
    def __init__(self, service: WallpaperService | None = None) -> None:
        super().__init__()
        self._load_windows_chinese_font()
        self.service = service or WallpaperService()
        if not self.service.config.get("monitor_user_set", False):
            self.service.update_config(monitor_enabled=False, monitor_user_set=True)
        workshop = discover_workshop_dir(str(self.service.config.get("workshop_dir", "")))
        engine = discover_engine_dir(str(self.service.config.get("wallpaper_engine_dir", "")))
        changes = {}
        if workshop:
            changes["workshop_dir"] = str(workshop)
        if engine:
            changes["wallpaper_engine_dir"] = str(engine)
        if changes:
            self.service.update_config(**changes)
        self.workshop_projects: list[WorkshopProject] = []
        self._workshop_scan_started = False
        self._navigation_history: list[str] = []
        self._navigation_index = -1
        self._navigation_pending_target = ""
        self._navigation_busy = False
        self.engine_controller = WallpaperEngineController(engine) if engine else None
        self.active_preview_names: set[str] = set()
        self.current_candidate: WallpaperCandidate | None = None
        self.current_project: WorkshopProject | None = None
        self.current_snapshot_stale = False
        self.current_rendered_candidate: WallpaperCandidate | None = None
        self.current_rendered_project_key = ""
        self.setWindowTitle("樱海壁纸收藏夹 · Wallpaper Engine 导出助手")
        self.setMinimumSize(820, 540)
        self.resize(900, 585)
        icon_path = resource_path("assets/app_icon.png")
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))
        self._build_ui()
        self._apply_style()
        self._wire_pages()
        self.hotkeys = GlobalHotkeyManager(QApplication.instance(), self)
        self.hotkeys.activated.connect(self._handle_global_hotkey)

        self.monitor_timer = QTimer(self)
        self.monitor_timer.timeout.connect(self.monitor_current)
        self.monitor_timer.start(int(self.service.config.get("monitor_seconds", 5)) * 1000)
        self.toast_timer = QTimer(self)
        self.toast_timer.setSingleShot(True)
        self.toast_timer.timeout.connect(self._clear_toast)
        self._toast_message = ""
        self._configure_hotkeys()
        QTimer.singleShot(100, self.refresh_all)

    def _build_ui(self) -> None:
        central = QWidget()
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(174)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(14, 16, 14, 14)
        side.setSpacing(8)

        avatar = CoverLabel(24)
        avatar.setFixedSize(58, 58)
        avatar_path = resource_path("assets/avatar.jpg")
        avatar.set_image(avatar_path if avatar_path.exists() else resource_path("assets/banner.jpg"))
        art_row = QHBoxLayout()
        art_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        art_row.addWidget(avatar)
        art_row.addWidget(ChibiMascot())
        side.addLayout(art_row)
        brand = QLabel("樱海壁纸收藏夹")
        brand.setObjectName("brand")
        brand.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subbrand = QLabel("原画质 · 安心归档")
        subbrand.setObjectName("mutedOnPink")
        subbrand.setAlignment(Qt.AlignmentFlag.AlignCenter)
        side.addWidget(brand)
        side.addWidget(subbrand)
        side.addSpacing(14)

        self.nav = QListWidget()
        self.nav.setObjectName("navigation")
        self.nav.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.nav.setFixedHeight(226)
        self.nav.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.nav.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        for text in ("当前壁纸", "Wallpaper 库", "Themes 批量", "更新与历史", "设置", "桌面全局快捷键"):
            item = QListWidgetItem(text)
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item.setSizeHint(QSize(0, 32))
            self.nav.addItem(item)
        self.nav.setCurrentRow(0)
        side.addWidget(self.nav)
        self.library_progress_label = QLabel("图库：等待扫描")
        self.library_progress_label.setObjectName("mutedOnPink")
        self.library_progress_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.library_progress = QProgressBar()
        self.library_progress.setTextVisible(False)
        self.library_progress.setFixedHeight(7)
        side.addStretch()
        side.addWidget(self.library_progress_label)
        side.addWidget(self.library_progress)
        badge = QLabel("4K 优先 · 不压缩 · 不放大")
        badge.setObjectName("sideBadge")
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        side.addWidget(badge)
        root.addWidget(sidebar)

        content = QWidget()
        content.setObjectName("content")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(16, 12, 16, 10)
        content_layout.setSpacing(10)

        header = QHBoxLayout()
        heading_box = QVBoxLayout()
        self.heading = QLabel("当前壁纸")
        self.heading.setObjectName("heading")
        self.subtitle = QLabel("检测 Wallpaper Engine 生成的无图标静态快照")
        self.subtitle.setObjectName("muted")
        heading_box.addWidget(self.heading)
        heading_box.addWidget(self.subtitle)
        header.addLayout(heading_box)
        header.addStretch()
        self.monitor_toggle = QCheckBox("自动保存")
        self.monitor_toggle.setObjectName("monitorToggle")
        self.monitor_toggle.setToolTip("开启：程序运行时自动保存新的桌面快照；关闭：只手动保存。")
        header.addWidget(self.monitor_toggle)
        content_layout.addLayout(header)

        self.stack = QStackedWidget()
        self.current_page = CurrentPage()
        self.workshop_page = WorkshopPage()
        self.batch_page = BatchPage()
        self.history_page = HistoryPage()
        self.settings_page = SettingsPage()
        self.shortcuts_page = GlobalShortcutsPage()
        for page in (self.current_page, self.workshop_page, self.batch_page, self.history_page, self.settings_page, self.shortcuts_page):
            self.stack.addWidget(page)
        content_layout.addWidget(self.stack, 1)

        footer = QHBoxLayout()
        self.status = QLabel("准备就绪")
        self.status.setObjectName("muted")
        self.progress = QProgressBar()
        self.progress.setRange(0, 1)
        self.progress.setValue(1)
        self.progress.setTextVisible(False)
        self.progress.setFixedWidth(170)
        self.progress.hide()
        footer.addWidget(self.status)
        footer.addStretch()
        footer.addWidget(self.progress)
        content_layout.addLayout(footer)
        root.addWidget(content, 1)
        self.setCentralWidget(central)

    def _wire_pages(self) -> None:
        self.nav.currentRowChanged.connect(self._change_page)
        self.current_page.export_requested.connect(self.export_current)
        self.current_page.refresh_requested.connect(self.refresh_all)
        self.current_page.choose_requested.connect(self.choose_export_dir)
        self.current_page.open_requested.connect(lambda: open_path(self.service.export_dir))
        self.current_page.preview_requested.connect(self.preview_current_snapshot)
        self.current_page.live_preview_requested.connect(self.preview_current_live)
        self.current_page.native_4k_requested.connect(self.check_native_4k_source)
        self.current_page.previous_requested.connect(self.previous_wallpaper)
        self.current_page.next_requested.connect(self.next_wallpaper)
        self.current_page.manage_requested.connect(self.manage_current_project)
        self.workshop_page.scan_requested.connect(self.scan_workshop)
        self.workshop_page.video_requested.connect(self.open_video_picker)
        self.workshop_page.play_requested.connect(self.play_workshop_project)
        self.workshop_page.close_preview_requested.connect(self.close_dynamic_previews)
        self.workshop_page.direct_batch_requested.connect(self.export_direct_batch)
        self.workshop_page.video_batch_requested.connect(self.export_video_batch)
        self.workshop_page.load_progress_changed.connect(self._update_library_progress)
        self.shortcuts_page.save_requested.connect(self.export_current)
        self.shortcuts_page.next_requested.connect(self.next_wallpaper)
        self.shortcuts_page.previous_requested.connect(self.previous_wallpaper)
        self.shortcuts_page.manage_requested.connect(self.manage_current_project)
        self.shortcuts_page.settings_requested.connect(lambda: self.nav.setCurrentRow(4))
        self.shortcuts_page.history_requested.connect(lambda: self.nav.setCurrentRow(3))
        self.batch_page.scan_requested.connect(self.scan_batch)
        self.batch_page.export_requested.connect(self.export_batch)
        self.history_page.clear_requested.connect(self.clear_history)
        self.history_page.export_filtered_requested.connect(self.export_filtered_history)
        self.history_page.open_record.connect(self.open_record_path)
        self.settings_page.save_requested.connect(self.save_settings)
        self.settings_page.browse_export.connect(self.choose_export_dir)
        self.settings_page.browse_themes.connect(self.choose_themes_dir)
        self.settings_page.browse_workshop.connect(self.choose_workshop_dir)
        self.settings_page.browse_engine.connect(self.choose_engine_dir)
        self.settings_page.open_themes.connect(lambda: open_path(self.service.themes_dir))
        self.monitor_toggle.toggled.connect(self.set_monitor_enabled)
        self.settings_page.monitor.toggled.connect(self.set_monitor_enabled)

    def _change_page(self, index: int) -> None:
        self.stack.setCurrentIndex(index)
        titles = [
            ("当前壁纸", "检测 Wallpaper Engine 生成的无图标静态快照"),
            ("Wallpaper 库", "按原始名称浏览、勾选和处理已下载项目"),
            ("Themes 批量", "查找 Windows Themes 中现存的有效 JPG / PNG"),
            ("更新与历史", "按发现时间查看自动归档记录"),
            ("设置", "保存位置、源目录与运行中监控"),
            ("桌面全局快捷键", "后台也能保存、切换和管理当前壁纸"),
        ]
        self.heading.setText(titles[index][0])
        self.subtitle.setText(titles[index][1])
        if index == 1 and not self.workshop_projects and not self._workshop_scan_started:
            QTimer.singleShot(0, self.scan_workshop)

    def _update_library_progress(self, loaded: int, total: int) -> None:
        self.library_progress.setRange(0, max(1, total))
        self.library_progress.setValue(loaded)
        self.library_progress_label.setText(f"图库：已加载 {loaded}/{total}")

    def _configure_hotkeys(self) -> None:
        if not self.hotkeys.available:
            return
        failed = []
        for action, key in (
            ("save", str(self.service.config.get("hotkey_save", "Ctrl+Alt+S"))),
            ("next", str(self.service.config.get("hotkey_next", "Ctrl+Alt+Right"))),
            ("previous", str(self.service.config.get("hotkey_previous", "Ctrl+Alt+Left"))),
        ):
            if key and not self.hotkeys.register(action, key):
                failed.append(key)
        if failed:
            self.show_toast(f"以下快捷键已被其他程序占用：{', '.join(failed)}", duplicate=True)

    def _handle_global_hotkey(self, action: str) -> None:
        if action == "save":
            self.export_current()
        elif action == "next":
            self.next_wallpaper()
        elif action == "previous":
            self.previous_wallpaper()
        elif action == "preview_escape":
            self.close_dynamic_previews()

    def next_wallpaper(self) -> None:
        if self._navigation_busy:
            self.show_toast("正在等待 Wallpaper Engine 完成上一次切换，请稍候。", duplicate=True)
            return
        controller = self._controller_or_warn()
        if controller is None:
            return
        current = controller.current_wallpaper_file()
        self._remember_navigation(current)
        try:
            self._navigation_busy = True
            controller.next_wallpaper(0)
        except OSError as exc:
            self._navigation_busy = False
            QMessageBox.warning(self, "切换失败", str(exc))
            return
        self.show_toast("已发送“下一张”命令，正在等待桌面完成切换。")
        QTimer.singleShot(180, lambda: self._wait_for_next(controller, current, 35))

    def previous_wallpaper(self) -> None:
        if self._navigation_busy:
            self.show_toast("正在等待 Wallpaper Engine 完成上一次切换，请稍候。", duplicate=True)
            return
        controller = self._controller_or_warn()
        if controller is None:
            return
        target_index = self._navigation_index - 1
        if target_index < 0:
            self.show_toast("本次运行还没有可返回的上一张记录。", duplicate=True)
            return
        previous = self._navigation_history[target_index]
        try:
            self._navigation_busy = True
            controller.open_file(previous)
        except OSError as exc:
            self._navigation_busy = False
            QMessageBox.warning(self, "返回失败", str(exc))
            return
        self.show_toast("正在返回最近使用的上一张壁纸。")
        QTimer.singleShot(180, lambda: self._wait_for_previous(controller, previous, target_index, 35))

    def _wait_for_next(self, controller: WallpaperEngineController, before: str, attempts: int) -> None:
        current = controller.current_wallpaper_file()
        if current and self._project_key(current) != self._project_key(before):
            self._navigation_busy = False
            self._sync_navigation(current)
            self.refresh_all()
            self.show_toast("已切换到下一张壁纸。")
            return
        if attempts <= 0:
            self._navigation_busy = False
            self.show_toast("Wallpaper Engine 未在预期时间内完成切换，请再试一次。", duplicate=True)
            return
        QTimer.singleShot(180, lambda: self._wait_for_next(controller, before, attempts - 1))

    def _wait_for_previous(
        self, controller: WallpaperEngineController, target: str, target_index: int, attempts: int
    ) -> None:
        current = controller.current_wallpaper_file()
        if current and self._project_key(current) == self._project_key(target):
            self._navigation_index = target_index
            self._navigation_pending_target = ""
            self._navigation_busy = False
            self.refresh_all()
            self.show_toast("已返回最近使用的上一张壁纸。")
            return
        if attempts <= 0:
            self._navigation_busy = False
            self.show_toast("返回上一张失败，已停止继续切换，避免桌面变空。", duplicate=True)
            return
        QTimer.singleShot(180, lambda: self._wait_for_previous(controller, target, target_index, attempts - 1))

    @staticmethod
    def _project_key(source: str) -> str:
        normalized = source.replace("\\", "/").casefold()
        parts = normalized.split("/431960/", 1)
        if len(parts) == 2:
            return parts[1].split("/", 1)[0]
        return str(Path(source).parent.resolve(strict=False)).casefold()

    def _remember_navigation(self, current: str) -> None:
        if not current:
            return
        if self._navigation_index < 0:
            self._navigation_history = [current]
            self._navigation_index = 0
            return
        if self._navigation_history[self._navigation_index] != current:
            self._navigation_history = self._navigation_history[: self._navigation_index + 1]
            self._navigation_history.append(current)
            self._navigation_index += 1

    def _sync_navigation(self, current: str) -> None:
        if not current:
            return
        if self._navigation_pending_target and current.casefold() == self._navigation_pending_target.casefold():
            self._navigation_pending_target = ""
            return
        if self._navigation_index >= 0 and self._navigation_history[self._navigation_index].casefold() == current.casefold():
            return
        self._remember_navigation(current)

    def manage_current_project(self) -> None:
        project = self._current_workshop_project()
        if project is None:
            self.show_toast("无法关联当前壁纸的 Workshop 项目。", duplicate=True)
            return
        self.open_project_management(project)

    def open_project_management(self, project: WorkshopProject) -> None:
        if not project.workshop_id.isdigit():
            self.show_toast("这个项目没有有效的 Steam Workshop ID。", duplicate=True)
            return
        QDesktopServices.openUrl(QUrl(f"steam://url/CommunityFilePage/{project.workshop_id}"))
        self.show_toast(f"已打开 Steam 项目页：{project.title}。可在页面中取消订阅。")

    def refresh_all(self) -> None:
        self.status.setText("正在检测壁纸…")
        QApplication.processEvents()
        self.current_candidate = self.service.current_wallpaper()
        controller = self._controller_or_warn(silent=True)
        current_file = ""
        if controller:
            current_file = controller.current_wallpaper_file()
            self._sync_navigation(current_file)
        self.current_project = scan_project_from_source(current_file) if current_file else None
        self.current_snapshot_stale = self._snapshot_is_stale(self.current_candidate, self.current_project, controller)
        if (
            self.current_rendered_candidate
            and self.current_project
            and self.current_rendered_project_key == self.current_project.workshop_id
            and Path(self.current_rendered_candidate.path).is_file()
        ):
            self.current_candidate = self.current_rendered_candidate
            self.current_snapshot_stale = False
        self.current_page.show_candidate(
            self.current_candidate,
            self.current_project.title if self.current_project else "",
            self.current_project.preview_path if self.current_snapshot_stale and self.current_project else "",
            self.current_snapshot_stale,
        )
        self.current_page.path.setText(str(self.service.export_dir))
        self.settings_page.export_path.setText(str(self.service.export_dir))
        self.settings_page.themes_path.setText(str(self.service.themes_dir))
        self.settings_page.workshop_path.setText(str(self.service.config.get("workshop_dir", "")))
        self.settings_page.engine_path.setText(str(self.service.config.get("wallpaper_engine_dir", "")))
        self.settings_page.save_hotkey.setKeySequence(QKeySequence(str(self.service.config.get("hotkey_save", "Ctrl+Alt+S"))))
        self.settings_page.next_hotkey.setKeySequence(QKeySequence(str(self.service.config.get("hotkey_next", "Ctrl+Alt+Right"))))
        self.settings_page.previous_hotkey.setKeySequence(QKeySequence(str(self.service.config.get("hotkey_previous", "Ctrl+Alt+Left"))))
        self.shortcuts_page.set_shortcuts(
            str(self.service.config.get("hotkey_save", "Ctrl+Alt+S")),
            str(self.service.config.get("hotkey_next", "Ctrl+Alt+Right")),
            str(self.service.config.get("hotkey_previous", "Ctrl+Alt+Left")),
        )
        monitor = bool(self.service.config.get("monitor_enabled", False))
        self.settings_page.monitor.blockSignals(True)
        self.settings_page.monitor.setChecked(monitor)
        self.settings_page.monitor.blockSignals(False)
        self.monitor_toggle.blockSignals(True)
        self.monitor_toggle.setChecked(monitor)
        self.monitor_toggle.setText("自动保存：开" if monitor else "自动保存：关")
        self.monitor_toggle.blockSignals(False)
        self.scan_batch()
        self.history_page.set_records(self.service.history)
        startup_record = (
            self._export_current_named(self.current_candidate)
            if self.service.config.get("monitor_enabled", False) and not self.current_snapshot_stale
            else None
        )
        if startup_record and startup_record.status == "success":
            self.history_page.set_records(self.service.history)
            self.status.setText(f"发现尚未归档的当前快照，已自动保存：{startup_record.width}×{startup_record.height}")
            return
        if self.current_candidate:
            self.status.setText(f"已检测：{self.current_candidate.resolution} · {self.current_candidate.image_format}")
        else:
            self.status.setText("未找到当前 Wallpaper Engine 快照")

    def scan_batch(self) -> None:
        candidates = self.service.best_per_exact_image(self.service.scan_theme_images())
        self.batch_page.set_candidates(candidates)
        if self.stack.currentWidget() is self.batch_page:
            self.status.setText(f"扫描完成：发现 {len(candidates)} 张有效静态图片")

    def _snapshot_is_stale(
        self,
        candidate: WallpaperCandidate | None,
        project: WorkshopProject | None,
        controller: WallpaperEngineController | None,
    ) -> bool:
        if candidate is None or project is None:
            return False
        for record in self.service.history:
            if record.status == "success" and record.content_hash == candidate.content_hash and record.workshop_id:
                return record.workshop_id != project.workshop_id
        if controller and controller.config_path.is_file():
            try:
                snapshot_time = datetime.fromisoformat(candidate.modified_at).timestamp()
                return controller.config_path.stat().st_mtime - snapshot_time > 300
            except (OSError, ValueError):
                return False
        return False

    def scan_workshop(self) -> None:
        if self._workshop_scan_started:
            return
        self._workshop_scan_started = True
        root = discover_workshop_dir(str(self.service.config.get("workshop_dir", "")))
        if not root:
            self._workshop_scan_started = False
            self.workshop_projects = []
            self.workshop_page.set_projects([])
            if self.stack.currentWidget() is self.workshop_page:
                QMessageBox.warning(self, "未找到 Wallpaper 库", "没有找到 Steam Workshop 的 431960 目录，请确认 Wallpaper Engine 已安装并下载过壁纸。")
            return
        self._set_busy(True, "正在读取 Wallpaper 原始名称和类型…")
        QApplication.processEvents()
        self.workshop_projects = WorkshopScanner(root).scan()
        self.workshop_page.set_projects(self.workshop_projects)
        self.service.update_config(workshop_dir=str(root))
        self._workshop_scan_started = False
        self._set_busy(False, f"Wallpaper 库扫描完成：{len(self.workshop_projects)} 项")

    def preview_current_snapshot(self) -> None:
        self.refresh_all()
        if self.current_snapshot_stale and self.current_project:
            preview = Path(self.current_project.preview_path)
            if preview.is_file():
                ImagePreviewDialog(preview, f"当前项目预览 · {self.current_project.title}", self).exec()
            else:
                self.show_toast("当前项目已识别，但 Wallpaper Engine 尚未生成可预览的新快照。", duplicate=True)
            return
        if not self.current_candidate:
            QMessageBox.information(self, "没有当前快照", "未找到有效的 WallpaperEngineLockOverride.jpg。")
            return
        ImagePreviewDialog(Path(self.current_candidate.path), f"当前快照 · {self.current_candidate.resolution}", self).exec()

    def preview_current_live(self) -> None:
        controller = self._controller_or_warn()
        if controller is None:
            return
        current = controller.current_wallpaper_file()
        if not current:
            QMessageBox.information(self, "无法定位当前项目", "Wallpaper Engine 配置中没有找到当前显示器的项目路径。")
            return
        project = next((item for item in self.workshop_projects if item.workshop_id in current), None)
        if project is None:
            project = WorkshopProject("current", "当前动态壁纸", "unknown", str(Path(current).parent), "", current, "")
        self.play_workshop_project(project)

    def check_native_4k_source(self) -> None:
        candidate = self.service.current_wallpaper()
        if candidate and max(candidate.width, candidate.height) >= 3840:
            self.show_toast("当前桌面快照已经达到原生 4K，无需放大。")
            return
        project = self._current_workshop_project()
        if project is None:
            self.show_toast("无法关联当前 Wallpaper 项目，不能确认是否存在原生 4K 来源。", duplicate=True)
            return
        if project.is_video:
            self.show_toast("已找到当前项目的原始视频；选帧器会按视频真实分辨率保存，若源视频为 4K 就得到原生 4K。")
            QTimer.singleShot(150, lambda: self.open_video_picker(project))
            return
        if project.is_direct_image:
            original = self.service.inspect_image(Path(project.content_path), "Workshop 原始静态图")
            if original and max(original.width, original.height) >= 3840:
                record = self.service.export_candidate(
                    original,
                    preferred_stem=project_export_stem(self.service.export_dir, project, original.extension),
                    original_title=project.title,
                    workshop_id=project.workshop_id,
                    project_path=project.project_json or project.project_dir,
                )
                self._show_export_result(record)
            else:
                self.show_toast("当前项目的原始静态图也没有达到 4K；不会进行虚假放大。", duplicate=True)
            return
        self.show_toast("当前项目是实时合成的 Scene/Web；2K 屏生成的快照不能恢复成原生 4K，不执行软件放大。", duplicate=True)

    def open_video_picker(self, project: WorkshopProject) -> None:
        if not project.is_video:
            QMessageBox.information(self, "不是可解码视频", "这个项目没有可读取的原始视频文件。")
            return
        VideoFrameDialog(project, self.service, self).exec()
        self.history_page.set_records(self.service.history)

    def play_workshop_project(self, project: WorkshopProject) -> None:
        controller = self._controller_or_warn()
        if controller is None:
            return
        try:
            self.close_dynamic_previews(silent=True)
            window_name = controller.play_in_window(project, 1280, 720)
            self.active_preview_names.add(window_name)
        except OSError as exc:
            QMessageBox.warning(self, "动态预览失败", str(exc))
            return
        self.hotkeys.register("preview_escape", "Esc")
        QTimer.singleShot(250, lambda: self._raise_preview_window(window_name, 8))
        self.show_toast(f"动态预览正在打开：{project.title}。按 Esc 或点击“关闭动态预览”。")

    def _raise_preview_window(self, window_name: str, attempts: int) -> None:
        if window_name not in self.active_preview_names:
            return
        controller = self._controller_or_warn(silent=True)
        if controller and controller.bring_window_front(window_name):
            return
        if attempts > 0:
            QTimer.singleShot(300, lambda: self._raise_preview_window(window_name, attempts - 1))

    def close_dynamic_previews(self, silent: bool = False) -> None:
        if not self.active_preview_names:
            self.hotkeys.unregister("preview_escape")
            if not silent:
                self.show_toast("当前没有由本程序打开的动态预览。", duplicate=True)
            return
        controller = self._controller_or_warn(silent=silent)
        if controller is None:
            return
        failed = 0
        for name in list(self.active_preview_names):
            try:
                controller.close_window(name)
                self.active_preview_names.discard(name)
            except OSError:
                failed += 1
        if not self.active_preview_names:
            self.hotkeys.unregister("preview_escape")
        if not silent:
            self.show_toast("动态预览已关闭。" if not failed else f"有 {failed} 个预览关闭失败，请在 Wallpaper Engine 中关闭。", duplicate=bool(failed))

    def export_video_batch(self, projects: list[WorkshopProject]) -> None:
        if not projects:
            QMessageBox.information(self, "没有视频项目", "请先在 Wallpaper 库中勾选至少一个视频项目。")
            return
        format_box = QMessageBox(self)
        format_box.setWindowTitle("选择视频 B 帧保存格式")
        format_box.setText(
            f"将从 {len(projects)} 个原始视频的 50% 位置读取 B 候选帧。\n\n"
            "无损 PNG：不再次压缩，文件较大。\n高质量 JPG：文件较小，但会再次有损压缩。"
        )
        png_button = format_box.addButton("无损 PNG（推荐）", QMessageBox.ButtonRole.AcceptRole)
        jpg_button = format_box.addButton("高质量 JPG", QMessageBox.ButtonRole.ActionRole)
        cancel_button = format_box.addButton("取消", QMessageBox.ButtonRole.RejectRole)
        format_box.exec()
        if format_box.clickedButton() == cancel_button:
            return
        image_format = "JPEG" if format_box.clickedButton() == jpg_button else "PNG"
        self.service.update_config(video_image_format=image_format)
        progress = QProgressDialog("准备解码视频…", "取消", 0, len(projects), self)
        progress.setWindowTitle("视频 B 帧批量保存")
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)
        success = failed = 0
        self._set_busy(True, "正在批量读取视频 B 帧…")
        for index, project in enumerate(projects):
            if progress.wasCanceled():
                break
            progress.setLabelText(f"{index + 1}/{len(projects)}  {project.title}")
            progress.setValue(index)
            QApplication.processEvents()
            result = extract_video_fractions(Path(project.content_path), [0.5], 20000)
            if result.error or not result.frames:
                failed += 1
                continue
            try:
                save_qimage(
                    result.frames[0],
                    self.service.export_dir,
                    f"{project.safe_title}_候选B_{format_time(result.positions_ms[0])}",
                    image_format,
                    self.service,
                    project,
                    project.content_path,
                    f"视频批量 B 候选帧，位置 {format_time(result.positions_ms[0]).replace('-', ':')}。",
                )
                success += 1
            except OSError:
                failed += 1
        progress.setValue(len(projects))
        self.history_page.set_records(self.service.history)
        self._set_busy(False, f"视频批量完成：成功 {success}，失败 {failed}")
        self.show_toast(f"视频批量完成：保存 {success}，失败 {failed}，未处理 {len(projects) - success - failed}", duplicate=bool(failed))

    def export_direct_batch(self, projects: list[WorkshopProject]) -> None:
        if not projects:
            QMessageBox.information(self, "没有直接/场景项目", "请先勾选图片、Scene 或 Web 项目。")
            return
        direct = [project for project in projects if project.is_direct_image]
        composited = [project for project in projects if project.is_composited]
        unsupported = len(projects) - len(direct) - len(composited)
        if composited:
            answer = QMessageBox.warning(
                self,
                "将连续切换桌面壁纸",
                f"其中 {len(composited)} 个 Scene/Web 项目必须逐个应用到桌面。程序优先读取新快照；若 Wallpaper Engine 未生成快照，会短暂显示纯桌面并抓取实际渲染帧。\n\n"
                "过程中桌面会连续变化；程序结束或取消后会尝试恢复原壁纸。请保持 Wallpaper Engine 正常运行。\n\n是否继续？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        controller = self._controller_or_warn() if composited else None
        if composited and controller is None:
            return
        progress = QProgressDialog("准备保存…", "取消", 0, len(direct) + len(composited), self)
        progress.setWindowTitle("直接 / Scene 高画质保存")
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)
        progress.setMinimumSize(680, 170)
        progress_label = progress.findChild(QLabel)
        if progress_label:
            progress_label.setWordWrap(True)
            progress_label.setMinimumWidth(540)
        success = failed = skipped = 0
        failure_messages: list[str] = []
        original_wallpaper = controller.current_wallpaper_file() if controller else ""
        self._set_busy(True, "正在处理直接/场景项目…")
        current_index = 0
        for project in direct:
            if progress.wasCanceled():
                break
            progress.setLabelText(f"复制原始图片：{project.title}")
            progress.setValue(current_index)
            current_index += 1
            QApplication.processEvents()
            candidate = self.service.inspect_image(Path(project.content_path), "Workshop 原始静态图")
            if not candidate:
                failed += 1
                continue
            record = self.service.export_candidate(
                candidate,
                preferred_stem=project_export_stem(self.service.export_dir, project, candidate.extension),
                original_title=project.title,
                workshop_id=project.workshop_id,
                project_path=project.project_json or project.project_dir,
            )
            success += record.status == "success"
            skipped += record.status == "duplicate"
            failed += record.status == "failed"

        try:
            if not progress.wasCanceled() and controller:
                for project in composited:
                    if progress.wasCanceled():
                        break
                    progress.setLabelText(f"应用并等待桌面快照：{project.title}")
                    progress.setValue(current_index)
                    current_index += 1
                    QApplication.processEvents()
                    before = self.service.current_wallpaper()
                    before_hash = before.content_hash if before else ""
                    before_modified = before.modified_at if before else ""
                    try:
                        controller.apply_project(project)
                    except OSError as exc:
                        failed += 1
                        failure_messages.append(f"{project.title}：切换失败，{exc}")
                        continue
                    applied_at = time.monotonic()
                    deadline = applied_at + 8.0
                    captured = None
                    while time.monotonic() < deadline and not progress.wasCanceled():
                        QApplication.processEvents()
                        candidate = self.service.current_wallpaper()
                        selected_file = controller.current_wallpaper_file()
                        selected_matches = project.workshop_id in selected_file
                        changed = candidate and (
                            candidate.content_hash != before_hash or candidate.modified_at != before_modified
                        )
                        if candidate and selected_matches and changed:
                            captured = candidate
                            break
                        if selected_matches and time.monotonic() - applied_at >= 2.5:
                            progress.setLabelText(f"抓取桌面实际渲染帧：{project.title}")
                            QApplication.processEvents()
                            captured = capture_rendered_desktop(self.service)
                            break
                        time.sleep(0.25)
                    if captured is None:
                        failed += 1
                        failure_messages.append(f"{project.title}：未确认桌面切换或无法抓取渲染帧")
                        continue
                    record = self.service.export_candidate(
                        captured,
                        preferred_stem=project_export_stem(self.service.export_dir, project, captured.extension),
                        original_title=project.title,
                        workshop_id=project.workshop_id,
                        project_path=project.project_json or project.project_dir,
                    )
                    success += record.status == "success"
                    skipped += record.status == "duplicate"
                    failed += record.status == "failed"
        finally:
            if controller and original_wallpaper:
                try:
                    controller.open_file(original_wallpaper)
                except OSError:
                    self.status.setText("任务结束，但自动恢复原壁纸失败，请在 Wallpaper Engine 中手动恢复。")

        progress.setValue(progress.maximum())
        self.history_page.set_records(self.service.history)
        self._set_busy(False, f"直接/场景处理完成：保存 {success}，重复 {skipped}，失败 {failed}")
        self.show_toast(
            f"直接/场景处理完成：保存 {success}，重复 {skipped}，失败 {failed}，不支持 {unsupported}",
            duplicate=bool(failed or skipped),
        )
        if failure_messages:
            details = "\n".join(failure_messages[:6])
            QMessageBox.warning(self, "部分壁纸保存失败", f"以下项目没有保存成功：\n\n{details}")

    def _controller_or_warn(self, silent: bool = False) -> WallpaperEngineController | None:
        engine = discover_engine_dir(str(self.service.config.get("wallpaper_engine_dir", "")))
        if not engine:
            if not silent:
                QMessageBox.warning(self, "未找到 Wallpaper Engine", "没有找到 wallpaper64.exe / wallpaper32.exe。")
            return None
        if self.engine_controller is None or self.engine_controller.engine_dir != engine:
            self.engine_controller = WallpaperEngineController(engine)
            self.service.update_config(wallpaper_engine_dir=str(engine))
        return self.engine_controller

    def _set_busy(self, busy: bool, status: str) -> None:
        self.status.setText(status)
        self.progress.setVisible(busy)
        if busy:
            self.progress.setRange(0, 0)
        else:
            self.progress.setRange(0, 1)
            self.progress.setValue(1)

    def choose_export_dir(self) -> None:
        selected = QFileDialog.getExistingDirectory(self, "选择壁纸保存文件夹", str(self.service.export_dir))
        if selected:
            self.service.update_config(export_dir=selected)
            self.current_page.path.setText(selected)
            self.settings_page.export_path.setText(selected)
            self.status.setText(f"保存位置已更新：{selected}")

    def choose_themes_dir(self) -> None:
        selected = QFileDialog.getExistingDirectory(self, "选择 Windows Themes 文件夹", str(self.service.themes_dir))
        if selected:
            self.settings_page.themes_path.setText(selected)

    def choose_workshop_dir(self) -> None:
        initial = str(self.service.config.get("workshop_dir", "")) or str(Path.home())
        selected = QFileDialog.getExistingDirectory(self, "选择 Steam Workshop 的 431960 文件夹", initial)
        if selected:
            self.settings_page.workshop_path.setText(selected)

    def choose_engine_dir(self) -> None:
        initial = str(self.service.config.get("wallpaper_engine_dir", "")) or str(Path.home())
        selected = QFileDialog.getExistingDirectory(self, "选择 Wallpaper Engine 安装文件夹", initial)
        if selected:
            self.settings_page.engine_path.setText(selected)

    def export_current(self) -> None:
        self.refresh_all()
        if not self.current_candidate:
            if self.current_project:
                self.show_toast("没有可用快照，正在抓取当前桌面渲染帧。")
                QApplication.processEvents()
                self._capture_and_export_project(self.current_project)
                return
            QMessageBox.warning(self, "没有可导出的画面", "未找到有效快照，也无法识别 Wallpaper Engine 当前项目。")
            return
        if self.current_snapshot_stale and self.current_project:
            if self.current_project.is_direct_image:
                candidate = self.service.inspect_image(Path(self.current_project.content_path), "Workshop 原始静态图")
                if candidate:
                    record = self.service.export_candidate(
                        candidate,
                        preferred_stem=project_export_stem(self.service.export_dir, self.current_project, candidate.extension),
                        original_title=self.current_project.title,
                        workshop_id=self.current_project.workshop_id,
                        project_path=self.current_project.project_json or self.current_project.project_dir,
                    )
                    self._show_export_result(record)
                    return
            if self.current_project.is_video:
                self.show_toast("当前桌面快照已经过期，已打开原始视频选帧器，不会保存旧快照。", duplicate=True)
                QTimer.singleShot(120, lambda: self.open_video_picker(self.current_project))
                return
            self.show_toast("Wallpaper Engine 未生成新快照，正在抓取当前桌面渲染帧。")
            QApplication.processEvents()
            self._capture_and_export_project(self.current_project)
            return
        record = self._export_current_named(self.current_candidate)
        self._show_export_result(record)

    def _capture_and_export_project(self, project: WorkshopProject) -> ExportRecord | None:
        candidate = capture_rendered_desktop(self.service)
        if candidate is None:
            QMessageBox.warning(self, "桌面帧保存失败", "无法读取 Wallpaper Engine 当前桌面渲染帧，所有桌面窗口已恢复。")
            return None
        self.current_rendered_candidate = candidate
        self.current_rendered_project_key = project.workshop_id
        self.current_candidate = candidate
        self.current_snapshot_stale = False
        self.current_page.show_candidate(candidate, project.title)
        record = self.service.export_candidate(
            candidate,
            preferred_stem=project_export_stem(self.service.export_dir, project, ".png"),
            original_title=project.title,
            workshop_id=project.workshop_id if project.workshop_id.isdigit() else "",
            project_path=project.project_json or project.project_dir,
        )
        self._show_export_result(record)
        return record

    def export_batch(self) -> None:
        selected = self.batch_page.selected_candidates()
        if not selected:
            QMessageBox.information(self, "未选择图片", "请先勾选至少一张图片。")
            return
        records = self.service.export_many(selected)
        success = sum(record.status == "success" for record in records)
        duplicate = sum(record.status == "duplicate" for record in records)
        failed = sum(record.status == "failed" for record in records)
        self.history_page.set_records(self.service.history)
        self.status.setText(f"批量完成：保存 {success}，跳过重复 {duplicate}，失败 {failed}")
        self.show_toast(f"Themes 批量完成：保存 {success}，跳过重复 {duplicate}，失败 {failed}", duplicate=bool(duplicate or failed))

    def monitor_current(self) -> None:
        if not self.service.config.get("monitor_enabled", False):
            return
        candidate = self.service.current_wallpaper()
        if candidate is None:
            return
        changed = self.current_candidate is None or candidate.content_hash != self.current_candidate.content_hash
        self.current_candidate = candidate
        if changed:
            self.refresh_all()
            if self.current_snapshot_stale:
                self.show_toast("检测到项目已切换，但新快照尚未生成，自动保存已跳过旧图。", duplicate=True)
                return
            record = self._export_current_named(candidate)
            if record and record.status == "success":
                self.history_page.set_records(self.service.history)
                self.show_toast(f"自动保存成功：{record.original_title or '当前壁纸'} · {candidate.resolution}")

    def save_settings(
        self, export_path: str, themes_path: str, workshop_path: str, engine_path: str, monitor: bool,
        save_hotkey: str, next_hotkey: str, previous_hotkey: str,
    ) -> None:
        export = Path(export_path).expanduser()
        themes = Path(themes_path).expanduser()
        workshop = Path(workshop_path).expanduser()
        engine = Path(engine_path).expanduser()
        if not themes.is_dir():
            QMessageBox.warning(self, "源目录无效", "请选择真实存在的 Windows Themes 文件夹。")
            return
        if not workshop.is_dir():
            QMessageBox.warning(self, "Workshop 目录无效", "请选择真实存在的 431960 Workshop 文件夹。")
            return
        if not (engine / "wallpaper64.exe").is_file() and not (engine / "wallpaper32.exe").is_file():
            QMessageBox.warning(self, "Wallpaper Engine 目录无效", "所选目录中没有 wallpaper64.exe 或 wallpaper32.exe。")
            return
        try:
            export.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            QMessageBox.warning(self, "保存目录不可用", str(exc))
            return
        self.service.update_config(
            export_dir=str(export), themes_dir=str(themes), workshop_dir=str(workshop), wallpaper_engine_dir=str(engine),
            monitor_enabled=monitor, monitor_user_set=True, hotkey_save=save_hotkey,
            hotkey_next=next_hotkey, hotkey_previous=previous_hotkey,
        )
        self.engine_controller = WallpaperEngineController(engine)
        self.workshop_projects = []
        self.current_page.path.setText(str(export))
        self.monitor_toggle.blockSignals(True)
        self.monitor_toggle.setChecked(monitor)
        self.monitor_toggle.setText("自动保存：开" if monitor else "自动保存：关")
        self.monitor_toggle.blockSignals(False)
        self.hotkeys.clear()
        self._configure_hotkeys()
        self.refresh_all()
        self.show_toast("设置与桌面快捷键已保存。")

    def set_monitor_enabled(self, enabled: bool) -> None:
        self.service.update_config(monitor_enabled=enabled, monitor_user_set=True)
        self.settings_page.monitor.blockSignals(True)
        self.settings_page.monitor.setChecked(enabled)
        self.settings_page.monitor.blockSignals(False)
        self.monitor_toggle.blockSignals(True)
        self.monitor_toggle.setChecked(enabled)
        self.monitor_toggle.setText("自动保存：开" if enabled else "自动保存：关")
        self.monitor_toggle.blockSignals(False)
        self.status.setText("自动保存已开启：新桌面快照会写入当前目录" if enabled else "自动保存已关闭：只在点击按钮时保存")

    def clear_history(self) -> None:
        answer = QMessageBox.question(
            self,
            "只清除程序记录？",
            "这只会清除本程序的历史记录，不会删除已经导出的任何图片。\n\n确定继续吗？",
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.service.clear_history_records()
            self.history_page.set_records([])
            self.status.setText("历史记录已清除，图片文件保持不变")

    def export_filtered_history(self) -> None:
        records = self.history_page.filtered_success_records()
        if not records:
            QMessageBox.information(self, "没有匹配图片", "所选发现日期范围内没有可另存的成功归档图片。")
            return
        selected = QFileDialog.getExistingDirectory(self, "选择筛选结果的保存文件夹", str(self.service.export_dir))
        if not selected:
            return
        candidates = []
        unavailable = 0
        for record in records:
            source = Path(record.target_path)
            if not source.is_file():
                source = Path(record.source_path)
            candidate = self.service.inspect_image(source, "历史归档")
            if candidate and candidate.content_hash == record.content_hash:
                candidates.append(candidate)
            else:
                unavailable += 1
        results = self.service.export_many(candidates, Path(selected))
        success = sum(item.status == "success" for item in results)
        duplicate = sum(item.status == "duplicate" for item in results)
        self.history_page.set_records(self.service.history)
        self.status.setText(f"日期筛选另存完成：保存 {success}，重复 {duplicate}，不可用 {unavailable}")
        self.show_toast(f"筛选另存完成：保存 {success}，重复 {duplicate}，不可用 {unavailable}", duplicate=bool(duplicate or unavailable))

    def open_record_path(self, path_text: str) -> None:
        path = Path(path_text)
        if path.is_file():
            open_path(path.parent)
        else:
            QMessageBox.information(self, "文件不可用", "记录中的目标文件当前不存在，但程序不会自动删除或修复它。")

    def _show_export_result(self, record: ExportRecord) -> None:
        self.history_page.set_records(self.service.history)
        if record.status == "success":
            self.show_toast(f"保存成功：{record.original_title or Path(record.target_path).stem} · {record.width}×{record.height}")
        elif record.status == "duplicate":
            self.show_toast("内容完全相同，已自动跳过，不会产生重复文件。", duplicate=True)
        else:
            self.status.setText(f"导出失败：{record.message}")
            QMessageBox.warning(self, "导出失败", record.message)

    def _current_workshop_project(self) -> WorkshopProject | None:
        controller = self._controller_or_warn(silent=True)
        if controller is None:
            return None
        current = controller.current_wallpaper_file().casefold()
        if not current:
            return None
        direct = scan_project_from_source(current)
        if direct:
            return direct
        if not self.workshop_projects and not self._workshop_scan_started:
            self.scan_workshop()
        return next((project for project in self.workshop_projects if project.workshop_id in current), None)

    def _export_current_named(self, candidate: WallpaperCandidate | None) -> ExportRecord | None:
        if candidate is None:
            return None
        project = self._current_workshop_project()
        if project is None:
            return self.service.export_candidate(candidate)
        return self.service.export_candidate(
            candidate,
            preferred_stem=project_export_stem(self.service.export_dir, project, candidate.extension),
            original_title=project.title,
            workshop_id=project.workshop_id,
            project_path=project.project_json or project.project_dir,
        )

    def show_toast(self, message: str, duplicate: bool = False) -> None:
        self._toast_message = message
        background = "#EDF8FC" if duplicate else "#E8F7EF"
        color = "#537985" if duplicate else "#3E775A"
        self.status.setStyleSheet(f"background:{background};color:{color};padding:5px 10px;border-radius:8px;")
        self.status.setText(message)
        self.toast_timer.start(4200)

    def _clear_toast(self) -> None:
        if self.status.text() == self._toast_message:
            self.status.setText("准备就绪")
            self.status.setStyleSheet("")
        self._toast_message = ""

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape and self.active_preview_names:
            self.close_dynamic_previews()
            return
        super().keyPressEvent(event)

    def closeEvent(self, event) -> None:
        self.close_dynamic_previews(silent=True)
        self.hotkeys.close()
        super().closeEvent(event)

    def _apply_style(self) -> None:
        QApplication.instance().setFont(QFont("Microsoft YaHei", 10))
        self.setStyleSheet(
            """
            QMainWindow, QWidget#content { background: #FFF9FC; color: #44536B; }
            QFrame#sidebar { background: #F7D7E2; border-right: 1px solid #EFC4D4; }
            QLabel#brand { font-size: 17px; font-weight: 700; color: #714E67; }
            QLabel#mutedOnPink { color: #9B7189; font-size: 12px; }
            QLabel#heading { font-size: 22px; font-weight: 700; color: #523F55; }
            QLabel#pageTitle { font-size: 18px; font-weight: 700; color: #59465A; }
            QLabel#muted { color: #8A7C8A; }
            QLabel#monitorBadge { background: #E0F4F7; color: #377B86; padding: 8px 14px; border-radius: 14px; }
            QCheckBox#monitorToggle { background: #E0F4F7; color: #377B86; padding: 8px 12px; border-radius: 14px; font-weight: 600; }
            QCheckBox#monitorToggle::indicator { width: 15px; height: 15px; border: 1px solid #84C5D0; border-radius: 4px; background: #FFFFFF; }
            QCheckBox#monitorToggle::indicator:checked { background: #58B7C7; border: 3px solid #DDF3F7; }
            QLabel#qualityNote { background: #EDF8FC; color: #537985; padding: 10px 14px; border: 1px solid #D3EDF5; border-radius: 10px; }
            QLabel#sideBadge { color: #8D6079; padding: 3px; font-size: 11px; }
            QFrame#infoPill { background: #FFFFFF; border: 1px solid #F0DDE6; border-radius: 14px; }
            QLabel#pillValue { color: #584657; font-size: 13px; font-weight: 600; }
            QFrame#settingsCard { background: #FFFFFF; border: 1px solid #F0DDE6; border-radius: 18px; }
            QFrame#projectCard { background: #FFFFFF; border: 1px solid #EFDDE6; border-radius: 14px; }
            QFrame#candidateFrame { background: #FFFFFF; border: 1px solid #EFDDE6; border-radius: 12px; }
            QLabel#typeBadge { background: #E8F6FA; color: #4F7B88; padding: 3px 8px; border-radius: 8px; font-size: 11px; }
            QLabel#cardTitle { color: #5D4959; font-weight: 600; }
            QPushButton#cardButton { padding: 5px 3px; }
            QListWidget#navigation { background: transparent; border: none; outline: none; font-size: 14px; color: #76596B; }
            QListWidget#navigation::item { padding: 7px 6px; margin: 1px 0; border-radius: 10px; text-align: center; }
            QListWidget#navigation::item:selected { background: #FFFFFF; color: #D06F98; font-weight: 700; }
            QListWidget#navigation::item:hover { background: rgba(255,255,255,120); }
            QPushButton { background: #FFFFFF; color: #76566B; border: 1px solid #EBCEDA; border-radius: 10px; padding: 7px 11px; font-weight: 600; }
            QPushButton:hover { background: #FFF2F7; border-color: #E5AFC4; }
            QPushButton:pressed { background: #F8E3EC; }
            QPushButton#primaryButton { background: #E88EAF; color: #FFFFFF; border: none; padding: 11px 20px; }
            QPushButton#primaryButton:hover { background: #DD7EA3; }
            QPushButton#secondaryButton { background: #F1F9FC; color: #557784; border-color: #CFE8F0; }
            QLineEdit, QDateEdit, QKeySequenceEdit { background: #FFFFFF; border: 1px solid #E8D6DF; border-radius: 9px; padding: 7px 9px; selection-background-color: #E9A8C1; }
            QTableWidget, QListWidget { background: #FFFFFF; alternate-background-color: #FFF8FB; border: 1px solid #EFDFE7; border-radius: 12px; gridline-color: #F2E7EC; }
            QHeaderView::section { background: #F7EEF3; color: #745E6C; border: none; border-bottom: 1px solid #EAD8E1; padding: 9px; font-weight: 600; }
            QProgressBar { background: #F3E7ED; border: none; border-radius: 4px; height: 7px; }
            QProgressBar::chunk { background: #9EDCE9; border-radius: 4px; }
            QCheckBox { spacing: 8px; }
            QScrollBar:vertical { width: 10px; background: transparent; }
            QScrollBar::handle:vertical { background: #E6C4D3; border-radius: 5px; min-height: 28px; }
            """
        )

    @staticmethod
    def _load_windows_chinese_font() -> None:
        if sys.platform != "win32":
            return
        font_path = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts" / "msyh.ttc"
        if font_path.is_file():
            QFontDatabase.addApplicationFont(str(font_path))


def run() -> int:
    if sys.platform == "win32":
        enable_per_monitor_dpi()
        try:
            import ctypes

            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("SakuraSea.WallpaperExporter.1")
        except (AttributeError, OSError):
            pass
    app = QApplication(sys.argv)
    app.setApplicationName("樱海壁纸收藏夹")
    app.setOrganizationName("Local")
    if os.environ.get("WALLPAPER_EXPORTER_CAPTURE_SMOKE") == "1":
        return 0 if capture_rendered_desktop(WallpaperService()) else 4
    video_smoke = os.environ.get("WALLPAPER_EXPORTER_VIDEO_SMOKE", "")
    if video_smoke:
        result = extract_video_fractions(Path(video_smoke), [0.5], 30000)
        output = os.environ.get("WALLPAPER_EXPORTER_VIDEO_SMOKE_OUT", "")
        if result.error or not result.frames or not output:
            return 2
        return 0 if result.frames[0].save(output, "PNG") else 3
    window = MainWindow()
    window.show()
    if os.environ.get("WALLPAPER_EXPORTER_SMOKE_TEST") == "1":
        QTimer.singleShot(1800, app.quit)
    return app.exec()
