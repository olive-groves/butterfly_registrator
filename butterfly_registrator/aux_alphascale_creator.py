#!/usr/bin/env python3

"""User interface to create and merge alphascale images.

Features:
    Select color with a colorpicker and preview the result.
    Merge multiple alphascale images and preview the result.

Credits:
    PyQt MDI Image Viewer by tpgit (http://tpgit.github.io/MDIImageViewer/) for image viewer panning and zooming.
"""
# SPDX-License-Identifier: GPL-3.0-or-later



import os
import time
from datetime import datetime

from PyQt5 import QtCore, QtGui, QtWidgets
import numpy as np
from cv2 import imread, imwrite, IMREAD_UNCHANGED

from aux_splitview import SplitView
from aux_buttons import InfoButton
from alg_alphascale import grayscale_to_alphascale, merge_alphascale



class CreateAlphascaleView(SplitView):
    """Viewer to preview the created alphascale image.

    Overrides SplitView by blocking right-click menu.
    
    See parent class for instantiation documentation.
    """

    def __init__(self, pixmap_main_topleft, filename_main_topleft, name=None, 
            pixmap_topright=None, pixmap_bottomleft=None, pixmap_bottomright=None, transform_mode_smooth=False):
        super().__init__(pixmap_main_topleft, filename_main_topleft, name, 
            pixmap_topright, pixmap_bottomleft, pixmap_bottomright, transform_mode_smooth, allow_main_opacity=False)
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose)

        self.set_scene_background_color(color = ["Gray", 127, 127, 127])

    def on_right_mouse_button_was_clicked(self):
        """Override parent method to disable right-click menu because it is not needed."""
        return
    


class MergeAlphascaleView(SplitView):
    """Viewer to preview the merged alphascale image.
    
    Overrides SplitView by blocking right-click menu.
    
    See parent class for instantiation documentation.
    """

    def __init__(self, pixmap_main_topleft, filename_main_topleft, name=None, 
            pixmap_topright=None, pixmap_bottomleft=None, pixmap_bottomright=None, transform_mode_smooth=False):
        super().__init__(pixmap_main_topleft, filename_main_topleft, name, 
            pixmap_topright, pixmap_bottomleft, pixmap_bottomright, transform_mode_smooth, allow_main_opacity=False)
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose)

        self.set_scene_background_color(color = ["Gray", 127, 127, 127])
        
    def on_right_mouse_button_was_clicked(self):
        """Override parent method to disable right-click menu because it is not needed."""
        return



class DragAndDropWidget(QtWidgets.QWidget):
    """Drag-and-drop widget to emit the filepaths of single and multiple images.
    
    Instantiate without input.
    """ 

    file_path_dragged_and_dropped = QtCore.pyqtSignal(str)
    file_paths_dragged_and_dropped = QtCore.pyqtSignal(list)

    def __init__(self):
        super().__init__()

        self.image_filetypes = [
            ".jpeg", ".jpg", ".jpe", ".jif", ".jfif", ".jfi", ".pjpeg", ".pjp",
            ".png",
            ".tiff", ".tif",
            ".bmp",
            ".webp",
            ".ico", ".cur"]

        self.setAcceptDrops(True)
        self.set_accept_multiple(False)

    def dragEnterEvent(self, event):
        """event: Override dragEnterEvent() to accept one or more image files based on setting."""
        if len(event.mimeData().urls()) is 1 and self.grab_image_urls_from_mimedata(event.mimeData()):
            event.accept()
        elif len(event.mimeData().urls()) >= 2 and self.accept_multiple and self.grab_image_urls_from_mimedata(event.mimeData()):
            event.accept()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        """event: Override dragMoveEvent() to accept one or more image files based on setting."""
        if len(event.mimeData().urls()) is 1 and self.grab_image_urls_from_mimedata(event.mimeData()):
            event.accept()
        elif len(event.mimeData().urls()) >= 2 and self.accept_multiple and self.grab_image_urls_from_mimedata(event.mimeData()):
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event):
        """event: Override dropEvent() to accept one or more image files based on setting."""
        urls = self.grab_image_urls_from_mimedata(event.mimeData())

        if urls:

            event.setDropAction(QtCore.Qt.CopyAction)

            if len(urls) >= 2 and self.accept_multiple:
                file_paths = []
                for url in urls:
                    file_paths.append(url.toLocalFile())
                self.file_paths_dragged_and_dropped.emit(file_paths)
            else:
                file_path = urls[0].toLocalFile()
                self.file_path_dragged_and_dropped.emit(file_path)
                
            event.accept()
                
        else:
            event.ignore()

    def grab_image_urls_from_mimedata(self, mimedata):
        """mimeData: Get urls (filepaths) from drop event."""
        urls = list()
        for url in mimedata.urls():
            if any([filetype in url.toLocalFile().lower() for filetype in self.image_filetypes]):
                urls.append(url)
        return urls
    
    def set_accept_multiple(self, boolean):
        """bool: True for drag zone to accept multiple image files to be dropped; False to reject."""
        self.accept_multiple = boolean
    


