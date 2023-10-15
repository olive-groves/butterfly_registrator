#!/usr/bin/env python3

"""Button widgets for Butterfly Registrator.

Not intended as a script.
"""
# SPDX-License-Identifier: GPL-3.0-or-later



from PyQt5 import QtCore, QtWidgets



class InfoButton(QtWidgets.QWidget):
    """Styled button providing extra info in a dialog box when clicked (a "question mark button").

    Adjusts automatically to smallest size.
    
    Args:
        margin (int): The margin (empty space) around the button in pixels."""

    def __init__(self, margin=12):
        super().__init__()

        self.button = QtWidgets.QToolButton()
        self.button.setText("?")
        self.button.setToolTip("Show info...")
        self.button.setStyleSheet("""
                QToolButton { 
                    font-size: 9pt;
                    } 
                """)
        self.button.clicked.connect(self.button_clicked)

        self.box_text = ""
        self.box_title = ""
        
        layout = QtWidgets.QGridLayout()
        layout.addWidget(self.button)
        w = margin
        layout.setContentsMargins(w,w,w,w)
        layout.setSpacing(w)

        self.setLayout(layout)

    def set_box_title(self, title):
        """str: The title of the dialog box."""
        self.box_title = title

    def set_box_text(self, text):
        """str: The text of the dialog box."""
        self.box_text = text

    def button_clicked(self):
        """Trigger when button is clicked."""
        self.show_messagebox()
        return
    
    def show_messagebox(self):
        """Show dialog box."""
        box_type = QtWidgets.QMessageBox.Information
        box_buttons = QtWidgets.QMessageBox.Close
        title = self.box_title
        text = self.box_text
        box = QtWidgets.QMessageBox(box_type, title, text, box_buttons)
        box.exec_()


class AboutButton(InfoButton):
    """Styled button providing about info in a dialog box when clicked (an "about button").

    Adjusts automatically to smallest size.
    
    Args:
        margin (int): The margin (empty space) around the button in pixels."""

    def __init__(self, margin=12):
        super().__init__(margin)

        self.button.setText("About")
        self.button.setToolTip("About...")
    
    def show_messagebox(self):
        """Show about box."""
        title = self.box_title
        text = self.box_text
        box = QtWidgets.QMessageBox.about(self, title, text)

class DragZoneButton(QtWidgets.QWidget):
    """Styled button for use within drag zones.

    Set text after instantiation with setText().

    Adjusts automatically to smallest size.    
    
    Args:
        margin (int): The margin (empty space) around the button in pixels.
    """

    def __init__(self, margin=12):
        super().__init__()

        self.button = QtWidgets.QToolButton()
        self.button.setStyleSheet("""
                QToolButton { 
                    font-size: 9pt;
                    } 
                """)
        self.button.clicked.connect(self.button_clicked)

        layout = QtWidgets.QGridLayout()
        layout.addWidget(self.button)
        w = margin
        layout.setContentsMargins(w,w,w,w)
        layout.setSpacing(w)

        self.setLayout(layout)

    clicked = QtCore.pyqtSignal()

    def button_clicked(self):
        """Emit signal when button is clicked."""
        self.clicked.emit()
        return
    
    def setText(self, text=str):
        """str: Set the text of the button."""
        self.button.setText(text)



class ControlPointUndoButton(QtWidgets.QToolButton):
    """Button to undo the last move of a given control point graphics item widget.

    Args:
        widget (QGraphicsLineItem): The graphics item of the control point with which to connect the button. 
    """

    def __init__(self, widget: QtWidgets.QGraphicsLineItem = None):
        super().__init__()

        # self.control_point_widget = control_point_widget
        # Connect signals to and from that widgets
        # was_clicked to call the "undo travel" of that widget
        # was_moved to enable the widget
        self.control_point_widget = widget
        self.is_undo = True
        self.set_as_undo()
        self.setEnabled(False)
        self.clicked.connect(self.button_clicked)

    def button_clicked(self):
        """Switch to undo/redo on click."""
        if self.is_undo:
            self.undo()
        elif not self.is_undo:
            self.redo()

    def undo(self):
        """Apply actual undo action and set interface elements to redo."""
        self.do_undo()
        self.set_as_redo()

    def redo(self):
        """Apply actual redo action and set interface elements to undo."""
        self.do_redo()
        self.set_as_undo()

    def set_as_undo(self):
        """Set interface elements to undo."""
        self.is_undo = True
        self.setText("Undo")
        self.setToolTip("Undo the last move of this control point")

    def set_as_redo(self):
        """Set interface elements to redo."""
        self.is_undo = False
        self.setText("Redo")
        self.setToolTip("Redo the last move of this control point")

    def do_undo(self):
        """Make control point widget undo its last travel."""
        widget = self.control_point_widget
        if not widget.scene():
            return
        widget.undo_last_travel()

    def do_redo(self):
        """Make control point widget redo its last travel."""
        widget = self.control_point_widget
        if not widget.scene():
            return
        widget.redo_last_travel()

    def set_control_point_widget(self, widget: QtWidgets.QGraphicsLineItem = None):
        """QGraphicsLineItem: Set the control point graphics item widget with which to undo/redo travel."""
        self.control_point_widget = widget
        if widget is None:
            self.set_as_undo()
            self.setEnabled(False)
            return