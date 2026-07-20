from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QImageReader, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from .workshop import WorkshopProject


_THUMBNAIL_CACHE: dict[tuple[str, int, int], QPixmap] = {}


def thumbnail_pixmap(path: str, size: QSize) -> QPixmap:
    if not path:
        return QPixmap()
    key = (path, size.width(), size.height())
    cached = _THUMBNAIL_CACHE.get(key)
    if cached is not None:
        return QPixmap(cached)
    reader = QImageReader(path)
    reader.setAutoTransform(True)
    original = reader.size()
    if original.isValid():
        original.scale(size, Qt.AspectRatioMode.KeepAspectRatioByExpanding)
        reader.setScaledSize(original)
    image = reader.read()
    if image.isNull():
        return QPixmap()
    pixmap = QPixmap.fromImage(image).scaled(
        size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
    )
    _THUMBNAIL_CACHE[key] = QPixmap(pixmap)
    if len(_THUMBNAIL_CACHE) > 600:
        for stale in list(_THUMBNAIL_CACHE)[:150]:
            _THUMBNAIL_CACHE.pop(stale, None)
    return pixmap


class ResponsiveScrollArea(QScrollArea):
    resized = Signal()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.resized.emit()


class ProjectCard(QFrame):
    selection_changed = Signal(str, bool)
    video_requested = Signal(object)
    play_requested = Signal(object)
    manage_requested = Signal(object)

    def __init__(self, project: WorkshopProject, selected: bool = False, card_width: int = 180, parent=None) -> None:
        super().__init__(parent)
        self.project = project
        self.setObjectName("projectCard")
        self.setFixedWidth(card_width)
        root = QVBoxLayout(self)
        root.setContentsMargins(9, 9, 9, 10)
        root.setSpacing(7)

        top = QHBoxLayout()
        self.check = QCheckBox()
        self.check.setChecked(selected)
        type_names = {"video": "视频", "scene": "Scene", "web": "网页", "image": "图片", "unknown": "未知"}
        badge = QLabel(type_names.get(project.project_type, project.project_type or "未知"))
        badge.setObjectName("typeBadge")
        top.addWidget(self.check)
        top.addStretch()
        top.addWidget(badge)
        root.addLayout(top)

        self.preview = QLabel("没有预览图")
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        preview_width = max(72, card_width - 18)
        preview_height = max(54, round(preview_width * 9 / 16))
        self.preview.setFixedSize(preview_width, preview_height)
        self.preview.setStyleSheet("background:#F1E7ED;border-radius:10px;color:#8A7C8A;")
        pixmap = thumbnail_pixmap(project.preview_path, QSize(preview_width, preview_height))
        if not pixmap.isNull():
            self.preview.setPixmap(pixmap)
        root.addWidget(self.preview)

        title = QLabel(project.title)
        title.setWordWrap(True)
        title.setToolTip(project.title)
        title.setMinimumHeight(42)
        title.setMaximumHeight(72)
        title.setObjectName("cardTitle")
        root.addWidget(title)
        info = QLabel(f"ID {project.workshop_id}")
        info.setObjectName("muted")
        root.addWidget(info)

        if project.is_video:
            action_text = "选帧" if card_width < 135 else ("三候选 / 精调" if card_width < 190 else "三候选 / 精细选帧")
        else:
            action_text = "播放" if card_width < 135 else ("动态播放" if card_width < 190 else "在 Wallpaper Engine 中播放")
        action = QPushButton(action_text)
        action.setObjectName("cardButton")
        if project.is_video:
            action.clicked.connect(lambda: self.video_requested.emit(self.project))
        elif project.is_composited:
            action.clicked.connect(lambda: self.play_requested.emit(self.project))
        else:
            action.setText("直接保存" if card_width < 190 else "可加入直接保存")
            action.setEnabled(project.is_direct_image)
        actions = QHBoxLayout()
        actions.setSpacing(5)
        actions.addWidget(action, 1)
        manage = QPushButton("Steam 管理")
        manage.setObjectName("cardButton")
        manage.setToolTip("打开该项目的 Steam Workshop 页面，可在页面中取消订阅")
        manage.clicked.connect(lambda: self.manage_requested.emit(self.project))
        if card_width < 150:
            manage.setText("管理")
        actions.addWidget(manage)
        root.addLayout(actions)
        self.check.toggled.connect(lambda checked: self.selection_changed.emit(project.workshop_id, checked))


