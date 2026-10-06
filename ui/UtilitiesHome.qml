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
    property real expandedShellX: 0
    property real expandedShellY: 0
    property real expandedShellWidth: width
    property real expandedShellHeight: height
    property string statusMessage: ""

    readonly property var selectedApplication: selectedIndex >= 0
        && selectedIndex < applications.length ? applications[selectedIndex] : null
    readonly property var screenshots: selectedApplication
        && Array.isArray(selectedApplication.screenshots) ? selectedApplication.screenshots : []
    readonly property var selectedScreenshot: screenshots.length
        ? screenshots[screenshotIndex % screenshots.length] : null
    readonly property real inset: 34 * uiScale
    readonly property real gap: 22 * uiScale
    readonly property real listWidth: Math.max(270 * uiScale, (width - 2 * inset - gap) * 0.34)

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

    MudosCardSurface {
        objectName: "utilitiesGlassBacking"
        anchors.fill: parent
        anchors.margins: root.inset
        radius: 20 * root.uiScale
        uiScale: root.uiScale
        luluPalette: root.luluPalette
        canonicalTexture: root.canonicalTexture
        canonicalCoordinateRoot: root.canonicalCoordinateRoot
        canonicalSize: root.canonicalSize
        mappingItem: root
    }

    Rectangle {
        anchors.fill: parent
        anchors.margins: root.inset
        radius: 20 * root.uiScale
        color: "transparent"
        border.color: root.luluPalette.libraryBorder
        border.width: Math.max(1, root.uiScale)

        Text {
            id: heading
            x: 26 * root.uiScale
            y: 18 * root.uiScale
            text: "UTILITIES"
            color: root.luluPalette.headingAccent
            font.family: root.typography.displayFamily
            font.weight: root.typography.displayWeight
            font.pixelSize: 28 * root.uiScale
        }

        Item {
            anchors.left: parent.left
            anchors.leftMargin: 22 * root.uiScale
            anchors.top: heading.bottom
            anchors.topMargin: 16 * root.uiScale
            anchors.bottom: parent.bottom
            anchors.bottomMargin: 24 * root.uiScale
            width: root.listWidth

            Rectangle {
                anchors.fill: parent
                radius: 14 * root.uiScale
                color: Qt.rgba(root.luluPalette.librarySurface.r,
                               root.luluPalette.librarySurface.g,
                               root.luluPalette.librarySurface.b, 0.56)
                border.color: root.luluPalette.libraryBorder
            }

            ListView {
                id: appList
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
                    radius: 10 * root.uiScale
                    color: index === root.selectedIndex
                        ? Qt.rgba(root.luluPalette.focusIndicator.r,
                                  root.luluPalette.focusIndicator.g,
                                  root.luluPalette.focusIndicator.b, 0.20)
                        : Qt.rgba(root.luluPalette.primaryText.r,
                                  root.luluPalette.primaryText.g,
                                  root.luluPalette.primaryText.b, 0.035)
                    border.color: index === root.selectedIndex
                        ? root.luluPalette.focusIndicator : root.luluPalette.libraryBorder
                    border.width: index === root.selectedIndex ? 2 * root.uiScale : 1

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
                        font.pixelSize: 15 * root.uiScale
                        elide: Text.ElideRight
                    }
                    MouseArea {
                        anchors.fill: parent
                        onClicked: root.selectedIndex = index
                    }
                }
            }
        }

        Item {
            id: detail
            anchors.left: parent.left
            anchors.leftMargin: 22 * root.uiScale + root.listWidth + root.gap
            anchors.right: parent.right
            anchors.rightMargin: 22 * root.uiScale
            anchors.top: heading.bottom
            anchors.topMargin: 16 * root.uiScale
            anchors.bottom: parent.bottom
            anchors.bottomMargin: 22 * root.uiScale
            visible: !!root.selectedApplication

            Rectangle {
                anchors.fill: parent
                radius: 14 * root.uiScale
                color: Qt.rgba(root.luluPalette.librarySurface.r,
                               root.luluPalette.librarySurface.g,
                               root.luluPalette.librarySurface.b, 0.56)
                border.color: root.luluPalette.libraryBorder
            }

            Image {
                id: screenshot
                anchors.top: parent.top
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.margins: 14 * root.uiScale
                height: Math.min(parent.height * 0.53, width * 0.52)
                source: root.selectedScreenshot ? String(root.selectedScreenshot.url || "")
                    : String(root.selectedApplication ? root.selectedApplication.icon || "" : "")
                fillMode: Image.PreserveAspectFit
                asynchronous: true
                cache: true
            }

            Text {
                anchors.top: screenshot.bottom
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.margins: 18 * root.uiScale
                text: root.selectedApplication ? String(root.selectedApplication.name || "") : ""
                color: root.luluPalette.primaryText
                font.family: root.typography.displayFamily
                font.weight: root.typography.displayWeight
                font.pixelSize: 24 * root.uiScale
                elide: Text.ElideRight
            }

            Text {
                id: summary
                anchors.top: screenshot.bottom
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.margins: 18 * root.uiScale
                anchors.topMargin: 52 * root.uiScale
                text: root.selectedApplication
                    ? String(root.selectedApplication.summary || "Application details are not available.") : ""
                color: root.luluPalette.secondaryText
                font.family: root.typography.interfaceFamily
                font.pixelSize: 14 * root.uiScale
                wrapMode: Text.WordWrap
                maximumLineCount: 2
                elide: Text.ElideRight
            }

            Text {
                id: description
                anchors.top: summary.bottom
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.margins: 18 * root.uiScale
                anchors.topMargin: 8 * root.uiScale
                height: Math.max(0, parent.height - y - 90 * root.uiScale)
                text: root.selectedApplication
                    ? String(root.selectedApplication.description || "") : ""
                color: root.luluPalette.secondaryText
                font.family: root.typography.interfaceFamily
                font.pixelSize: 12 * root.uiScale
                wrapMode: Text.WordWrap
                maximumLineCount: 5
                elide: Text.ElideRight
                clip: true
            }

            Text {
                anchors.left: parent.left
                anchors.leftMargin: 18 * root.uiScale
                anchors.bottom: parent.bottom
                anchors.bottomMargin: 46 * root.uiScale
                text: root.selectedApplication
                    ? [root.selectedApplication.developer || root.selectedApplication.publisher,
                       root.selectedApplication.version ? "Version " + root.selectedApplication.version : "",
                       root.selectedApplication.categories ? root.selectedApplication.categories.join(" · ") : ""]
                        .filter(function(value) { return !!value }).join("  ·  ") : ""
                color: root.luluPalette.mutedText
                font.family: root.typography.interfaceFamily
                font.pixelSize: 11 * root.uiScale
                elide: Text.ElideRight
                width: parent.width - 36 * root.uiScale
            }

            Text {
                anchors.right: parent.right
                anchors.rightMargin: 18 * root.uiScale
                anchors.bottom: parent.bottom
                anchors.bottomMargin: 16 * root.uiScale
                text: root.screenshots.length > 1
                    ? "◀  Screenshot " + (root.screenshotIndex + 1) + " / " + root.screenshots.length + "  ▶     A  Launch"
                    : "A  Launch"
                color: root.luluPalette.headingAccent
                font.family: root.typography.interfaceFamily
                font.pixelSize: 13 * root.uiScale
            }
        }

        Text {
            anchors.centerIn: parent
            visible: !root.selectedApplication
            text: root.statusMessage || "No managed Flatpak utilities are installed."
            color: root.luluPalette.secondaryText
            font.family: root.typography.interfaceFamily
            font.pixelSize: 16 * root.uiScale
            wrapMode: Text.WordWrap
            width: parent.width * 0.72
            horizontalAlignment: Text.AlignHCenter
        }
    }
}
