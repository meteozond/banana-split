// Copyright (c) 2023 jarrrgh.
// This tool is released under the terms of the AGPLv3 or higher.

import QtQuick 2.2
import QtQuick.Controls 1.2
import UM 1.1 as UM

Item {
    id: base
    width: childrenRect.width
    height: childrenRect.height
    
    property bool splittable: UM.ActiveTool.properties.getValue("Splittable") || false
    property bool linked: UM.ActiveTool.properties.getValue("Linked") || false
    property bool throttle: UM.ActiveTool.properties.getValue("Throttle") || false
    property bool zeesaw: UM.ActiveTool.properties.getValue("Zeesaw") || false
    property int pinHoleCount: UM.ActiveTool.properties.getValue("PinHoleCount") || 0
    property real pinHoleDiameter: UM.ActiveTool.properties.getValue("PinHoleDiameter") || 0
    property real pinHoleDepth: UM.ActiveTool.properties.getValue("PinHoleDepth") || 0

    Row {
        id: buttonRow
        spacing: UM.Theme.getSize("default_margin").width

        Button {
            id: splitButton
            text: "Split"
            enabled: base.splittable
            iconSource: "../resources/tanto.svg"
            property bool needBorder: true;
            style: UM.Theme.styles.tool_button
            onClicked: UM.ActiveTool.triggerAction("split")
            z: 2;
        }

        Button {
            id: linkButton
            text: "Link Z"
            enabled: base.linked
            checked: base.zeesaw && !base.splittable
            iconSource: "../resources/link.svg"
            property bool needBorder: true;
            style: UM.Theme.styles.tool_button;
            onClicked: this.checked ?
                UM.ActiveTool.triggerAction("disableZeesaw") :
                UM.ActiveTool.triggerAction("enableZeesaw")
            z: 1;
        }
    }

    CheckBox {
        id: throttleCheckBox
        anchors.top: buttonRow.bottom
        anchors.topMargin: UM.Theme.getSize("default_margin").width
        text: "Throttle updates"
        checked: base.throttle
        onClicked: UM.ActiveTool.setProperty("Throttle", checked)
    }

    Grid {
        id: pinHoleGrid
        anchors.top: throttleCheckBox.bottom
        anchors.topMargin: UM.Theme.getSize("default_margin").width
        columns: 2
        columnSpacing: UM.Theme.getSize("default_margin").width
        rowSpacing: UM.Theme.getSize("default_lining").height
        verticalItemAlignment: Grid.AlignVCenter

        Label {
            id: pinHoleCountLabel
            text: "Pin holes"
            color: UM.Theme.getColor("text")
            font: UM.Theme.getFont("default")
        }

        TextField {
            id: pinHoleCountField
            width: UM.Theme.getSize("setting_control").width
            height: UM.Theme.getSize("setting_control").height
            style: UM.Theme.styles.text_field
            text: base.pinHoleCount
            validator: IntValidator {
                bottom: 0
            }
            onEditingFinished: UM.ActiveTool.setProperty("PinHoleCount", text)
        }

        Label {
            id: pinHoleDiameterLabel
            text: "Pin hole diameter (mm)"
            color: UM.Theme.getColor("text")
            font: UM.Theme.getFont("default")
        }

        TextField {
            id: pinHoleDiameterField
            width: UM.Theme.getSize("setting_control").width
            height: UM.Theme.getSize("setting_control").height
            style: UM.Theme.styles.text_field
            text: base.pinHoleDiameter
            validator: DoubleValidator {
                bottom: 0
                decimals: 2
            }
            onEditingFinished: UM.ActiveTool.setProperty("PinHoleDiameter", text.replace(",", "."))
        }

        Label {
            id: pinHoleDepthLabel
            text: "Pin hole depth (mm)"
            color: UM.Theme.getColor("text")
            font: UM.Theme.getFont("default")
        }

        TextField {
            id: pinHoleDepthField
            width: UM.Theme.getSize("setting_control").width
            height: UM.Theme.getSize("setting_control").height
            style: UM.Theme.styles.text_field
            text: base.pinHoleDepth
            validator: DoubleValidator {
                bottom: 0
                decimals: 2
            }
            onEditingFinished: UM.ActiveTool.setProperty("PinHoleDepth", text.replace(",", "."))
        }
    }
}
