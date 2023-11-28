#!/usr/bin/env python3

"""User interface to convert the file types of images.

Features:
    Select files in a given directory.
    Select file type to convert to.
    Select destination directory.
    Convert and save.
"""
# SPDX-License-Identifier: GPL-3.0-or-later



import os
import time
import traceback, sys

from PyQt5 import QtCore, QtGui, QtWidgets
import numpy as np
from cv2 import imread, imwrite, IMREAD_UNCHANGED, IMWRITE_JPEG_QUALITY

from aux_buttons import InfoButton


class ElideLabel(QtWidgets.QLabel):
    """QLabel which elides text to its current size instead of resizing.

    Used for showing long single-line texts, like directories.

    Credit:
    - musicamante: https://stackoverflow.com/a/68092991
    """

    _elideMode = QtCore.Qt.ElideMiddle

    def elideMode(self):
        return self._elideMode

    def setElideMode(self, mode):
        if self._elideMode != mode and mode != QtCore.Qt.ElideNone:
            self._elideMode = mode
            self.updateGeometry()

    def minimumSizeHint(self):
        return self.sizeHint()

    def sizeHint(self):
        hint = self.fontMetrics().boundingRect(self.text()).size()
        l, t, r, b = self.getContentsMargins()
        margin = self.margin() * 2
        return QtCore.QSize(
            min(100, hint.width()) + l + r + margin, 
            min(self.fontMetrics().height(), hint.height()) + t + b + margin
        )

    def paintEvent(self, event):
        qp = QtGui.QPainter(self)
        opt = QtWidgets.QStyleOptionFrame()
        self.initStyleOption(opt)
        self.style().drawControl(
            QtWidgets.QStyle.CE_ShapedFrame, opt, qp, self)
        l, t, r, b = self.getContentsMargins()
        margin = self.margin()
        try:
            # since Qt >= 5.11
            m = self.fontMetrics().horizontalAdvance('x') / 2 - margin
        except:
            m = self.fontMetrics().width('x') / 2 - margin
        r = self.contentsRect().adjusted(
            margin + m,  margin, -(margin + m), -margin)
        qp.drawText(r, self.alignment(), 
            self.fontMetrics().elidedText(
                self.text(), self.elideMode(), r.width()))



class CheckLabel(QtWidgets.QLabel):
    """Checkmark label which hides when disabled and keeps its size when hidden.

    Instantiate without input. See parent class for documentation.
    """

    def __init__(self):

        super().__init__()

        self.setText("✓")

        policy = QtWidgets.QSizePolicy()
        policy.setRetainSizeWhenHidden(True)

        self.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
        self.setSizePolicy(policy)

class ConverterStepRow(QtWidgets.QWidget):
    """Widget containing checkmark and addable widget for a single converter step, arranged horizontally in a row.

    Signals is finished when enabled (setEnabled(True)) and is disabled when disabled (setEnabled(False)).

    Instantiate without input. See parent class for documentation.
    """

    finished = QtCore.pyqtSignal(bool)
    disabled = QtCore.pyqtSignal()

    def __init__(self):

        super().__init__()

        self.layout = QtWidgets.QHBoxLayout()
        self.layout.setContentsMargins(0,0,0,0)

        self.check_widget = CheckLabel()
        self.layout.addWidget(self.check_widget)
        
        self.setLayout(self.layout)

        self._is_finished = False
        self.check_widget.setVisible(self.is_finished)

    def addWidget(self, widget):
        """QWidget: Add widget to layout (adds to the right as a new column)."""
        self.layout.addWidget(widget)

    def setEnabled(self, value):
        """Override to emit is finished if enabled or emit is disabled if disabled."""
        if value:
            self.finished.emit(self.is_finished)
        else:
            self.disabled.emit()
        super().setEnabled(value)

    @property
    def is_finished(self):
        return self._is_finished
    
    @is_finished.setter
    def is_finished(self, value: bool):
        self._is_finished = value
        self.check_widget.setVisible(value)
        self.finished.emit(value)


class WorkerSignals(QtCore.QObject):
    '''
    Defines the signals available from a running worker thread.

    Supported signals are:

    finished
        No data

    error
        tuple (exctype, value, traceback.format_exc() )

    result
        object data returned from processing, anything

    progress
        int indicating % progress

    '''
    finished = QtCore.pyqtSignal()
    error = QtCore.pyqtSignal(tuple)
    result = QtCore.pyqtSignal(object)
    progress = QtCore.pyqtSignal(int)


