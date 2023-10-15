#!/usr/bin/env python3

"""User interface to manually register images and create alphascale images.

Intended to be run as a script:
    $ python butterfly_registrator.py

Registration features:
    Register images using four-point perspective transformation (homography).
    Zoom and pan for target and moving images with draggable control points.
    Preview of the registered image and the target reference image shown in a sliding overlay.
    Batch mode to register multiple images with the same resizing and homography (for example, XRF element maps).

Alphascale creation features:
    Select color with a colorpicker and preview the result.
    Merge multiple alphascale images and preview the result.

Credits:
    PyQt MDI Image Viewer by tpgit (http://tpgit.github.io/MDIImageViewer/) for image viewer panning and zooming.
"""
# SPDX-License-Identifier: GPL-3.0-or-later



import sys
import os
import time
import csv
from datetime import datetime

from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtWidgets import QGraphicsSceneMouseEvent
import numpy as np
from cv2 import imread, imwrite, IMREAD_UNCHANGED, warpPerspective, getPerspectiveTransform, INTER_AREA, resize, IMWRITE_JPEG_QUALITY
import six # Do not remove. Needed to package with Pyinstaller. Otherwise does not include in dist.

from aux_splitview import SplitView
from aux_buttons import InfoButton, AboutButton, DragZoneButton, ControlPointUndoButton
from aux_lineedits import NumberLineEdit
import aux_alphascale_creator
from aux_exif import get_exif_rotation_angle
import aux_converter
import icons_rc


os.environ["QT_ENABLE_HIGHDPI_SCALING"]   = "1"
os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"
os.environ["QT_SCALE_FACTOR"]             = "1"

__version__ = "1.0"
COMPANY = "No company provided"
DOMAIN = "No domain provided"
APPNAME = "Butterfly Registrator" + " " + __version__



class ResultView(SplitView):
    """Viewer to preview the result of registration.

    Overrides SplitView by blocking right-click menu.
    
    See parent class for instantiation documentation.
    """

    def __init__(self, pixmap_main_topleft, filename_main_topleft, name, 
            pixmap_topright, pixmap_bottomleft, pixmap_bottomright, transform_mode_smooth):
        super().__init__(pixmap_main_topleft, filename_main_topleft, name, 
            pixmap_topright, pixmap_bottomleft, pixmap_bottomright, transform_mode_smooth, allow_main_opacity=False)
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose)

        self._scene_main_topleft.disable_right_click = True


class CustomQGraphicsLineItem(QtWidgets.QGraphicsLineItem):
    """Overides QGraphicsLineItem to emit signal in scene that it has changed.
    
    See parent class for documentation.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.travel_start = QtCore.QPointF()
        self.travel_end = QtCore.QPointF()
        self.undo_widget = None
        self.undo_widget_has_seen_travel = False

    def itemChange(self, change, value):
        """"Extend to emit signal from scene that an item has changed."""
        if change == QtWidgets.QGraphicsItem.ItemScenePositionHasChanged:
            self.scene().position_changed_qgraphicsitem.emit()
        return super().itemChange(change, value)
    
    def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        """"Extend to record scene position at moment when mouse was pressed."""
        self.travel_start = self.scenePos()
        return super().mousePressEvent(event)
    
    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        """"Extend to record scene position at moment when mouse was released and emit a travel occurred."""
        self.travel_end = self.scenePos()
        self.tell_undo_widget_travel_was_made()
        return super().mouseReleaseEvent(event)

    def set_position_manually(self, x, y):
        """"Set position manually with scene coordinates and record as a travel."""
        self.travel_start = self.scenePos()
        self.setPos(x, y)
        self.travel_end = self.scenePos()
        self.tell_undo_widget_travel_was_made()

    def tell_undo_widget_travel_was_made(self):
        """"Set associated undo widget that a travel was made."""
        if self.undo_widget:
            self.undo_widget.set_as_undo()
            if not self.undo_widget_has_seen_travel:
                self.undo_widget_has_seen_travel = True
                self.undo_widget.setEnabled(True)

    def undo_last_travel(self):
        """"Undo last recorded travel."""
        self.setPos(self.travel_start)

    def redo_last_travel(self):
        """"Redo last recorded travel."""
        self.setPos(self.travel_end)

    def set_undo_widget(self, widget=None):
        """"Set associated undo widget."""
        self.undo_widget = widget



class RegisterView(SplitView):
    """Viewer with registration control points for target and moving images.

    Extends SplitView by adding control points for four-point perspective transformation.

    Overrides SplitView by blocking right-click menu.
    
    See parent class for instantiation documentation.
    """

    registration_point_emitted = QtCore.pyqtSignal(QtCore.QPointF, int)
    registration_point_changed = QtCore.pyqtSignal()

    def __init__(self, pixmap_main_topleft, filename_main_topleft, name, 
            pixmap_topright, pixmap_bottomleft, pixmap_bottomright, transform_mode_smooth):

        super().__init__(pixmap_main_topleft, filename_main_topleft, name, 
            pixmap_topright, pixmap_bottomleft, pixmap_bottomright, transform_mode_smooth, allow_main_opacity=False)
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose)
        
        self._scene_main_topleft.disable_right_click = True

        self.registration_points = []

        offset = 0.3

        self.registration_points.append(self.make_registration_point(placement_x=offset, placement_y=offset, text="1"))
        self.registration_points.append(self.make_registration_point(placement_x=1-offset, placement_y=offset, text="2"))
        self.registration_points.append(self.make_registration_point(placement_x=offset, placement_y=1-offset, text="3"))
        self.registration_points.append(self.make_registration_point(placement_x=1-offset, placement_y=1-offset, text="4"))

        i = -1
        for point in self.registration_points:
            i += 1
            self._scene_main_topleft.addItem(self.registration_points[i])

        self._scene_main_topleft.position_changed_qgraphicsitem.connect(self.on_registration_point_moved)

    def on_registration_point_moved(self):
        """Emit signals when control point is moved."""
        self.registration_point_changed.emit()
        self.emit_registration_points()
        return

    def emit_registration_points(self):
        """Emit the position of all control points."""
        i = -1
        for point in self.registration_points:
            i += 1
            scene_pos = self.registration_points[i].scenePos()
            self.registration_point_emitted.emit(scene_pos, i)

    def make_registration_point(self, placement_x, placement_y, text):
        """Create a control point.
        
        Args:
            placement_x (float): Horizontal position as a proportion of the image's width (0-1).
            placement_y (float): Vertical position as a proportion of the image's width (0-1).
            text (str): Text to show.

        Returns:
            line_item_bounding_box (CustomQGraphicsLineItem): Control point as a QGraphicsItem.
        """
        width_pixmap_main_topleft = self._pixmapItem_main_topleft.pixmap().width()
        height_pixmap_main_topleft = self._pixmapItem_main_topleft.pixmap().height()

        placement_x = placement_x
        placement_y = placement_y

        pos_x = width_pixmap_main_topleft*placement_x
        pos_y = height_pixmap_main_topleft*placement_y

        pos_on_scene = QtCore.QPointF(pos_x, pos_y)

        pen = QtGui.QPen() 
        pen.setWidth(2)
        pen.setColor(QtCore.Qt.white) # setColor also works
        pen.setCapStyle(QtCore.Qt.SquareCap)
        pen.setJoinStyle(QtCore.Qt.MiterJoin)
            
        brush = QtGui.QBrush()
        brush.setColor(QtCore.Qt.white)
        brush.setStyle(QtCore.Qt.SolidPattern)

        width = 4
        height = 4

        point_topleft = QtCore.QPointF(-width/2, -height/2)
        point_bottomright = QtCore.QPointF(width/2,height/2)

        ellipse_rect = QtCore.QRectF(point_topleft, point_bottomright)
        ellipse_item = QtWidgets.QGraphicsEllipseItem(ellipse_rect)

        ellipse_item.setPos(0,0)
        
        ellipse_item.setBrush(brush)
        ellipse_item.setPen(pen)

        ellipse_item.setFlags(QtWidgets.QGraphicsItem.ItemIgnoresTransformations)

        self.shadow = QtWidgets.QGraphicsDropShadowEffect(blurRadius=8, color=QtGui.QColor(0, 0, 0, 255), xOffset=0, yOffset=0)

        dx = 30
        dy = -30
        point_p1 = QtCore.QPointF(0,0)
        point_p2 = QtCore.QPointF(dx,dy)
        line = QtCore.QLineF(point_p1, point_p2)
        line_item = QtWidgets.QGraphicsLineItem(line)
        pen = QtGui.QPen() 
        pen.setWidth(2)
        pen.setColor(QtCore.Qt.white)
        pen.setCapStyle(QtCore.Qt.SquareCap)
        pen.setJoinStyle(QtCore.Qt.MiterJoin)
        line_item.setPen(pen)
        line_item.setFlags(QtWidgets.QGraphicsItem.ItemIgnoresTransformations)
        line_item.setPos(0,0)
        line_item.setGraphicsEffect(self.shadow)

        line_item_bounding_box = CustomQGraphicsLineItem(line)
        pen = QtGui.QPen() 
        pen.setWidth(20)
        pen.setColor(QtCore.Qt.transparent)
        pen.setCapStyle(QtCore.Qt.SquareCap)
        pen.setJoinStyle(QtCore.Qt.MiterJoin)
        line_item_bounding_box.setPen(pen)
        line_item_bounding_box.setFlags(QtWidgets.QGraphicsItem.ItemIsMovable | QtWidgets.QGraphicsItem.ItemIgnoresTransformations | QtWidgets.QGraphicsItem.ItemSendsScenePositionChanges)
        line_item_bounding_box.set_position_manually(pos_on_scene.x(),pos_on_scene.y())

        text_item = QtWidgets.QGraphicsTextItem(text)
        font = text_item.font()
        font.setPointSize(14)
        text_item.setFont(font)
        text_item.setPos(dx+1,dy-18)
        text_item.setDefaultTextColor(QtCore.Qt.white)
        text_item.setFlags(QtWidgets.QGraphicsItem.ItemIgnoresTransformations) # QtWidgets.QGraphicsItem.ItemIsSelectable

        text_item.setParentItem(line_item)
        ellipse_item.setParentItem(line_item)
        line_item.setParentItem(line_item_bounding_box)

        return line_item_bounding_box
    
    def set_point(self, which_point: int, x_or_y: str, value: float):
        """"Set position of control point coordinate in scene.
        
        Args:
            which_point (int): Index of control point to set (1, 2, 3, or 4).
            x_or_y (str): String of coordinate ("x" or "y").
            value (float): Value of coordinate in scene.
        """
        
        if which_point < 1 or which_point > 4:
            return
        
        i = which_point - 1
        scene_pos = self.registration_points[i]

        if x_or_y == "x":
            x = value
            y = scene_pos.y()
        elif x_or_y == "y":
            x = scene_pos.x()
            y = value
        else:
            return
        
        self.registration_points[i].set_position_manually(x, y)

    def set_points(self, pairs: list=None):
        """Set position of all control points on scene with x,y pairs.
        
        Args:
            pairs (list): Position x,y pairs of control points ([[x1,y1],[x2,y2],[x3,y3],[x4,y4]]).
        """
        if len(pairs) != 4:
            return
        for i, pair in enumerate(pairs):
            self.registration_points[i].set_position_manually(pair[0], pair[1])