class WorkshopPage(QWidget):
    scan_requested = Signal()
    video_requested = Signal(object)
    play_requested = Signal(object)
    close_preview_requested = Signal()
    direct_batch_requested = Signal(list)
    video_batch_requested = Signal(list)
    manage_requested = Signal(object)
    load_progress_changed = Signal(int, int)

    PAGE_SIZE = 48

    def __init__(self) -> None:
        super().__init__()
        self.projects: list[WorkshopProject] = []
        self.filtered: list[WorkshopProject] = []
        self.selected_ids: set[str] = set()
        self.visible_count = 0
        self.cards: list[ProjectCard] = []
        self.zoom_level = 0
        self._last_layout = (0, 0)
        self._rebuilding = False
        self._resize_timer = QTimer(self)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.setInterval(160)
        self._resize_timer.timeout.connect(self._responsive_rebuild_now)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)

        title_row = QHBoxLayout()
        title = QLabel("Wallpaper 库")
        title.setObjectName("pageTitle")
        self.summary = QLabel("尚未扫描")
        self.summary.setObjectName("muted")
        refresh = QPushButton("重新扫描")
        refresh.clicked.connect(self.scan_requested)
        close_preview = QPushButton("关闭动态预览（Esc）")
        close_preview.setObjectName("secondaryButton")
        close_preview.clicked.connect(self.close_preview_requested)
        title_row.addWidget(title)
        title_row.addWidget(self.summary)
        title_row.addStretch()
        title_row.addWidget(close_preview)
        title_row.addWidget(refresh)
        root.addLayout(title_row)

        filters = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("搜索 Wallpaper 原始名称或 Workshop ID")
        self.type_filter = QComboBox()
        for label, value in (("全部类型", "all"), ("视频", "video"), ("Scene", "scene"), ("网页", "web"), ("图片", "image"), ("未知", "unknown")):
            self.type_filter.addItem(label, value)
        filters.addWidget(self.search, 1)
        filters.addWidget(self.type_filter)
        root.addLayout(filters)

        tools = QHBoxLayout()
        select_all = QPushButton("全选当前结果")
        clear = QPushButton("清空选择")
        zoom_out = QPushButton("− 缩小")
        zoom_out.setMinimumWidth(74)
        zoom_out.setToolTip("缩小缩略图，每行显示更多壁纸")
        zoom_in = QPushButton("＋ 放大")
        zoom_in.setMinimumWidth(74)
        zoom_in.setToolTip("放大缩略图，显示更完整的大图")
        self.zoom_label = QLabel("缩略图：紧凑")
        self.zoom_label.setObjectName("muted")
        zoom_out.clicked.connect(lambda: self.change_zoom(-1))
        zoom_in.clicked.connect(lambda: self.change_zoom(1))
        select_all.clicked.connect(self.select_all_filtered)
        clear.clicked.connect(self.clear_selection)
        tools.addWidget(select_all)
        tools.addWidget(clear)
        tools.addStretch()
        tools.addWidget(zoom_out)
        tools.addWidget(self.zoom_label)
        tools.addWidget(zoom_in)
        root.addLayout(tools)

        note = QLabel("图库使用项目预览图帮助识别，但最终保存不会使用低清预览图：视频从原 MP4 解码，Scene/Web 通过桌面合成快照。")
        note.setWordWrap(True)
        note.setObjectName("qualityNote")
        root.addWidget(note)

        self.scroll = ResponsiveScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.grid_host = QWidget()
        self.grid = QGridLayout(self.grid_host)
        self.grid.setContentsMargins(0, 0, 6, 0)
        self.grid.setSpacing(8)
        self.grid.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.scroll.setWidget(self.grid_host)
        root.addWidget(self.scroll, 1)

        self.load_progress = QProgressBar()
        self.load_progress.setTextVisible(True)
        self.load_progress.setFormat("已加载 %v / %m")
        self.load_progress.setMinimumHeight(16)
        root.addWidget(self.load_progress)

        bottom = QHBoxLayout()
        self.selection_label = QLabel("已选择 0 项")
        self.selection_label.setObjectName("muted")
        direct = QPushButton("保存勾选的直接 / Scene 类")
        direct.setObjectName("secondaryButton")
        videos = QPushButton("视频按 B 中间帧批量保存")
        videos.setObjectName("primaryButton")
        direct.clicked.connect(self._emit_direct)
        videos.clicked.connect(self._emit_videos)
        bottom.addWidget(self.selection_label)
        bottom.addStretch()
        bottom.addWidget(direct)
        bottom.addWidget(videos)
        root.addLayout(bottom)

        self.search.textChanged.connect(self.apply_filter)
        self.type_filter.currentIndexChanged.connect(self.apply_filter)
        self.scroll.resized.connect(self._responsive_rebuild)
        self.scroll.verticalScrollBar().valueChanged.connect(self._auto_load_at_bottom)

    def set_projects(self, projects: list[WorkshopProject]) -> None:
        _THUMBNAIL_CACHE.clear()
        self.projects = projects
        existing = {project.workshop_id for project in projects}
        self.selected_ids.intersection_update(existing)
        self.apply_filter()

    def apply_filter(self) -> None:
        query = self.search.text().strip().casefold()
        kind = str(self.type_filter.currentData())
        self.filtered = [
            project for project in self.projects
            if (kind == "all" or project.project_type == kind)
            and (not query or query in project.searchable_name)
        ]
        self.visible_count = min(self.PAGE_SIZE, len(self.filtered))
        self._rebuild_cards()

    def show_more(self) -> None:
        self.visible_count = min(len(self.filtered), self.visible_count + self.PAGE_SIZE)
        self._rebuild_cards()

    def change_zoom(self, delta: int) -> None:
        new_level = max(0, min(3, self.zoom_level + delta))
        if new_level == self.zoom_level:
            return
        self.zoom_level = new_level
        self.zoom_label.setText(("缩略图：紧凑", "缩略图：中", "缩略图：大", "缩略图：特大")[new_level])
        self._last_layout = (0, 0)
        self._rebuild_cards()

    def select_all_filtered(self) -> None:
        self.selected_ids.update(project.workshop_id for project in self.filtered)
        self._rebuild_cards()

    def clear_selection(self) -> None:
        self.selected_ids.clear()
        self._rebuild_cards()

    def selected_projects(self) -> list[WorkshopProject]:
        return [project for project in self.projects if project.workshop_id in self.selected_ids]

    def _rebuild_cards(self) -> None:
        if self._rebuilding:
            return
        self._rebuilding = True
        while self.grid.count():
            item = self.grid.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        self.cards.clear()
        columns, card_width = self._layout_metrics()
        for index, project in enumerate(self.filtered[: self.visible_count]):
            card = ProjectCard(project, project.workshop_id in self.selected_ids, card_width)
            card.selection_changed.connect(self._selection_changed)
            card.video_requested.connect(self.video_requested)
            card.play_requested.connect(self.play_requested)
            card.manage_requested.connect(self.manage_requested)
            self.grid.addWidget(card, index // columns, index % columns)
            card.show()
            self.cards.append(card)
        rows = (len(self.cards) + columns - 1) // columns if self.cards else 0
        card_height = max((card.minimumSizeHint().height() for card in self.cards), default=0)
        self.grid_host.setMinimumHeight(rows * card_height + max(0, rows - 1) * self.grid.verticalSpacing())
        type_counts: dict[str, int] = {}
        for project in self.projects:
            type_counts[project.project_type] = type_counts.get(project.project_type, 0) + 1
        self.summary.setText(
            f"{len(self.projects)} 项 · 视频 {type_counts.get('video', 0)} · Scene {type_counts.get('scene', 0)} · Web {type_counts.get('web', 0)}"
        )
        self.selection_label.setText(f"已选择 {len(self.selected_ids)} 项 · 当前显示 {self.visible_count}/{len(self.filtered)}")
        self.load_progress.setRange(0, max(1, len(self.filtered)))
        self.load_progress.setValue(self.visible_count)
        self.load_progress_changed.emit(self.visible_count, len(self.filtered))
        self._last_layout = (columns, card_width)
        self._rebuilding = False

    def _layout_metrics(self) -> tuple[int, int]:
        available = max(320, self.scroll.viewport().width() - 8)
        target_widths = (88, 138, 188, 242)
        max_columns = (8, 6, 5, 4)
        spacing = self.grid.horizontalSpacing()
        columns = max(1, min(max_columns[self.zoom_level], (available + spacing) // (target_widths[self.zoom_level] + spacing)))
        card_width = max(82, (available - spacing * (columns - 1)) // columns)
        return columns, card_width

    def _responsive_rebuild(self) -> None:
        self._resize_timer.start()

    def _responsive_rebuild_now(self) -> None:
        metrics = self._layout_metrics()
        if metrics != self._last_layout and self.projects:
            self._rebuild_cards()

    def _auto_load_at_bottom(self, value: int) -> None:
        bar = self.scroll.verticalScrollBar()
        if self._rebuilding or self.visible_count >= len(self.filtered) or bar.maximum() <= 0:
            return
        if value >= int(bar.maximum() * 0.70):
            self.show_more()

    def _selection_changed(self, workshop_id: str, checked: bool) -> None:
        if checked:
            self.selected_ids.add(workshop_id)
        else:
            self.selected_ids.discard(workshop_id)
        self.selection_label.setText(f"已选择 {len(self.selected_ids)} 项 · 当前显示 {self.visible_count}/{len(self.filtered)}")

    def _emit_direct(self) -> None:
        projects = [project for project in self.selected_projects() if not project.is_video]
        self.direct_batch_requested.emit(projects)

    def _emit_videos(self) -> None:
        projects = [project for project in self.selected_projects() if project.is_video]
        self.video_batch_requested.emit(projects)


class ImagePreviewDialog(QDialog):
    def __init__(self, path: Path, title: str, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(960, 620)
        root = QVBoxLayout(self)
        image = QLabel()
        image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            image.setText("图片无法预览")
        else:
            image.setPixmap(pixmap.scaled(920, 550, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        root.addWidget(image, 1)
        info = QLabel(str(path))
        info.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        info.setObjectName("muted")
        root.addWidget(info)