class AlphascaleCreator(QtWidgets.QWidget):
    """Interface to create an alphascale image with a colorpicker and viewer preview.

    Instantiate without input.

    Alphascale requires a grayscale image as input.
    
    Interface sequence: 
        Load the grayscale image by drag-and-drop or open dialog. 
        Preview the alphascale image in the image viewer.
        Adjust and apply the color with the colorpicker.
        Save the alphascale image by save dialog.
    """

    def __init__(self):
        super().__init__()

        self.input_filepath = None
        self.img_input = None
        self.img_alphascale = None
        self.pixmap = None
        self.viewer_exists = False
        self.color_rgb = None

        self.color_dialog = QtWidgets.QColorDialog()
        self.color_dialog.setOption(QtWidgets.QColorDialog.NoButtons)
        self.color_dialog.setCurrentColor(QtCore.Qt.red)
        self.color_dialog.currentColorChanged.connect(self.color_changed)
        self.color_dialog.setStyleSheet("""
            font-size: 9pt;
            """)

        drag_widget = DragAndDropWidget()
        drag_widget.file_path_dragged_and_dropped.connect(self.dragged_and_dropped_create)

        self.drag_border = QtWidgets.QLabel()
        self.drag_border.setAlignment(QtCore.Qt.AlignCenter | QtCore.Qt.AlignVCenter)
        self.drag_border.setStyleSheet("""
            QLabel { 
                font-size: 10pt;
                border: 0.15em dashed gray;
                border-radius: 0.3em;
                background-color: transparent;
                padding: 1.2em;
                } 
            """)
        self.drag_border.setWordWrap(True)
        self.drag_border.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents)

        self.drag_label = QtWidgets.QLabel("Drag or select single grayscale image")
        self.drag_label.setAlignment(QtCore.Qt.AlignCenter | QtCore.Qt.AlignVCenter)
        self.drag_label.setStyleSheet("""
            QLabel { 
                font-size: 10.5pt;
                background-color: transparent;
                padding: 1.2em;
                } 
            """)
        self.drag_label.setWordWrap(True)
        self.drag_label.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents)

        info_str = "Alphascale images are derived from grayscale images and show intensity by transparency instead of intensity by shades of gray. They are intended to be generated from grayscale maps (e.g., MA-XRF and RIS) and used as overlays."
        info_str = info_str + "\n\nAn alphascale image is generated from a given grayscale image by taking each grayscale pixel intensity and setting it to the value of the alpha channel in its corresponding pixel in the alphascale image. The RGB channels of all pixels in the alphascale image are then set to the same color."
        info_str = info_str + "\n\nFor a 'red' alphascale image, a black pixel in its grayscale counterpart would appear 100% transparent in the alphascale image, a white pixel would be appear 100% opaque, and a gray pixel would appear 50% transparent. The color of all pixels in the alphascale image would be the same (r = 255, g = 0, b = 0)."
        
        info_button = InfoButton(margin=8)
        info_button.set_box_title("Creating alphascale images")
        info_button.set_box_text(info_str)

        instructions_label = QtWidgets.QLabel("Supports grayscale images with both grayscale colortype and truecolor colortype (monochannel and RGB multichannel).")
        instructions_label.setAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignBottom)
        instructions_label.setStyleSheet("""
            QLabel {
                background-color: transparent;
                padding: 1.2em;
                } 
            """)
        instructions_label.setWordWrap(True)
        instructions_label.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents)
        
        self.open_button = QtWidgets.QPushButton("Select image...")
        self.open_button.clicked.connect(self.select_via_dialog)
        self.open_button.setEnabled(True)

        open_button_layout = QtWidgets.QHBoxLayout()
        open_button_layout.setAlignment(QtCore.Qt.AlignCenter | QtCore.Qt.AlignBottom)
        open_button_layout.addWidget(self.open_button)
        open_button_layout.addStretch(1)

        self.color_changed_but_not_applied = False
        
        self.apply_instantly = True
        self.apply_button = QtWidgets.QPushButton("Apply")
        self.apply_button.setEnabled(False)
        self.apply_button.clicked.connect(self.apply_button_clicked)
        self.apply_instantly_checkbox = QtWidgets.QCheckBox("Instantly apply (turn off if slow)")
        self.apply_instantly_checkbox.setChecked(self.apply_instantly)
        self.apply_instantly_checkbox.stateChanged.connect(self.apply_checkbox_changed)

        apply_button_layout = QtWidgets.QHBoxLayout()
        apply_button_layout.setAlignment(QtCore.Qt.AlignCenter | QtCore.Qt.AlignBottom)
        # apply_button_layout.addStretch(1)
        apply_button_layout.addWidget(self.apply_button)
        apply_button_layout.addWidget(self.apply_instantly_checkbox)
        apply_button_layout.setStretch(0,1)

        self.save_button = QtWidgets.QPushButton("Save as...")
        self.save_button.setEnabled(False)
        self.save_button.clicked.connect(self.save_via_dialog)

        save_button_layout = QtWidgets.QHBoxLayout()
        save_button_layout.setAlignment(QtCore.Qt.AlignCenter | QtCore.Qt.AlignBottom)
        save_button_layout.addStretch(1)
        save_button_layout.addWidget(self.save_button)

        self.loading_grayout_label = QtWidgets.QLabel("Loading...")
        self.loading_grayout_label.setAlignment(QtCore.Qt.AlignCenter | QtCore.Qt.AlignVCenter)
        self.loading_grayout_label.setVisible(False)
        self.loading_grayout_label.setStyleSheet("""
            QLabel { 
                background-color: rgba(255,255,255,223);
                } 
            """)
        
        self.viewer_layout = QtWidgets.QGridLayout()
        self.viewer_widget = QtWidgets.QWidget()
        self.viewer_widget.setLayout(self.viewer_layout)
        self.viewer_layout.addWidget(drag_widget, 0, 0)
        self.viewer_layout.addWidget(self.drag_border, 0, 0)
        self.viewer_layout.addWidget(self.drag_label, 0, 0)
        self.viewer_layout.addWidget(instructions_label, 0, 0)
        self.viewer_layout.addWidget(info_button, 0, 0, QtCore.Qt.AlignTop|QtCore.Qt.AlignRight)
        self.viewer_layout.addLayout(open_button_layout, 1, 0)

        self.edit_layout = QtWidgets.QGridLayout()
        self.edit_widget = QtWidgets.QWidget()
        self.edit_widget.setLayout(self.edit_layout)
        self.edit_layout.addWidget(self.color_dialog, 0, 0)
        self.edit_layout.addLayout(apply_button_layout, 1, 0)
        self.edit_layout.setRowStretch(2,1)
        self.edit_layout.addLayout(save_button_layout, 3, 0)

        self.layout = QtWidgets.QGridLayout()
        self.layout.setContentsMargins(0,0,0,0)
        self.layout.addWidget(self.viewer_widget, 0, 0)
        self.layout.setColumnStretch(0, 1)
        self.layout.addWidget(self.edit_widget, 0, 1)
        self.layout.addWidget(self.loading_grayout_label, 0, 0, 1, 2)

        self.setLayout(self.layout)

    def apply_checkbox_changed(self,int):
        """int: Trigger when the checkbox for instant-apply is clicked."""
        value = int
        if value is 0:
            self.apply_instantly = False
            if self.apply_button:
                self.apply_button.setEnabled(True)
        elif value is 2:
            self.apply_instantly = True
            if self.color_changed_but_not_applied:
                self.apply_color()
            if self.apply_button:
                self.apply_button.setEnabled(False)

    def apply_button_clicked(self):
        """Trigger when the apply button is clicked."""
        self.apply_button.setEnabled(False)
        self.display_loading_grayout(True, "Creating alphascale image...")
        self.apply_color()
        self.display_loading_grayout(False, pseudo_load_time=0)

    def color_changed(self):
        """Trigger when the color is changed in the color dialog to apply color."""
        if not self.apply_instantly and self.apply_button:
            if not self.apply_button.isEnabled():
                self.apply_button.setEnabled(True)
            # This ensures that the current color the user has selected is the same color which will be used in the alphascale map.
            # Specifically, whenever the current color is changed, the user must first re-apply the image before they can save. 
            if self.save_button:
                self.save_button.setEnabled(False)
            self.color_changed_but_not_applied = True
        if self.apply_instantly:
            self.apply_color()

    def apply_color(self):
        """Get the color from the picker; trigger the alphascale to (re)generate; update the viewer."""
        color = self.color_dialog.currentColor()
        red = color.red()
        green = color.green()
        blue = color.blue()

        img_input = self.img_input
        
        if img_input is not None:
            img_alphascale = self.generate_alphascale_of_loaded_image(img_input, red, green, blue)
            if img_alphascale is not None:
                pixmap = self.generate_pixmap_from_generated_alphascale(img_alphascale)
                self.update_viewer_with_generated_pixmap(pixmap)
                self.save_button.setEnabled(True)
                self.color_changed_but_not_applied = False

    def dragged_and_dropped_create(self, str):
        """str: Trigger when an image file is dropped into the drag zone."""
        filepath = str
        self.create_viewer(filepath=filepath)

    def select_via_dialog(self):
        """Select and load an image via dialog window."""
        self.display_loading_grayout(True, "Choosing image from which to create alphascale...")

        filepath = self.input_filepath
        filters = "\
            All supported image files (*.jpeg *.jpg  *.png *.tiff *.tif *.gif *.bmp);;\
            JPEG image files (*.jpeg *.jpg);;\
            PNG image files (*.png);;\
            TIFF image files (*.tiff *.tif);;\
            BMP (*.bmp)"
        filename, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Select image from which to create alphascale", filepath, filters)

        if filename:
            if self.viewer_exists:
                self.close_viewer()
            self.display_loading_grayout(False, pseudo_load_time=0)
            self.create_viewer(filename)
        else:
            self.display_loading_grayout(False, pseudo_load_time=0)

    def save_via_dialog(self):
        """Open a save dialog window to save the alphascale image to file."""
        self.display_loading_grayout(True, "Saving alphascale image...")

        r = self.color_rgb[0]
        g = self.color_rgb[1]
        b = self.color_rgb[2]
        rgb = str(r) + "_" + str(g) + "_" + str(b)

        filepath = self.input_filepath
        suffix = "_alphascale_rgb_" + rgb + "."
        filepath = filepath.replace('.', suffix)

        base, _ = os.path.splitext(filepath)

        if filepath.endswith('.jpg') or filepath.endswith('.jpeg'):
            filepath = base + ".png"
            name_filters = "PNG (*.png);; TIFF (*.tiff);; TIF (*.tif)"
        elif filepath.endswith('.tif'):
            name_filters = "TIF (*.tif);; PNG (*.png);; TIFF (*.tiff)"
        elif filepath.endswith('.tiff'):
            name_filters = "TIFF (*.tiff);; PNG (*.png);; TIF (*.tif)"
        elif filepath.endswith('.bmp'):
            filepath = base + ".png"
            name_filters = "PNG (*.png);; TIFF (*.tiff);; TIF (*.tif)"
        else:
            name_filters = "PNG (*.png);; TIFF (*.tiff);; TIF (*.tif)"

        filename, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Save alphascale image", filepath, name_filters)

        if filename:
            self.display_loading_grayout(True, "Saving alphascale image '" + filepath.split("/")[-1] + "'...")
            imwrite(filename, self.img_alphascale)

        self.display_loading_grayout(False)

    def create_viewer(self, filepath=None):
        """str: Create the viewer of an image using its filepath."""
        self.display_loading_grayout(True, "Loading...")

        img_input = self.load_image_from_file(filepath_input=filepath)

        if img_input is not None:

            color = self.color_dialog.currentColor()
            red = color.red()
            green = color.green()
            blue = color.blue()

            img_alphascale = self.generate_alphascale_of_loaded_image(img_input, red, green, blue)

            if img_alphascale is not None:
                pixmap = self.generate_pixmap_from_generated_alphascale(img_alphascale)
                self.instantiate_viewer_with_generated_pixmap(pixmap)
                self.save_button.setEnabled(True)

        self.display_loading_grayout(False)

    def load_image_from_file(self, filepath_input=None):
        """Load image from file as NumPy array.

        Sets image as self.img_input and returns pointer to it.

        Args:
            filepath_input (str): Fullpath of image to load.
        
        Returns:
            self.img_input (pointer to NumPy array): Image with BGRA channels.
        """
        self.input_filepath = filepath_input
        self.img_input = imread(filepath_input)
        return self.img_input
    
    def generate_alphascale_of_loaded_image(self, img_bgr=None, red=None, green=None, blue=None):
        """Generate an alphascale image from a grayscale image and specified RGB color.
        
        Args:
            img_bgr (NumPy array): Grayscale image with BGR channels (for example, from imread(filepath_input)).
            red (int): Red channel 0-255.
            green (int): Green channel 0-255.
            blue (int): Blue channel 0-255.
        
        Returns:
            self.img_alphascale (NumPy array): Alphascale image with BGRA channels.
        """
        color_rgb = [red, green, blue]
        self.img_alphascale = grayscale_to_alphascale(img=img_bgr, which_color_rgb=color_rgb)
        self.color_rgb = color_rgb
        return self.img_alphascale
    
    def generate_pixmap_from_generated_alphascale(self, img_alphascale):
        """Generate a pixmap from an alphascale image.

        Args:
            img_alphascale (NumPy array): Alphascale image with BGRA channels.

        Returns:
            self.pixmap (QPixmap): Pixmap of the alphascale image.
        """
        img = img_alphascale
        height, width, channels = img.shape
        total_bytes = img.nbytes
        bytes_per_line = int(total_bytes/height)
        if channels is 4:
            qimage = QtGui.QImage(img.data, width, height, bytes_per_line, QtGui.QImage.Format_RGBA8888).rgbSwapped()
        else:
            qimage = QtGui.QImage(img.data, width, height, bytes_per_line, QtGui.QImage.Format_RGB888).rgbSwapped()

        self.pixmap = QtGui.QPixmap(qimage)

        return self.pixmap

    def instantiate_viewer_with_generated_pixmap(self, pixmap):
        """QPixmap: Instantiate viewer with pixmap of the alphascale image."""
        self.viewer = self.create_viewer_widget(pixmap, self.input_filepath)
        self.viewer_layout.addWidget(self.viewer, 0, 0)
        QtCore.QTimer.singleShot(1, self.viewer.fitToWindow)
        self.viewer_exists = True

    def update_viewer_with_generated_pixmap(self, pixmap):
        """QPixmap: Update the viewer's pixmap with a new pixmap."""
        if self.viewer_exists:
            self.viewer._pixmapItem_main_topleft.setPixmap(pixmap)

    def create_viewer_widget(self, pixmap, filename):
        """Create viewer widget.
        
        Args:
            pixmap (QPixmap): The pixmap to view.
            filename (str): The filename to show on the viewer label.

        Returns:
            viewer (CreateAlphascaleView)
        """
        viewer = CreateAlphascaleView(pixmap, filename)
        viewer.label_main_topleft.setText(filename)
        viewer.label_main_topleft.set_visible_based_on_text(True)
        viewer.was_clicked_close_pushbutton.connect(self.close_viewer)
        return viewer
    
    def close_viewer(self):
        """Close the alphascale preview image viewer."""
        self.viewer.close()
        self.viewer.deleteLater()
        self.pixmap = None
        self.input_filepath = None
        self.img_input = None
        self.img_alphascale = None
        self.save_button.setEnabled(False)
        self.viewer_exists = False
  
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

    
    
