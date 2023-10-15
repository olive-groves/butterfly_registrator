#!/usr/bin/env python3

"""QGraphicsScene with signals and right-click functionality for SplitView.

Not intended as a script.

Creates the base (main) scene of the SplitView for the Butterfly Viewer and Registrator.
"""
# SPDX-License-Identifier: GPL-3.0-or-later



from PyQt5 import QtCore, QtWidgets

from aux_comments import CommentItem
from aux_rulers import RulerItem
from aux_dialogs import PixelUnitConversionInputDialog



class CustomQGraphicsScene(QtWidgets.QGraphicsScene):
    """QGraphicsScene with signals and right-click functionality for SplitView.

    Recommended to be instantiated without input (for example, my_scene = CustomQGraphicsScene())
    
    Signals for right click menu for comments (create comment, save comments, load comments).
    Signals for right click menu for rulers (create ruler, set origin relative position, set px-per-unit conversion) 
    Signals for right click menu for transform mode (interpolate, non-interpolate)
    Methods for right click menu.

    Args:
        Identical to base class QGraphicsScene.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.px_conversion = 1.0
        self.unit_conversion = 1.0
        self.px_per_unit = 1.0
        self.px_per_unit_conversion_set = False
        self.relative_origin_position = "bottomleft"
        self.single_transform_mode_smooth = False

        self.background_colors = [["Dark gray (default)", 32, 32, 32],
                                  ["White", 255, 255, 255],
                                  ["Light gray", 223, 223, 223],
                                  ["Black", 0, 0, 0]]
        self._background_color = self.background_colors[0]

        self.disable_right_click = False

    right_click_comment = QtCore.pyqtSignal(QtCore.QPointF)
    right_click_ruler = QtCore.pyqtSignal(QtCore.QPointF, str, str, float) # Scene position, relative origin position, unit, px-per-unit
    right_click_save_all_comments = QtCore.pyqtSignal()
    right_click_load_comments = QtCore.pyqtSignal()
    right_click_relative_origin_position = QtCore.pyqtSignal(str)
    changed_px_per_unit = QtCore.pyqtSignal(str, float) # Unit, px-per-unit
    right_click_single_transform_mode_smooth = QtCore.pyqtSignal(bool)
    right_click_all_transform_mode_smooth = QtCore.pyqtSignal(bool)
    right_click_background_color = QtCore.pyqtSignal(list)
    position_changed_qgraphicsitem = QtCore.pyqtSignal()
    
    def contextMenuEvent(self, event):
        """Override the event of the context menu (right-click menu)  to display options.

        Triggered when mouse is right-clicked on scene.

        Args:
            event (PyQt event for contextMenuEvent)
        """
        if self.disable_right_click:
            return
        
        what_menu_type = "View"

        scene_pos = event.scenePos()
        item = self.itemAt(scene_pos, self.views()[0].transform())

        action_delete = None
        menu_set_color = None
        action_set_color_red = None
        action_set_color_white = None
        action_set_color_blue = None
        action_set_color_green = None
        action_set_color_yellow = None
        action_set_color_black = None

        item_parent = item
        if item is not None:
            while item_parent.parentItem(): # Loop "upwards" to find parent item
                item_parent = item_parent.parentItem()
        
        if isinstance(item_parent, CommentItem) or isinstance(item_parent, RulerItem):
            action_delete = QtWidgets.QAction("Delete")

            if isinstance(item_parent, CommentItem):
                menu_set_color = QtWidgets.QMenu("Set comment color...")
                action_set_color_red = menu_set_color.addAction("Red")
                action_set_color_red.triggered.connect(lambda: item_parent.set_color("red"))
                action_set_color_white = menu_set_color.addAction("White")
                action_set_color_white.triggered.connect(lambda: item_parent.set_color("white"))
                action_set_color_blue = menu_set_color.addAction("Blue")
                action_set_color_blue.triggered.connect(lambda: item_parent.set_color("blue"))
                action_set_color_green = menu_set_color.addAction("Green")
                action_set_color_green.triggered.connect(lambda: item_parent.set_color("green"))
                action_set_color_yellow = menu_set_color.addAction("Yellow")
                action_set_color_yellow.triggered.connect(lambda: item_parent.set_color("yellow"))
                action_set_color_black = menu_set_color.addAction("Black")
                action_set_color_black.triggered.connect(lambda: item_parent.set_color("black"))

            action_delete.triggered.connect(lambda: self.removeItem(item_parent))

            what_menu_type = "Edit item(s)"

        menu = QtWidgets.QMenu()

        if what_menu_type == "Edit item(s)":
            if menu_set_color:
                menu.addMenu(menu_set_color)
            if action_delete:
                menu.addAction(action_delete) # action_delete.triggered.connect(lambda: self.removeItem(item.parentItem())) # = menu.addAction("Delete", self.removeItem(item.parentItem()))
        else:
            action_comment = menu.addAction("Comment")
            action_comment.setToolTip("Add a draggable text comment here")
            action_comment.triggered.connect(lambda: self.right_click_comment.emit(scene_pos)) # action_comment.triggered.connect(lambda state, x=scene_pos: self.right_click_comment.emit(x))

            menu_ruler = QtWidgets.QMenu("Measurement ruler...")
            menu_ruler.setToolTip("Add a ruler to measure distances and angles in this image window...")
            menu_ruler.setToolTipsVisible(True)
            menu.addMenu(menu_ruler)

            action_set_px_per_mm = menu_ruler.addAction("Set the ruler conversion factor for real distances (mm, cm)...")
            action_set_px_per_mm.triggered.connect(lambda: self.dialog_to_set_px_per_mm())

            menu_ruler.addSeparator()

            action_ruler_px = menu_ruler.addAction("Pixel ruler")
            action_ruler_px.setToolTip("Add a ruler to measure distances in pixels")
            action_ruler_px.triggered.connect(lambda: self.right_click_ruler.emit(scene_pos, self.relative_origin_position, "px", 1.0))

            action_ruler_mm = menu_ruler.addAction("Millimeter ruler")
            action_ruler_mm.setToolTip("Add a ruler to measure distances in millimeters")
            action_ruler_mm.triggered.connect(lambda: self.right_click_ruler.emit(scene_pos, self.relative_origin_position, "mm", self.px_per_unit))

            action_ruler_cm = menu_ruler.addAction("Centimeter ruler")
            action_ruler_cm.setToolTip("Add a ruler to measure distances in centimeters")
            action_ruler_cm.triggered.connect(lambda: self.right_click_ruler.emit(scene_pos, self.relative_origin_position, "cm", self.px_per_unit*10))
            
            if not self.px_per_unit_conversion_set:
                text_disclaimer = "(requires conversion to be set before using)"
                tooltip_disclaimer = "To use this ruler, first set the ruler conversion factor"

                action_ruler_mm.setEnabled(False)
                action_ruler_mm.setText(action_ruler_mm.text() + " " + text_disclaimer)
                action_ruler_mm.setToolTip(tooltip_disclaimer)

                action_ruler_cm.setEnabled(False)
                action_ruler_cm.setText(action_ruler_cm.text() + " " + text_disclaimer)
                action_ruler_cm.setToolTip(tooltip_disclaimer)

            menu_ruler.addSeparator()

            action_set_relative_origin_position_topleft = menu_ruler.addAction("Switch relative origin to top-left")
            action_set_relative_origin_position_topleft.triggered.connect(lambda: self.right_click_relative_origin_position.emit("topleft"))
            action_set_relative_origin_position_topleft.triggered.connect(lambda: self.set_relative_origin_position("topleft"))
            action_set_relative_origin_position_bottomleft = menu_ruler.addAction("Switch relative origin to bottom-left")
            action_set_relative_origin_position_bottomleft.triggered.connect(lambda: self.right_click_relative_origin_position.emit("bottomleft"))
            action_set_relative_origin_position_bottomleft.triggered.connect(lambda: self.set_relative_origin_position("bottomleft"))

            if self.relative_origin_position == "bottomleft":
                action_set_relative_origin_position_bottomleft.setEnabled(False)
            elif self.relative_origin_position == "topleft": 
                action_set_relative_origin_position_topleft.setEnabled(False)
            
            menu.addSeparator()

            action_save_all_comments = menu.addAction("Save all comments of this view (.csv)...")
            action_save_all_comments.triggered.connect(lambda: self.right_click_save_all_comments.emit())
            action_load_comments = menu.addAction("Load comments into this view (.csv)...")
            action_load_comments.triggered.connect(lambda: self.right_click_load_comments.emit())

            menu.addSeparator()

            menu_transform = QtWidgets.QMenu("Upsample when zoomed...")
            menu_transform.setToolTipsVisible(True)
            menu.addMenu(menu_transform)

            transform_on_tooltip_str = "Pixels are interpolated when zoomed in, thus rendering a smooth appearance"
            transform_off_tooltip_str = "Pixels are unchanged when zoomed in, thus rendering a true-to-pixel appearance"

            action_set_single_transform_mode_smooth_on = menu_transform.addAction("Switch on")
            action_set_single_transform_mode_smooth_on.setToolTip(transform_on_tooltip_str)
            action_set_single_transform_mode_smooth_on.triggered.connect(lambda: self.right_click_single_transform_mode_smooth.emit(True))
            action_set_single_transform_mode_smooth_on.triggered.connect(lambda: self.set_single_transform_mode_smooth(True))

            action_set_single_transform_mode_smooth_off = menu_transform.addAction("Switch off")
            action_set_single_transform_mode_smooth_off.setToolTip(transform_off_tooltip_str)
            action_set_single_transform_mode_smooth_off.triggered.connect(lambda: self.right_click_single_transform_mode_smooth.emit(False))
            action_set_single_transform_mode_smooth_off.triggered.connect(lambda: self.set_single_transform_mode_smooth(False))

            if self.single_transform_mode_smooth:
                action_set_single_transform_mode_smooth_on.setEnabled(False)
            else:
                action_set_single_transform_mode_smooth_off.setEnabled(False)

            menu_transform.addSeparator()

            action_set_all_transform_mode_smooth_on = menu_transform.addAction("Switch on (all windows)")
            action_set_all_transform_mode_smooth_on.setToolTip(transform_on_tooltip_str+" (applies to all current and new image windows)")
            action_set_all_transform_mode_smooth_on.triggered.connect(lambda: self.right_click_all_transform_mode_smooth.emit(True))
    
            action_set_all_transform_mode_smooth_off = menu_transform.addAction("Switch off (all windows)")
            action_set_all_transform_mode_smooth_off.setToolTip(transform_off_tooltip_str+" (applies to all current and new image windows)")
            action_set_all_transform_mode_smooth_off.triggered.connect(lambda: self.right_click_all_transform_mode_smooth.emit(False))

            menu.addSeparator()

            menu_background = QtWidgets.QMenu("Set background color...")
            menu_background.setToolTipsVisible(True)
            menu.addMenu(menu_background)

            for color in self.background_colors:
                descriptor = color[0]
                rgb = color[1:4]
                action_set_background = menu_background.addAction(descriptor)
                action_set_background.setToolTip("RGB " + ", ".join([str(channel) for channel in rgb]))
                action_set_background.triggered.connect(lambda value, color=color: self.right_click_background_color.emit(color))
                action_set_background.triggered.connect(lambda value, color=color: self.background_color_lambda(color))
                if color == self.background_color:
                    action_set_background.setEnabled(False)

        menu.exec(event.screenPos())

    def set_relative_origin_position(self, string):
        """Set the descriptor of the position of the relative origin for rulers.

        Describes the coordinate orientation:
            "bottomleft" for Cartesian-style (positive X right, positive Y up)
            "topleft" for image-style (positive X right, positive Y down)
        
        Args:
            string (str): "topleft" or "bottomleft" for position of the origin for coordinate system of rulers.
        """
        self.relative_origin_position = string

    def set_single_transform_mode_smooth(self, boolean):
        """Set the descriptor of the status of smooth transform mode.

        Describes the transform mode of pixels on zoom:
            True for smooth (interpolated)
            False for non-smooth (non-interpolated)
        
        Args:
            boolean (bool): True for smooth; False for non-smooth.
        """
        self.single_transform_mode_smooth = boolean

    def dialog_to_set_px_per_mm(self):
        """Open the dialog for users to set the conversion for pixels to millimeters.
        
        Emits the value of the px-per-mm conversion if user clicks "Ok" on dialog.
        """        
        dialog_window = PixelUnitConversionInputDialog(unit="mm", px_conversion=self.px_conversion, unit_conversion=self.unit_conversion, px_per_unit=self.px_per_unit)
        dialog_window.setWindowModality(QtCore.Qt.ApplicationModal)
        if dialog_window.exec_() == QtWidgets.QDialog.Accepted:
            self.px_per_unit = dialog_window.px_per_unit
            if self.px_per_unit_conversion_set:
                self.changed_px_per_unit.emit("mm", self.px_per_unit)
            self.px_per_unit_conversion_set = True
            self.px_conversion = dialog_window.px_conversion
            self.unit_conversion = dialog_window.unit_conversion

    @property
    def background_color(self):
        """Current background color."""
        return self._background_color
    
    @background_color.setter
    def background_color(self, color):
        """Set color as list with descriptor and RGB values [str, r, g, b]."""
        self._background_color = color

    def background_color_lambda(self, color):
        """Within lambda, set color as list with descriptor and RGB values [str, r, g, b]."""
        self.background_color = color

    @property
    def background_rgb(self):
        """Current background color RGB."""
        return self._background_color[1:4]