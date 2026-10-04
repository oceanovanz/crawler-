from PySide6.QtWidgets import (
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
    QFrame,
    QComboBox,
)


def create_spin_box(value=None, tip=None, min=0.1, max=10.0, dp=2, suffix=" m"):
    box = QDoubleSpinBox()
    box.setRange(min, max)
    box.setDecimals(dp)
    box.setSuffix(suffix)
    if value:
        box.setValue(value)
    if tip:
        box.setToolTip(tip)
    return box


def create_combo_box(items, current=None, tip=None):
    box = QComboBox()
    box.addItems(items)
    box.setStyleSheet("color: white; background-color: #1e1e1e;")
    if current:
        box.setCurrentText(current)
    if tip:
        box.setToolTip(tip)
    return box


def create_divider():
    divider = QFrame()
    divider.setFrameShape(QFrame.Shape.HLine)
    divider.setFrameShadow(QFrame.Shadow.Sunken)
    divider.setStyleSheet("""
        background-color: #333333;
        max-height: 1px;
    """)
    return divider