class AlphascaleMerger(QtWidgets.QWidget):
    """Interface to merge multiple alphascale images into a single alphascale image with a viewer preview.

    Instantiate without input.
    
    Interface sequence: 
        Load the alphascale images by drag-and-drop or open dialog. 
        Preview the merged image in the image viewer.
        Save the merged image by save dialog.
    """

    def __init__(self):

        super().__init__()

        self.input_filepaths = []
        self.img_merged = None
        self.pixmap = None
        self.viewer_exists = False

        drag_widget = DragAndDropWidget()
        drag_widget.file_path_dragged_and_dropped.connect(self.dragged_and_dropped_single)
        drag_widget.file_paths_dragged_and_dropped.connect(self.dragged_and_dropped_multiple)
        drag_widget.set_accept_multiple(True)

        self.drag_border = QtWidgets.QLabel()
        self.drag_border.setAlignment(QtCore.Qt.AlignCenter | QtCore.Qt.AlignVCenter)
        self.drag_border.setStyleSheet("""
            QLabel { 
                font-size: 10pt;
                border: 0.15em dashed gray;
                border-radius: 0.3em;
                background-color: transparent;
                padding: 1.2em;
                } 
            """)
        self.drag_border.setWordWrap(True)
        self.drag_border.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents)

        self.drag_label = QtWidgets.QLabel("Drag or select multiple alphascale images")
        self.drag_label.setAlignment(QtCore.Qt.AlignCenter | QtCore.Qt.AlignVCenter)
        self.drag_label.setStyleSheet("""
            QLabel { 
                font-size: 10.5pt;
                background-color: transparent;
                padding: 1.2em;
                } 
            """)
        self.drag_label.setWordWrap(True)
        self.drag_label.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents)

        info_str = "The color of each pixel in the merged alphascale image is calculated by averaging the inputs' RGB channels with their respective alpha channels as weights at that pixel. In other words, the merged color is the weighted average of the colors of the inputs, with their opacity as weights."
        info_str = info_str + "\n\nThe alpha channel of each pixel in the merged alphascale image is set to the highest alpha channel of the inputs at that pixel."
        
        info_button = InfoButton(margin=8)
        info_button.set_box_title("Merging alphascale images")
        info_button.set_box_text(info_str)
        
        instructions_label = QtWidgets.QLabel("Supports alphascale images generated with this app only.")
        instructions_label.setAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignBottom)
        instructions_label.setStyleSheet("""
            QLabel { 
                background-color: transparent;
                padding: 1.2em;
                } 
            """)
        instructions_label.setWordWrap(True)
        instructions_label.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents)

        self.open_button = QtWidgets.QPushButton("Select alphascale images...")
        self.open_button.clicked.connect(self.select_via_dialog)
        self.open_button.setEnabled(True)

        self.save_button = QtWidgets.QPushButton("Save merged image as...")
        self.save_button.clicked.connect(self.save_via_dialog)
        self.save_button.setEnabled(False)

        self.loading_grayout_label = QtWidgets.QLabel("Loading...")
        self.loading_grayout_label.setAlignment(QtCore.Qt.AlignCenter | QtCore.Qt.AlignVCenter)
        self.loading_grayout_label.setVisible(False)
        self.loading_grayout_label.setStyleSheet("""
            QLabel { 
                background-color: rgba(255,255,255,223);
                } 
            """)

        self.button_layout = QtWidgets.QHBoxLayout()
        self.button_layout.setContentsMargins(0,6,0,0)
        self.button_widget = QtWidgets.QWidget()
        self.button_widget.setLayout(self.button_layout)
        self.button_layout.addWidget(self.open_button)
        self.button_layout.addStretch(1)
        self.button_layout.addWidget(self.save_button)

        self.viewer_layout = QtWidgets.QGridLayout()
        self.viewer_layout.setContentsMargins(0,0,0,0)
        self.viewer_widget = QtWidgets.QWidget()
        self.viewer_widget.setLayout(self.viewer_layout)
        self.viewer_layout.addWidget(drag_widget, 0, 0)
        self.viewer_layout.addWidget(self.drag_border, 0, 0)
        self.viewer_layout.addWidget(self.drag_label, 0, 0)
        self.viewer_layout.addWidget(instructions_label, 0, 0)
        self.viewer_layout.addWidget(info_button, 0, 0, QtCore.Qt.AlignTop|QtCore.Qt.AlignRight)

        self.layout = QtWidgets.QGridLayout()
        self.layout.addWidget(self.viewer_widget, 0, 0)
        self.layout.setRowStretch(0, 1)
        self.layout.addWidget(self.button_widget, 1, 0)
        self.layout.addWidget(self.loading_grayout_label, 0, 0, 2, 1)

        self.setLayout(self.layout)

    def dragged_and_dropped_single(self, input_filepath=str):
        """str: Trigger when a single image file is dropped into the drag zone."""
        messagebox_popup = QtWidgets.QMessageBox()
        messagebox_popup.information(self, "Multiple dragged images needed...", "Drag and drop multiple image files at the same time to create a merged alphascale image.")

    def dragged_and_dropped_multiple(self, input_filepaths=list):
        """Trigger when multiple image files are dropped into the drag zone.
        
        input_filepaths (list of str): List of filepaths."""
        self.create_viewer(input_filepaths)

    def select_via_dialog(self):
        """Select images to merge via dialog window."""
        self.display_loading_grayout(True, "Choosing alphascale images to merge...")

        try:
            filepath = self.input_filepaths[0]
        except IndexError:
            filepath = None
        
        filters = "\
            All supported image files (*.png *.tiff *.tif);;\
            PNG image files (*.png);;\
            TIFF image files (*.tiff *.tif)"
        filenames, _ = QtWidgets.QFileDialog.getOpenFileNames(self, "Select images to merge", filepath, filters)

        if len(filenames) >= 2:
            if self.viewer_exists:
                self.close_viewer()
            self.display_loading_grayout(False, pseudo_load_time=0)
            self.create_viewer(filenames)
        elif len(filenames) == 1:
            messagebox_popup = QtWidgets.QMessageBox()
            messagebox_popup.information(self, "Multiple selected images needed...", "Select multiple image files with Ctrl or Shift to create a merged alphascale image.")
            self.display_loading_grayout(False, pseudo_load_time=0)

        self.display_loading_grayout(False, pseudo_load_time=0)

    def save_via_dialog(self):
        """Open a save dialog window to save the merged alphascale image to file."""
        self.display_loading_grayout(True, "Saving merged alphascale image...")

        filepath = self.input_filepaths[0]
        date_and_time = datetime.now().strftime('%Y-%m-%d_%H%M%S') # Sets the default filename with date and time 
        suffix = "_merged_" + date_and_time + "."
        filepath = filepath.replace('.', suffix)

        if filepath.endswith('.tif'):
            name_filters = "TIF (*.tif);; PNG (*.png);; TIFF (*.tiff)"
        elif filepath.endswith('.tiff'):
            name_filters = "TIFF (*.tiff);; PNG (*.png);; TIF (*.tif)"
        else:
            name_filters = "PNG (*.png);; TIFF (*.tiff);; TIF (*.tif)"

        filename, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Save merged alphascale image", filepath, name_filters)

        if filename:
            self.display_loading_grayout(True, "Saving merged alphascale image '" + filepath.split("/")[-1] + "'...")
            imwrite(filename, self.img_merged)

        self.display_loading_grayout(False)

    def create_viewer(self, filepaths=[]):
        """list of str: Create the viewer."""
        self.display_loading_grayout(True, "Loading images from file...")

        imgs_input = self.load_images_from_file(filepaths=filepaths)
        
        if imgs_input is False:
            box_type = QtWidgets.QMessageBox.Warning
            title = "One or more images not alphascale"
            text = "One or more images selected to merge is not an alphascale image."
            box_buttons = QtWidgets.QMessageBox.Close
            box = QtWidgets.QMessageBox(box_type, title, text, box_buttons)
            box.exec_()
        
        elif len(imgs_input) >= 2:

            self.display_loading_grayout(True, "Merging images...\n\nThis may take a few minutes for many images and/or very large images.")

            img_merged = merge_alphascale(imgs=imgs_input)
            self.img_merged = img_merged

            if img_merged is not None:
                pixmap = self.generate_pixmap_from_merged_image(img_merged)
                self.instantiate_viewer_with_generated_pixmap(pixmap)
                self.save_button.setEnabled(True)

        self.display_loading_grayout(False)

    def load_images_from_file(self, filepaths=[]):
        """Load images from file. Reject if an image does not have BGRA channels.

        Args:
            filepaths (list of str): Filepaths to the images.
        
        Returns:
            imgs (list of NumPy array): Images with BGRA channels.
        """
        self.input_filepaths = filepaths
        imgs = []

        i = 0
        for filepath in self.input_filepaths:
            img = imread(filepath, IMREAD_UNCHANGED)
            dims = img.astype('uint8').shape
            try:
                dims[2] == 4
            except:
                return False
            else:
                if dims[2] == 4:
                    imgs.append(img)
                    i += 1
                else:
                    return False

        return imgs
    
    def generate_pixmap_from_merged_image(self, img):
        """Generate a pixmap from an alphascale image.

        Args:
            img_alphascale (NumPy array): Alphascale image with BGRA channels.

        Returns:
            self.pixmap (QPixmap): Pixmap of the alphascale image.
        """
        img = img
        height, width, channels = img.shape
        total_bytes = img.nbytes
        bytes_per_line = int(total_bytes/height)
        if channels is 4:
            qimage = QtGui.QImage(img.data, width, height, bytes_per_line, QtGui.QImage.Format_RGBA8888).rgbSwapped()
        else:
            qimage = QtGui.QImage(img.data, width, height, bytes_per_line, QtGui.QImage.Format_RGB888).rgbSwapped()

        pixmap = QtGui.QPixmap(qimage)

        return pixmap

    def instantiate_viewer_with_generated_pixmap(self, pixmap):
        """QPixmap: Instantiate viewer with pixmap of the alphascale image."""
        self.viewer = self.create_viewer_widget(pixmap, "Merged")
        self.viewer_layout.addWidget(self.viewer, 0, 0)
        QtCore.QTimer.singleShot(1, self.viewer.fitToWindow)
        self.viewer_exists = True

    def create_viewer_widget(self, pixmap, filename):
        """Create viewer widget.
        
        Args:
            pixmap (QPixmap): The pixmap to view.
            filename (str): The filename to show on the viewer label.

        Returns:
            viewer (MergeAlphascaleView)
        """
        viewer = MergeAlphascaleView(pixmap, filename)
        viewer.label_main_topleft.setText(filename)
        viewer.label_main_topleft.set_visible_based_on_text(True)
        viewer.was_clicked_close_pushbutton.connect(self.close_viewer)
        return viewer
    
    def close_viewer(self):
        """Close the merged alphascale image viewer."""
        self.viewer.close()
        self.viewer.deleteLater()
        self.pixmap = None
        self.input_filepaths = []
        self.img_merged = None
        self.save_button.setEnabled(False)
        self.viewer_exists = False

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

    

class Alphascaler(QtWidgets.QWidget):
    """QWidget with tabs for alphascale creator and merger interfaces.
    
    Instantiate without input. See parent class for documentation.
    """

    def __init__(self):

        super().__init__()
        
        self.create_widget = AlphascaleCreator()
        self.merge_widget = AlphascaleMerger()

        self.tab_widget = QtWidgets.QTabWidget()
        self.tab_widget.addTab(self.create_widget, "Create single")
        self.tab_widget.addTab(self.merge_widget, "Merge multiple")

        alphascale_layout = QtWidgets.QGridLayout()
        alphascale_layout.addWidget(self.tab_widget, 0, 0)

        self.setLayout(alphascale_layout)