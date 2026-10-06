import QtQuick
import QtQuick.Controls
import QtWebEngine
import QtCore

Item {
    id: root
    property string initialUrl: ""
    property string address: view.url.toString()
    property string errorMessage: ""
    property bool editableCaptureLocked: false
    property string trustedProfile: ""
    property string trustedOrigin: ""
    property bool suppressExternalNavigationError: false
    property string externalActionMessage: ""
    property string lastWebUrl: ""
    // One consistent Mudos browser scale; WebEngine rerenders page layout,
    // unlike a QML view transform which would leave text physically small.
    property real pageZoom: 1.25
    LuluPalette { id: luluPalette }
    Typography { id: typography }
    signal closed()
    signal editableFocused(var field)
    signal editableTargetUnavailable()
    signal trustedLoginForm(var details)
    signal trustedCredentialsCaptured(var details)
    signal externalNavigationRequested(string targetUrl, string sourceOrigin, string disposition)

    function open(url) {
        errorMessage = ""
        externalActionMessage = ""
        view.url = url
        view.forceActiveFocus()
    }
    function currentOrigin() {
        try { return (new URL(view.url.toString())).origin }
        catch (error) { return "" }
    }
    function setExternalActionMessage(value) { externalActionMessage = value || "" }
    function dispatchExternalNavigation(target, disposition) {
        var scheme = target.split(":")[0].toLowerCase()
        if (scheme === "mudos" && target === "mudos://return") {
            root.closed()
            return true
        }
        if (scheme === "http" || scheme === "https" || scheme === "about")
            return false
        root.suppressExternalNavigationError = true
        root.externalActionMessage = "Preparing installation…"
        var origin = root.currentOrigin()
        if ((!origin || origin === "null") && root.lastWebUrl) {
            try { origin = (new URL(root.lastWebUrl)).origin }
            catch (error) { origin = "" }
        }
        root.externalNavigationRequested(target, origin, disposition)
        return true
    }
    function applyTrustedCredentials(username, password) {
        if (!trustedProfile || !trustedOrigin)
            return
        var script = "(function(username,password,origin){if(location.origin!==origin)return false;"
            + "var p=[...document.querySelectorAll('input[type=password]')].find(function(e){return e.offsetParent!==null;});"
            + "if(!p)return false;var f=p.form||document;"
            + "var u=[...f.querySelectorAll('input')].find(function(e){var t=(e.type||'text').toLowerCase();return e.offsetParent!==null&&['text','email','username'].indexOf(t)>=0;});"
            + "if(!u)return false;function set(e,v){var d=Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value');"
            + "if(d&&d.set)d.set.call(e,v);else e.value=v;"
            + "e.dispatchEvent(new InputEvent('input',{bubbles:true,composed:true,inputType:'insertText'}));"
            + "e.dispatchEvent(new Event('change',{bubbles:true,composed:true}));}"
            + "set(u,username);set(p,password);"
            + "window.__mudosAutofilled=true;return true;})(" + JSON.stringify(username) + ","
            + JSON.stringify(password) + "," + JSON.stringify(trustedOrigin) + ")"
        view.runJavaScript(script, function(result) {
            // React routes can render the form between the lookup and the
            // script execution. Permit the timer to retry in that case.
            if (!result)
                view.runJavaScript("window.__mudosAutofillRequested=false")
        })
    }
    function clearTrustedCredentialCandidate() {
        view.runJavaScript("window.__mudosCredentialCandidate=null;window.__mudosCredentialCaptureSent=false")
    }
    function goBackOrClose() {
        if (view.canGoBack) view.goBack()
        else closed()
    }
    function reloadPage() { view.reload() }
    function goForward() { if (view.canGoForward) view.goForward() }
    function releasePage() {
        view.stop()
        view.url = "about:blank"
    }
    function directional(key) {
        // WebEngine's spatial navigation remains enabled for real keyboard
        // events. The generic fallback only moves focus/scrolls and never
        // contains website-specific selectors.
        var script = "(function(){var e=document.activeElement;"
            + "if(" + JSON.stringify(key) + "==='down'||" + JSON.stringify(key) + "==='up')"
            + "window.scrollBy(0," + (key === "down" ? "420" : "-420") + ");"
            + "else if(e&&e.parentElement){var a=[...document.querySelectorAll('a,button,input,textarea,select,[tabindex]')];"
            + "var i=a.indexOf(e);if(i>=0)a[(i+" + (key === "right" ? "1" : "-1") + "+a.length)%a.length].focus();}"
            + "})()"
        view.runJavaScript(script)
    }
    function activate() {
        view.runJavaScript(
            "(function(){if(document.activeElement)document.activeElement.click();"
            + "var e=document.activeElement,t=(e&&e.tagName||'').toLowerCase(),type=(e&&e.type||'text').toLowerCase();"
            + "var editable=!!e&&(e.isContentEditable||t==='textarea'||(t==='input'&&['button','checkbox','file','hidden','image','radio','range','reset','submit'].indexOf(type)<0));"
            + "if(!editable)return null;window.__mudosExplicitEditableActivation=e;window.__mudosFocusedEditable=e;"
            + "return {secret:type==='password',type:e.isContentEditable?'contenteditable':(t==='textarea'? 'textarea':type),value:type==='password'?'':String(e.value===undefined?(e.textContent||''):e.value)};})()",
            function(field) {
                if (field) root.editableFocused(field)
                else root.editableTargetUnavailable()
            })
    }
    function requestTextEntryForFocusedElement() {
        view.runJavaScript(
            "(function(){var e=document.activeElement,t=(e&&e.tagName||'').toLowerCase(),type=(e&&e.type||'text').toLowerCase();"
            + "var editable=!!e&&(e.isContentEditable||t==='textarea'||(t==='input'&&['button','checkbox','file','hidden','image','radio','range','reset','submit'].indexOf(type)<0));"
            + "if(!editable)return null;window.__mudosFocusedEditable=e;"
            + "return {secret:type==='password',type:e.isContentEditable?'contenteditable':(t==='textarea'?'textarea':type),value:type==='password'?'':String(e.value===undefined?(e.textContent||''):e.value)};})()",
            function(field) {
                if (field) root.editableFocused(field)
                else root.editableTargetUnavailable()
            })
    }
    function commitText(value, submit, callback) {
        var script = "(function(value,submit){var e=window.__mudosFocusedEditable;"
            + "if(!e||!document.contains(e))return false;"
            + "if(e.isContentEditable){e.textContent=value;}"
            + "else{var p=e.tagName.toLowerCase()==='textarea'?HTMLTextAreaElement:HTMLInputElement;"
            + "var d=Object.getOwnPropertyDescriptor(p.prototype,'value');"
            + "if(d&&d.set)d.set.call(e,value);else e.value=value;}"
            + "e.dispatchEvent(new Event('input',{bubbles:true}));"
            + "e.dispatchEvent(new Event('change',{bubbles:true}));e.focus();"
            + "if(submit){['keydown','keypress','keyup'].forEach(function(k){e.dispatchEvent(new KeyboardEvent(k,{key:'Enter',code:'Enter',keyCode:13,which:13,bubbles:true}));});}"
            + "return true;})(" + JSON.stringify(value) + "," + (submit ? "true" : "false") + ")"
        view.runJavaScript(script, function(result) {
            root.editableCaptureLocked = false
            view.forceActiveFocus()
            if (callback) callback(result)
        })
    }
    function clearEditableState() {
        root.editableCaptureLocked = false
        view.runJavaScript("window.__mudosFocusedEditable=null;window.__mudosExplicitEditableActivation=null")
        view.forceActiveFocus()
    }
    function lockEditable() { editableCaptureLocked = true }

    Timer {
        id: editableFocusTimer
        interval: 150
        repeat: true
        running: root.visible
        onTriggered: view.runJavaScript(
            "(function(){function isEditable(e){var t=(e&&e.tagName||'').toLowerCase(),type=(e&&e.type||'text').toLowerCase();"
            + "return !!e&&(e.isContentEditable||t==='textarea'||(t==='input'&&['button','checkbox','file','hidden','image','radio','range','reset','submit'].indexOf(type)<0));}"
            + "function mark(ev){if(!ev.isTrusted)return;var e=ev.target;while(e&&!isEditable(e))e=e.parentElement;"
            + "if(isEditable(e))window.__mudosExplicitEditableActivation=e;}"
            + "if(!window.__mudosEditableActivationHooks){window.__mudosEditableActivationHooks=true;"
            + "document.addEventListener('pointerdown',mark,true);document.addEventListener('click',mark,true);"
            + "document.addEventListener('keydown',function(ev){if(ev.key==='Enter'||ev.key===' ')mark(ev);},true);}"
            + "var e=document.activeElement;var t=(e&&e.tagName||'').toLowerCase();"
            + "var type=(e&&e.type||'text').toLowerCase();"
            + "var editable=!!e&&(e.isContentEditable||t==='textarea'||(t==='input'&&['button','checkbox','file','hidden','image','radio','range','reset','submit'].indexOf(type)<0));"
            + "if(" + (root.editableCaptureLocked ? "true" : "false") + ")return null;"
            + "var changed=window.__mudosFocusedEditable!==e;"
            + "if(editable)window.__mudosFocusedEditable=e;else window.__mudosFocusedEditable=null;"
            + "if(!editable||!changed||window.__mudosExplicitEditableActivation!==e)return null;"
            + "window.__mudosExplicitEditableActivation=null;"
            + "return {secret:type==='password',type:e.isContentEditable?'contenteditable':(t==='textarea'?'textarea':type),value:type==='password'?'':String(e.value===undefined?(e.textContent||''):e.value)};})()",
            function(field) { if (field) root.editableFocused(field) })
    }

    Timer {
        id: trustedLoginTimer
        interval: 500
        repeat: true
        running: root.visible && root.trustedProfile !== ""
        onTriggered: view.runJavaScript(
            "(function(profile,origin){if(location.origin!==origin)return null;"
            + "function visible(e){return e&&e.offsetParent!==null;}"
            + "function remember(){var ps=[...document.querySelectorAll('input[type=password]')].filter(visible);"
            + "var pp=ps[0],ff=pp&&(pp.form||document);if(!pp||!ff)return;"
            + "var uu=[...ff.querySelectorAll('input')].find(function(e){var t=(e.type||'text').toLowerCase();"
            + "return visible(e)&&['text','email','username'].indexOf(t)>=0;});"
            + "if(uu&&uu.value&&pp.value)window.__mudosCredentialCandidate={username:String(uu.value),password:String(pp.value)};}"
            + "var passwords=[...document.querySelectorAll('input[type=password]')].filter(visible);"
            + "var p=passwords[0];"
            + "if(p){if(!window.__mudosLoginHooked){window.__mudosLoginHooked=true;"
            + "document.addEventListener('submit',function(){window.__mudosLoginSubmitted=true;remember();},true);"
            + "document.addEventListener('click',function(ev){var e=ev.target&&ev.target.closest&&ev.target.closest('button,input[type=submit]');"
            + "if(e){window.__mudosLoginSubmitted=true;remember();}},true);}"
            + "remember();"
            + "window.__mudosLoginSeen=true;var request=!window.__mudosAutofillRequested;window.__mudosAutofillRequested=true;"
            + "return {profile:profile,origin:origin,requestAutofill:request};}"
            + "if(window.__mudosLoginSeen&&window.__mudosLoginSubmitted&&window.__mudosCredentialCandidate&&!p&&!window.__mudosCredentialCaptureSent){"
            + "window.__mudosCredentialCaptureSent=true;return {profile:profile,origin:origin,candidate:window.__mudosCredentialCandidate};}return null;})("
            + JSON.stringify(root.trustedProfile) + "," + JSON.stringify(root.trustedOrigin) + ")",
            function(details) {
                if (!details) return
                if (details.requestAutofill) root.trustedLoginForm(details)
                if (details.candidate) root.trustedCredentialsCaptured(details)
            })
    }

    WebEngineProfile {
        id: profile
        storageName: "mudos-browser"
        persistentStoragePath: StandardPaths.writableLocation(StandardPaths.AppDataLocation) + "/browser/storage"
        persistentCookiesPolicy: WebEngineProfile.ForcePersistentCookies
    }

    Rectangle { anchors.fill: parent; color: luluPalette.backdrop }
    Rectangle {
        id: toolbar
        anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top
        height: 64
        color: luluPalette.glassTint
        Row {
            anchors.fill: parent; anchors.margins: 8; spacing: 8
            Button {
                text: "Back"
                font.family: typography.interfaceFamily
                palette.button: luluPalette.actionSurface
                palette.buttonText: luluPalette.actionText
                background: Rectangle {
                    radius: luluPalette.radius("row", 6)
                    color: parent.down ? luluPalette.selectionSurface : luluPalette.actionSurface
                    border.color: parent.activeFocus ? luluPalette.focusIndicator : luluPalette.glassBorder
                    MudosChromeFrame { anchors.fill: parent; luluPalette: root.luluPalette; cornerRadius: parent.radius; raised: !parent.down }
                }
                contentItem: Text { text: parent.text; color: parent.down ? luluPalette.selectedText : luluPalette.actionText; font: parent.font; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                onClicked: root.goBackOrClose()
            }
            Button {
                text: "Forward"
                font.family: typography.interfaceFamily
                palette.button: luluPalette.actionSurface
                palette.buttonText: luluPalette.actionText
                background: Rectangle {
                    radius: luluPalette.radius("row", 6)
                    color: parent.down ? luluPalette.selectionSurface : luluPalette.actionSurface
                    border.color: parent.activeFocus ? luluPalette.focusIndicator : luluPalette.glassBorder
                    MudosChromeFrame { anchors.fill: parent; luluPalette: root.luluPalette; cornerRadius: parent.radius; raised: !parent.down }
                }
                contentItem: Text { text: parent.text; color: parent.down ? luluPalette.selectedText : luluPalette.actionText; font: parent.font; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                onClicked: root.goForward()
            }
            Button {
                text: "Reload"
                font.family: typography.interfaceFamily
                palette.button: luluPalette.actionSurface
                palette.buttonText: luluPalette.actionText
                background: Rectangle {
                    radius: luluPalette.radius("row", 6)
                    color: parent.down ? luluPalette.selectionSurface : luluPalette.actionSurface
                    border.color: parent.activeFocus ? luluPalette.focusIndicator : luluPalette.glassBorder
                    MudosChromeFrame { anchors.fill: parent; luluPalette: root.luluPalette; cornerRadius: parent.radius; raised: !parent.down }
                }
                contentItem: Text { text: parent.text; color: parent.down ? luluPalette.selectedText : luluPalette.actionText; font: parent.font; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                onClicked: root.reloadPage()
            }
            TextInput {
                id: addressInput; width: parent.width - 310; height: 48
                text: root.address; color: luluPalette.primaryText; font.family: typography.interfaceFamily; font.pixelSize: 20
                onAccepted: { view.url = text; view.forceActiveFocus() }
            }
        }
        Rectangle {
            anchors.right: parent.right
            anchors.rightMargin: 12
            anchors.verticalCenter: parent.verticalCenter
            width: Math.min(parent.width * 0.32, 520)
            height: 44
            radius: luluPalette.radius("row", 6)
            color: luluPalette.cardSurface
            visible: root.externalActionMessage !== ""
            z: 3
            Text {
                anchors.fill: parent
                anchors.leftMargin: 12
                anchors.rightMargin: 12
                text: root.externalActionMessage
                color: luluPalette.primaryText
                font.family: typography.interfaceFamily
                font.pixelSize: 18
                verticalAlignment: Text.AlignVCenter
                horizontalAlignment: Text.AlignHCenter
                elide: Text.ElideRight
            }
        }
    }
    WebEngineView {
        id: view
        anchors.left: parent.left; anchors.right: parent.right
        anchors.top: toolbar.bottom; anchors.bottom: parent.bottom
        profile: profile
        zoomFactor: root.pageZoom
        settings.spatialNavigationEnabled: true
        focus: true
        onUrlChanged: {
            var changedUrl = url.toString()
            if (root.dispatchExternalNavigation(changedUrl, "url-changed")) {
                if (root.lastWebUrl)
                    view.url = root.lastWebUrl
                return
            }
            root.lastWebUrl = changedUrl
            root.address = changedUrl
            var sameTrustedOrigin = false
            if (root.trustedOrigin !== "") {
                try { sameTrustedOrigin = (new URL(url.toString())).origin === root.trustedOrigin }
                catch (error) { sameTrustedOrigin = false }
            }
            // Single-page apps change routes with browser history. Preserve the
            // submitted candidate across same-origin route changes so the
            // success transition can still save it; navigation away clears
            // it immediately.
            if (sameTrustedOrigin)
                view.runJavaScript("window.__mudosLoginHooked=false;window.__mudosLoginSeen=true;window.__mudosAutofillRequested=false;window.__mudosExplicitEditableActivation=null")
            else
                view.runJavaScript("window.__mudosLoginHooked=false;window.__mudosLoginSeen=false;window.__mudosLoginSubmitted=false;window.__mudosCredentialCandidate=null;window.__mudosCredentialCaptureSent=false;window.__mudosAutofillRequested=false;window.__mudosExplicitEditableActivation=null")
        }
        onLoadingChanged: function(loadRequest) {
            if (loadRequest.errorString)
                if (root.suppressExternalNavigationError) {
                    root.suppressExternalNavigationError = false
                    root.errorMessage = ""
                } else {
                    root.errorMessage = loadRequest.errorString
                }
            else {
                root.errorMessage = ""
                view.runJavaScript("window.__mudosEditableActivationHooks=false")
            }
        }
        onNewWindowRequested: function(request) {
            var target = request.requestedUrl.toString()
            var scheme = target.split(":")[0].toLowerCase()
            if (scheme === "http" || scheme === "https") {
                request.openIn(view)
            } else {
                root.dispatchExternalNavigation(target, "new-window")
                request.reject()
            }
        }
        onNavigationRequested: function(request) {
            var target = request.url.toString()
            var scheme = target.split(":")[0].toLowerCase()
            if (scheme === "http" || scheme === "https")
                return
            root.dispatchExternalNavigation(target, "navigation")
            request.action = WebEngineNavigationRequest.IgnoreRequest
        }
    }
    Rectangle {
        anchors.centerIn: view; visible: root.errorMessage !== ""
        color: luluPalette.warning; radius: luluPalette.radius("row", 4); width: Math.min(parent.width - 80, 900); height: 70
        Text { anchors.centerIn: parent; text: root.errorMessage; color: luluPalette.selectedText; font.family: typography.interfaceFamily; font.pixelSize: 18 }
    }
    Rectangle {
        anchors.horizontalCenter: view.horizontalCenter
        anchors.bottom: view.bottom
        anchors.bottomMargin: 36
        visible: root.externalActionMessage !== ""
        color: luluPalette.overlaySurface
        radius: luluPalette.radius("row", 8)
        width: Math.min(view.width - 80, 720)
        height: 58
        z: 4
        Text {
            anchors.centerIn: parent
            text: root.externalActionMessage
            color: luluPalette.primaryText
            font.family: typography.interfaceFamily
            font.pixelSize: 20
        }
    }
    Component.onCompleted: open(initialUrl)
}
