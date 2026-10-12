// Copyright (c) 2023 jarrrgh.
// This tool is released under the terms of the AGPLv3 or higher.

import QtQuick 6.0
import QtQuick.Controls 6.0

import UM 1.7 as UM
import Cura 1.0 as Cura

Item {
    id: base
    width: childrenRect.width
    height: childrenRect.height

    property bool splittable: UM.Controller.properties.getValue("Splittable") || false
    property bool linked: UM.Controller.properties.getValue("Linked") || false
    property bool throttle: UM.Controller.properties.getValue("Throttle") || false
    property bool zeesaw: UM.Controller.properties.getValue("Zeesaw") || false
    property int pinHoleCount: UM.Controller.properties.getValue("PinHoleCount") || 0
    property real pinHoleDiameter: UM.Controller.properties.getValue("PinHoleDiameter") || 0
    property real pinHoleDepth: UM.Controller.properties.getValue("PinHoleDepth") || 0
    
    Row {
        id: buttonRow
        spacing: UM.Theme.getSize("default_margin").width

        UM.ToolbarButton {
            id: splitButton
            text: "Split"
            enabled: base.splittable
            toolItem: UM.ColorImage {
                source: Qt.resolvedUrl("../resources/tanto.svg")
                color: UM.Theme.getColor("icon")
            }
            onClicked: UM.Controller.triggerAction("split")
        }

        UM.ToolbarButton {
            id: linkButton
            text: "Link Z"
            checked: base.zeesaw
            enabled: base.linked
            toolItem: UM.ColorImage {
                source: Qt.resolvedUrl("../resources/link.svg")
                color: UM.Theme.getColor("icon")
            }
            onClicked: this.checked ?
                UM.Controller.triggerAction("disableZeesaw") :
                UM.Controller.triggerAction("enableZeesaw")
        }
    }

    UM.CheckBox {
        id: throttleCheckBox
        anchors.top: buttonRow.bottom
        anchors.topMargin: UM.Theme.getSize("default_margin").width
        text: "Throttle updates"
        checked: base.throttle
        onClicked: UM.Controller.setProperty("Throttle", checked)
    }

    Grid {
        id: pinHoleGrid
        anchors.top: throttleCheckBox.bottom
        anchors.topMargin: UM.Theme.getSize("default_margin").width
        columns: 2
        columnSpacing: UM.Theme.getSize("default_margin").width
        rowSpacing: UM.Theme.getSize("default_lining").height
        verticalItemAlignment: Grid.AlignVCenter

        UM.Label {
            id: pinHoleCountLabel
            text: "Pin holes"
        }

        UM.TextFieldWithUnit {
            id: pinHoleCountField
            width: UM.Theme.getSize("setting_control").width
            height: UM.Theme.getSize("setting_control").height
            text: base.pinHoleCount
            validator: UM.IntValidator {}
            onEditingFinished: UM.Controller.setProperty("PinHoleCount", text)
        }

        UM.Label {
            id: pinHoleDiameterLabel
            text: "Pin hole diameter"
        }

        UM.TextFieldWithUnit {
            id: pinHoleDiameterField
            width: UM.Theme.getSize("setting_control").width
            height: UM.Theme.getSize("setting_control").height
            unit: "mm"
            text: base.pinHoleDiameter
            validator: UM.FloatValidator {
                maxBeforeDecimal: 3
                maxAfterDecimal: 2
            }
            onEditingFinished: UM.Controller.setProperty("PinHoleDiameter", text.replace(",", "."))
        }

        UM.Label {
            id: pinHoleDepthLabel
            text: "Pin hole depth"
        }

        UM.TextFieldWithUnit {
            id: pinHoleDepthField
            width: UM.Theme.getSize("setting_control").width
            height: UM.Theme.getSize("setting_control").height
            unit: "mm"
            text: base.pinHoleDepth
            validator: UM.FloatValidator {
                maxBeforeDecimal: 3
                maxAfterDecimal: 2
            }
            onEditingFinished: UM.Controller.setProperty("PinHoleDepth", text.replace(",", "."))
        }
    }
}
