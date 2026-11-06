"""
Barre de pré-écoute intégrée (QMediaPlayer).
Masquée par défaut ; apparaît quand l'utilisateur pré-écoute un fichier.
"""
import os

from PyQt6.QtCore    import Qt, QUrl, QSize, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QLabel, QPushButton, QSlider, QComboBox,
)

from ui.icons import icon, PALETTE

try:
    from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput, QMediaDevices
    MULTIMEDIA_OK = True
except ImportError:
    MULTIMEDIA_OK = False


def _fmt_ms(ms: int) -> str:
    s = max(0, ms) // 1000
    return f"{s // 60}:{s % 60:02d}"


class _SeekSlider(QSlider):
    """Slider dont un clic saute directement à la position cliquée."""

    def __init__(self):
        super().__init__(Qt.Orientation.Horizontal)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.maximum() > self.minimum():
            ratio = event.position().x() / max(1, self.width())
            value = self.minimum() + round((self.maximum() - self.minimum()) * ratio)
            self.setValue(int(value))
        # super() prend le relais : la poignée est maintenant sous le curseur,
        # le glissement fonctionne naturellement
        super().mousePressEvent(event)


class PreviewPlayer(QWidget):
    """Barre horizontale : ▶/⏸ | titre | position | temps | sortie | volume | ✕."""

    stopped = pyqtSignal()   # lecture arrêtée (✕, conversion, fermeture)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("panel_player")
        self._player = None
        self._audio  = None

        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 8, 12, 8)
        lay.setSpacing(12)

        self._btn_play = QPushButton()
        self._btn_play.setIconSize(QSize(16, 16))
        self._set_play_icon(True)
        self._btn_play.setObjectName("btn_icon")
        self._btn_play.setFixedSize(34, 30)
        self._btn_play.clicked.connect(self._toggle_play)
        lay.addWidget(self._btn_play)

        self._lbl_title = QLabel("")
        self._lbl_title.setStyleSheet(
            "color: rgba(200,180,255,220); font-size:12px; font-weight:600;")
        self._lbl_title.setMinimumWidth(140)
        lay.addWidget(self._lbl_title)

        # Position : saut au clic, recherche au relâchement uniquement
        # (chercher en continu pendant le glissement rend la lecture saccadée)
        self._slider = _SeekSlider()
        self._slider.setRange(0, 0)
        self._slider.sliderReleased.connect(self._on_slider_released)
        self._slider.sliderMoved.connect(self._on_slider_moved)
        lay.addWidget(self._slider, 1)

        self._lbl_time = QLabel("0:00 / 0:00")
        self._lbl_time.setStyleSheet("color: rgba(255,255,255,130); font-size:11px;")
        lay.addWidget(self._lbl_time)

        # Sortie audio : permet de choisir le bon périphérique si le
        # défaut Windows n'est pas celui qu'on écoute
        self._combo_device = QComboBox()
        self._combo_device.setToolTip("Périphérique de sortie audio")
        self._combo_device.setMaximumWidth(190)
        self._combo_device.currentIndexChanged.connect(self._on_device_changed)
        lay.addWidget(self._combo_device)

        vol_icon = QLabel("🔊")
        vol_icon.setStyleSheet("font-size:12px;")
        lay.addWidget(vol_icon)

        self._vol = QSlider(Qt.Orientation.Horizontal)
        self._vol.setRange(0, 100)
        self._vol.setValue(100)
        self._vol.setFixedWidth(90)
        self._vol.valueChanged.connect(self._set_volume)
        lay.addWidget(self._vol)

        btn_close = QPushButton()
        btn_close.setIcon(icon("close", PALETTE["dark"]["muted"], 15))
        btn_close.setIconSize(QSize(15, 15))
        btn_close.setObjectName("btn_icon")
        btn_close.setFixedSize(30, 30)
        btn_close.clicked.connect(self.stop_and_hide)
        lay.addWidget(btn_close)

        self.hide()

    # ── Public ────────────────────────────────────────────────────────────────

    def play_file(self, path: str) -> bool:
        """Lance la lecture. Return False si QtMultimedia indisponible."""
        if not MULTIMEDIA_OK:
            return False

        if self._player is None:
            self._player = QMediaPlayer(self)
            self._audio  = QAudioOutput(self)
            self._audio.setDevice(QMediaDevices.defaultAudioOutput())
            self._player.setAudioOutput(self._audio)
            self._player.positionChanged.connect(self._on_position)
            self._player.durationChanged.connect(self._on_duration)
            self._player.errorOccurred.connect(self._on_error)
            self._set_volume(self._vol.value())
            self._populate_devices()

        self._player.stop()
        self._lbl_title.setText(os.path.basename(path))
        self._player.setSource(QUrl.fromLocalFile(path))
        self._player.play()
        self._set_play_icon(True)
        self.show()
        return True

    def stop(self):
        """Arrête la lecture et libère le fichier (verrou Windows)."""
        if self._player:
            self._player.stop()
            self._player.setSource(QUrl())   # release file handle
        self._set_play_icon(False)
        self.stopped.emit()

    def stop_and_hide(self):
        self.stop()
        self.hide()

    def current_source(self) -> str:
        if self._player:
            return self._player.source().toLocalFile()
        return ""

    # ── Périphériques de sortie ───────────────────────────────────────────────

    def _populate_devices(self):
        default = QMediaDevices.defaultAudioOutput()
        self._combo_device.blockSignals(True)
        self._combo_device.clear()
        for dev in QMediaDevices.audioOutputs():
            self._combo_device.addItem(dev.description(), userData=dev)
            if dev.id() == default.id():
                self._combo_device.setCurrentIndex(self._combo_device.count() - 1)
        self._combo_device.blockSignals(False)

    def _on_device_changed(self, index: int):
        dev = self._combo_device.itemData(index)
        if self._audio and dev is not None:
            self._audio.setDevice(dev)

    # ── Private ───────────────────────────────────────────────────────────────

    def _set_play_icon(self, playing: bool):
        """Bouton lecture : pause pendant la lecture, play sinon."""
        self._btn_play.setIcon(icon("pause" if playing else "play",
                                    PALETTE["dark"]["text"], 16))

    def _toggle_play(self):
        if not self._player:
            return
        if self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self._player.pause()
            self._set_play_icon(False)
        else:
            self._player.play()
            self._set_play_icon(True)

    def _on_slider_released(self):
        if self._player:
            self._player.setPosition(self._slider.value())

    def _on_slider_moved(self, pos: int):
        # Pendant le glissement : n'actualiser que l'affichage du temps
        dur = self._player.duration() if self._player else 0
        self._lbl_time.setText(f"{_fmt_ms(pos)} / {_fmt_ms(dur)}")

    def _set_volume(self, value: int):
        if self._audio:
            self._audio.setVolume(value / 100)

    def _on_position(self, pos: int):
        if self._slider.isSliderDown():
            return   # l'utilisateur glisse : ne pas lui reprendre la poignée
        self._slider.setValue(pos)
        dur = self._player.duration() if self._player else 0
        self._lbl_time.setText(f"{_fmt_ms(pos)} / {_fmt_ms(dur)}")

    def _on_duration(self, dur: int):
        self._slider.setRange(0, dur)

    def _on_error(self, _error, error_string: str):
        self._lbl_title.setText(f"⚠ Lecture impossible — {error_string}")
        self._set_play_icon(False)
