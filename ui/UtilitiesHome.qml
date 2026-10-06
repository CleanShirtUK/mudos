import QtQuick

Item {
    id: root

    property var applications: []
    property int selectedIndex: 0
    property int screenshotIndex: 0
    property real uiScale: 1
    property var typography
    property var luluPalette
    property var canonicalTexture
    property var canonicalCoordinateRoot
    property size canonicalSize: Qt.size(1280, 720)
    property real expandedContentX: 0
    property real expandedContentY: 0
    property real expandedContentWidth: width
    property real expandedContentHeight: height
    property real innerInset: 20 * uiScale
    property real titleX: 0
    property real titleY: 0
    readonly property rect internalFrameBounds: Qt.rect(innerInset, innerInset,
        Math.max(0, width - 2 * innerInset),
        Math.max(0, height - 2 * innerInset))
    property string statusMessage: ""

    readonly property var selectedApplication: selectedIndex >= 0
        && selectedIndex < applications.length ? applications[selectedIndex] : null
    readonly property var screenshots: selectedApplication
        && Array.isArray(selectedApplication.screenshots) ? selectedApplication.screenshots : []
    readonly property var selectedScreenshot: screenshots.length
        ? screenshots[screenshotIndex % screenshots.length] : null
    readonly property real gap: 18 * uiScale
    readonly property real listWidth: Math.min(380 * uiScale,
        Math.max(220 * uiScale, (width - 3 * gap) * 0.34))
    readonly property var controllerHints: {
        var hints = [{action: "navigation", label: "Applications"}]
        if (screenshots.length > 1) {
            hints.push({action: "previousCollection", label: "Screenshot"})
            hints.push({action: "nextCollection", label: "Screenshot"})
        }
        hints.push({action: "confirm", label: "Launch"})
        hints.push({action: "back", label: "Back"})
        return hints
    }

    signal launchRequested(string applicationRef)

    function move(delta) {
        if (!applications.length)
            return
        selectedIndex = Math.max(0, Math.min(applications.length - 1, selectedIndex + delta))
        screenshotIndex = 0
        appList.positionViewAtIndex(selectedIndex, ListView.Contain)
    }

    function moveScreenshot(delta) {
        if (screenshots.length < 2)
            return
        screenshotIndex = (screenshotIndex + delta + screenshots.length) % screenshots.length
    }

    function activateSelected() {
        if (selectedApplication && selectedApplication.ref)
            launchRequested(String(selectedApplication.ref))
    }

    onApplicationsChanged: {
        selectedIndex = Math.max(0, Math.min(selectedIndex, applications.length - 1))
        screenshotIndex = 0
    }
    onSelectedIndexChanged: screenshotIndex = 0

    MudosPanelSurface {
        objectName: "utilitiesGlassSubstrate"
        anchors.fill: parent
        cornerRadius: 18 * root.uiScale
        uiScale: root.uiScale
        luluPalette: root.luluPalette
        canonicalTexture: root.canonicalTexture
        canonicalCoordinateRoot: root.canonicalCoordinateRoot
        canonicalSize: root.canonicalSize
        mappingItem: root
    }

    Rectangle {
        id: listPane
        objectName: "utilitiesInternalFrame"
        x: root.innerInset
        y: root.innerInset
        width: root.listWidth
        height: Math.max(0, root.height - y - root.innerInset)
        radius: 12 * root.uiScale
        color: root.luluPalette.librarySurface
        border.color: root.luluPalette.glassBorder
        border.width: root.uiScale

        ListView {
            id: appList
            objectName: "utilitiesApplicationRows"
            anchors.fill: parent
            anchors.margins: 8 * root.uiScale
            clip: true
            model: root.applications
            spacing: 5 * root.uiScale
            delegate: Rectangle {
                required property int index
                required property var modelData
                width: appList.width
                height: 72 * root.uiScale
                radius: 9 * root.uiScale
                color: index === root.selectedIndex
                    ? root.luluPalette.selectionSurface : "transparent"
                border.color: index === root.selectedIndex
                    ? root.luluPalette.focusIndicator : root.luluPalette.glassBorder
                border.width: index === root.selectedIndex ? 2 * root.uiScale : root.uiScale

                Image {
                    id: appIcon
                    anchors.left: parent.left
                    anchors.leftMargin: 10 * root.uiScale
                    anchors.verticalCenter: parent.verticalCenter
                    width: 48 * root.uiScale
                    height: width
                    source: String(modelData.icon || "")
                    fillMode: Image.PreserveAspectFit
                    asynchronous: true
                }
                Text {
                    anchors.left: appIcon.right
                    anchors.leftMargin: 12 * root.uiScale
                    anchors.right: parent.right
                    anchors.rightMargin: 10 * root.uiScale
                    anchors.verticalCenter: parent.verticalCenter
                    text: String(modelData.name || modelData.application_id || "Application")
                    color: index === root.selectedIndex
                        ? root.luluPalette.selectedText : root.luluPalette.primaryText
                    font.family: root.typography.interfaceFamily
                    font.pixelSize: root.typography.size("body", 15)
                    elide: Text.ElideRight
                }
                MouseArea {
                    anchors.fill: parent
                    onClicked: root.selectedIndex = index
                }
            }
        }
    }

    Rectangle {
        id: detailPane
        x: listPane.x + listPane.width + root.gap
        y: listPane.y
        width: Math.max(0, root.width - x - 20 * root.uiScale)
        height: listPane.height
        radius: 12 * root.uiScale
        color: root.luluPalette.librarySurface
        border.color: root.luluPalette.glassBorder
        border.width: root.uiScale
        visible: !!root.selectedApplication

        readonly property real mediaAspectRatio: {
            var image = root.selectedScreenshot
            var imageWidth = image && Number(image.width) > 0 ? Number(image.width) : 16
            var imageHeight = image && Number(image.height) > 0 ? Number(image.height) : 9
            return imageWidth / imageHeight
        }
        readonly property real mediaHeight: Math.min(height * 0.43, 300 * root.uiScale)

        Image {
            id: screenshot
            objectName: "utilitiesScreenshot"
            anchors.top: parent.top
            anchors.topMargin: 12 * root.uiScale
            anchors.horizontalCenter: parent.horizontalCenter
            width: Math.min(parent.width - 28 * root.uiScale,
                            parent.mediaHeight * parent.mediaAspectRatio)
            height: Math.min(parent.mediaHeight, width / parent.mediaAspectRatio)
            source: root.selectedScreenshot ? String(root.selectedScreenshot.url || "")
                : String(root.selectedApplication ? root.selectedApplication.icon || "" : "")
            fillMode: Image.PreserveAspectFit
            asynchronous: true
            cache: true
        }

        Text {
            id: appTitle
            anchors.top: screenshot.bottom
            anchors.topMargin: 12 * root.uiScale
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.leftMargin: 18 * root.uiScale
            anchors.rightMargin: 18 * root.uiScale
            text: root.selectedApplication ? String(root.selectedApplication.name || "") : ""
            color: root.luluPalette.primaryText
            font.family: root.typography.displayFamily
            font.weight: root.typography.displayWeight
            font.pixelSize: root.typography.size("heading", 24)
            elide: Text.ElideRight
        }

        Text {
            id: summary
            anchors.top: appTitle.bottom
            anchors.topMargin: 7 * root.uiScale
            anchors.left: appTitle.left
            anchors.right: appTitle.right
            text: root.selectedApplication
                ? String(root.selectedApplication.summary || "Application details are not available.") : ""
            color: root.luluPalette.secondaryText
            font.family: root.typography.interfaceFamily
            font.pixelSize: root.typography.size("body", 14)
            wrapMode: Text.WordWrap
            maximumLineCount: 2
            elide: Text.ElideRight
        }

        Text {
            id: description
            anchors.top: summary.bottom
            anchors.topMargin: 8 * root.uiScale
            anchors.left: appTitle.left
            anchors.right: appTitle.right
            height: Math.max(0, detailPane.height - y - 46 * root.uiScale)
            text: root.selectedApplication
                ? String(root.selectedApplication.description || "") : ""
            color: root.luluPalette.secondaryText
            font.family: root.typography.interfaceFamily
            font.pixelSize: root.typography.size("body", 12)
            wrapMode: Text.WordWrap
            maximumLineCount: 6
            elide: Text.ElideRight
            clip: true
        }

        Text {
            anchors.left: appTitle.left
            anchors.right: appTitle.right
            anchors.bottom: parent.bottom
            anchors.bottomMargin: 12 * root.uiScale
            text: root.selectedApplication
                ? [root.selectedApplication.developer || root.selectedApplication.publisher,
                   root.selectedApplication.version ? "Version " + root.selectedApplication.version : "",
                   root.selectedApplication.categories ? root.selectedApplication.categories.join(" · ") : ""]
                    .filter(function(value) { return !!value }).join("  ·  ") : ""
            color: root.luluPalette.mutedText
            font.family: root.typography.interfaceFamily
            font.pixelSize: root.typography.size("hint", 11)
            elide: Text.ElideRight
        }
    }

    MudosEmptyState {
        anchors.centerIn: parent
        visible: !root.selectedApplication
        iconName: "applications"
        title: "No managed utilities"
        detail: root.statusMessage || "No managed Flatpak utilities are installed."
        uiScale: root.uiScale
        typography: root.typography
        luluPalette: root.luluPalette
        maximumTextWidth: root.width * 0.62
    }
}