class DragAndDropWidget(QtWidgets.QWidget):
    """Drag-and-drop widget for single image files to emit their filepaths.
    
    Instantiate without input.
    """ 

    file_path_dragged_and_dropped = QtCore.pyqtSignal(str)    

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

    def dragEnterEvent(self, event):
        """event: Override dragEnterEvent() to accept a single image file."""
        if len(event.mimeData().urls()) is 1 and self.grab_image_urls_from_mimedata(event.mimeData()):
            event.accept()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        """event: Override dragMoveEvent() to accept a single image file."""
        if len(event.mimeData().urls()) is 1 and self.grab_image_urls_from_mimedata(event.mimeData()):
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event):
        """event: Override dropEvent() to accept a single image file."""
        urls = self.grab_image_urls_from_mimedata(event.mimeData())

        if len(urls) is 1 and urls:
            event.setDropAction(QtCore.Qt.CopyAction)
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



class Registrator(QtWidgets.QWidget):
    """Interface to register a moving image to a target image by setting control points in viewers of each.

    Instantiate without input.

    Registration is based on four-point perspective transformation where the control points are manually dragged.
    
    Interface sequence: 
        Load the target image by drag-and-drop or open dialog. 
        Load the moving image by drag-and-drop or open dialog.
        Set the control points on each image by click-and-drag. 
        Preview the registered image and compare with the target image in a split-view. 
        Adjust and re-compare the control points, if needed.
        Save the registered image.
        (Optional) Batch-register multiple images with the current registration, if needed.
    """
    
    loading = QtCore.pyqtSignal(bool)

    def __init__(self):
        super().__init__()

        self.n_registration_points = 4
        self.registration_point_changed_but_not_applied = True
        self.fullpath_reference = None
        self.fullpath_toregister = None

        # Build 'reference' image
        self.reference_layout = QtWidgets.QGridLayout()
        self.reference_layout.setContentsMargins(0,0,0,0)

        reference_title_label = QtWidgets.QLabel("Reference (target)")
        reference_title_label.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Maximum)

        reference_drag_widget = DragAndDropWidget()
        reference_drag_widget.file_path_dragged_and_dropped.connect(self.dragged_and_dropped_reference)

        reference_drag_label = QtWidgets.QLabel("Step 1:\n\nDrag or select reference image")
        reference_drag_label.setAlignment(QtCore.Qt.AlignCenter | QtCore.Qt.AlignVCenter)
        reference_drag_label.setStyleSheet("""
            QLabel {
                font-size: 10pt;
                border: 0.15em dashed gray;
                border-radius: 0.3em;
                background-color: transparent;
                padding: 1.2em;
                } 
            """)
        reference_drag_label.setWordWrap(True)
        reference_drag_label.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents)

        self.select_reference_button = DragZoneButton(margin=16)
        self.select_reference_button.setText("Select image...")
        self.select_reference_button.clicked.connect(self.select_via_dialog_reference)

        self.reference_info_button = InfoButton(margin=0)
        self.reference_info_button.set_box_title("Target image")
        self.reference_info_button.set_box_text("The reference image is the 'target' to which the 'moving' image will be registered. It can be considered the 'ground truth' for registration. \n\nFor example, a target image 900×900px will cause a moving image 400×300px to increase to 900×900px.")

        val = 0.0
        val_str = '{0:0.2f}'.format(val)

        reference_point_label_x = QtWidgets.QLabel("x (px)")
        reference_point_label_x.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Fixed)
        reference_point_label_x.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
        reference_point_label_y = QtWidgets.QLabel("y (px)")
        reference_point_label_y.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Fixed)
        reference_point_label_y.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)

        reference_point_label_name1 = QtWidgets.QLabel(" 1 ")
        reference_point_label_name1.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        reference_point_label_name1.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)

        self.reference_point_label_x1 = NumberLineEdit(1, "x", val_str)
        self.reference_point_label_y1 = NumberLineEdit(1, "y", val_str)
 
        reference_point_label_name2 = QtWidgets.QLabel(" 2 ")
        reference_point_label_name2.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        reference_point_label_name2.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
        self.reference_point_label_x2 = NumberLineEdit(2, "x", val_str)
        self.reference_point_label_y2 = NumberLineEdit(2, "y", val_str)
 
        reference_point_label_name3 = QtWidgets.QLabel(" 3 ")
        reference_point_label_name3.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        reference_point_label_name3.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
        self.reference_point_label_x3 = NumberLineEdit(3, "x", val_str)
        self.reference_point_label_y3 = NumberLineEdit(3, "y", val_str)
 
        reference_point_label_name4 = QtWidgets.QLabel(" 4 ")
        reference_point_label_name4.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        reference_point_label_name4.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
        self.reference_point_label_x4 = NumberLineEdit(4, "x", val_str)
        self.reference_point_label_y4 = NumberLineEdit(4, "y", val_str)

        self.reference_point_undo_buttons = []
        for i in range(self.n_registration_points):
            self.reference_point_undo_buttons.append(ControlPointUndoButton())
 
        reference_points_layout = QtWidgets.QGridLayout()
        reference_points_layout.setContentsMargins(0,0,0,0)

        reference_points_layout.addWidget(reference_point_label_x, 0, 1)
        reference_points_layout.addWidget(reference_point_label_y, 0, 2)

        row = 1

        reference_points_layout.addWidget(reference_point_label_name1, row, 0)
        reference_points_layout.addWidget(self.reference_point_label_x1, row, 1)
        reference_points_layout.addWidget(self.reference_point_label_y1, row, 2)

        row += 1

        reference_points_layout.addWidget(reference_point_label_name2, row, 0)
        reference_points_layout.addWidget(self.reference_point_label_x2, row, 1)
        reference_points_layout.addWidget(self.reference_point_label_y2, row, 2)

        row += 1

        reference_points_layout.addWidget(reference_point_label_name3, row, 0)
        reference_points_layout.addWidget(self.reference_point_label_x3, row, 1)
        reference_points_layout.addWidget(self.reference_point_label_y3, row, 2)

        row += 1

        reference_points_layout.addWidget(reference_point_label_name4, row, 0)
        reference_points_layout.addWidget(self.reference_point_label_x4, row, 1)
        reference_points_layout.addWidget(self.reference_point_label_y4, row, 2)

        row = 1
        for button in self.reference_point_undo_buttons:
            reference_points_layout.addWidget(button, row, 3)
            row += 1

        self.points_reference = np.array([
            [0,0], [0,0],
            [0,0], [0,0]
            ], dtype=np.float32) # aka "destination" points

        self.reference_layout.addWidget(reference_title_label, 0, 0)
        self.reference_layout.addWidget(reference_drag_widget, 1, 0)
        self.reference_layout.addWidget(reference_drag_label, 1, 0)
        self.reference_layout.addWidget(self.select_reference_button, 1, 0, QtCore.Qt.AlignBottom|QtCore.Qt.AlignLeft)
        self.reference_layout.addLayout(reference_points_layout, 2, 0)
        # self.reference_layout.addWidget(self.load_points_button, 3, 0)

        reference_widget = QtWidgets.QWidget()
        reference_widget.setLayout(self.reference_layout)

        reference_splitter_layout = QtWidgets.QGridLayout()
        reference_splitter_layout.setContentsMargins(0,0,0,0)
        reference_splitter_layout.setSpacing(0)
        reference_splitter_layout.addWidget(reference_widget, 0, 0)
        reference_splitter_layout.addWidget(self.reference_info_button, 0, 0, QtCore.Qt.AlignTop|QtCore.Qt.AlignRight)
        reference_splitter_widget = QtWidgets.QWidget()
        reference_splitter_widget.setLayout(reference_splitter_layout)

        # Build 'to register' (image to be registered)
        
        self.toregister_layout = QtWidgets.QGridLayout()
        self.toregister_layout.setContentsMargins(0,0,0,0)

        toregister_title_label = QtWidgets.QLabel("To be registered (moving)")
        toregister_title_label.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Maximum)

        toregister_drag_widget = DragAndDropWidget()
        toregister_drag_widget.file_path_dragged_and_dropped.connect(self.dragged_and_dropped_toregister) 

        self.toregister_drag_label = QtWidgets.QLabel("Step 2:\n\nDrag or select image to be registered")
        self.toregister_drag_label.setAlignment(QtCore.Qt.AlignCenter | QtCore.Qt.AlignVCenter)
        self.toregister_drag_label.setStyleSheet("""
            QLabel { 
                font-size: 10pt;
                border: 0.15em dashed gray;
                border-radius: 0.3em;
                background-color: transparent;
                padding: 1.2em;
                } 
            """)
        self.toregister_drag_label.setWordWrap(True)
        self.toregister_drag_label.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents)

        self.select_toregister_button = DragZoneButton(margin=16)
        self.select_toregister_button.setText("Select image...")
        self.select_toregister_button.clicked.connect(self.select_via_dialog_toregister)

        self.toregister_info_button = InfoButton(margin=0)
        self.toregister_info_button.set_box_title("Moving image")
        self.toregister_info_button.set_box_text("The image to be registered is the one 'moving' to align to the 'target' reference image. \n\nFor example, a moving image 8000×6000px to be registered to a target 400×700px would be reduced to 400×700px.")

        val = 0.0
        val_str = '{0:0.2f}'.format(val)

        toregister_point_label_x = QtWidgets.QLabel("x (px)")
        toregister_point_label_x.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Fixed)
        toregister_point_label_x.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
        toregister_point_label_y = QtWidgets.QLabel("y (px)")
        toregister_point_label_y.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Fixed)
        toregister_point_label_y.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)

        toregister_point_label_name1 = QtWidgets.QLabel(" 1 ")
        toregister_point_label_name1.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        toregister_point_label_name1.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
        self.toregister_point_label_x1 = NumberLineEdit(1, "x", val_str)
        self.toregister_point_label_y1 = NumberLineEdit(1, "y", val_str)
 
        toregister_point_label_name2 = QtWidgets.QLabel(" 2 ")
        toregister_point_label_name2.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        toregister_point_label_name2.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
        self.toregister_point_label_x2 = NumberLineEdit(2, "x", val_str)
        self.toregister_point_label_y2 = NumberLineEdit(2, "y", val_str)
 
        toregister_point_label_name3 = QtWidgets.QLabel(" 3 ")
        toregister_point_label_name3.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        toregister_point_label_name3.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
        self.toregister_point_label_x3 = NumberLineEdit(3, "x", val_str)
        self.toregister_point_label_y3 = NumberLineEdit(3, "y", val_str)
 
        toregister_point_label_name4 = QtWidgets.QLabel(" 4 ")
        toregister_point_label_name4.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        toregister_point_label_name4.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
        self.toregister_point_label_x4 = NumberLineEdit(4, "x", val_str)
        self.toregister_point_label_y4 = NumberLineEdit(4, "y", val_str)

        self.toregister_point_undo_buttons = []
        for i in range(self.n_registration_points):
            self.toregister_point_undo_buttons.append(ControlPointUndoButton())
 
        toregister_points_layout = QtWidgets.QGridLayout()
        toregister_points_layout.setContentsMargins(0,0,0,0)

        toregister_points_layout.addWidget(toregister_point_label_x, 0, 1)
        toregister_points_layout.addWidget(toregister_point_label_y, 0, 2)

        row = 1

        toregister_points_layout.addWidget(toregister_point_label_name1, row, 0)
        toregister_points_layout.addWidget(self.toregister_point_label_x1, row, 1)
        toregister_points_layout.addWidget(self.toregister_point_label_y1, row, 2)

        row += 1

        toregister_points_layout.addWidget(toregister_point_label_name2, row, 0)
        toregister_points_layout.addWidget(self.toregister_point_label_x2, row, 1)
        toregister_points_layout.addWidget(self.toregister_point_label_y2, row, 2)

        row += 1

        toregister_points_layout.addWidget(toregister_point_label_name3, row, 0)
        toregister_points_layout.addWidget(self.toregister_point_label_x3, row, 1)
        toregister_points_layout.addWidget(self.toregister_point_label_y3, row, 2)

        row += 1

        toregister_points_layout.addWidget(toregister_point_label_name4, row, 0)
        toregister_points_layout.addWidget(self.toregister_point_label_x4, row, 1)
        toregister_points_layout.addWidget(self.toregister_point_label_y4, row, 2)

        row = 1
        for button in self.toregister_point_undo_buttons:
            toregister_points_layout.addWidget(button, row, 3)
            row += 1

        self.points_toregister = np.array([
            [0,0], [0,0],
            [0,0], [0,0]
            ], dtype=np.float32) # aka "source" points

        self.toregister_layout.addWidget(toregister_title_label, 0, 0)
        self.toregister_layout.addWidget(toregister_drag_widget, 1, 0)
        self.toregister_layout.addWidget(self.toregister_drag_label, 1, 0)
        self.toregister_layout.addWidget(self.select_toregister_button, 1, 0, QtCore.Qt.AlignBottom|QtCore.Qt.AlignLeft)
        self.toregister_layout.addLayout(toregister_points_layout, 2, 0)

        self.toregister_widget = QtWidgets.QWidget()
        self.toregister_widget.setLayout(self.toregister_layout)

        toregister_splitter_layout = QtWidgets.QGridLayout()
        toregister_splitter_layout.setContentsMargins(0,0,0,0)
        toregister_splitter_layout.setSpacing(0)
        toregister_splitter_layout.addWidget(self.toregister_widget, 0, 0)
        toregister_splitter_layout.addWidget(self.toregister_info_button, 0, 0, QtCore.Qt.AlignTop|QtCore.Qt.AlignRight)
        toregister_splitter_widget = QtWidgets.QWidget()
        toregister_splitter_widget.setLayout(toregister_splitter_layout)

        self.set_enabled_toregister(False)
        self.viewer_toregister_isclosed = True

        # Build 'result' (show reference and registered images in splitview)
        self.result_layout = QtWidgets.QGridLayout()
        self.result_layout.setContentsMargins(0,0,0,0)

        result_title_label = QtWidgets.QLabel("Registered (aligned moving)")
        result_title_label.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Maximum)

        self.result_placeholder_text_default = "Step 3:\n\nAdjust control points on images and click 'Apply'"
        self.result_placeholder_text_refresh = "Control point(s) modified\n\nClick 'Apply' to refresh result"
        self.result_placeholder_label = QtWidgets.QLabel(self.result_placeholder_text_default)
        self.result_placeholder_label.setAlignment(QtCore.Qt.AlignCenter | QtCore.Qt.AlignVCenter)
        self.result_placeholder_label.setWordWrap(True)
        self.result_placeholder_label.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)

        self.result_info_button = InfoButton(margin=0)
        self.result_info_button.set_box_title("Aligned moving image")
        self.result_info_button.set_box_text("Adjust the control points for registration by dragging each marker on the target and moving images. \n\nZoom (scroll) and pan (drag) the images for more exact placement. \n\nClick 'Apply' to preview the registered 'aligned moving' image in a checkered split-view with the target image. \n\nClick 'Save as...' to save the registered image.")
        
        # Apply and save buttons
        self.result_button_widget = QtWidgets.QWidget()

        self.result_hide_apply_popup_checkbox = QtWidgets.QCheckBox("Hide 'Apply' reminder")
        self.result_hide_apply_popup_checkbox.setSizePolicy(QtWidgets.QSizePolicy.Maximum, QtWidgets.QSizePolicy.Preferred)
        self.result_apply_popup_is_hidden = False
        self.result_hide_apply_popup_checkbox.setChecked(self.result_apply_popup_is_hidden)
        self.result_hide_apply_popup_checkbox.toggled.connect(self.set_hidden_apply_popup)

        self.result_apply_button = QtWidgets.QPushButton("Apply")
        self.result_apply_button.setEnabled(False)
        self.result_apply_button.clicked.connect(self.register_and_load_result)

        self.result_save_button = QtWidgets.QPushButton("Save as...")
        self.result_save_button.setEnabled(False)
        self.result_save_button.clicked.connect(self.save_result)
        
        result_button_layout = QtWidgets.QHBoxLayout()
        result_button_layout.setContentsMargins(0,0,0,0)

        result_button_layout.addWidget(self.result_apply_button)
        result_button_layout.addWidget(self.result_hide_apply_popup_checkbox)
        result_button_layout.addWidget(self.result_save_button)

        self.result_button_widget.setLayout(result_button_layout)

        # Load and save control points
        self.control_points_widget = QtWidgets.QWidget()
        self.control_points_widget.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Maximum)

        self.control_points_load_button = QtWidgets.QPushButton("Load control points from .csv...")
        self.control_points_load_button.clicked.connect(self.on_click_load_points)
        self.control_points_save_button = QtWidgets.QPushButton("Save control points to .csv...")
        self.control_points_save_button.clicked.connect(self.on_click_save_points)

        control_points_button_layout = QtWidgets.QVBoxLayout()
        control_points_button_layout.setContentsMargins(0,0,0,0)

        control_points_button_layout.addWidget(self.control_points_load_button)
        control_points_button_layout.addWidget(self.control_points_save_button)
        control_points_button_layout.addStretch(1)

        self.control_points_widget.setLayout(control_points_button_layout)
        # self.control_points_widget.setEnabled(False)

        # Batch register and save
        self.result_batch_widget = QtWidgets.QWidget()
        self.result_batch_widget.setEnabled(False)

        self.result_batch_select_button = QtWidgets.QPushButton("Select image(s)...")
        # self.result_batch_select_button.setSizePolicy(QtWidgets.QSizePolicy.Maximum, QtWidgets.QSizePolicy.Maximum)
        self.result_batch_select_button.clicked.connect(self.select_batch_files)
        self.result_batch_select_button.setEnabled(False)
        self.filepaths_batch = None

        self.result_batch_folder_button = QtWidgets.QPushButton("Select destination folder...")
        # self.result_batch_folder_button.setSizePolicy(QtWidgets.QSizePolicy.Maximum, QtWidgets.QSizePolicy.Maximum)
        self.result_batch_folder_button.clicked.connect(self.select_batch_folder)
        self.result_batch_folder_button.setEnabled(False)
        self.folderpath_batch = None

        self.result_batch_save_button = QtWidgets.QPushButton("Register and save batch")
        self.result_batch_save_button.clicked.connect(self.save_batch)
        self.result_batch_save_button.setEnabled(False)

        self.result_batch_checkbox = QtWidgets.QCheckBox("Enable batch registration")
        self.result_batch_checkbox.toggled.connect(self.set_enabled_batch_buttons)

        result_batch_button_layout = QtWidgets.QVBoxLayout()
        result_batch_button_layout.setContentsMargins(0,0,0,0)
        
        result_batch_button_layout.addWidget(self.result_batch_checkbox)
        result_batch_button_layout.addWidget(self.result_batch_select_button)
        result_batch_button_layout.addWidget(self.result_batch_folder_button)
        result_batch_button_layout.addWidget(self.result_batch_save_button)

        self.result_batch_widget.setLayout(result_batch_button_layout)
        self.result_batch_widget.setSizePolicy(QtWidgets.QSizePolicy.Maximum, QtWidgets.QSizePolicy.Preferred)

        linev = QtWidgets.QFrame()
        linev.setFrameShape(QtWidgets.QFrame.VLine)
        linev.setFrameShadow(QtWidgets.QFrame.Sunken)

        self.result_layout.addWidget(result_title_label, 0, 0, 1, 3)
        self.result_layout.addWidget(self.result_placeholder_label, 1, 0, 1, 3)
        self.result_layout.addWidget(self.result_button_widget, 2, 0, 1, 3)
        self.result_layout.addWidget(self.control_points_widget, 3, 0, QtCore.Qt.AlignBottom)
        self.result_layout.addWidget(linev, 3, 1)
        self.result_layout.addWidget(self.result_batch_widget, 3, 2)

        self.result_widget = QtWidgets.QWidget()
        self.result_widget.setLayout(self.result_layout)

        result_splitter_layout = QtWidgets.QGridLayout()
        result_splitter_layout.setContentsMargins(0,0,0,0)
        result_splitter_layout.setSpacing(0)
        result_splitter_layout.addWidget(self.result_widget, 0, 0)
        result_splitter_layout.addWidget(self.result_info_button, 0, 0, QtCore.Qt.AlignTop|QtCore.Qt.AlignRight)
        result_splitter_widget = QtWidgets.QWidget()
        result_splitter_widget.setLayout(result_splitter_layout)
        
        self.viewer_result_isclosed = True
        self.set_enabled_result(False)

        # Splitter arrangment of viewers for ease of resizing
        splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        splitter.setChildrenCollapsible(False)

        splitter.addWidget(reference_splitter_widget)
        splitter.addWidget(toregister_splitter_widget)
        splitter.addWidget(result_splitter_widget)

        self.loading_grayout_label = QtWidgets.QLabel("Loading...")
        self.loading_grayout_label.setAlignment(QtCore.Qt.AlignCenter | QtCore.Qt.AlignVCenter)
        # self.loading_grayout_label.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents)
        self.loading_grayout_label.setVisible(False)
        self.loading_grayout_label.setStyleSheet("""
            QLabel { 
                background-color: rgba(255,255,255,223);
                } 
            """)

        # Layout of register tab
        register_layout = QtWidgets.QGridLayout()
        register_layout.addWidget(splitter, 0, 0)
        register_layout.addWidget(self.loading_grayout_label, 0, 0)

        self.setLayout(register_layout)

    def set_enabled_batch_buttons(self, boolean):
        """bool: Set enabled state of the batch registration buttons (convenience)."""
        self.result_batch_select_button.setEnabled(boolean)
        self.result_batch_folder_button.setEnabled(False)
        self.result_batch_save_button.setEnabled(False)

    def set_hidden_apply_popup(self, boolean):
        """bool: Hide reminder to click 'Apply' when control point(s) moved (convenience)."""
        self.result_apply_popup_is_hidden = boolean
        self.refresh_result_placeholder_label()
    
    def on_registration_point_emitted_reference(self, pos_on_scene, index):
        """Update the displayed coordinates of a given target control point.
        
        Triggered when a control point is moved on the reference image.
        
        Args:
            pos_on_scene (QPointF): The position on the scene of the control point.
            index (int): The index of the control point (which control point it is).
        """
        x = pos_on_scene.x()
        y = pos_on_scene.y()
        i = index + 1

        x_str = '{0:0.2f}'.format(x)
        y_str = '{0:0.2f}'.format(y)

        if i is 1:
            self.reference_point_label_x1.setText(x_str)
            self.reference_point_label_x1.value = x
            self.reference_point_label_y1.setText(y_str)
            self.reference_point_label_y1.value = y
        elif i is 2:
            self.reference_point_label_x2.setText(x_str)
            self.reference_point_label_x2.value = x
            self.reference_point_label_y2.setText(y_str)
            self.reference_point_label_y2.value = y
        elif i is 3:
            self.reference_point_label_x3.setText(x_str)
            self.reference_point_label_x3.value = x
            self.reference_point_label_y3.setText(y_str)
            self.reference_point_label_y3.value = y
        elif i is 4:
            self.reference_point_label_x4.setText(x_str)
            self.reference_point_label_x4.value = x
            self.reference_point_label_y4.setText(y_str)
            self.reference_point_label_y4.value = y

        self.points_reference[i-1][0] = x
        self.points_reference[i-1][1] = y

    def on_registration_point_emitted_toregister(self, pos_on_scene, index):
        """Update the displayed coordinates of a given moving control point.
        
        Triggered when a control point is moved on the to-be-registered image.
        
        Args:
            pos_on_scene (QPointF): The position on the scene of the control point.
            index (int): The index of the control point (which control point it is).
        """
        x = pos_on_scene.x()
        y = pos_on_scene.y()
        i = index + 1

        x_str = '{0:0.2f}'.format(x)
        y_str = '{0:0.2f}'.format(y)

        if i is 1:
            self.toregister_point_label_x1.setText(x_str)
            self.toregister_point_label_x1.value = x
            self.toregister_point_label_y1.setText(y_str)
            self.toregister_point_label_y1.value = y
        elif i is 2:
            self.toregister_point_label_x2.setText(x_str)
            self.toregister_point_label_x2.value = x
            self.toregister_point_label_y2.setText(y_str)
            self.toregister_point_label_y2.value = y
        elif i is 3:
            self.toregister_point_label_x3.setText(x_str)
            self.toregister_point_label_x3.value = x
            self.toregister_point_label_y3.setText(y_str)
            self.toregister_point_label_y3.value = y
        elif i is 4:
            self.toregister_point_label_x4.setText(x_str)
            self.toregister_point_label_x4.value = x
            self.toregister_point_label_y4.setText(y_str)
            self.toregister_point_label_y4.value = y

        self.points_toregister[i-1][0] = x
        self.points_toregister[i-1][1] = y

    def on_registration_point_changed(self):
        """Record that a registration point has changed on either image."""
        self.registration_point_changed_but_not_applied = True
        self.result_apply_button.setEnabled(True)
        self.result_save_button.setEnabled(False)
        self.refresh_result_placeholder_label()

    def load_reference(self, filename_main_topleft, filename_topright=None, filename_bottomleft=None, filename_bottomright=None):
        """Load an image as the target image.
        
        Args:
            filename_main_topleft (str): The image filepath for the reference image.
            filename_topright (str): Unused. Keep as None.
            filename_bottomleft (str): Unused. Keep as None.
            filename_bottomright (str): Unused. Keep as None.
        """
        self.display_loading_grayout(True, "Loading reference image...")

        self.fullpath_reference = filename_main_topleft
        
        self.pixmap_reference = QtGui.QPixmap(self.fullpath_reference)
        pixmap_topright = QtGui.QPixmap(filename_topright)
        pixmap_bottomleft = QtGui.QPixmap(filename_bottomleft)
        pixmap_bottomright = QtGui.QPixmap(filename_bottomright)

        angle = get_exif_rotation_angle(self.fullpath_reference)
        if angle:
            self.pixmap_reference = self.pixmap_reference.transformed(QtGui.QTransform().rotate(angle))

        self.viewer_reference = self.create_viewer_reference(self.pixmap_reference, self.fullpath_reference, pixmap_topright, pixmap_bottomleft, pixmap_bottomright)
        self.reference_layout.addWidget(self.viewer_reference, 1, 0)
        QtCore.QTimer.singleShot(50, self.viewer_reference.fitToWindow)
        QtCore.QTimer.singleShot(50, self.viewer_reference.emit_registration_points)

        # Registration
        self.image_reference_width = self.pixmap_reference.width()
        self.image_reference_height = self.pixmap_reference.height()
        self.viewer_reference.registration_point_emitted.connect(self.on_registration_point_emitted_reference)
        self.set_enabled_toregister(True)

        # Line edits
        self.reference_point_label_x1.changed_value.connect(self.viewer_reference.set_point)
        self.reference_point_label_y1.changed_value.connect(self.viewer_reference.set_point)
        self.reference_point_label_x2.changed_value.connect(self.viewer_reference.set_point)
        self.reference_point_label_y2.changed_value.connect(self.viewer_reference.set_point)
        self.reference_point_label_x3.changed_value.connect(self.viewer_reference.set_point)
        self.reference_point_label_y3.changed_value.connect(self.viewer_reference.set_point)
        self.reference_point_label_x4.changed_value.connect(self.viewer_reference.set_point)
        self.reference_point_label_y4.changed_value.connect(self.viewer_reference.set_point)

        self.display_loading_grayout(False)

    def create_viewer_reference(self, pixmap_main_topleft, filename_main_topleft, pixmap_topright=None, pixmap_bottomleft=None, pixmap_bottomright=None):
        """Create a viewer for the target image.

        Args:
            pixmap_main_topleft (QPixmap): The target image pixmap.
            filename_main_topleft (str): The target image filename.
            pixmap_topright (QPixmap): Unused. Keep as None.
            pixmap_bottomleft (QPixmap): Unused. Keep as None.
            pixmap_bottomright (QPixmap): Unused. Keep as None.

        Returns:
            viewer (RegisterView): The viewer instance.
        """
        name = "Reference"
        transform_mode_smooth = False
        viewer = RegisterView(pixmap_main_topleft, filename_main_topleft, name, pixmap_topright, pixmap_bottomleft, pixmap_bottomright, transform_mode_smooth)

        viewer.label_main_topleft.setText(filename_main_topleft)
        viewer.label_main_topleft.set_visible_based_on_text(True)

        viewer.was_clicked_close_pushbutton.connect(self.close_viewer_reference)
        viewer.registration_point_changed.connect(self.on_registration_point_changed)

        for button, point in zip(self.reference_point_undo_buttons, viewer.registration_points):
            button.set_control_point_widget(point)
            point.set_undo_widget(button)

        return viewer

    def close_viewer_reference(self):
        """Close the target image viewer."""

        box_type = QtWidgets.QMessageBox.Question
        title = "Close and reset control points?"

        if not self.viewer_toregister_isclosed:
            text = "Closing the reference image will also close the moving image and reset all control points."
        else:
            text = "Closing the reference image will reset its control points."
        
        box = QtWidgets.QMessageBox(box_type, title, text)
        box.addButton("Close and reset", QtWidgets.QMessageBox.AcceptRole)
        box.addButton("Cancel", QtWidgets.QMessageBox.RejectRole)
        response = box.exec_()

        if response != QtWidgets.QMessageBox.AcceptRole:
            return

        if response == QtWidgets.QMessageBox.AcceptRole:
        
            if self.viewer_reference:
                self.viewer_reference.close()
                self.viewer_reference.deleteLater()
                del self.pixmap_reference
                if not self.viewer_toregister_isclosed:
                    self.close_viewer_toregister(bypass_message=True)
                self.set_enabled_toregister(False)
                for button in self.reference_point_undo_buttons:
                    button.set_control_point_widget(None)

    def dragged_and_dropped_reference(self, str):
        """str: Load the target image from a drag-and-drop filepath signal."""
        self.load_reference(filename_main_topleft=str)

    def select_via_dialog_reference(self):
        """Select and load the target image via dialog window."""
        self.display_loading_grayout(True, "Selecting reference image...")

        filepath = self.fullpath_reference
        filters = "\
            All supported image files (*.jpeg *.jpg  *.png *.tiff *.tif *.gif *.bmp);;\
            JPEG image files (*.jpeg *.jpg);;\
            PNG image files (*.png);;\
            TIFF image files (*.tiff *.tif);;\
            BMP (*.bmp)"
        filename, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Select reference image", filepath, filters)

        if filename:
            self.display_loading_grayout(False, pseudo_load_time=0)
            self.load_reference(filename_main_topleft=filename)
        else:
            self.display_loading_grayout(False, pseudo_load_time=0)

    # "To register" functions for the image which is to be registered to the reference image
    def load_toregister(self, filename_main_topleft, filename_topright=None, filename_bottomleft=None, filename_bottomright=None):
        """Load an image as the moving image.

        Resizes and pads the moving image to match the dimensions of the target image.
        
        Args:
            filename_main_topleft (str): The image filepath for the to-be-registered image.
            filename_topright (str): Unused. Keep as None.
            filename_bottomleft (str): Unused. Keep as None.
            filename_bottomright (str): Unused. Keep as None.
        """
        self.display_loading_grayout(True, "Loading image to be registered...")

        self.fullpath_toregister = filename_main_topleft

        # Load image
        if self.fullpath_toregister.endswith(".png"): # Preserve the alpha channel if a PNG.
            self.image_toregister = imread(self.fullpath_toregister, IMREAD_UNCHANGED)
            if self.image_toregister.ndim is 2: # ...but if the PNG is monochannel, redo the imread and let cv2 determine how.
                self.image_toregister = imread(self.fullpath_toregister) 
        else:
            self.image_toregister = imread(self.fullpath_toregister)
        self.image_toregister = self.image_toregister.astype('uint8')
        self.image_toregister_dims = self.image_toregister.shape
        self.image_toregister_height = self.image_toregister_dims[0]
        self.image_toregister_width = self.image_toregister_dims[1]

        aspect_reference = self.image_reference_width/self.image_reference_height # W/H (e.g., 4:3)
        aspect_toregister = self.image_toregister_width/self.image_toregister_height # w/h (e.g., 16:9)

        if aspect_toregister > aspect_reference: # If the toregister is wider than the reference, resize toregister to match widths
            self.image_toregister_resize_width = self.image_reference_width
            self.image_toregister_resize_height = int(self.image_toregister_resize_width/aspect_toregister)
        else: # If the toregister is narrower or equi-aspect to the reference, resize toregister to match heights
            self.image_toregister_resize_height = self.image_reference_height
            self.image_toregister_resize_width = int(self.image_toregister_resize_height*aspect_toregister)
            
        self.image_toregister_resize_dims = (self.image_toregister_resize_width, self.image_toregister_resize_height)
        self.image_toregister_resize = resize(self.image_toregister, self.image_toregister_resize_dims, interpolation = INTER_AREA)

        # Pad
        # If the toregister is shorter in aspect than the reference, pad the height [rows] to match heights
        # If the toregister is narrower in aspect than the reference, pad the width [columns] to match widths
        add_rows = self.image_reference_height - self.image_toregister_resize_height
        add_cols = self.image_reference_width - self.image_toregister_resize_width
        if self.image_toregister.ndim is 2:
            self.image_toregister_resize = np.pad(self.image_toregister_resize, ((0,add_rows), (0,add_cols)), 'constant')
        else:
            self.image_toregister_resize = np.pad(self.image_toregister_resize, ((0,add_rows), (0,add_cols), (0,0)), 'constant')

        self.image_toregister_resize_width += add_cols
        self.image_toregister_resize_height += add_rows

        # Convert cvImage to QPixmap
        height, width, channels = self.image_toregister_resize.shape
        
        total_bytes = self.image_toregister_resize.nbytes
        bytes_per_line = int(total_bytes/height)
        # bytes_per_line = width*3
        if channels is 4:
            qimage = QtGui.QImage(self.image_toregister_resize.data, width, height, bytes_per_line, QtGui.QImage.Format_RGBA8888).rgbSwapped()
        else:
            qimage = QtGui.QImage(self.image_toregister_resize.data, width, height, bytes_per_line, QtGui.QImage.Format_RGB888).rgbSwapped()

        self.pixmap_toregister_resize = QtGui.QPixmap(qimage)
        pixmap_topright = QtGui.QPixmap(filename_topright)
        pixmap_bottomleft = QtGui.QPixmap(filename_bottomleft)
        pixmap_bottomright = QtGui.QPixmap(filename_bottomright)

        self.viewer_toregister = self.create_viewer_toregister(self.pixmap_toregister_resize, self.fullpath_toregister, pixmap_topright, pixmap_bottomleft, pixmap_bottomright)
        self.toregister_layout.addWidget(self.viewer_toregister, 1, 0)
        
        self.viewer_toregister.zoomFactor = self.viewer_reference.zoomFactor
        QtCore.QTimer.singleShot(50, self.viewer_toregister.centerView)
        QtCore.QTimer.singleShot(50, self.viewer_toregister.emit_registration_points)
        
        self.viewer_toregister.registration_point_emitted.connect(self.on_registration_point_emitted_toregister)

        self.set_enabled_result(True)
        self.result_apply_button.setEnabled(True)
        self.result_batch_widget.setEnabled(True)

        self.viewer_toregister_isclosed = False

        self.viewer_reference.emit_registration_points()
        self.viewer_toregister.emit_registration_points()

        # Line edits
        self.toregister_point_label_x1.changed_value.connect(self.viewer_toregister.set_point)
        self.toregister_point_label_y1.changed_value.connect(self.viewer_toregister.set_point)
        self.toregister_point_label_x2.changed_value.connect(self.viewer_toregister.set_point)
        self.toregister_point_label_y2.changed_value.connect(self.viewer_toregister.set_point)
        self.toregister_point_label_x3.changed_value.connect(self.viewer_toregister.set_point)
        self.toregister_point_label_y3.changed_value.connect(self.viewer_toregister.set_point)
        self.toregister_point_label_x4.changed_value.connect(self.viewer_toregister.set_point)
        self.toregister_point_label_y4.changed_value.connect(self.viewer_toregister.set_point)

        self.display_loading_grayout(False)

    def create_viewer_toregister(self, pixmap_main_topleft, filename_main_topleft, pixmap_topright=None, pixmap_bottomleft=None, pixmap_bottomright=None):
        """Create a viewer for the moving image.

        Args:
            pixmap_main_topleft (QPixmap): The moving image pixmap.
            filename_main_topleft (str): The moving image filename.
            pixmap_topright (QPixmap): Unused. Keep as None.
            pixmap_bottomleft (QPixmap): Unused. Keep as None.
            pixmap_bottomright (QPixmap): Unused. Keep as None.

        Returns:
            viewer (RegisterView): The viewer instance.
        """
        name = "To be registered"
        transform_mode_smooth = False
        viewer = RegisterView(pixmap_main_topleft, filename_main_topleft, name, pixmap_topright, pixmap_bottomleft, pixmap_bottomright, transform_mode_smooth)

        viewer.label_main_topleft.setText(filename_main_topleft)
        viewer.label_main_topleft.set_visible_based_on_text(True)

        viewer.was_clicked_close_pushbutton.connect(self.close_viewer_toregister)
        viewer.registration_point_changed.connect(self.on_registration_point_changed)

        for button, point in zip(self.toregister_point_undo_buttons, viewer.registration_points):
            button.set_control_point_widget(point)
            point.set_undo_widget(button)

        return viewer

    def close_viewer_toregister(self, bypass_message=False):
        """Close the moving image viewer."""

        response = QtWidgets.QMessageBox.RejectRole

        if not bypass_message:
            box_type = QtWidgets.QMessageBox.Question
            title = "Close and reset control points?"
            text = "Closing the moving image will reset its control points."
            box = QtWidgets.QMessageBox(box_type, title, text)
            box.addButton("Close and reset", QtWidgets.QMessageBox.AcceptRole)
            box.addButton("Cancel", QtWidgets.QMessageBox.RejectRole)
            response = box.exec_()

            if response != QtWidgets.QMessageBox.AcceptRole:
                return

        if bypass_message or (response == QtWidgets.QMessageBox.AcceptRole):

            if not self.viewer_toregister_isclosed:

                self.viewer_toregister.close()
                self.viewer_toregister.deleteLater()
                del self.pixmap_toregister_resize
                self.image_toregister = None
                self.viewer_toregister_isclosed = True

                for button in self.toregister_point_undo_buttons:
                    button.set_control_point_widget(None)

                self.result_widget.setEnabled(False)

                if not self.viewer_result_isclosed:
                    self.close_viewer_result()

                self.set_enabled_result(False)
                self.result_apply_button.setEnabled(False)
                self.result_save_button.setEnabled(False)
                self.result_batch_widget.setEnabled(False)
                self.filepaths_batch = None
                self.folderpath_batch = None
                self.result_batch_checkbox.setChecked(False)
                self.result_batch_folder_button.setEnabled(False)
                self.result_batch_save_button.setEnabled(False)

    def dragged_and_dropped_toregister(self, str):
        """str: Load the moving image from a drag-and-drop filepath signal."""
        self.load_toregister(filename_main_topleft=str)

    def select_via_dialog_toregister(self):
        """Select and load the moving image via dialog window."""
        self.display_loading_grayout(True, "Selecting image to be registered...")

        filepath = self.fullpath_toregister
        if filepath is None: filepath = self.fullpath_reference
        filters = "\
            All supported image files (*.jpeg *.jpg  *.png *.tiff *.tif *.gif *.bmp);;\
            JPEG image files (*.jpeg *.jpg);;\
            PNG image files (*.png);;\
            TIFF image files (*.tiff *.tif);;\
            BMP (*.bmp)"
        filename, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Select image to be registered", filepath, filters)

        if filename:
            self.display_loading_grayout(False, pseudo_load_time=0)
            self.load_toregister(filename_main_topleft=filename)
        else:
            self.display_loading_grayout(False, pseudo_load_time=0)

    # Result
    def register_and_load_result(self):
        """Register the moving image and load the preview in a split-view with the target image."""
        self.result_apply_button.setEnabled(False)
        self.registration_point_changed_but_not_applied = False

        self.display_loading_grayout(True, "Registering and loading preview...")
        
        self.register_result()
        self.load_result()       
        self.result_save_button.setEnabled(True)
                
        self.display_loading_grayout(False)

    def register_result(self):
        """Register the moving image."""
        points_source = self.points_toregister
        points_destination = self.points_reference

        image = self.image_toregister_resize
        width = self.image_toregister_resize_width
        height = self.image_toregister_resize_height
        size = (width, height)

        transform = getPerspectiveTransform(points_source, points_destination)

        self.image_registered = warpPerspective(image, transform, size)

        # Convert cvImage to QPixmap
        height, width, channels = self.image_registered.shape
        total_bytes = self.image_registered.nbytes
        bytes_per_line = int(total_bytes/height)
        if channels is 4:
            qimage = QtGui.QImage(self.image_registered.data, width, height, bytes_per_line, QtGui.QImage.Format_RGBA8888).rgbSwapped()
        else:
            qimage = QtGui.QImage(self.image_registered.data, width, height, bytes_per_line, QtGui.QImage.Format_RGB888).rgbSwapped()

        self.pixmap_registered = QtGui.QPixmap(qimage)

    def load_result(self):
        """Load the registered image into a viewer."""
        if not self.viewer_result_isclosed:
            self.viewer_result.close()
            self.viewer_result.deleteLater()

        self.filename_result_reference = self.fullpath_reference
        self.filename_result_registered = self.fullpath_toregister
        
        # Split view left=reference, right=registered
        pixmap = self.pixmap_reference
        pixmap_topright = self.pixmap_registered
        pixmap_bottomright = self.pixmap_registered
        pixmap_bottomleft = self.pixmap_registered

        self.viewer_result = self.create_viewer_result(pixmap, self.filename_result_reference, pixmap_topright, pixmap_bottomleft, pixmap_bottomright)
        self.result_layout.addWidget(self.viewer_result, 1, 0, 1, 3)
        
        QtCore.QTimer.singleShot(50, self.viewer_result.fitToWindow)

        self.viewer_result_isclosed = False
        self.refresh_result_placeholder_label()

    def create_viewer_result(self, pixmap_main_topleft, filename_main_topleft, pixmap_topright=None, pixmap_bottomleft=None, pixmap_bottomright=None):
        """Create a viewer for the registered moving image.

        Args:
            pixmap_main_topleft (QPixmap): The registered image pixmap.
            filename_main_topleft (str): The registered image filename.
            pixmap_topright (QPixmap): Unused. Keep as None.
            pixmap_bottomleft (QPixmap): Unused. Keep as None.
            pixmap_bottomright (QPixmap): Unused. Keep as None.

        Returns:
            viewer (RegisterView): The viewer instance.
        """
        name = "Result"
        viewer = ResultView(pixmap_main_topleft, filename_main_topleft, name,
            pixmap_topright, pixmap_bottomleft, pixmap_bottomright, transform_mode_smooth=False)
        viewer.label_main_topleft.setText(self.filename_result_reference)
        viewer.label_main_topleft.set_visible_based_on_text(True)
        suffix = "_registered_to_" + os.path.basename(self.fullpath_reference).split('.')[0] + "."
        viewer.label_bottomleft.setText(self.filename_result_registered.replace('.', suffix))
        viewer.label_bottomleft.set_visible_based_on_text(True)
        opacity_topright = 33
        opacity_bottomright = 66
        viewer.set_opacity_topright(opacity_topright)
        viewer.set_opacity_bottomright(opacity_bottomright)
        viewer.label_topright.setText(f"Registered {opacity_topright}% overlayed")
        viewer.label_topright.set_visible_based_on_text(True)
        viewer.label_bottomright.setText(f"Registered {opacity_bottomright}% overlayed")
        viewer.label_bottomright.set_visible_based_on_text(True)

        viewer.was_clicked_close_pushbutton.connect(self.close_viewer_result)

        return viewer

    def close_viewer_result(self):
        """Close the registered image viewer."""
        if not self.viewer_result_isclosed:
            self.viewer_result.close()
            self.viewer_result.deleteLater()
            del self.pixmap_registered
            self.image_registered = None
            self.viewer_result_isclosed = True
            self.result_apply_button.setEnabled(True)
        self.result_save_button.setEnabled(False)
        self.refresh_result_placeholder_label()

    def save_result(self):
        """Open a save dialog window to save the registered image to file."""
        self.display_loading_grayout(True, "Saving registered image...")

        fullpath_initial = self.fullpath_toregister
        suffix = "_registered_to_" + os.path.basename(self.fullpath_reference).split('.')[0] + "."
        fullpath_initial = fullpath_initial.replace('.', suffix)

        name_filters = "JPEG (*.jpeg);; JPG (*.jpg);; PNG (*.png);; TIFF (*.tiff);; TIF (*.tif);; BMP (*.bmp)"

        selected_filter = None

        if fullpath_initial.endswith('.jpeg'):
            selected_filter = "JPEG (*.jpeg)"
        elif fullpath_initial.endswith('.jpg'):
            selected_filter = "JPG (*.jpg)"
        elif fullpath_initial.endswith('.png'):
            selected_filter = "PNG (*.png)"
        elif fullpath_initial.endswith('.tiff'):
            selected_filter = "TIFF (*.tiff)"
        elif fullpath_initial.endswith('.tif'):
            selected_filter = "TIF (*.tif)"
        elif fullpath_initial.endswith('.bmp'):
            selected_filter = "BMP (*.bmp)"

        fullpath_selected, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Save registered image", fullpath_initial, name_filters, selected_filter)

        if fullpath_selected:
            self.display_loading_grayout(True, "Saving registered image '" + fullpath_selected.split("/")[-1] + "'...")
            if fullpath_selected.endswith('.jpg') or fullpath_selected.endswith('.jpeg'):
                imwrite(fullpath_selected, self.image_registered, [int(IMWRITE_JPEG_QUALITY), 100])
            else:
                imwrite(fullpath_selected, self.image_registered)

            box_type = QtWidgets.QMessageBox.Question
            title = "Auto-save control points?"
            text = "Do you also want to save the control points?"
            text += "\n\nThis will automatically save them to .csv control point file in the same directory as the registered image. You can then later load and redo the registration if needed."
            box = QtWidgets.QMessageBox(box_type, title, text)
            box.addButton("Auto-save control points", QtWidgets.QMessageBox.AcceptRole)
            box.addButton("Skip", QtWidgets.QMessageBox.RejectRole)
            response = box.exec_()

            if response == QtWidgets.QMessageBox.AcceptRole:

                directory_csv = os.path.dirname(fullpath_selected)
                directory_csv = directory_csv + "\\"
                filename_csv = self.generate_points_filename()
                fullpath_csv = directory_csv + filename_csv

                filename_reference = os.path.basename(self.fullpath_reference)
                filename_toregister = os.path.basename(self.fullpath_toregister)

                points_reference = self.points_reference 
                points_toregister = self.points_toregister

                self.save_points(fullpath_csv,
                                filename_reference, points_reference, 
                                [filename_toregister], points_toregister)

        self.display_loading_grayout(False)

    def select_batch_files(self):
        """Open an open dialog window to select images to batch register."""
        self.display_loading_grayout(True, "Selecting image(s) to batch register...")

        filepath = self.fullpath_toregister
        filters = "\
            All supported image files (*.jpeg *.jpg  *.png *.tiff *.tif *.gif *.bmp);;\
            JPEG image files (*.jpeg *.jpg);;\
            PNG image files (*.png);;\
            TIFF image files (*.tiff *.tif);;\
            BMP (*.bmp)"
        filenames, _ = QtWidgets.QFileDialog.getOpenFileNames(self, "Select image(s) to batch register", filepath, filters)

        if filenames:
            self.filepaths_batch = filenames
            self.result_batch_folder_button.setEnabled(True)
        else:
            self.result_batch_folder_button.setEnabled(False)
            self.result_batch_save_button.setEnabled(False)

        self.display_loading_grayout(False)

    def select_batch_folder(self):
        """Open an open dialog window to select a destination folder to which to save the batch-registered file(s)."""
        self.display_loading_grayout(True, "Selecting folder to save batch registered image(s)...")

        filepath = QtWidgets.QFileDialog.getExistingDirectory(self, "Select folder")

        if filepath:
            self.folderpath_batch = filepath
            self.result_batch_save_button.setEnabled(True)
        else:
            self.result_batch_save_button.setEnabled(False)

        self.display_loading_grayout(False)

    def save_batch(self):
        """Register and save the selected batch files to the selected destination folder."""
        self.display_loading_grayout(True, "Registering and saving batch image(s)...")

        one_or_more_images_mismatch = False

        fullpaths = self.filepaths_batch
        folderpath = self.folderpath_batch

        one_or_more_already_exists = False

        for fullpath in fullpaths:
            fullpath_intended = self.generate_registered_fullpath(folderpath, fullpath)[0]
            if os.path.isfile(fullpath_intended):
                one_or_more_already_exists = True

        if one_or_more_already_exists:
            box_type = QtWidgets.QMessageBox.Warning
            title = "Overwrite already registered files?"
            text = "One or more of the images you selected already exist as registered images in the selected destination folder."
            box = QtWidgets.QMessageBox(box_type, title, text)
            box.addButton("Overwrite and proceed", QtWidgets.QMessageBox.AcceptRole)
            box.addButton("Cancel", QtWidgets.QMessageBox.RejectRole)
            response = box.exec_()

            if response != QtWidgets.QMessageBox.AcceptRole:
                self.display_loading_grayout(False)
                return
        
        fullpaths_successful = []

        for i, fullpath in enumerate(fullpaths):

            text = "Registering batch image '" + fullpath.split("/")[-1] + "' (" + str(i+1) + "/" + str(len(fullpaths)) + ")..."
            self.display_loading_grayout(True, text)

            image_registered = self.read_resize_pad_register(fullpath)

            if image_registered is not False:
                
                fullpath_registered, filename_registered = self.generate_registered_fullpath(folderpath, fullpath)

                text = "Saving batch image '" + filename_registered + "' (" + str(i+1) + "/" + str(len(fullpaths)) + ")..."
                self.display_loading_grayout(True, text)
                
                if fullpath_registered.endswith('.jpg') or fullpath_registered.endswith('.jpeg'):
                    imwrite(fullpath_registered, image_registered, [int(IMWRITE_JPEG_QUALITY), 100])
                else:
                    imwrite(fullpath_registered, image_registered)

                fullpaths_successful.append(fullpath)
            else:
                one_or_more_images_mismatch = True

            QtWidgets.QApplication.processEvents()

        box_type = QtWidgets.QMessageBox.Information
        title = "Batch complete"
        text = "Batch registration and saving is complete."
        box_buttons = QtWidgets.QMessageBox.Close
        box = QtWidgets.QMessageBox(box_type, title, text, box_buttons)
        box.exec_()

        if one_or_more_images_mismatch:
            box_type = QtWidgets.QMessageBox.Warning
            title = "One or more unsuccessful registrations"
            text = "One or more images selected in the batch were not registered. Their height and width do not match those of the moving image where the control points are set."
            box_buttons = QtWidgets.QMessageBox.Close
            box = QtWidgets.QMessageBox(box_type, title, text, box_buttons)
            box.exec_()

        if len(fullpaths_successful) > 0:
            box_type = QtWidgets.QMessageBox.Question
            title = "Auto-save control points?"
            text = "Do you also want to save the control points?"
            text += "\n\nThis will auto-save them to .csv in the same directory as the registered images, allowing you to load and redo the registration if needed."
            box = QtWidgets.QMessageBox(box_type, title, text)
            box.addButton("Auto-save control points", QtWidgets.QMessageBox.AcceptRole)
            box.addButton("Skip", QtWidgets.QMessageBox.RejectRole)
            response = box.exec_()

            if response == QtWidgets.QMessageBox.AcceptRole:

                directory_csv = folderpath
                directory_csv = directory_csv + "\\"
                filename_csv = self.generate_points_filename(batch=True)
                fullpath_csv = directory_csv + filename_csv

                filename_reference = os.path.basename(self.fullpath_reference)
                filenames_toregister = []
                for fullpath in fullpaths_successful:
                    filenames_toregister.append(os.path.basename(fullpath))

                points_reference = self.points_reference 
                points_toregister = self.points_toregister

                self.save_points(fullpath_csv,
                                filename_reference, points_reference, 
                                filenames_toregister, points_toregister)

        self.display_loading_grayout(False)

    def on_click_save_points(self):
        """Opens dialog to specify filename where to save control points of target and moving images."""
        self.display_loading_grayout(True, "Saving control points...")

        if self.viewer_toregister_isclosed:
            return

        filename_reference = os.path.basename(self.fullpath_reference)
        filename_toregister = os.path.basename(self.fullpath_toregister)
        points_reference = self.points_reference 
        points_toregister = self.points_toregister

        directory_default = None

        if self.fullpath_toregister:
            directory_default = os.path.dirname(self.fullpath_toregister)
            directory_default = directory_default + "\\"
        else:
            self.display_loading_grayout(False, pseudo_load_time=0)
            return

        filename = self.generate_points_filename()
        name_filters = "CSV (*.csv)" # Allows users to select filetype of screenshot
        
        fullpath, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Save current control points of target and moving images to .csv", directory_default+filename, name_filters)

        if fullpath:
            self.save_points(fullpath,
                             filename_reference, points_reference, 
                             [filename_toregister], points_toregister)
        
        self.display_loading_grayout(False)

    def generate_points_filename(self, batch: bool=False):
        """str: Returns default filename for control points .csv."""
        filename_reference = os.path.basename(self.fullpath_reference)
        filename_toregister = os.path.basename(self.fullpath_toregister)

        date_and_time = datetime.now().strftime('%Y-%m-%d %H%M%S') # Sets the default filename with date and time 

        if batch:
            filename_toregister = "Batch"

        filename_csv = "Registration points" + " - " + filename_toregister.split('.')[0] + " to " + filename_reference.split('.')[0] + " - " + date_and_time + ".csv"

        return filename_csv
    
    def generate_registered_fullpath(self, folderpath: str=None, fullpath_toregister: str=None):
        """str: Returns default fullpath and filename for an image to be registered given a destination folder."""
        fullpath_registered = None
        filename_registered = fullpath_toregister.split("/")[-1]
        suffix = "_registered_to_" + os.path.basename(self.fullpath_reference).split('.')[0] + "."
        filename_registered = filename_registered.replace('.', suffix)
        if folderpath:
            fullpath_registered = folderpath + "/" + filename_registered

        return fullpath_registered, filename_registered
    

    def on_click_load_points(self):
        """Opens dialog to open .csv file of control points."""
        self.display_loading_grayout(True, "Selecting .csv file to load control points...")

        if self.viewer_toregister_isclosed:
            return
        
        directory_default = None

        if self.fullpath_toregister:
            directory_default = os.path.dirname(self.fullpath_toregister)
            directory_default = directory_default + "\\"
        else:
            self.display_loading_grayout(False, pseudo_load_time=0)
            return
        
        fullpath, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Select control point file (.csv) to load", directory_default, "Comma-Separated Value File (*.csv)")

        filename_reference = os.path.basename(self.fullpath_reference)
        filename_toregister = os.path.basename(self.fullpath_toregister)
        
        points_reference, points_toregister = self.load_points(fullpath, filename_reference, filename_toregister)

        self.set_points(points_reference, points_toregister)

        self.display_loading_grayout(False)

    def load_points(self,
                    fullpath: str=None,
                    filename_reference: str=None,
                    filename_toregister: str=None):
        """Get control points from .csv to target and moving images.

        Checks whether current target image and moving image are those in the .csv file.

        Args:
            fullpath (str): Absolute path of .csv of control points to be loaded.
            filename_reference (str): Filename of current target image.
            filename_toregister (list of str): Filename of current moving image.

        Returns:
            points_reference (list): Control points of target image in format [ [X1, Y1], [X2, Y2], ... ]
            points_toregister (list): Control points of moving image in format [ [X1, Y1], [X2, Y2], ... ]
        """
        
        points_reference = []
        points_toregister = []

        if fullpath:

            with open(fullpath, "r", newline='') as csv_file:
                csv_reader = csv.reader(csv_file, delimiter="|")
                csv_list = list(csv_reader)

            i = None

            try:
                i = csv_list.index(["target"])
            except ValueError:
                box_type = QtWidgets.QMessageBox.Warning
                title = "Invalid .csv control point file"
                text = "The selected .csv control point file does not have a format accepted by this app."
                box_buttons = QtWidgets.QMessageBox.Close
                box = QtWidgets.QMessageBox(box_type, title, text, box_buttons)
                box.exec_()
            else:
                skip_reference = False
                skip_toregister = False

                i += 1 # Move to target filename
                if not csv_list[i][0] == filename_reference:
                    box_type = QtWidgets.QMessageBox.Warning
                    title = "Filename mismatch target image"
                    text = "The filename of the reference image (the target image) does not match the target filename in the control point file."
                    box = QtWidgets.QMessageBox(box_type, title, text)
                    box.addButton("Load reference points anyway", QtWidgets.QMessageBox.AcceptRole)
                    box.addButton("Cancel", QtWidgets.QMessageBox.RejectRole)
                    response = box.exec_()
                    if response != QtWidgets.QMessageBox.AcceptRole:
                        skip_reference = True

                i += 2 # Move to moving filename
                try:
                    csv_list[i].index(filename_toregister)
                except ValueError:
                    box_type = QtWidgets.QMessageBox.Warning
                    title = "Filename mismatch moving image"
                    text = "The filename of the to-be-registered image (the moving image) does not match any moving filenames in the control point file."
                    box = QtWidgets.QMessageBox(box_type, title, text)
                    box.addButton("Load moving points anyway", QtWidgets.QMessageBox.AcceptRole)
                    box.addButton("Cancel", QtWidgets.QMessageBox.RejectRole)
                    response = box.exec_()
                    if response != QtWidgets.QMessageBox.AcceptRole:
                        skip_toregister = True

                i += 2 # Move to XY pairs
                point = -1
                for row in csv_list[i:]:
                    point += 1
                    if not skip_reference:
                        points_reference.append([float(row[0]), float(row[1])])
                        if not skip_toregister:
                            points_toregister.append([float(row[2]), float(row[3])])

        return points_reference, points_toregister           
        
    def set_points(self,
                    points_reference,
                    points_toregister):
        """Set positions of control points for reference and to-register images.
        
        Args:
            points_reference (list): Control points of target image in format [ [X1, Y1], [X2, Y2], ... ].
            points_toregister (list): Control points of moving image in format [ [X1, Y1], [X2, Y2], ... ].
        """
        self.viewer_reference.set_points(points_reference)
        self.viewer_toregister.set_points(points_toregister)

    def save_points(self, 
                    fullpath: str=None,
                    filename_reference: str=None, points_reference: list=None, 
                    filename_toregister: list=None, points_toregister: list=None):
        """Save the control points of the target image and moving image to a .csv with a given filepath.
        
        Args:
            fullpath (str): Absolute path of .csv to be saved.
            filename_reference (str): Filename of target image. Can be produced with os.path.basename(fullpath. Example: "image.jpg".
            points_reference (list): Control points of target image in format: [ [X1, Y1], [X2, Y2], ... ]
            filename_toregister (list of str): Filename(s) of moving image(s).
            points_toregister (list): Control points of moving image.
        """
        # Check if all inputs exist
        if filename_reference is None:
            return 
        elif points_reference is None:
            return
        elif filename_toregister is None:
            return
        elif points_toregister is None:
            return
        elif len(points_reference) != len(points_toregister):
            return
        
        x_reference = []
        y_reference = []
        x_toregister = []
        y_toregister = []
        
        header = [["Butterfly Registrator"],
                  [__version__],
                  ["control points"],
                  ["Assumes moving image(s) resized and padded to match target image dimensions"],
                  ["target"],
                  [filename_reference],
                  ["moving"],
                  filename_toregister,
                  ["x", "y", "x", "y"]]
        
        for point_reference, point_toregister in zip(points_reference, points_toregister):
            x_reference.append(point_reference[0])
            y_reference.append(point_reference[1])
            x_toregister.append(point_toregister[0])
            y_toregister.append(point_toregister[1])


        with open(fullpath, "w", newline='') as csv_file:
            csv_writer = csv.writer(csv_file, delimiter="|")
            for row in header:
                csv_writer.writerow(row)
            for row in zip(x_reference, y_reference, x_toregister, y_toregister):
                csv_writer.writerow(row)

    def read_resize_pad_register(self, filename):
        """Read, resize, and register an image file with the last applied homography.
        
        Args:
            filename (str): The absolute filepath to the image.
            
        Returns:
            image_registered (cvImage, bool): Registered image if successful; False if dimensions do not match those of base moving image."""

        points_source = self.points_toregister
        points_destination = self.points_reference

        filename_toregister = filename

        # Load image to be registered
        if filename_toregister.endswith(".png"): # Preserve the alpha channel if a PNG.
            image_toregister = imread(filename_toregister, IMREAD_UNCHANGED)
            if image_toregister.ndim is 2: # ...but if the PNG is monochannel, redo the imread and let cv2 determine how.
                image_toregister = imread(filename_toregister) 
        else:
            image_toregister = imread(filename_toregister)
        image_toregister = image_toregister.astype('uint8')
        image_toregister_dims = image_toregister.shape
        image_toregister_height = image_toregister_dims[0]
        image_toregister_width = image_toregister_dims[1]

        if (image_toregister_height != self.image_toregister_height) or (image_toregister_width != self.image_toregister_width):
            return False

        # Resize
        aspect_reference = self.image_reference_width/self.image_reference_height # W/H (e.g., 4:3)
        aspect_toregister = image_toregister_width/image_toregister_height # w/h (e.g., 16:9)

        if aspect_toregister > aspect_reference: # If the toregister is wider than the reference, resize toregister to match widths
            image_toregister_resize_width = self.image_reference_width
            image_toregister_resize_height = int(image_toregister_resize_width/aspect_toregister)
        else: # If the toregister narrower or equi-aspect to the reference, resize toregister to match heights
            image_toregister_resize_height = self.image_reference_height
            image_toregister_resize_width = int(image_toregister_resize_height*aspect_toregister)
            
        image_toregister_resize_dims = (image_toregister_resize_width, image_toregister_resize_height)
        image_toregister_resize = resize(image_toregister, image_toregister_resize_dims, interpolation = INTER_AREA)

        # Pad
        # If the toregister is shorter in aspect than the reference, pad the height [rows] to match heights
        # If the toregister is narrower in aspect than the reference, pad the width [columns] to match widths
        add_rows = self.image_reference_height - image_toregister_resize_height
        add_cols = self.image_reference_width - image_toregister_resize_width
        if image_toregister.ndim is 2:
            image_toregister_resize = np.pad(image_toregister_resize, ((0,add_rows), (0,add_cols)), 'constant')
        else:
            image_toregister_resize = np.pad(image_toregister_resize, ((0,add_rows), (0,add_cols), (0,0)), 'constant')

        image_toregister_resize_width += add_cols
        image_toregister_resize_height += add_rows

        image = image_toregister_resize
        width = image_toregister_resize_width
        height = image_toregister_resize_height
        size = (width, height)

        transform = getPerspectiveTransform(points_source, points_destination)

        image_registered = warpPerspective(image, transform, size)

        return image_registered

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
        self.loading.emit(boolean)

    def set_enabled_toregister(self, boolean):
        """bool: Set enabled state and stylesheet of target image widget."""
        self.toregister_widget.setEnabled(boolean)
        if boolean:
            self.toregister_drag_label.setStyleSheet("""
                QLabel { 
                    font-size: 10pt;
                    border: 0.15em dashed gray;
                    border-radius: 0.3em;
                    background-color: transparent;
                    padding: 1.2em;
                    } 
                """)
        else:
            self.toregister_drag_label.setStyleSheet("""
                QLabel { 
                    font-size: 10pt;
                    border: 0.15em dashed lightGray;
                    border-radius: 0.3em;
                    background-color: transparent;
                    padding: 1.2em;
                    } 
                """)

    def set_enabled_result(self, boolean):
        """bool: Set enabled state and stylesheet of registered image preview widget."""
        self.result_widget.setEnabled(boolean)
        self.refresh_result_placeholder_label()
    
    def refresh_result_placeholder_label(self):
        if self.result_widget.isEnabled():
            self.result_placeholder_label.setStyleSheet("""
                QLabel {
                    font-size: 10pt;
                    color: white;
                    border: 0.15em solid gray;
                    background-color: rgba(31,31,31,223);
                    padding: 1.2em;
                    } 
                """)
        else:
            self.result_placeholder_label.setStyleSheet("""
                QLabel { 
                    font-size: 10pt;
                    color: white;
                    border: 0.15em solid lightGray;
                    background-color: rgba(31,31,31,223);
                    padding: 1.2em;
                    } 
                """)
        if (not self.result_apply_popup_is_hidden) and self.registration_point_changed_but_not_applied:
            self.result_placeholder_label.raise_()
        else:
            self.result_placeholder_label.lower()
        if not self.viewer_result_isclosed:
            text = self.result_placeholder_text_refresh
        else:
            text = self.result_placeholder_text_default
        self.result_placeholder_label.setText(text)


