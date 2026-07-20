from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QEventLoop, QObject, QTimer, QUrl, Qt, Signal
from PySide6.QtGui import QImage, QKeyEvent, QPixmap
from PySide6.QtMultimedia import QMediaMetaData, QMediaPlayer, QVideoFrame, QVideoSink
from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from .core import WallpaperService, sha256_file
from .workshop import WorkshopProject, project_export_stem, sanitize_title


@dataclass
class FrameExtractionResult:
    duration_ms: int
    frame_rate: float
    frames: list[QImage]
    positions_ms: list[int]
    error: str = ""


def format_time(milliseconds: int) -> str:
    milliseconds = max(0, milliseconds)
    total_seconds, ms = divmod(milliseconds, 1000)
    minutes, seconds = divmod(total_seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours:02d}-{minutes:02d}-{seconds:02d}.{ms:03d}"
    return f"{minutes:02d}-{seconds:02d}.{ms:03d}"


def extract_video_fractions(path: Path, fractions: list[float], timeout_ms: int = 20000) -> FrameExtractionResult:
    """Decode the nearest available frame for each fraction through Qt's FFmpeg backend."""
    if not path.is_file():
        return FrameExtractionResult(0, 0.0, [], [], "视频文件不存在。")
    loop = QEventLoop()
    player = QMediaPlayer()
    sink = QVideoSink()
    player.setVideoOutput(sink)
    result = FrameExtractionResult(0, 0.0, [], [])
    targets: list[int] = []
    index = {"value": 0}
    ready = {"value": False}

    def finish_error(message: str) -> None:
        if not result.error:
            result.error = message
        player.stop()
        loop.quit()

    def seek_current() -> None:
        if index["value"] >= len(targets):
            player.stop()
            loop.quit()
            return
        ready["value"] = True
        player.setPosition(targets[index["value"]])
        player.play()

    def on_duration(duration: int) -> None:
        if duration <= 0 or targets:
            return
        result.duration_ms = duration
        meta = player.metaData().value(QMediaMetaData.Key.VideoFrameRate)
        try:
            result.frame_rate = float(meta or 0.0)
        except (TypeError, ValueError):
            result.frame_rate = 0.0
        targets.extend(max(0, min(duration - 1, round(duration * fraction))) for fraction in fractions)
        QTimer.singleShot(0, seek_current)

    def on_frame(frame: QVideoFrame) -> None:
        if not ready["value"] or not frame.isValid() or index["value"] >= len(targets):
            return
        target = targets[index["value"]]
        tolerance = max(120, round(2000 / result.frame_rate)) if result.frame_rate else 250
        if abs(player.position() - target) > tolerance:
            return
        image = frame.toImage()
        if image.isNull():
            return
        ready["value"] = False
        result.frames.append(image.copy())
        result.positions_ms.append(player.position())
        player.pause()
        index["value"] += 1
        QTimer.singleShot(20, seek_current)

    player.durationChanged.connect(on_duration)
    sink.videoFrameChanged.connect(on_frame)
    player.errorOccurred.connect(lambda error, text: finish_error(text or f"视频解码错误：{error}"))
    timer = QTimer()
    timer.setSingleShot(True)
    timer.timeout.connect(lambda: finish_error("视频帧读取超时。"))
    timer.start(timeout_ms)
    player.setSource(QUrl.fromLocalFile(str(path)))
    player.play()
    loop.exec()
    timer.stop()
    sink.setVideoFrame(QVideoFrame())
    player.deleteLater()
    sink.deleteLater()
    if len(result.frames) != len(fractions) and not result.error:
        result.error = f"只读取到 {len(result.frames)}/{len(fractions)} 张候选帧。"
    return result


def save_qimage(
    image: QImage,
    destination: Path,
    stem: str,
    image_format: str,
    service: WallpaperService,
    project: WorkshopProject,
    source_path: str,
    message: str,
) -> Path:
    fmt = image_format.upper()
    extension = ".png" if fmt == "PNG" else ".jpg"
    clean_stem = sanitize_title(stem)
    target = service.unique_target(
        destination,
        project_export_stem(destination, project, extension, clean_stem[len(project.safe_title):] if clean_stem.startswith(project.safe_title) else f"_{clean_stem}"),
        extension,
    )
    temp = target.with_name(f".{target.stem}.tmp{extension}")
    quality = -1 if fmt == "PNG" else 95
    if not image.save(str(temp), fmt, quality):
        raise OSError("图片编码失败。")
    temp_hash = sha256_file(temp)
    previous = service.previous_export(temp_hash, destination)
    if previous is not None:
        temp.unlink(missing_ok=True)
        return Path(previous.target_path)
    existing = service.find_existing_file(temp_hash, destination, temp.stat().st_size, exclude=temp)
    if existing is not None:
        temp.unlink(missing_ok=True)
        return existing
    temp.replace(target)
    service.register_external_export(
        source_path=source_path,
        target_path=target,
        width=image.width(),
        height=image.height(),
        image_format=fmt,
        original_title=project.title,
        workshop_id=project.workshop_id,
        project_path=project.project_json or project.project_dir,
        message=message,
    )
    return target


