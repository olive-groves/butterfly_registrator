#!/usr/bin/env python3

"""QLineEdit widgets for Butterfly Registrator.

Not intended as a script.
"""
# SPDX-License-Identifier: GPL-3.0-or-later



from PyQt5 import QtCore, QtGui, QtWidgets



class NumberLineEdit(QtWidgets.QLineEdit):
    """QLineEdit for numbers only in 0.0 format.

    Stores text also as numerical value.

    Corrects:
        Decimal comma to decimal point.
        No leading zero to leading zero.
        Hanging decimal to zero in tenths place.

    Filters:
        Non-numeric text.
        Non float-to-text convertible numbers.
    
    Args:
        text (str): Text (value) to show when initialized.
    """

    changed_value = QtCore.pyqtSignal(int, str, float)
    
    def __init__(self, which_point: int, x_or_y: str, text=0.0):
        super().__init__()

        self.which_point = which_point
        self.x_or_y = x_or_y
        
        self.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Fixed)
        self.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)

        self.has_value_changed_since_being_focused = False

        self.value = 0.0
        self.filter_and_correct_text(text)
        self.textEdited.connect(self.filter_and_correct_text)
        self.editingFinished.connect(self.editing_has_finished)
        self.setText(text)

    def focusInEvent(self, event) -> None:
        self.has_value_changed_since_being_focused = False
        return super().focusInEvent(event)

    def editing_has_finished(self):
        if self.has_value_changed_since_being_focused:
            self.setText("{:.2f}".format(self.value))
            self.changed_value.emit(self.which_point, self.x_or_y, self.value)
        
    def filter_and_correct_text(self, text, set_value=True):
        """Filter and correct text typed into field to 0.0 format.
        
        Sets value if text is numeric.

        Triggered by QLineEdit.textEdited.
        
        Args:
            text (str): From QLineEdit.textEdited.

        Returns:
            text (str): Filtered and corrected to 0.0 format.
        """
        if text is None:
            return
        text = text.replace(" ", "")
        if text is "":
            return
        text = text.replace(",", ".")
        text_filter = text
        text_filter = text.replace(".", "")
        if not text_filter.isnumeric():
            return
        if text.endswith("."):
            text.replace(".", ".0")
        if text.startswith("."):
            text.replace(".", "0.")
        
        try: 
            value = float(text)
        except:
            return
        
        if set_value:
            self.value = value
            self.has_value_changed_since_being_focused = True

        return text