class Worker(QtCore.QRunnable):
    '''
    Worker thread

    Inherits from QRunnable to handler worker thread setup, signals and wrap-up.

    :param callback: The function callback to run on this worker thread. Supplied args and
                     kwargs will be passed through to the runner.
    :type callback: function
    :param args: Arguments to pass to the callback function
    :param kwargs: Keywords to pass to the callback function

    '''

    def __init__(self, fn, *args, **kwargs):
        super(Worker, self).__init__()

        # Store constructor arguments (re-used for processing)
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()

        # Add the callback to our kwargs
        self.kwargs['progress_callback'] = self.signals.progress

    @QtCore.pyqtSlot()
    def run(self):
        '''
        Initialise the runner function with passed args, kwargs.
        '''

        # Retrieve args/kwargs here; and fire processing using them
        try:
            result = self.fn(*self.args, **self.kwargs)
        except:
            traceback.print_exc()
            exctype, value = sys.exc_info()[:2]
            self.signals.error.emit((exctype, value, traceback.format_exc()))
        else:
            self.signals.result.emit(result)  # Return the result of the processing
        finally:
            self.signals.finished.emit()  # Done


class FileTypeConverter(QtWidgets.QWidget):
    """Interface for converting the file types of images.
    
    Instantiate without input. See parent class for documentation.

    Interface sequence:
        Select files in a given directory.
        Select file type to convert to.
        Select destination directory.
        Convert and save.
    """

    loading = QtCore.pyqtSignal(bool)
    loading_custom = QtCore.pyqtSignal(bool, str)

    def __init__(self):

        super().__init__()

        self.threadpool = QtCore.QThreadPool()

        self.images_select_button = QtWidgets.QPushButton("Select image(s)...")
        self.images_select_button.clicked.connect(self.select_images_via_dialog)
        self.images_select_fullpaths = []
        self.images_select_widget = ConverterStepRow()
        self.images_select_widget.addWidget(self.images_select_button)
        self.images_select_widget.setEnabled(True)
        
        self.filetype_select_prompt = QtWidgets.QLabel("File type to convert to?")
        self.filetype_select_prompt.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
        self.filetype_select_combo = QtWidgets.QComboBox()
        self.filetype_select_combo.addItem("Select...")
        self.filetype_select_extension = None
        self.filetype_items = ["*.jpeg", "*.jpg", "*.png", "*.tiff", "*.tif", "*.bmp"]
        self.filetype_filters = ["*.jpeg, *.jpg", "*.png", "*.tiff, *.tif", "*.bmp"]
        self.filetype_names = ["JPEG image files", "PNG image files", "TIFF image files", "BMP"]
        self.filetype_select_combo.addItems(self.filetype_items)
        self.filetype_select_combo.currentIndexChanged.connect(self.selected_filetype_combo_index)
        self.filetype_select_widget = ConverterStepRow()
        self.filetype_select_widget.addWidget(self.filetype_select_prompt)
        self.filetype_select_widget.addWidget(self.filetype_select_combo)
        self.filetype_select_widget.setEnabled(False)

        self.destination_select_button = QtWidgets.QPushButton("Select destination folder...")
        self.destination_select_button.clicked.connect(self.select_destination_via_dialog)
        self.destination_select_widget = ConverterStepRow()
        self.destination_select_widget.addWidget(self.destination_select_button)
        self.destination_select_widget.setEnabled(False)
        self.destination_select_directory = None

        self.convert_save_button = QtWidgets.QPushButton("Convert and save image(s)")
        self.convert_save_button.clicked.connect(self.save_button_clicked)
        self.convert_save_widget = ConverterStepRow()
        self.convert_save_widget.addWidget(self.convert_save_button)
        self.convert_save_widget.setEnabled(False)

        self.images_select_label = ElideLabel()
        self.images_select_label.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
        self.filetype_select_label = ElideLabel()
        self.filetype_select_label.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
        self.destination_select_label = ElideLabel()
        self.destination_select_label.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
        self.convert_save_label = ElideLabel()
        self.convert_save_label.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
        
        # If a step gives a signal that it is finished, enable the following step; 
        # if it not finished, disable the following step. 
        self.images_select_widget.finished.connect(self.filetype_select_widget.setEnabled)
        self.filetype_select_widget.finished.connect(self.destination_select_widget.setEnabled)
        self.destination_select_widget.finished.connect(self.convert_save_widget.setEnabled)

        # If a step gives a signal that it is disabled, disable the following the step.
        self.images_select_widget.disabled.connect(lambda: self.filetype_select_widget.setEnabled(False))
        self.filetype_select_widget.disabled.connect(lambda: self.destination_select_widget.setEnabled(False))
        self.destination_select_widget.disabled.connect(lambda: self.convert_save_widget.setEnabled(False))

        layout = QtWidgets.QGridLayout()
        layout.setAlignment(QtCore.Qt.AlignLeft)
        layout.addWidget(self.images_select_widget, 0, 0)
        layout.addWidget(self.images_select_label, 0, 1)
        layout.addWidget(self.filetype_select_widget, 1, 0)
        layout.addWidget(self.filetype_select_label, 1, 1)
        layout.addWidget(self.destination_select_widget, 2, 0)
        layout.addWidget(self.destination_select_label, 2, 1)
        layout.addWidget(self.convert_save_widget, 3, 0)
        layout.addWidget(self.convert_save_label, 3, 1)
        layout.setRowStretch(4, 1)

        self.setLayout(layout)

    def select_images_via_dialog(self):
        """Select images to convert via dialog window."""
        self.loading_custom.emit(True, "Selecting images to convert...")

        try:
            existing_fullpath = self.images_select_fullpaths[0]
        except IndexError:
            existing_fullpath = None
        
        filter_dialog_all = "All supported (" + " ".join(self.filetype_filters) + ");;"
        filter_dialog_single_list = [name + " (" + filtertype + ")" for name, filtertype in zip(self.filetype_names, self.filetype_filters)]
        filter_dialog_single = ";; ".join(filter_dialog_single_list)
        filter_dialog = filter_dialog_all + filter_dialog_single

        fullpaths, _ = QtWidgets.QFileDialog.getOpenFileNames(self, "Select images to convert", existing_fullpath, filter_dialog)

        self.loading.emit(False)

        if len(fullpaths) >= 1:
            self.images_selected(fullpaths)
        else:
            self.images_not_selected()

    def images_selected(self, fullpaths: list):
        """list of str: Indicate image(s) selected with their fullpaths."""

        self.images_select_fullpaths = fullpaths
        n = len(self.images_select_fullpaths)
        if n < 1:
            return
        text = f"{n} file{'s'[:n^1]} selected"
        self.images_select_label.setText(text)

        self.images_select_widget.is_finished = True

    def images_not_selected(self):
        """Indicate no image selected."""
        self.images_select_fullpaths = []
        self.images_select_widget.is_finished = False
        self.images_select_label.setText("")

    def selected_filetype_combo_index(self, index):
        """TODO: Finish docstring."""
        if index > 0:
            filetype_extension = self.filetype_select_combo.currentText().strip("*")

            if self.do_selected_files_already_exist_with_filetype(filetype_extension=filetype_extension):
                text = "Heads-up: One or more files already are this filetype, so this conversion will be redundant"
            else:
                text = ""
            
            self.filetype_select_label.setText(text)

            self.filetype_select_extension = filetype_extension
            self.filetype_select_widget.is_finished = True
        else:
            self.filetype_select_extension = None
            self.filetype_select_widget.is_finished = False

    def do_selected_files_already_exist_with_filetype(self, filetype_extension=None, remove_existing_files_from_list=False):
        """TODO: Finish docstring."""
        selected_files_already_exist_with_filetype = False
        filetype_extension = filetype_extension
        fullpaths = self.images_select_fullpaths

        if not filetype_extension: # If no filetype given
            return False
        elif not fullpaths: # If files is empty list
            return False
        elif not self.filetype_select_combo.currentIndex(): # If combobox at index 0
            return False
                
        # For each path
        for fullpath in fullpaths:
            if self.change_fullpath_extension(fullpath, filetype_extension) == fullpath:
                selected_files_already_exist_with_filetype = True

        return selected_files_already_exist_with_filetype

    def change_fullpath_extension(self, fullpath, extension):
        """
        Args:
            fullpath (str): Original fullpath.
            extension (str): File type extensions with period. Example ".jpg", ".tiff".

        Returns:
            new_fullpath (str): New fullpath with extension.
        """
        original_fullpath = fullpath
        new_extension = extension
        new_fullpath = os.path.splitext(original_fullpath)[0] + new_extension
        return new_fullpath
    
    def change_fullpath_directory(self, fullpath, directory):
        """
        Args:
            fullpath (str): Original fullpath.
            directory (str): Directory to which the new fullpath should have.

        Returns:
            new_fullpath (str): New fullpath with directory.
        """
        original_fullpath = fullpath
        new_directory = directory
        new_fullpath = new_directory + '/' + original_fullpath.split('/')[-1]
        print(new_fullpath)
        return new_fullpath

    def select_destination_via_dialog(self):
        """Open an open dialog window to select a destination folder to which to save the converted file(s)."""

        n = len(self.images_select_fullpaths)
        self.loading_custom.emit(True, f"Selecting folder to save converted image{'s'[:n^1]}...")

        directory = QtWidgets.QFileDialog.getExistingDirectory(self, "Select folder")
        
        self.loading.emit(False)

        if directory:
            self.destination_selected(directory)
        else:
            self.destination_not_selected()

    def destination_selected(self, directory: str):
        """str: Indicate destination selected with its directory."""
        self.destination_select_directory = directory
        if self.destination_select_directory == None:
            return
        text = f"{directory}"
        self.destination_select_label.setText(text)

        self.destination_select_widget.is_finished = True

    def destination_not_selected(self):
        """Indicate destination not selected."""
        self.destination_select_directory = None
        self.destination_select_widget.is_finished = False
        self.destination_select_label.setText("")

    def save_button_clicked(self):
        self.thread_convert_and_save_images()

    def convert_and_save_images(self, progress_callback):
        """TODO: Conversion function. 
        
        Lars: I want to switch image processing to pyvips instead of cv2 as it 
        is faster and retains most/all image metadata when manipulating and 
        converting images. This of course involves rewriting the code with 
        pyvips, but it also means adding/installing the libvips .dlls and
        adding it to PATH for pyvips to find. I'm not certain how easy this is 
        when creating the executable and installer for Windows and MacOS.
        """
        extension = self.filetype_select_extension
        fullpaths = self.images_select_fullpaths
        directory = self.destination_select_directory
        n = len(fullpaths)
        for i, fullpath in enumerate(fullpaths):
            img = self.read_image(fullpath)
            new_fullpath = self.change_fullpath_extension(fullpath, extension)
            new_fullpath = self.change_fullpath_directory(new_fullpath, directory)
            self.write_image(new_fullpath, img)
            progress_callback.emit((i+1)*100/n)
        self.convert_save_widget.is_finished = True
        self.convert_save_label.setText("Finished")
        return "Done."
    
    def write_image(self, fullpath, img):
        """Writes image using a fullpath(str) and a cv2 image (NumPy array)."""
        if fullpath.endswith('.jpg') or fullpath.endswith('.jpeg'):
            imwrite(fullpath, img, [int(IMWRITE_JPEG_QUALITY), 100])
        else:
            imwrite(fullpath, img)
    
    def read_image(self, fullpath):
        """Returns cv2 image (NumPy array) read using a fullpath (str)."""
        if fullpath.endswith(".png"): # Preserve the alpha channel if a PNG.
            img = imread(fullpath, IMREAD_UNCHANGED)
            if img.ndim is 2: # ...but if the PNG is monochannel, redo the imread and let cv2 determine how.
                img = imread(fullpath) 
        else:
            img = imread(fullpath)
        img = img.astype('uint8')
        return img

    def progress_fn(self, n):
        self.convert_save_label.setText("Converting and saving %d%%" % n)

    # def execute_this_fn(self, progress_callback):
    #     for n in range(0, 5):
    #         time.sleep(1)
    #         progress_callback.emit(n*100/4)

    #     return "Done."

    def print_output(self, s):
        print(s)

    def thread_complete(self):
        print("THREAD COMPLETE!")

    def thread_convert_and_save_images(self):
        # Pass the function to execute
        worker = Worker(self.convert_and_save_images) # Any other args, kwargs are passed to the run function
        worker.signals.result.connect(self.print_output)
        worker.signals.finished.connect(self.thread_complete)
        worker.signals.progress.connect(self.progress_fn)

        # Disable interface
        # Execute
        self.threadpool.start(worker)
        # Enable interface

