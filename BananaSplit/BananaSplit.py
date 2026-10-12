# Copyright (c) 2023 jarrrgh.
# This tool is released under the terms of the AGPLv3 or higher.

from BananaSplit.ZeesawLinkDecorator import ZeesawLinkDecorator
from BananaSplit.ZeesawLinkNode import ZeesawLinkNode
from BananaSplit.SetTransformationOperation import SetTransformationOperation
from BananaSplit.PinHoleLinkDecorator import PinHoleLinkDecorator
from cura.CuraApplication import CuraApplication
from cura.Operations.SetParentOperation import SetParentOperation
from cura.Scene import ZOffsetDecorator
from cura.Scene.BuildPlateDecorator import BuildPlateDecorator
from cura.Scene.CuraSceneNode import CuraSceneNode
from cura.Scene.SliceableObjectDecorator import SliceableObjectDecorator
from math import pi
from typing import Optional, Tuple, Union
from UM.Application import Application
from UM.Event import Event
from UM.Logger import Logger
from UM.Math.Matrix import Matrix
from UM.Math.Quaternion import Quaternion
from UM.Math.Vector import Vector
from UM.Mesh.MeshBuilder import MeshBuilder
from UM.Message import Message
from UM.Operations.AddSceneNodeOperation import AddSceneNodeOperation
from UM.Operations.GroupedOperation import GroupedOperation
from UM.Operations.RotateOperation import RotateOperation
from UM.Operations.TranslateOperation import TranslateOperation
from UM.Scene.SceneNode import SceneNode
from UM.Scene.SceneNodeSettings import SceneNodeSettings
from UM.Scene.Selection import Selection
from UM.Settings.SettingInstance import SettingInstance
from UM.Tool import Tool
from UM.Version import Version

import os
import copy
import numpy

try:
    from BananaSplit import PinHoles

    PIN_HOLES_IMPORT_ERROR = None
except Exception as exception:
    # PinHoles needs trimesh and shapely. Any failure there only disables pin holes, never the whole plugin.
    PinHoles = None
    PIN_HOLES_IMPORT_ERROR = str(exception)

QT_VERSION = Version("6")
try:
    from PyQt6.QtCore import Qt, QT_VERSION_STR
    from PyQt6.QtCore import QTimer

    QT_VERSION = Version(QT_VERSION_STR)
except ImportError:
    from PyQt5.QtCore import Qt, QT_VERSION_STR
    from PyQt5.QtCore import QTimer

    QT_VERSION = Version(QT_VERSION_STR)

APP_VERSION = Application.getInstance().getVersion()
# Logger.debug("App version: {}".format(APP_VERSION))
# Logger.debug("Qt version: {}".format(QT_VERSION))

PIN_HOLE_COUNT_PREFERENCE = "banana_split/pin_hole_count"
PIN_HOLE_DIAMETER_PREFERENCE = "banana_split/pin_hole_diameter"
PIN_HOLE_DEPTH_PREFERENCE = "banana_split/pin_hole_depth"
# A piece of 1.75 mm filament as the pin plus 0.2 mm clearance
DEFAULT_PIN_HOLE_DIAMETER = 1.95
# Into each half, so the pin is twice as long
DEFAULT_PIN_HOLE_DEPTH = 6.0
# Wall kept between a hole and the cut outline or a neighboring hole, in mm. About four 0.4 mm lines.
PIN_HOLE_WALL_MARGIN = 1.5
# A cutting mesh with no walls, infill, top or bottom prints nothing, which leaves a hole and the surrounding
# model gets walls around it. The zeros are what keeps the hole empty.
PIN_HOLE_MESH_SETTINGS = {
    "cutting_mesh": True,
    "wall_line_count": 0,
    "infill_sparse_density": 0,
    "top_layers": 0,
    "bottom_layers": 0,
}