class MainWindow(QtWidgets.QMainWindow):
    """QMainWindow with tabs for image registration and alphascale creation.
    
    Instantiate without input. See parent class for documentation.
    """

    def __init__(self):
        super().__init__()
        self.setWindowTitle(APPNAME)

        self.register_widget = Registrator()
        self.register_widget.loading.connect(self.loading)
        self.alphascale_creator_widget = aux_alphascale_creator.Alphascaler()
        # self.converter_widget = aux_converter.Converter()
        # self.converter_widget.loading.connect(self.loading)

        self.tab_widget = QtWidgets.QTabWidget()
        self.tab_widget.addTab(self.register_widget, "Register")
        self.tab_widget.addTab(self.alphascale_creator_widget, "Alphascale")
        # self.tab_widget.addTab(self.converter_widget, "File Type Converter")

        self.about_button = AboutButton(margin=1)
        sp = "<br>"
        title = "Butterfly Registrator"
        text = "Butterfly Registrator"
        text = text + sp + "Lars Maxfield"
        text = text + sp + "Version: " + __version__
        text = text + sp + "License: <a href='https://www.gnu.org/licenses/gpl-3.0.en.html'>GNU GPL v3</a> or later"
        text = text + sp + "Source: <a href='https://github.com/olive-groves/butterfly_registrator'>github.com/olive-groves/butterfly_registrator</a>"
        text = text + sp + "Tutorial: <a href='https://olive-groves.github.io/butterfly_registrator'>olive-groves.github.io/butterfly_registrator</a>"
        self.about_button.set_box_title(title)
        self.about_button.set_box_text(text)

        layout = QtWidgets.QGridLayout()
        layout.addWidget(self.tab_widget, 0, 0)
        layout.addWidget(self.about_button, 0, 0, QtCore.Qt.AlignTop|QtCore.Qt.AlignRight)
        layout.setContentsMargins(2,2,2,2)
        
        self.central_widget = QtWidgets.QWidget()
        self.central_widget.setLayout(layout)

        self.setCentralWidget(self.central_widget)
        self.setStyleSheet("""
            QWidget { font-size: 9pt }
            QSplitter::handle{ 
                background-color: 
                    qlineargradient(spread:pad, x1:0, y1:0, x2:0, y2:1,
                        stop:0 rgba(0, 0, 0, 0),
                        stop:0.4850 rgba(0, 0, 0, 0),
                        stop:0.4851 rgba(63, 63, 63, 255),
                        stop:0.4899 rgba(63, 63, 63, 255),
                        stop:0.4900 rgba(0, 0, 0, 0),
                        stop:0.4975 rgba(0, 0, 0, 0),
                        stop:0.4976 rgba(63, 63, 63, 255),
                        stop:0.5024 rgba(63, 63, 63, 255),
                        stop:0.5025 rgba(0, 0, 0, 0),
                        stop:0.5100 rgba(0, 0, 0, 0),
                        stop:0.5101 rgba(63, 63, 63, 255),
                        stop:0.5149 rgba(63, 63, 63, 255),
                        stop:0.5150 rgba(0, 0, 0, 0),
                        stop:1 rgba(0, 0, 0, 0)
                        );
                margin-left: 0.15em; margin-right: 0.15em}
                """)
        
        self.readSettings()

    def readSettings(self):
        """Read application settings."""
        settings = QtCore.QSettings()

        pos = settings.value('pos', QtCore.QPoint(100, 100))
        size = settings.value('size', QtCore.QSize(1100, 600))
        self.move(pos)
        self.resize(size)

        if settings.contains('windowgeometry'):
            self.restoreGeometry(settings.value('windowgeometry'))
        if settings.contains('windowstate'):
            self.restoreState(settings.value('windowstate'))

    def writeSettings(self):
        """Write application settings."""
        settings = QtCore.QSettings()
        settings.setValue('pos', self.pos())
        settings.setValue('size', self.size())
        settings.setValue('windowgeometry', self.saveGeometry())
        settings.setValue('windowstate', self.saveState())

    def closeEvent(self, event):
        """QEvent: Override close event to save application settings."""
        self.writeSettings()
        event.accept()

    def loading(self, boolean):
        """bool: For enabling/disabling interface when loading (True=disable; False=enable)."""
        self.setEnabled(not boolean)


def main():
    """Run MainWindow as main app.
    
    Attributes:
        app (QApplication): Starts and holds the main event loop of application.
        w (MainWindow): The main window.
    """
    app = QtWidgets.QApplication(sys.argv)
    QtCore.QSettings.setDefaultFormat(QtCore.QSettings.IniFormat)
    app.setOrganizationName(COMPANY)
    app.setOrganizationDomain(DOMAIN)
    app.setApplicationName(APPNAME)
    app.setWindowIcon(QtGui.QIcon(":/icon.png"))

    w = MainWindow()
    w.show()
    sys.exit(app.exec_())



if __name__=='__main__':
    main()