class Converter(QtWidgets.QWidget):
    """Parent interface to hold the image file type converter.
    
    Instantiate without input. See parent class for documentation.
    """

    loading = QtCore.pyqtSignal(bool)

    def __init__(self):

        super().__init__()

        self.filetype_select_converter = FileTypeConverter()
        self.filetype_select_converter.loading.connect(self.loading)
        self.filetype_select_converter.loading.connect(self.display_loading_grayout)
        self.filetype_select_converter.loading_custom.connect(lambda boolean: self.loading.emit(boolean))
        self.filetype_select_converter.loading_custom.connect(self.display_loading_grayout)

        layout = QtWidgets.QGridLayout()
        layout.addWidget(self.filetype_select_converter, 0, 0)
        
        self.loading_grayout_label = QtWidgets.QLabel("Loading...")
        self.loading_grayout_label.setAlignment(QtCore.Qt.AlignCenter | QtCore.Qt.AlignVCenter)
        self.loading_grayout_label.setVisible(False)
        self.loading_grayout_label.setStyleSheet("""
            QLabel { 
                background-color: rgba(255,255,255,223);
                } 
            """)

        layout.addWidget(self.loading_grayout_label, 0, 0, layout.rowCount(), layout.columnCount())

        self.setLayout(layout)
    
    def display_loading_grayout(self, boolean, text=None, pseudo_load_time=0.2):
        """Show/hide grayout screen for loading sequences.

        Args:
            boolean (bool): True to show grayout; False to hide.
            text (str): The text to show on the grayout.
            pseudo_load_time (float): The delay (in seconds) to hide the grayout to give users a feeling of action.
        """
        if text:
            self.loading_grayout_label.setText(text)
        if not boolean:
            self.loading_grayout_label.setText("Loading...")
        self.loading_grayout_label.setVisible(boolean)
        if boolean:
            self.loading_grayout_label.repaint()
        if not boolean:
            time.sleep(pseudo_load_time)