class VideoCanvas(QLabel):
    def __init__(self) -> None:
        super().__init__()
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(560, 300)
        self.setStyleSheet("background:#241F28;border-radius:14px;color:white;")
        self._image = QImage()

    def show_image(self, image: QImage) -> None:
        self._image = image.copy()
        pixmap = QPixmap.fromImage(image).scaled(
            self.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
        )
        self.setPixmap(pixmap)

    def resizeEvent(self, event) -> None:
        if not self._image.isNull():
            self.show_image(self._image)
        super().resizeEvent(event)


class CandidateChoice(QFrame):
    chosen = Signal(int)

    def __init__(self, index: int, label: str) -> None:
        super().__init__()
        self.index = index
        self.setObjectName("candidateFrame")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(7, 7, 7, 7)
        self.image = QLabel("读取中…")
        self.image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image.setMinimumSize(170, 96)
        self.image.setStyleSheet("background:#F3E8EE;border-radius:8px;")
        self.radio = QRadioButton(label)
        layout.addWidget(self.image)
        layout.addWidget(self.radio, alignment=Qt.AlignmentFlag.AlignCenter)
        self.radio.clicked.connect(lambda: self.chosen.emit(self.index))

    def set_frame(self, image: QImage, time_text: str) -> None:
        pixmap = QPixmap.fromImage(image).scaled(
            200, 112, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
        )
        self.image.setPixmap(pixmap)
        self.radio.setText(f"{self.radio.text().split(' · ')[0]} · {time_text}")

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.radio.setChecked(True)
            self.chosen.emit(self.index)
        super().mouseReleaseEvent(event)