class BananaSplit(Tool):
    def __init__(self):
        super().__init__()

        # Shortcut
        if QT_VERSION < Version("6"):
            self._shortcut_key = Qt.Key_B
        else:
            self._shortcut_key = Qt.Key.Key_B

        # Little indicator to point out linked nodes
        self._clippy = ZeesawLinkNode()

        # Allow/disallow splitting
        self._splittable = False
        # Enable/disable zeesaw action
        self._zeesaw = True
        # Enable/disable throttling zeesaw transformations
        self._throttle = False
        # Pin holes added on split, 0 disables them
        preferences = Application.getInstance().getPreferences()
        preferences.addPreference(PIN_HOLE_COUNT_PREFERENCE, 0)
        preferences.addPreference(PIN_HOLE_DIAMETER_PREFERENCE, DEFAULT_PIN_HOLE_DIAMETER)
        preferences.addPreference(PIN_HOLE_DEPTH_PREFERENCE, DEFAULT_PIN_HOLE_DEPTH)
        self._pin_hole_count = int(preferences.getValue(PIN_HOLE_COUNT_PREFERENCE))
        self._pin_hole_diameter = float(preferences.getValue(PIN_HOLE_DIAMETER_PREFERENCE))
        self._pin_hole_depth = float(preferences.getValue(PIN_HOLE_DEPTH_PREFERENCE))
        # Linked evaluates True, if selected nodes have link decorators and they point to each other
        self._linked = False

        # Avoid unnecessary transformations by comparing to previous values
        self._committed_selected_transformation = None
        self._committed_linked_transformation = None
        self._previous_selected_node = None
        self._previous_selected_transformation = None
        self._previous_selection_center = None

        # Timer for throttling updates
        self._update_timer = None

        self.setExposedProperties(
            "Splittable", "Linked", "Zeesaw", "Throttle", "PinHoleCount", "PinHoleDiameter", "PinHoleDepth"
        )

        Selection.selectionChanged.connect(self._selectionChanged)
        Selection.selectionCenterChanged.connect(self._selectionCenterChanged)
        self.getController().getScene().sceneChanged.connect(self._sceneChanged)

    def event(self, event: Event) -> bool:
        super().event(event)

        if event.type == Event.ToolActivateEvent:
            if Selection.hasSelection() and self._clippy:
                self._clippy.setParent(self.getController().getScene().getRoot())
                self._clippy.setEnabled(True)

        if event.type == Event.ToolDeactivateEvent and self._clippy:
            self._clippy.setParent(None)
            self._clippy.setEnabled(False)

        return False

    def getSplittable(self) -> bool:
        """True if node has not been linked and part of it is below bed surface."""
        return self._splittable

    def setSplittable(self, splittable: bool) -> None:
        """Enabled/disable splitting."""
        if splittable != self._splittable:
            self._splittable = splittable
            self.propertyChanged.emit()

    def getZeesaw(self) -> bool:
        """True if zeesawing enabled."""
        return self._zeesaw

    def setZeesaw(self, enabled: bool) -> None:
        """Enable/disable zeesawing."""
        if enabled != self._zeesaw:
            self._zeesaw = enabled
            self.propertyChanged.emit()

    def getThrottle(self) -> bool:
        """True if thorttling enabled."""
        return self._throttle

    def setThrottle(self, enabled: bool) -> None:
        """Enable/disable throttling."""
        if enabled != self._throttle:
            self._throttle = enabled
            self.propertyChanged.emit()

    def getPinHoleCount(self) -> int:
        """Number of pin holes added on split, 0 if disabled."""
        return self._pin_hole_count

    def setPinHoleCount(self, count: Union[int, str]) -> None:
        """Set number of pin holes added on split."""
        count = self._parseNumber(count, int)
        if count is not None and count >= 0 and count != self._pin_hole_count:
            self._pin_hole_count = count
            Application.getInstance().getPreferences().setValue(PIN_HOLE_COUNT_PREFERENCE, count)
        # Emit even without a change, so the panel field drops invalid input and shows the current value
        self.propertyChanged.emit()

    def getPinHoleDiameter(self) -> float:
        """Pin hole diameter in mm, clearance for the pin included."""
        return self._pin_hole_diameter

    def setPinHoleDiameter(self, diameter: Union[float, str]) -> None:
        """Set pin hole diameter in mm."""
        diameter = self._parseNumber(diameter, float)
        if diameter is not None and diameter > 0 and diameter != self._pin_hole_diameter:
            self._pin_hole_diameter = diameter
            Application.getInstance().getPreferences().setValue(PIN_HOLE_DIAMETER_PREFERENCE, diameter)
        # Emit even without a change, so the panel field drops invalid input and shows the current value
        self.propertyChanged.emit()

    def getPinHoleDepth(self) -> float:
        """Pin hole depth in mm into each half."""
        return self._pin_hole_depth

    def setPinHoleDepth(self, depth: Union[float, str]) -> None:
        """Set pin hole depth in mm into each half."""
        depth = self._parseNumber(depth, float)
        if depth is not None and depth > 0 and depth != self._pin_hole_depth:
            self._pin_hole_depth = depth
            Application.getInstance().getPreferences().setValue(PIN_HOLE_DEPTH_PREFERENCE, depth)
        # Emit even without a change, so the panel field drops invalid input and shows the current value
        self.propertyChanged.emit()

    def getLinked(self) -> bool:
        """True if selection is linked."""
        return self._linked

    def setLinked(self, linked: bool) -> None:
        """Enabled/disable link"""
        if linked != self._linked:
            self._linked = linked
            self.propertyChanged.emit()

    def enableZeesaw(self) -> None:
        """Enable zeesaw."""
        selected_node = Selection.getSelectedObject(0)
        if selected_node:
            linked_node = self._findLinkedNode(selected_node)
            if linked_node:
                self.setZeesaw(True)
                self._updateProperties()

                # If transformation did change, commit zeesaw operation to make it undoable (able to undo)
                self._committed_linked_transformation = linked_node.getWorldTransformation()
                self.operateZeesaw(
                    selected_node, linked_node, old_transformation=self._committed_linked_transformation
                )

    def disableZeesaw(self) -> None:
        """Disable zeesaw."""
        self.setZeesaw(False)
        self._updateProperties()

    def split(self) -> None:
        if APP_VERSION < Version("5.2.0"):
            # Ask user to disable auto drop down altogether, since ZOffsetDecorator is hard to handle
            app_preferences = Application.getInstance().getPreferences()
            if app_preferences.getValue("physics/automatic_drop_down"):
                Message(
                    text='To avoid issues while positioning models below build plate, please disable "Automatically drop models to the build plate" under Preferences > General, or update to Cura 5.2.0 or newer.',
                    title="Warning: Auto Drop Enabled",
                ).show()
                return

        selected_node = Selection.getSelectedObject(0)
        if selected_node:
            new_node = copy.deepcopy(selected_node)
            new_node.setParent(selected_node.getParent())

            build_plate_number = selected_node.callDecoration("getBuildPlateNumber")
            new_node.callDecoration("setBuildPlateNumber", build_plate_number)
            for child in new_node.getChildren():
                child.callDecoration("setBuildPlateNumber", build_plate_number)

            # Store reference transformation
            self._previous_selected_transformation = selected_node.getLocalTransformation()

            # Cross-link nodes
            self._addLinkDecorators(selected_node, new_node)

            # Add node to the scene and perform the zeesaw transformations
            self.operateZeesaw(selected_node, new_node, add_to_scene=True)

            if self._pin_hole_count > 0:
                self._addPinHoles(selected_node, new_node)

            self._selectionChanged()

    def operateZeesaw(
        self,
        selected_node: SceneNode,
        linked_node: SceneNode,
        add_to_scene: bool = False,
        old_transformation: Optional[Matrix] = None,
    ) -> bool:
        """Update linked node transformation using transformation operations. User can undo this.
        Returns True, if operation was pushed to stack, and False, if the operation would have not
        made any difference to the linked node.
        """

        # Store reference transformation
        transformation = selected_node.getLocalTransformation()
        world_transformation = selected_node.getWorldTransformation()
        self._previous_selected_transformation = world_transformation.copy()

        # Avoid unnecessary transformations, if reference has not changed
        if self._transformationsSamey(world_transformation, self._committed_selected_transformation):
            return False

        # Preview, if zeesaw update would make a difference on the linked node
        self.updateZeesaw(selected_node, linked_node, forced=True)

        # The result does differ slightly possibly due to rounding errors
        if self._transformationsSamey(linked_node.getWorldTransformation(), self._committed_linked_transformation):
            return False

        if APP_VERSION >= Version("5.2.0"):
            # Disable auto drop down. Makes things easier and fixes undo functionality
            selected_node.setSetting(SceneNodeSettings.AutoDropDown, False)
            linked_node.setSetting(SceneNodeSettings.AutoDropDown, False)
        else:
            # Assist auto drop down to keep the node below platform surface
            # TODO: avoid auto drop issues with ZOffsetDecorator
            # self._updateInverseZOffsetDecorator(selected_node, linked_node)
            pass

        operation = GroupedOperation()

        if add_to_scene:
            operation.addOperation(AddSceneNodeOperation(linked_node, linked_node.getParent()))

        # Reset transformation
        operation.addOperation(SetTransformationOperation(linked_node, transformation, old_transformation))

        # Rotate 180 degrees. This turned out to be way faster than mirroring
        rotation = Quaternion.fromAngleAxis(pi, Vector.Unit_Z)
        operation.addOperation(RotateOperation(linked_node, rotation))

        # By default translate node back to previous position and
        # mirror y world coordinate. Note that y is what user sees as z
        x = linked_node.getWorldPosition().x
        y = -selected_node.getWorldPosition().y
        z = linked_node.getWorldPosition().z

        if add_to_scene:
            world_position = selected_node.getWorldPosition()
            bbox = selected_node.getBoundingBox()

            # Align bounding boxes along x axis and move new node next to the original node
            x = world_position.x + 2 * (bbox.center.x - world_position.x)
            x = x + bbox.width + 4

        operation.addOperation(TranslateOperation(linked_node, Vector(x, y, z), set_position=True))

        operation.push()
        return True

    def updateZeesaw(self, selected_node: SceneNode, linked_node: SceneNode, forced: bool = False) -> bool:
        """Update linked node transformation skipping the operation stack. Returns True, if transformation
        got updated, and False, if the operation would have not made any difference to the linked node.
        """
        # Logger.debug("updateZeesaw")
        transformation = selected_node.getLocalTransformation()
        world_transformation = selected_node.getWorldTransformation()

        if not forced:
            if self._transformationsSamey(world_transformation, self._previous_selected_transformation):
                return False
        self._previous_selected_transformation = world_transformation.copy()

        # Target position
        selected_position = selected_node.getWorldPosition()
        linked_position = linked_node.getWorldPosition()

        # Rotate 180 degrees
        rotation = Quaternion.fromAngleAxis(pi, Vector.Unit_Z)
        orientation_matrix = rotation.toMatrix()
        transformation.multiply(world_transformation.getInverse())
        transformation.multiply(orientation_matrix)
        transformation.multiply(world_transformation)
        linked_node.setTransformation(transformation)

        # Linked node position after rotation
        current_world_position = linked_node.getWorldPosition()

        transformation = linked_node.getLocalTransformation()
        world_transformation = linked_node.getWorldTransformation()

        # Translate back to orignal just possibly updating Z (actually Y)
        target_position = Vector(linked_position.x, -selected_position.y, linked_position.z)
        translation = target_position - current_world_position
        translation_matrix = Matrix()
        translation_matrix.setByTranslation(translation)
        transformation.multiply(world_transformation.getInverse())
        transformation.multiply(translation_matrix)
        transformation.multiply(world_transformation)
        linked_node.setTransformation(transformation)

        return True

    def scheduleUpdate(self) -> None:
        # Logger.debug("scheduleUpdate")
        if self._throttle:
            self._update_timer = QTimer()
            self._update_timer.setInterval(1000)
            self._update_timer.setSingleShot(True)
            self._update_timer.timeout.connect(self._scheduledUpdate)
            self._update_timer.start()
        else:
            self._scheduledUpdate()

    def _scheduledUpdate(self) -> None:
        # Logger.debug("_scheduledUpdate")
        self._update_timer = None
        selected_node, linked_node = self._getSelectedAndLinkedNode(0)
        if selected_node and linked_node and self._zeesaw:
            self.updateZeesaw(selected_node, linked_node)

    def _sceneChanged(self, node: SceneNode) -> None:
        # Logger.debug("_sceneChanged")
        self._syncLinkedPinHole(node)
        if self._update_timer:
            return
        if self._zeesaw and node.hasDecoration("zeesawLinkedNodeId"):
            selected_node, linked_node = self._getSelectedAndLinkedNode(0)
            if node is selected_node and linked_node and self._update_timer is None:
                CuraApplication.getInstance().callLater(self.scheduleUpdate)

    def _selectionChanged(self) -> None:
        # Logger.debug("_selectionChanged")
        self._updateProperties()
        selected_node, linked_node = self._getSelectedAndLinkedNode(0)

        if not selected_node:
            self._previous_selected_node = None
            return

        # Selected node changed so update linked transformation in undoable manner
        if self._zeesaw and linked_node and selected_node is not self._previous_selected_node:
            self._committed_linked_transformation = linked_node.getWorldTransformation()
            self.operateZeesaw(selected_node, linked_node, old_transformation=self._committed_linked_transformation)
        self._previous_selected_node = selected_node

    def _selectionCenterChanged(self) -> None:
        # Logger.debug("_selectionCenterChanged")
        selected_node, linked_node = self._getSelectedAndLinkedNode(0)
        if selected_node and linked_node and self._zeesaw:
            self._clippy.updatePosition(selected_node, linked_node)
        self._updateProperties()

    def _updateProperties(self) -> None:
        # Logger.debug("_updateProperties")
        self._clippy.setEnabled(self._zeesaw)
        splittable = False
        linked = False

        selection_count = Selection.getCount()
        primary_node, primary_linked_node = self._getSelectedAndLinkedNode(0)
        secondary_node, secondary_linked_node = self._getSelectedAndLinkedNode(1)

        if primary_node and primary_linked_node:
            self._clippy.updatePosition(primary_node, primary_linked_node)

        if selection_count == 1 and primary_node:
            if primary_linked_node:
                linked = True
            else:
                # Check if node is partly submerged in the build plate
                bbox = primary_node.getBoundingBox()
                if bbox.bottom < -0.1 and bbox.top > 0.1:
                    splittable = True
        elif selection_count == 2 and secondary_node and secondary_linked_node:
            if primary_node is secondary_linked_node and secondary_node is primary_linked_node:
                linked = True

        self._clippy.setVisible(linked and self._zeesaw)
        self.setLinked(linked)
        self.setSplittable(splittable)

    def _findLinkedNode(self, node: SceneNode) -> Optional[SceneNode]:
        # Logger.debug("_findLinkedNode")
        linked_node_id = node.callDecoration("zeesawLinkedNodeId")
        if linked_node_id:
            scene = Application.getInstance().getController().getScene()
            return scene.findObject(linked_node_id)

    def _addLinkDecorators(self, node1: SceneNode, node2: SceneNode) -> None:
        # Logger.debug("_addLinkDecorators")
        self._removeLinkDecorators(node1)
        self._removeLinkDecorators(node2)
        node1.addDecorator(ZeesawLinkDecorator(id(node2)))
        node2.addDecorator(ZeesawLinkDecorator(id(node1)))

    def _removeLinkDecorators(self, node: SceneNode) -> None:
        # Logger.debug("_removeLinkDecorators")
        linked_node = self._findLinkedNode(node)
        node.removeDecorator(ZeesawLinkDecorator)
        if linked_node:
            linked_node.removeDecorator(ZeesawLinkDecorator)

    def _updateInverseZOffsetDecorator(self, selected_node: SceneNode, linked_node: SceneNode) -> None:
        # Logger.debug("_updateInverseZOffsetDecorator")
        bbox = selected_node.getBoundingBox()
        linked_node.removeDecorator(ZOffsetDecorator.ZOffsetDecorator)
        linked_node.addDecorator(ZOffsetDecorator.ZOffsetDecorator())
        if bbox.bottom > 0:
            linked_node.callDecoration("setZOffset", -bbox.height)
        else:
            z_offset = -(bbox.height + bbox.bottom)
            linked_node.callDecoration("setZOffset", z_offset)

    def _transformationsSamey(self, a: Matrix, b: Matrix) -> bool:
        if a and b:
            return numpy.allclose(a.getData(), b.getData(), rtol=1.0e-5, atol=1.0e-5)
        else:
            return False

    def _getSelectedAndLinkedNode(self, index: int) -> Tuple[Optional[SceneNode], Optional[SceneNode]]:
        if index >= Selection.getCount():
            return (None, None)
        selected_node = Selection.getSelectedObject(index)
        if selected_node is None:
            return (None, None)
        if not selected_node.hasDecoration("zeesawLinkedNodeId"):
            return (selected_node, None)
        linked_node = self._findLinkedNode(selected_node)
        if linked_node and not linked_node.hasDecoration("zeesawLinkedNodeId"):
            # Fix broken link. Decorator may have been lost during undo/redo...
            self._addLinkDecorators(selected_node, linked_node)
        return (selected_node, linked_node)

    def _addPinHoles(self, selected_node: SceneNode, linked_node: SceneNode) -> None:
        """Add matching pin holes to both halves at the cut plane, which is the build plate level."""
        if PinHoles is None:
            Message(text="Pin holes unavailable: {}".format(PIN_HOLES_IMPORT_ERROR), title="Pin Holes").show()
            return
        mesh_data = selected_node.getMeshData()
        if mesh_data is None:
            Message(text="Pin holes need a single model, not a group.", title="Pin Holes").show()
            return
        world_mesh = mesh_data.getTransformed(selected_node.getWorldTransformation())
        vertices = world_mesh.getVertices()
        faces = world_mesh.getIndices()
        if faces is None:
            faces = numpy.arange(len(vertices)).reshape(-1, 3)

        radius = self._pin_hole_diameter / 2
        try:
            solids = PinHoles.cutSectionSolids(vertices, faces)
            centers = PinHoles.pinHoleCenters(solids, self._pin_hole_count, radius, PIN_HOLE_WALL_MARGIN)
            # Symmetric about the cut plane: the half below the build plate is not sliced in either part,
            # so each half gets exactly the hole depth
            cylinder = PinHoles.cylinder(radius, self._pin_hole_depth)
        except Exception as exception:
            Message(text="Could not place pin holes: {}".format(exception), title="Pin Holes").show()
            return
        if not centers:
            Message(text="No room for pin holes in the cut section.", title="Pin Holes").show()
            return
        if len(centers) < self._pin_hole_count:
            text = "Only {} of {} pin holes fit in the cut section.".format(len(centers), self._pin_hole_count)
            Message(text=text, title="Pin Holes").show()

        # Both halves share the same mesh, so a point on the cut maps between them through their world transforms
        selected_to_linked = numpy.dot(
            linked_node.getWorldTransformation().getData(),
            numpy.linalg.inv(selected_node.getWorldTransformation().getData()),
        )
        root = self.getController().getScene().getRoot()
        operation = GroupedOperation()
        for x, z in centers:
            linked_position = numpy.dot(selected_to_linked, [x, 0, z, 1])
            selected_hole, linked_hole = self._createPinHoleNode(*cylinder), self._createPinHoleNode(*cylinder)
            selected_hole.addDecorator(PinHoleLinkDecorator(id(linked_hole)))
            linked_hole.addDecorator(PinHoleLinkDecorator(id(selected_hole)))
            placements = (
                (selected_hole, selected_node, Vector(x, 0, z)),
                (linked_hole, linked_node, Vector(*linked_position[:3])),
            )
            for hole, parent, position in placements:
                operation.addOperation(AddSceneNodeOperation(hole, root))
                operation.addOperation(SetParentOperation(hole, parent))
                operation.addOperation(TranslateOperation(hole, position, set_position=True))
        operation.push()

    def _createPinHoleNode(self, vertices: numpy.ndarray, indices: numpy.ndarray) -> CuraSceneNode:
        """Cutting mesh that leaves an empty hole in the model it is parented to."""
        builder = MeshBuilder()
        builder.setVertices(vertices)
        builder.setIndices(indices)
        builder.calculateNormals(fast=True)

        node = CuraSceneNode()
        node.setName("Pin hole")
        node.setSelectable(True)
        node.setCalculateBoundingBox(True)
        node.setMeshData(builder.build())
        node.calculateBoundingBoxMesh()
        active_build_plate = CuraApplication.getInstance().getMultiBuildPlateModel().activeBuildPlate
        node.addDecorator(BuildPlateDecorator(active_build_plate))
        node.addDecorator(SliceableObjectDecorator())

        stack = node.callDecoration("getStack")
        settings = stack.getTop()
        for key, value in PIN_HOLE_MESH_SETTINGS.items():
            definition = stack.getSettingDefinition(key)
            if definition is None:
                continue
            instance = SettingInstance(definition, settings)
            instance.setProperty("value", value)
            instance.resetState()
            settings.addInstance(instance)
        return node

    def _syncLinkedPinHole(self, node: SceneNode) -> None:
        """Mirror a moved pin hole onto its linked hole in the other half."""
        linked_id = node.callDecoration("pinHoleLinkedNodeId")
        if linked_id is None or not Selection.isSelected(node):
            return
        linked_hole = self.getController().getScene().findObject(linked_id)
        if linked_hole is None or Selection.isSelected(linked_hole):
            return
        # Both halves share the mesh, so linked holes share the local transform
        transformation = node.getLocalTransformation()
        if not self._transformationsSamey(transformation, linked_hole.getLocalTransformation()):
            linked_hole.setTransformation(transformation)

    def _parseNumber(self, value: Union[float, str], number_type: type) -> Optional[float]:
        """The value converted to number_type, or None if it is not a number."""
        try:
            return number_type(value)
        except ValueError:
            return None