class VideoFrameDialog(QDialog):
    def __init__(self, project: WorkshopProject, service: WallpaperService, parent=None) -> None:
        super().__init__(parent)
        self.project = project
        self.service = service
        self.player = QMediaPlayer(self)
        self.sink = QVideoSink(self)
        self.player.setVideoOutput(self.sink)
        self.current_image = QImage()
        self.candidate_images: list[QImage] = []
        self.candidate_positions: list[int] = []
        self.frame_rate = 0.0
        self._slider_dragging = False
        self._pending_pause = False
        self._toast_timer = QTimer(self)
        self._toast_timer.setSingleShot(True)
        self._toast_timer.timeout.connect(self._clear_toast)
        self.setWindowTitle(f"视频选帧 · {project.title}")
        self.resize(900, 720)
        self.setMinimumSize(760, 620)
        self._build_ui()
        self._wire()
        QTimer.singleShot(0, self._load)

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        title = QLabel(self.project.title)
        title.setObjectName("pageTitle")
        subtitle = QLabel(f"Workshop ID: {self.project.workshop_id} · 左右键 1 帧 · Shift+左右键 10 帧 · 空格播放/暂停")
        subtitle.setObjectName("muted")
        root.addWidget(title)
        root.addWidget(subtitle)

        self.canvas = VideoCanvas()
        root.addWidget(self.canvas, 1)
        time_row = QHBoxLayout()
        self.play_button = QPushButton("播放")
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, 0)
        self.time_label = QLabel("00:00.000 / 00:00.000")
        time_row.addWidget(self.play_button)
        time_row.addWidget(self.slider, 1)
        time_row.addWidget(self.time_label)
        root.addLayout(time_row)

        step_row = QHBoxLayout()
        back10 = QPushButton("后退 10 帧")
        back1 = QPushButton("后退 1 帧")
        forward1 = QPushButton("前进 1 帧")
        forward10 = QPushButton("前进 10 帧")
        back10.clicked.connect(lambda: self.step_frames(-10))
        back1.clicked.connect(lambda: self.step_frames(-1))
        forward1.clicked.connect(lambda: self.step_frames(1))
        forward10.clicked.connect(lambda: self.step_frames(10))
        for button in (back10, back1, forward1, forward10):
            step_row.addWidget(button)
        step_row.addStretch()
        self.frame_info = QLabel("等待视频信息…")
        step_row.addWidget(self.frame_info)
        root.addLayout(step_row)

        candidates = QHBoxLayout()
        self.choice_group = QButtonGroup(self)
        self.choices = []
        for index, text in enumerate(("A · 25%", "B · 50%", "C · 75%")):
            choice = CandidateChoice(index, text)
            choice.chosen.connect(self.choose_candidate)
            self.choice_group.addButton(choice.radio, index)
            self.choices.append(choice)
            candidates.addWidget(choice)
        self.choices[1].radio.setChecked(True)
        root.addLayout(candidates)

        save_row = QHBoxLayout()
        save_row.addWidget(QLabel("保存格式"))
        self.format_png = QRadioButton("无损 PNG（推荐，不再次压缩）")
        self.format_jpg = QRadioButton("高质量 JPG（较小，会再次有损压缩）")
        self.format_group = QButtonGroup(self)
        self.format_group.addButton(self.format_png)
        self.format_group.addButton(self.format_jpg)
        if self.service.config.get("video_image_format") == "JPEG":
            self.format_jpg.setChecked(True)
        else:
            self.format_png.setChecked(True)
        save_row.addWidget(self.format_png)
        save_row.addWidget(self.format_jpg)
        save_row.addStretch()
        save_candidate = QPushButton("保存选中的 A/B/C")
        save_current = QPushButton("保存当前精调帧")
        save_current.setObjectName("primaryButton")
        save_candidate.clicked.connect(self.save_selected_candidate)
        save_current.clicked.connect(self.save_current_frame)
        save_row.addWidget(save_candidate)
        save_row.addWidget(save_current)
        root.addLayout(save_row)
        self.save_notice = QLabel("")
        self.save_notice.setObjectName("qualityNote")
        self.save_notice.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.save_notice.hide()
        root.addWidget(self.save_notice)

    def _wire(self) -> None:
        self.player.durationChanged.connect(self._duration_changed)
        self.player.positionChanged.connect(self._position_changed)
        self.player.playbackStateChanged.connect(self._state_changed)
        self.player.metaDataChanged.connect(self._metadata_changed)
        self.player.errorOccurred.connect(lambda error, text: QMessageBox.warning(self, "视频播放失败", text or str(error)))
        self.sink.videoFrameChanged.connect(self._video_frame)
        self.play_button.clicked.connect(self.toggle_play)
        self.slider.sliderPressed.connect(lambda: setattr(self, "_slider_dragging", True))
        self.slider.sliderReleased.connect(self._slider_released)
        self.slider.sliderMoved.connect(lambda value: self.time_label.setText(f"{format_time(value).replace('-', ':')} / {format_time(self.player.duration()).replace('-', ':')}"))

    def _load(self) -> None:
        self.setEnabled(False)
        result = extract_video_fractions(Path(self.project.content_path), [0.25, 0.5, 0.75])
        self.setEnabled(True)
        if result.error or len(result.frames) != 3:
            QMessageBox.warning(self, "候选帧读取不完整", result.error or "无法读取三张候选帧。")
        self.candidate_images = result.frames
        self.candidate_positions = result.positions_ms
        self.frame_rate = result.frame_rate
        for index, image in enumerate(result.frames):
            self.choices[index].set_frame(image, format_time(result.positions_ms[index]).replace("-", ":"))
        if len(result.frames) > 1:
            self.current_image = result.frames[1].copy()
            self.canvas.show_image(self.current_image)
        self.player.setSource(QUrl.fromLocalFile(self.project.content_path))
        self.player.play()
        if len(self.candidate_positions) > 1:
            QTimer.singleShot(250, lambda: self._seek_and_pause(self.candidate_positions[1]))

    def choose_candidate(self, index: int) -> None:
        if index < len(self.candidate_positions):
            self._seek_and_pause(self.candidate_positions[index])

    def toggle_play(self) -> None:
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def step_frames(self, count: int) -> None:
        fps = self.frame_rate or 30.0
        step = max(1, round(1000.0 / fps)) * count
        self._seek_and_pause(max(0, min(self.player.duration() - 1, self.player.position() + step)))

    def keyPressEvent(self, event: QKeyEvent) -> None:
        multiplier = 10 if event.modifiers() & Qt.KeyboardModifier.ShiftModifier else 1
        if event.key() == Qt.Key.Key_Left:
            self.step_frames(-multiplier)
            return
        if event.key() == Qt.Key.Key_Right:
            self.step_frames(multiplier)
            return
        if event.key() == Qt.Key.Key_Space:
            self.toggle_play()
            return
        super().keyPressEvent(event)

    def save_selected_candidate(self) -> None:
        index = self.choice_group.checkedId()
        if index < 0 or index >= len(self.candidate_images):
            self._show_toast("候选帧还没有读取完成，请稍候。", warning=True)
            return
        labels = "ABC"
        self._save_image(
            self.candidate_images[index],
            f"{self.project.safe_title}_候选{labels[index]}_{format_time(self.candidate_positions[index])}",
            f"视频候选 {labels[index]} 帧，位置 {format_time(self.candidate_positions[index]).replace('-', ':')}。",
        )

    def save_current_frame(self) -> None:
        if self.current_image.isNull():
            self._show_toast("当前帧还没有准备好，请先播放或定位视频。", warning=True)
            return
        self._save_image(
            self.current_image,
            f"{self.project.safe_title}_{format_time(self.player.position())}",
            f"视频手动精调帧，位置 {format_time(self.player.position()).replace('-', ':')}。",
        )

    def _save_image(self, image: QImage, stem: str, message: str) -> None:
        fmt = "JPEG" if self.format_jpg.isChecked() else "PNG"
        self.service.update_config(video_image_format=fmt)
        try:
            target = save_qimage(
                image,
                self.service.export_dir,
                stem,
                fmt,
                self.service,
                self.project,
                self.project.content_path,
                message,
            )
        except OSError as exc:
            QMessageBox.warning(self, "保存失败", str(exc))
            return
        self._show_toast(f"已保存：{Path(target).name} · {image.width()}×{image.height()} · {fmt}")

    def _show_toast(self, message: str, warning: bool = False) -> None:
        background = "#FFF3E8" if warning else "#E8F7EF"
        color = "#9A6336" if warning else "#3E775A"
        self.save_notice.setStyleSheet(
            f"background:{background};color:{color};padding:7px 10px;border-radius:8px;"
        )
        self.save_notice.setText(message)
        self.save_notice.show()
        self._toast_timer.start(3800)

    def _clear_toast(self) -> None:
        self.save_notice.clear()
        self.save_notice.hide()

    def _duration_changed(self, duration: int) -> None:
        self.slider.setRange(0, max(0, duration))
        self._position_changed(self.player.position())

    def _position_changed(self, position: int) -> None:
        if not self._slider_dragging:
            self.slider.setValue(position)
        current = format_time(position).replace("-", ":")
        total = format_time(self.player.duration()).replace("-", ":")
        self.time_label.setText(f"{current} / {total}")
        frame_number = round(position * (self.frame_rate or 30.0) / 1000.0)
        self.frame_info.setText(f"约第 {frame_number} 帧 · {self.frame_rate or 30.0:.3g} fps")

    def _state_changed(self, state) -> None:
        self.play_button.setText("暂停" if state == QMediaPlayer.PlaybackState.PlayingState else "播放")

    def _metadata_changed(self) -> None:
        value = self.player.metaData().value(QMediaMetaData.Key.VideoFrameRate)
        try:
            self.frame_rate = float(value or self.frame_rate or 30.0)
        except (TypeError, ValueError):
            pass

    def _video_frame(self, frame: QVideoFrame) -> None:
        if not frame.isValid():
            return
        image = frame.toImage()
        if image.isNull():
            return
        self.current_image = image.copy()
        self.canvas.show_image(self.current_image)
        if self._pending_pause:
            self._pending_pause = False
            self.player.pause()
        self.frame_info.setText(
            f"{image.width()}×{image.height()} · {self.frame_rate or 30.0:.3g} fps · 最接近可解码帧"
        )

    def _slider_released(self) -> None:
        self._slider_dragging = False
        self._seek_and_pause(self.slider.value())

    def _seek_and_pause(self, position: int) -> None:
        self.player.setPosition(position)
        self._pending_pause = True
        self.player.play()
        QTimer.singleShot(600, self._seek_pause_fallback)

    def _seek_pause_fallback(self) -> None:
        if self._pending_pause:
            self._pending_pause = False
            self.player.pause()

    def closeEvent(self, event) -> None:
        self.player.stop()
        super().closeEvent(event)
